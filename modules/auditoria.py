"""Módulo `auditoria`: expone la auditoría multi-carpeta como herramienta.

Corre el mismo flujo que `main.py auditoria` y devuelve la ruta del
markdown generado."""
from auditoria import auditar

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_auditoria",
            "description": "Audita varias carpetas a la vez con el pipeline map-reduce (una sección por carpeta + síntesis global comparativa) y devuelve la ruta del markdown. Úsalo cuando el usuario quiera comparar carpetas o auditar varias a la vez.",
            "parameters": {
                "type": "object",
                "properties": {
                    "carpetas": {"type": "string", "description": "Carpetas a auditar, separadas por coma"},
                    "glob": {"type": "string", "description": "Patrón de archivos (default: '*.jsonl')"},
                    "salida": {"type": "string", "description": "Archivo de salida (default: auditoria.md)"},
                },
                "required": ["carpetas"],
            },
        },
    },
]


def run_auditoria(carpetas, glob="*.jsonl", salida="auditoria.md"):
    if isinstance(carpetas, (list, tuple)):
        lista = [str(c).strip() for c in carpetas if str(c).strip()]
    else:
        lista = [c.strip() for c in str(carpetas).split(",") if c.strip()]
    try:
        ruta = auditar(lista, glob, salida)
    except ValueError as e:
        return f"ERROR: {e}"
    return f"Auditoría generada: {ruta}. Lee el archivo con read_file para el detalle."


IMPL = {"run_auditoria": run_auditoria}
