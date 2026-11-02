"""Módulo `escritura`: write_file con aprobación humana (HITL).

Nada toca el disco sin un 's' del usuario en la terminal. Un rechazo
(o EOF/Ctrl+C durante la pregunta) también es rechazo: el default seguro.
El rechazo se devuelve al modelo como texto — es información para corregir,
no un error. Si el archivo existe, la vista previa es un diff unificado."""
import difflib

from utils.aprobaciones import Pedido, pedir_aprobacion
from utils.aprobaciones import registrar as registrar_aprobacion
from utils.fs_tools import _resolve, escribir_atomico
from utils.terminal import highlight_diff, recortar_lineas

PREVIEW_LINES = 30
DIFF_LINES = 60

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





def _approve(pedido):
    """Punto de parcheo de los tests: la lógica vive en utils/aprobaciones."""
    return pedir_aprobacion(pedido)


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
        cuerpo = recortar_lineas(diff, DIFF_LINES, "[... diff truncado ...]")
    else:
        print(f"(archivo nuevo, {len(content.splitlines())} líneas)")
        cuerpo = recortar_lineas(content, PREVIEW_LINES, "[... contenido truncado ...]")
    print(highlight_diff(cuerpo))

    decision = _approve(Pedido(f"¿Escribir? → {resolved}", cuerpo, "escritura", str(resolved)))
    if not decision:
        registrar_aprobacion("write_file", f"{resolved}", False, "preguntar")
        motivo = getattr(decision, "motivo", "") or "el archivo no se modificó"
        return f"RECHAZADO por el usuario: {motivo}."
    registrar_aprobacion("write_file", f"{resolved}", True, "preguntar")

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        escribir_atomico(resolved, content)
    except OSError as e:
        return f"ERROR al escribir: {e.strerror}"
    return f"Escrito: {resolved} ({len(content)} caracteres)"


IMPL = {"write_file": write_file}
