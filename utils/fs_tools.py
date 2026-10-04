"""Herramientas del agente: listar y leer archivos en directorios permitidos.

El modelo construye las rutas; _resolve() garantiza que ninguna salga de
los directorios permitidos (AGENT_ALLOWED_DIRS, separados por ':').
Los errores de uso (ruta fuera de rango, archivo inexistente, argumentos
mal formados) se devuelven como texto "ERROR: ..." para que el modelo
corrija en la siguiente vuelta; no son fallos transitorios del API.
"""
import fnmatch
import json
import os
from pathlib import Path

from utils.call_llm import _setting

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


def allowed_roots():
    text = _setting("AGENT_ALLOWED_DIRS", DEFAULT_ALLOWED_DIRS)
    return [Path(p).expanduser().resolve() for p in text.split(":") if p.strip()]


def _resolve(raw):
    roots = allowed_roots()
    expanded = Path(raw).expanduser()
    if expanded.is_absolute():
        candidates = [expanded]
    else:
        candidates = [root / expanded for root in roots]
    for cand in candidates:
        resolved = Path.resolve(cand)
        for root in roots:
            if resolved == root or root in resolved.parents:
                return resolved, None
    return None, "ruta fuera de los directorios permitidos: " + ", ".join(str(r) for r in roots)


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
            entries = sorted(d.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
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
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                rel_posix = fpath.relative_to(root).as_posix()
                if not _name_matches(rel_posix, fname, pattern):
                    continue
                try:
                    size = fpath.stat().st_size
                except OSError:
                    continue
                if not query:
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
        out = [f"{len(file_hits)} archivos coinciden con '{pattern}':"]
        out += [f"- {p} ({s} B)" for p, s in sorted(file_hits)]
        if len(file_hits) == SEARCH_MAX_FILES:
            out.append(f"[tope de {SEARCH_MAX_FILES} alcanzado: puede haber más]")
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
    """Ejecuta una tool call de la API y devuelve el mensaje role=tool.
    extra_impls incorpora las implementaciones de los módulos."""
    fn = tool_call.function
    impls = {
        "list_files": list_files,
        "read_file": read_file,
        "search_files": search_files,
    }
    if extra_impls:
        impls.update(extra_impls)
    impl = impls.get(fn.name)
    if impl is None:
        result = f"ERROR: herramienta desconocida: {fn.name}"
    else:
        try:
            args = json.loads(fn.arguments or "{}")
            result = str(impl(**args))
        except Exception as e:
            result = f"ERROR: {type(e).__name__}: {e}"
    return {"role": "tool", "tool_call_id": tool_call.id, "content": result}
