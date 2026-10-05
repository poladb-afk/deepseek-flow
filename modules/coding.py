"""Módulo `coding`: run_command y edit_file con aprobación humana (HITL).

El agente de archivos se vuelve agente de código: ejecutar comandos y
editar quirúrgicamente. Nada se ejecuta sin un 's' del usuario — para
shell esa aprobación ES la contención (un comando llega a donde las
raíces permitidas de las tools de archivos no llegan; decirlo explícito
es parte del contrato). Rieles mecánicos: timeout, salida truncada (el
resultado viaja al historial del chat), stdin cerrado para que nada
quede esperando input interactivo.

edit_file es reemplazo exacto y único: la lección medida del clobber de
fs_tools.py — write_file de archivo entero lo pisó con un fragmento
(282→16 líneas). Un edit que falla ruidosamente (no existe / no es
único) obliga al modelo a volver al archivo en vez de reescribirlo de
memoria. write_file queda para archivos nuevos o reescrituras totales.
"""
import difflib
import subprocess
from pathlib import Path

from utils import hitl_web
from utils.call_llm import _setting
from utils.fs_tools import _resolve

TIMEOUT_S = 120
SALIDA_MAX = 4000  # chars: el resultado entra al historial y al costo
PREVIEW_LINES = 30

YES = {"s", "si", "sí", "y", "yes"}

_cuerpo = [""]  # cuerpo del próximo pedido HITL web (lo lee _approve)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Ejecuta un comando de shell (tests, git, python, herramientas del sistema) "
                "y devuelve código de salida más la salida combinada. Requiere aprobación "
                "humana en la terminal antes de ejecutar; un rechazo se devuelve como texto. "
                "El comando corre en el directorio de trabajo actual, sin stdin, con tope de "
                "2 minutos y salida truncada."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "El comando a ejecutar"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Edita un archivo de forma quirúrgica: reemplaza old_string por new_string "
                "(una sola ocurrencia, texto EXACTO copiado del archivo). Muestra el diff y "
                "pide aprobación humana. Falla si old_string no aparece o aparece varias "
                "veces: usá read_file y copiá literal, no reescribas de memoria. Para "
                "archivos nuevos o reescrituras completas usá write_file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta absoluta o relativa a un directorio permitido"},
                    "old_string": {"type": "string", "description": "Texto exacto a reemplazar (único en el archivo)"},
                    "new_string": {"type": "string", "description": "Texto de reemplazo (vacío = borrar)"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
]


def _approve(prompt):
    if _setting("HITL_WEB", "0") == "1":
        return hitl_web.aprobar(prompt, _cuerpo[0])
    try:
        answer = input(f"{prompt} (s/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in YES


def _clip(text, max_chars, marker):
    if len(text) <= max_chars:
        return text
    mitad = max_chars // 2
    return text[:mitad] + f"\n{marker}\n" + text[-mitad:]


def run_command(command):
    if not command or not str(command).strip():
        return "ERROR: comando vacío"
    command = str(command)
    print(f"\n── run_command ──\n{command}")
    _cuerpo[0] = command
    if not _approve("¿Ejecutar?"):
        return "RECHAZADO por el usuario: el comando no se ejecutó. Puedes proponer otro o preguntar qué cambiaría."

    try:
        r = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            stdin=subprocess.DEVNULL,
            cwd=Path.cwd(),
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: timeout de {TIMEOUT_S}s — el comando no terminó (¿loop infinito o esperaba algo?)"
    salida = (r.stdout or "").strip()
    if r.stderr:
        salida += (("\n" if salida else "") + "[stderr]\n" + r.stderr.strip()).rstrip()
    salida = _clip(salida, SALIDA_MAX, "[... salida truncada ...]")
    return f"exit {r.returncode}\n{salida or '(sin salida)'}"


def edit_file(path, old_string, new_string):
    resolved, err = _resolve(path)
    if err:
        return f"ERROR: {err}"
    if resolved.is_dir():
        return f"ERROR: es un directorio: {resolved}"
    if not resolved.exists():
        return f"ERROR: no existe: {resolved} (para crear archivos usá write_file)"
    if not old_string:
        return "ERROR: old_string vacío — no hay nada que buscar"
    if old_string == new_string:
        return "ERROR: old_string y new_string son idénticos — el edit no haría nada"

    texto = resolved.read_text(encoding="utf-8", errors="replace")
    n = texto.count(old_string)
    if n == 0:
        return (
            f"ERROR: old_string no aparece en {resolved.name}. "
            "Leé el archivo con read_file y copiá el texto EXACTO; no lo reescribas de memoria."
        )
    if n > 1:
        return (
            f"ERROR: old_string aparece {n} veces en {resolved.name}. "
            "Agregá líneas de contexto alrededor hasta que la ocurrencia sea única."
        )

    nuevo = texto.replace(old_string, new_string, 1)
    diff = "\n".join(
        difflib.unified_diff(
            texto.splitlines(),
            nuevo.splitlines(),
            fromfile=f"{resolved.name} (actual)",
            tofile=f"{resolved.name} (editado)",
            lineterm="",
        )
    )
    print(f"\n── edit_file: {resolved} ──")
    diff_mostrado = _clip(diff, SALIDA_MAX, "[... diff truncado ...]")
    print(diff_mostrado)
    _cuerpo[0] = diff_mostrado
    if not _approve(f"¿Aplicar? → {resolved}"):
        return "RECHAZADO por el usuario: el archivo no se modificó."

    try:
        resolved.write_text(nuevo, encoding="utf-8")
    except OSError as e:
        return f"ERROR al escribir: {e.strerror}"
    return f"Editado: {resolved} ({len(diff.splitlines())} líneas de diff)"


IMPL = {"run_command": run_command, "edit_file": edit_file}
