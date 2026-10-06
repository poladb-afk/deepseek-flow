"""Módulo `escritura`: write_file con aprobación humana (HITL).

Nada toca el disco sin un 's' del usuario en la terminal. Un rechazo
(o EOF/Ctrl+C durante la pregunta) también es rechazo: el default seguro.
El rechazo se devuelve al modelo como texto — es información para corregir,
no un error. Si el archivo existe, la vista previa es un diff unificado."""
import difflib

from utils import hitl_web
from utils.aprobaciones import registrar as registrar_aprobacion
from utils.call_llm import _setting
from utils.fs_tools import _resolve
from utils.terminal import highlight_diff

PREVIEW_LINES = 30
DIFF_LINES = 60
YES = {"s", "si", "sí", "y", "yes"}

_cuerpo = [""]  # cuerpo del próximo pedido HITL web (lo lee _approve local)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Escribe un archivo de texto (crea o sobrescribe) dentro de los directorios permitidos. Antes de tocar el disco muestra una vista previa (diff si el archivo ya existe) y pide aprobación humana en la terminal; si el usuario rechaza, recibirás ese rechazo como resultado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta absoluta o relativa a un directorio permitido"},
                    "content": {"type": "string", "description": "Contenido completo del archivo"},
                },
                "required": ["path", "content"],
            },
        },
    },
]


def _clip(text, max_lines, marker):
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    half = max_lines // 2
    return "\n".join(lines[:half] + [marker] + lines[-half:])


def _approve(prompt):
    if _setting("HITL_WEB", "0") == "1":
        return hitl_web.aprobar(prompt, _cuerpo[0])
    try:
        answer = input(f"{prompt} (s/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in YES


def write_file(path, content):
    resolved, err = _resolve(path)
    if err:
        return f"ERROR: {err}"
    if resolved.is_dir():
        return f"ERROR: es un directorio: {resolved}"

    print(f"\n── write_file: {resolved} ──")
    if resolved.exists():
        try:
            old = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"ERROR: no se pudo leer el archivo actual: {e.strerror}"
        if old == content:
            return "El archivo ya contiene exactamente ese contenido; no hace falta escribir."
        diff = "\n".join(
            difflib.unified_diff(
                old.splitlines(),
                content.splitlines(),
                fromfile=f"{resolved.name} (actual)",
                tofile=f"{resolved.name} (nuevo)",
                lineterm="",
            )
        )
        cuerpo = _clip(diff, DIFF_LINES, "[... diff truncado ...]")
    else:
        print(f"(archivo nuevo, {len(content.splitlines())} líneas)")
        cuerpo = _clip(content, PREVIEW_LINES, "[... contenido truncado ...]")
    print(highlight_diff(cuerpo))
    _cuerpo[0] = cuerpo

    if not _approve(f"¿Escribir? → {resolved}"):
        registrar_aprobacion("write_file", f"{resolved}", False, "preguntar")
        return "RECHAZADO por el usuario: el archivo no se modificó. Puedes proponer otro contenido o preguntar qué cambiaría."
    registrar_aprobacion("write_file", f"{resolved}", True, "preguntar")

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"ERROR al escribir: {e.strerror}"
    return f"Escrito: {resolved} ({len(content)} caracteres)"


IMPL = {"write_file": write_file}
