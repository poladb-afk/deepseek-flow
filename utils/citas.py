"""Verificación determinista de citas archivo:línea en una respuesta.

No valida la AFIRMACIÓN (eso requiere leer y razonar): valida que la línea
citada exista en el archivo real y devuelve su contenido. Con eso:
- la respuesta puede mostrar evidencia verificable;
- si hay citas que no coinciden, el chat pide una segunda pasada de corrección.

Medido en sesiones reales: las citas de línea eran el punto más frágil
(0/3 y 3/11 hallazgos confirmados, líneas corridas)."""
import re
from pathlib import Path

from utils.fs_tools import _resolve

CITAS_RE = re.compile(
    r"(?P<path>[A-Za-z0-9_./~-]+\.(?:py|md|toml|txt|jsonl|json|csv|log|yaml|yml))"
    r"(?::(?P<line>\d+)(?:-(?P<line2>\d+))?)?"
)
MAX_DETALLE = 160
# Nombres de ejemplo en prosa (archivo.py:10-20): no son citas reales.
_PLACEHOLDERS = {"archivo.py", "archivo.md", "file.py", "ruta.py",
                 "ejemplo.py", "path.py", "foo.py", "bar.py"}


def extraer(texto):
    """[(path, linea, linea2|None)] únicos y en orden de aparición.

    Solo cuenta una cita si hay `:línea` (o rango): mencionar un archivo sin
    línea NO es una cita verificable (S11: los nombres de archivo sueltos se
    contaban como `:0` y generaban falsos linea_fuera). Los rangos N-M se
    conservan (A52)."""
    vistos = set()
    out = []
    for m in CITAS_RE.finditer(texto or ""):
        path = m.group("path").strip("'\"()[]<>.,;").replace(chr(96), "")
        if Path(path).name in _PLACEHOLDERS or not m.group("line"):
            continue
        try:
            linea = int(m.group("line"))
        except ValueError:
            continue
        linea2 = int(m.group("line2")) if m.group("line2") else None
        clave = (path, linea, linea2)
        if clave in vistos:
            continue
        vistos.add(clave)
        out.append(clave)
    return out


def _por_nombre_suelto(nombre):
    """Nombre sin ruta (p. ej. una cita abreviada sin directorio): si es
    ÚNICO en el árbol fuente del cwd, es esa cita. Excluye artefactos
    (salidas/, mutants/, venvs): evita falsos no_existe cuando el modelo
    abrevia tras citar la ruta completa (9/14 en una sesión real)."""
    if "/" in nombre or "\\" in nombre:
        return None
    candidatos = []
    try:
        for p in Path.cwd().rglob(nombre):
            if not p.is_file() or any(parte in _EXCLUIR for parte in p.parts):
                continue
            candidatos.append(p)
            if len(candidatos) > 1:
                return None
    except OSError:
        return None
    return candidatos[0] if len(candidatos) == 1 else None


_EXCLUIR = {".git", ".venv", "__pycache__", "salidas", ".runs", "mutants",
            "node_modules", ".modelos", ".pytest_cache", ".ruff_cache"}


def verificar_citas(texto):
    """Verifica cada cita contra el disco. Nunca lanza: un fallo de lectura
    queda como estado, no corta la respuesta. Un rango N-M se valida en sus
    dos extremos (A52)."""
    citas = []
    for path, linea, linea2 in extraer(texto):
        resolved, err = _resolve(path)
        por_nombre = False
        if (err or resolved is None or not resolved.is_file()) and "/" not in path:
            alterno = _por_nombre_suelto(path)
            if alterno is not None:
                resolved, err = alterno, None
                por_nombre = True
        if err or resolved is None:
            citas.append({"path": path, "linea": linea, "linea2": linea2,
                          "estado": "fuera",
                          "detalle": (err or "fuera de raíces")[:MAX_DETALLE]})
            continue
        if not resolved.is_file():
            citas.append({"path": path, "linea": linea, "linea2": linea2,
                          "estado": "no_existe", "detalle": "el archivo no existe"})
            continue
        try:
            lineas = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            citas.append({"path": path, "linea": linea, "linea2": linea2,
                          "estado": "error_lectura", "detalle": type(exc).__name__})
            continue
        fin = linea2 if linea2 is not None else linea
        if linea < 1 or fin > len(lineas) or fin < linea:
            citas.append({"path": path, "linea": linea, "linea2": linea2,
                          "estado": "linea_fuera",
                          "detalle": f"rango {linea}-{fin}; el archivo tiene {len(lineas)} líneas"})
            continue
        texto_linea = lineas[linea - 1].strip()
        if linea2 is not None:
            texto_linea += " … " + lineas[linea2 - 1].strip()
        citas.append({"path": path, "linea": linea, "linea2": linea2, "estado": "ok",
                      "resuelto_por_nombre": por_nombre,
                      "detalle": texto_linea[:MAX_DETALLE] or "(línea vacía)"})
    mal = [c for c in citas if c["estado"] != "ok"]
    for c in citas:
        if c["estado"] == "ok" and c.get("resuelto_por_nombre"):
            c["detalle"] = "resuelta por nombre único: " + c["detalle"]
    return {"citas": citas, "total": len(citas), "ok": len(citas) - len(mal), "mal": mal}


def _etiqueta(c):
    return f"{c['path']}:{c['linea']}" + (f"-{c['linea2']}" if c.get("linea2") else "")


def reporte(resultado, solo_mal=True):
    """Texto legible para el usuario y para el prompt de corrección."""
    seleccion = resultado["mal"] if solo_mal else resultado["citas"]
    if not seleccion:
        return ""
    lineas = [f"[citas] {resultado['ok']}/{resultado['total']} verificadas contra el disco:"]
    for c in seleccion:
        lineas.append(f"- {_etiqueta(c)} -> {c['estado']} ({c['detalle']})")
    return "\n".join(lineas)
