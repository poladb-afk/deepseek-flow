"""Módulo `effective_n`: expone la deduplicación exacta (effective_n.py)
como herramienta del chat. La pieza sigue utilizable sola:
`main.py effective_n`. Código puro: sin LLM, determinista."""
from effective_n import DEFAULT_FOLDER, create_effective_n_flow
from utils.fs_tools import _resolve

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_effective_n",
            "description": (
                "Mide el Effective N de trazas .jsonl: deduplicación exacta por contenido "
                "(sha1 de fields+next, ignora id/created), archivos duplicados enteros, "
                "solape por pares y contradicciones de etiqueta. Escribe un informe markdown "
                "y devuelve el resumen; lee el archivo con read_file para el detalle."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "carpeta": {"type": "string", "description": f"Carpeta a analizar (default: {DEFAULT_FOLDER})"},
                    "glob": {"type": "string", "description": "Patrón de archivos (default: '*.jsonl')"},
                    "salida": {"type": "string", "description": "Archivo de salida (default: 'effective_n.md')"},
                },
                "required": [],
            },
        },
    },
]


def run_effective_n(carpeta=None, glob="*.jsonl", salida="effective_n.md"):
    folder, err = _resolve(carpeta or DEFAULT_FOLDER)
    if err:
        return f"ERROR: {err}"
    if not folder.is_dir():
        return f"ERROR: no es una carpeta: {folder}"
    shared = {"folder": str(folder), "glob": glob, "salida": salida}
    create_effective_n_flow().run(shared)
    return f"Effective N medido: {shared['resumen']}. Informe: {shared['informe']}"


IMPL = {"run_effective_n": run_effective_n}
