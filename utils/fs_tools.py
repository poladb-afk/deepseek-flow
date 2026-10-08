"""Herramientas del agente: listar y leer archivos en directorios permitidos.

El modelo construye las rutas; _resolve() garantiza que ninguna salga de
los directorios permitidos (AGENT_ALLOWED_DIRS, separados por ':').
Los errores de uso (ruta fuera de rango, archivo inexistente, argumentos
mal formados) se devuelven como texto "ERROR: ..." para que el modelo
corrija en la siguiente vuelta; no son fallos transitorios del API.
"""
import contextlib
import fnmatch
import json
import os
import subprocess
from pathlib import Path

from utils.call_llm import _setting
from utils.terminal import colorear

DEFAULT_ALLOWED_DIRS = "."  # portable: CWD; en producción, AGENT_ALLOWED_DIRS en .env
MAX_TOOL_ROUNDS = int(_setting("MAX_TOOL_ROUNDS", "8"))
READ_MAX_CHARS = int(_setting("READ_MAX_CHARS", "24000"))
LIST_MAX_ENTRIES = 300
SEARCH_MAX_FILES = 50
SEARCH_MAX_MATCHES = 200
SEARCH_HITS_PER_FILE = 5
CONTENT_MAX_BYTES = 4 * 1024 * 1024
# Directorios que el listado salta: miles de entradas irrelevantes para el agente.
SKIP_DIRS = {".git", "__pycache__", "node_modules"} | {".venv", ".venv-train"}


def sin_enlaces(entradas):
    """Política ÚNICA de recorrido: el agente no sigue enlaces simbólicos.

    Comprobar la carpeta inicial NO comprueba cada archivo — medido
    (2026-10-08): read_file rechazaba un enlace externo y search_files
    devolvía su contenido. Todo recorrido (list/search, informes, índice)
    pasa sus candidatos por acá. Si algún día se quieren permitir enlaces,
    hay que resolver el destino REAL de cada candidato contra las raíces;
    validar solo la raíz no alcanza."""
    return [p for p in entradas if not p.is_symlink()]

# Hooks post-tool (mesa 2): {nombre_tool: [fn]}. Cada fn(tool_call_dict,
# resultado_str) -> str puede ENRIQUECER el resultado antes de que viaje al
# modelo. Contrato de hierro: un hook NUNCA rompe la ejecución — si lanza,
# el resultado queda intacto. El patrón que habilita es 'error como
# feedback': un chequeo barato tras la escritura (p. ej. py_compile)
# devuelve el problema al modelo para que se autocorrija.
HOOKS_POST = {}

# Hooks pre-tool (mesa 2): {nombre_tool: [fn]}. Cada fn(tool_call_dict) se
# corre ANTES de ejecutar la implementación. Sirve para DENYLIST y guardas
# que deben decidir antes de que el efecto ocurra (un hook post ya llegaría
# tarde para un comando que ya corrió). Contrato de hierro, igual que los
# post: un hook NUNCA rompe la ejecución — si lanza, se ignora.
HOOKS_PRE = {}


def _hook_py_compile(tool_call, resultado):
    """Tras edit_file/write_file sobre un .py, corre `python3 -m py_compile`
    del archivo. Si falla, agrega '⚠ SINTAXIS: <error>' al resultado para
    que el MODELO lo vea y corrija (habría pescado el clobber de
    fs_tools.py al instante). Jamás rompe: si py_compile no existe,
    el archivo no es .py o cualquier cosa falla raro, devuelve intacto."""
    try:
        args = json.loads(tool_call["function"].get("arguments") or "{}")
        path = args.get("path")
        if not path or not str(path).endswith(".py"):
            return resultado
        resolved, err = _resolve(path)
        if err or not resolved.is_file():
            return resultado
        proc = subprocess.run(
            ["python3", "-m", "py_compile", str(resolved)],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0:
            detalle = (proc.stderr or proc.stdout or "").strip()
            print(colorear(f"  [hook] ⚠ SINTAXIS devuelta al modelo: "
                           f"{detalle.splitlines()[-1] if detalle else path}", "aviso"), flush=True)
            return resultado + f"\n⚠ SINTAXIS: {detalle}"
        return resultado
    except Exception:  # noqa: BLE001  (un hook nunca rompe la ejecución)
        return resultado


# Registro: validation barata tras cada escritura de .py.
HOOKS_POST["edit_file"] = [_hook_py_compile]
HOOKS_POST["write_file"] = [_hook_py_compile]


def allowed_roots():
    text = _setting("AGENT_ALLOWED_DIRS", DEFAULT_ALLOWED_DIRS)
    return [Path(p).expanduser().resolve() for p in text.split(":") if p.strip()]


def _resolve(raw):
    roots = allowed_roots()
    expanded = Path(raw).expanduser()
    if expanded.is_absolute():
        candidates = [expanded]
    else:
        # un relativo también puede serlo al CWD del proceso (medido: el
        # modelo arma rutas como las ve en el listado, ancladas al CWD que
        # declara el system prompt, no a las raíces permitidas)
        candidates = [Path.cwd() / expanded] + [root / expanded for root in roots]
    permitido = None  # bajo el techo pero inexistente: write_file podría crearlo
    for cand in candidates:
        resolved = Path.resolve(cand)
        for root in roots:
            if resolved == root or root in resolved.parents:
                if resolved.exists():
                    return resolved, None
                if permitido is None:
                    permitido = resolved
    if permitido is not None:
        return permitido, None
    return None, "ruta fuera de los directorios permitidos: " + ", ".join(str(r) for r in roots)


def escribir_salida(ruta, texto):
    """El ÚNICO camino de escritura de un flujo (C01 de la auditoría externa).

    Los flujos escribían con Path.write_text() una ruta de SALIDA elegida por
    el modelo, sin pasar por _resolve: medido, con las raíces acotadas
    write_file rechazaba la ruta externa y los flujos la escribían igual.
    Misma forma que _resolve —(ruta, None) o (None, error)— para que cada
    llamador decida: la tool del chat devuelve ERROR y el CLI corta. El HITL
    de write_file sigue siendo el de modules/escritura: acá NO se agrega
    fricción (los flujos también corren desde la CLI y desde el banco)."""
    destino, err = _resolve(ruta)
    if err:
        return None, err
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    except OSError as e:
        return None, f"no se pudo escribir {destino}: {e.strerror or e}"
    return destino, None


def list_files(path=None, depth=2):
    if path is None:
        roots = allowed_roots()
        return "Directorios permitidos:\n" + "\n".join(
            f"- {r}{' (no existe)' if not r.is_dir() else ''}" for r in roots
        )
    target, err = _resolve(path)
    if err:
        return f"ERROR: {err}"
    if not target.exists():
        return f"ERROR: no existe: {target}"
    if not target.is_dir():
        return f"ERROR: no es un directorio: {target}"

    depth = min(3, max(1, int(depth)))
    lines, count = [], 0

    def walk(d, level):
        nonlocal count
        try:
            entries = sorted(sin_enlaces(d.iterdir()), key=lambda e: (e.is_file(), e.name.lower()))
        except OSError as e:
            lines.append(f"{e.filename} [ERROR: {e.strerror}]")
            return
        for e in entries:
            if count >= LIST_MAX_ENTRIES:
                lines.append(f"... [truncado: más de {LIST_MAX_ENTRIES} entradas]")
                return
            if e.name in SKIP_DIRS:
                continue
            count += 1
            if e.is_dir():
                lines.append(f"{e}/")
                if level < depth:
                    walk(e, level + 1)
            else:
                try:
                    size = e.stat().st_size
                except OSError:
                    size = 0
                lines.append(f"{e} ({size} B)")

    walk(target, 1)
    return "\n".join(lines)


def read_file(path, offset=1, limit=400):
    resolved, err = _resolve(path)
    if err:
        return f"ERROR: {err}"
    if not resolved.exists():
        return f"ERROR: no existe: {resolved}"
    if not resolved.is_file():
        return f"ERROR: no es un archivo regular: {resolved}"

    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"ERROR: {e.strerror}"
    if "\x00" in text[:4000]:
        return "ERROR: archivo binario"

    offset = max(1, int(offset))
    limit = min(500, max(1, int(limit)))
    lines = text.splitlines()
    selected = lines[offset - 1 : offset - 1 + limit]
    last = min(offset + limit - 1, len(lines))
    out = f"[{resolved} — líneas {offset}–{last} de {len(lines)}]\n" + "\n".join(selected)
    if len(out) > READ_MAX_CHARS:
        half = READ_MAX_CHARS // 2
        out = out[:half] + "\n[... cortado: usa offset/limit para ver el resto ...]\n" + out[-half:]
    return out


def _name_matches(rel_posix, name, pattern):
    p = pattern.lstrip("./")
    if p.startswith("**/"):
        p = p[3:]
    if "/" in p:
        return fnmatch.fnmatch(rel_posix, p) or fnmatch.fnmatch(rel_posix, "**/" + p)
    return fnmatch.fnmatch(name, p)


def search_files(query=None, glob=None, path=None):
    query = (query or "").strip() or None
    glob = (glob or "").strip() or None
    if not query and not glob:
        return "ERROR: indica qué buscar: query (texto del contenido) y/o glob (patrón de nombre como '*.jsonl')"
    roots = allowed_roots()
    if path:
        target, err = _resolve(path)
        if err:
            return f"ERROR: {err}"
        if not target.exists():
            return f"ERROR: no existe: {target}"
        roots = [target]
    pattern = glob or "*"

    file_hits, content_hits, skipped_big = [], [], 0
    file_total = 0  # conteo EXACTO antes de truncar a la muestra SEARCH_MAX_FILES
    for root in roots:
        if root.is_file():
            # os.walk sobre un ARCHIVO no visita nada: falso negativo
            # silencioso (medido: "Ningún archivo contiene..." sobre un
            # archivo que sí lo contiene). Lo tratamos como único
            # habitante de su directorio padre.
            walks = [(str(root.parent), [], [root.name])]
        else:
            walks = os.walk(root)
        for dirpath, dirnames, filenames in walks:
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            # os.walk no baja por enlaces de directorio, pero SÍ entrega los
            # archivos enlazados: la política se aplica a cada candidato.
            for fpath in sin_enlaces(Path(dirpath) / f for f in filenames):
                rel_posix = fpath.relative_to(root).as_posix()
                if not _name_matches(rel_posix, fpath.name, pattern):
                    continue
                try:
                    size = fpath.stat().st_size
                except OSError:
                    continue
                if not query:
                    file_total += 1
                    if len(file_hits) < SEARCH_MAX_FILES:
                        file_hits.append((fpath, size))
                    continue
                if size > CONTENT_MAX_BYTES:
                    skipped_big += 1
                    continue
                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if "\x00" in text[:4000]:
                    continue
                hits = [
                    (n, line.strip()[:200])
                    for n, line in enumerate(text.splitlines(), 1)
                    if query.lower() in line.lower()
                ]
                if hits and len(content_hits) < SEARCH_MAX_FILES:
                    content_hits.append((fpath, hits))

    if not query:
        if not file_hits:
            return f"Ningún archivo coincide con '{pattern}'."
        shown = len(file_hits)
        out = [f"{file_total} archivos coinciden con '{pattern}':"]
        out += [f"- {p} ({s} B)" for p, s in sorted(file_hits)]
        if file_total > shown:
            scope = path or " ".join(str(r) for r in roots)
            out.append(
                f"... y {file_total - shown} archivos más "
                f"(mostrando {shown} de {file_total}; para el listado completo: "
                f"run_command 'find {scope} -name \"{pattern}\"' ya es solo-lectura auto)"
            )
        return "\n".join(out)

    if not content_hits:
        scope = f" coincidentes con '{pattern}'" if glob else ""
        return f"Ningún archivo{scope} contiene '{query}'."
    total_lines = sum(len(h) for _, h in content_hits)
    out = [f"'{query}' aparece en {len(content_hits)} archivos ({total_lines} líneas):"]
    shown = 0
    for fpath, hits in sorted(content_hits):
        out.append(f"- {fpath}")
        for n, line in hits[:SEARCH_HITS_PER_FILE]:
            if shown >= SEARCH_MAX_MATCHES:
                break
            out.append(f"    L{n}: {line}")
            shown += 1
        if len(hits) > SEARCH_HITS_PER_FILE:
            out.append(f"    ... y {len(hits) - SEARCH_HITS_PER_FILE} líneas más en este archivo")
    if skipped_big:
        out.append(f"[{skipped_big} archivos de más de {CONTENT_MAX_BYTES // (1024 * 1024)} MB omitidos]")
    if shown >= SEARCH_MAX_MATCHES or len(content_hits) == SEARCH_MAX_FILES:
        out.append("[resultado truncado: acota con path o glob]")
    return "\n".join(out)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Lista el contenido de un directorio con tamaños. Sin path, lista los directorios permitidos. Devuelve rutas absolutas que puedes pasar a read_file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta absoluta o relativa a un directorio permitido"},
                    "depth": {"type": "integer", "description": "Profundidad del listado, 1 a 3 (default 2)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee líneas de un archivo de texto. En archivos grandes pagina con offset y limit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta del archivo"},
                    "offset": {"type": "integer", "description": "Primera línea a leer, 1-indexada (default 1)"},
                    "limit": {"type": "integer", "description": "Cantidad de líneas, máx 500 (default 400)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Busca archivos por nombre (glob) y/o por texto en su contenido (query). Devuelve rutas y números de línea listos para read_file. Sin query, lista los archivos cuyo nombre coincide con el glob.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Texto a buscar dentro de los archivos (insensible a mayúsculas, sin regex)"},
                    "glob": {"type": "string", "description": "Patrón de nombre de archivo, p. ej. '*.jsonl' o 'design*'"},
                    "path": {"type": "string", "description": "Directorio donde buscar (default: todos los permitidos)"},
                },
                "required": [],
            },
        },
    },
]


def run_tool_call(tool_call, extra_impls=None):
    """Ejecuta una tool call (la forma dict canónica del historial) y
    devuelve el mensaje role=tool. extra_impls incorpora las
    implementaciones de los módulos. Antes de ejecutar corre los hooks
    pre-tool de HOOKS_PRE[tool] (denylist/guardas: pueden CANCELAR la
    ejecución devolviendo texto); tras la ejecución corre los post-tool de
    HOOKS_POST[tool] para enriquecer el resultado."""
    fn = tool_call["function"]
    impls = {
        "list_files": list_files,
        "read_file": read_file,
        "search_files": search_files,
    }
    if extra_impls:
        impls.update(extra_impls)

    # Hooks pre-tool: la última palabra antes del efecto (denylist). Un hook
    # que devuelve texto CANCELA la ejecución (el texto es el resultado); si
    # devuelve None, no opina. Un hook que lanza no rompe nada: se ignora.
    for hook in HOOKS_PRE.get(fn["name"], ()):
        try:
            veto = hook(tool_call)
        except Exception:  # noqa: BLE001
            veto = None
        if veto is not None:
            return {"role": "tool", "tool_call_id": tool_call["id"], "content": str(veto)}

    impl = impls.get(fn["name"])
    if impl is None:
        result = f"ERROR: herramienta desconocida: {fn['name']}"
    else:
        try:
            args = json.loads(fn["arguments"] or "{}")
            result = str(impl(**args))
        except Exception as e:  # noqa: BLE001  (el error es un hecho, no un crash)
            result = f"ERROR: {type(e).__name__}: {e}"

    # Hooks post-tool: enriquecen el resultado antes de que viaje al modelo
    # (patrón error-como-feedback). Un hook que lanza no rompe nada.
    for hook in HOOKS_POST.get(fn["name"], ()):
        with contextlib.suppress(Exception):  # un hook que lanza no rompe nada
            result = hook(tool_call, result)

    return {"role": "tool", "tool_call_id": tool_call["id"], "content": result}
