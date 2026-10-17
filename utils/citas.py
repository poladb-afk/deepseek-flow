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
    r"(?P<path>[A-Za-z0-9_./~-]+\.(?:py|md|toml|txt|json|yaml|yml))(?::(?P<line>\d+))"
)
MAX_DETALLE = 160


def extraer(texto):
    """[(path, linea)] únicos y en orden de aparición."""
    vistos = set()
    out = []
    for m in CITAS_RE.finditer(texto or ""):
        path = m.group("path").strip("'\"()[]<>.,;").replace(chr(96), "")
        try:
            linea = int(m.group("line"))
        except ValueError:
            continue
        clave = (path, linea)
        if clave in vistos:
            continue
        vistos.add(clave)
        out.append(clave)
    return out


_EXCLUIR = {".git", ".venv", "__pycache__", "salidas", ".runs", "mutants",
            "node_modules", ".modelos", ".pytest_cache", ".ruff_cache"}


def _por_nombre_suelto(nombre):
    """Nombre sin ruta (policy.py:88): si es ÚNICO en el árbol fuente del cwd,
    es esa cita. Excluye artefactos (salidas/, mutants/, venvs): evita falsos
    no_existe cuando el modelo abrevia tras citar la ruta completa (9/14 en
    una sesión real)."""
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


def verificar_citas(texto):
    """Verifica cada cita contra el disco. Nunca lanza: un fallo de lectura
    queda como estado, no corta la respuesta."""
    citas = []
    for path, linea in extraer(texto):
        resolved, err = _resolve(path)
        if (err or resolved is None or not resolved.is_file()) and "/" not in path:
            alterno = _por_nombre_suelto(path)
            if alterno is not None:
                resolved, err = alterno, None
        if err or resolved is None:
            citas.append({"path": path, "linea": linea, "estado": "fuera",
                          "detalle": (err or "fuera de raíces")[:MAX_DETALLE]})
            continue
        if not resolved.is_file():
            citas.append({"path": path, "linea": linea, "estado": "no_existe",
                          "detalle": "el archivo no existe"})
            continue
        try:
            lineas = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            citas.append({"path": path, "linea": linea, "estado": "error_lectura",
                          "detalle": type(exc).__name__})
            continue
        if linea < 1 or linea > len(lineas):
            citas.append({"path": path, "linea": linea, "estado": "linea_fuera",
                          "detalle": f"el archivo tiene {len(lineas)} líneas"})
            continue
        citas.append({"path": path, "linea": linea, "estado": "ok",
                      "detalle": lineas[linea - 1].strip()[:MAX_DETALLE] or "(línea vacía)"})
    mal = [c for c in citas if c["estado"] != "ok"]
    return {"citas": citas, "total": len(citas), "ok": len(citas) - len(mal), "mal": mal}


def reporte(resultado, solo_mal=True):
    """Texto legible para el usuario y para el prompt de corrección."""
    seleccion = resultado["mal"] if solo_mal else resultado["citas"]
    if not seleccion:
        return ""
    lineas = [f"[citas] {resultado['ok']}/{resultado['total']} verificadas contra el disco:"]
    for c in seleccion:
        lineas.append(f"- {c['path']}:{c['linea']} -> {c['estado']} ({c['detalle']})")
    return "\n".join(lineas)
