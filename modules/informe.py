"""Módulo `informe`: expone el pipeline map-reduce (informe.py) como una
herramienta del chat. La pieza sigue utilizable sola: `main.py informe`.
El progreso del pipeline se imprime en la terminal mientras corre."""
import asyncio

from informe import DEFAULT_FOLDER, create_informe_flow
from utils.fs_tools import _resolve

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_informe",
            "description": "Genera un informe map-reduce de trazas .jsonl: estadísticas exactas por archivo, lectura de cada uno y síntesis final. Devuelve la ruta del markdown generado; léelo con read_file para el detalle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "carpeta": {"type": "string", "description": f"Carpeta a analizar (default: {DEFAULT_FOLDER})"},
                    "glob": {"type": "string", "description": "Patrón de archivos (default: '*.jsonl')"},
                    "salida": {"type": "string", "description": "Archivo de salida (default: salidas/informe.md)"},
                },
                "required": [],
            },
        },
    },
]


def run_informe(carpeta=None, glob="*.jsonl", salida="salidas/informe.md"):
    folder, err = _resolve(carpeta or DEFAULT_FOLDER)
    if err:
        return f"ERROR: {err}"
    if not folder.is_dir():
        return f"ERROR: no es una carpeta: {folder}"
    shared = {"folder": str(folder), "glob": glob, "salida": salida}
    asyncio.run(create_informe_flow().run_async(shared))
    return (
        f"Informe generado: {shared['informe']} "
        f"({len(shared.get('analisis', []))} archivos analizados)."
    )


IMPL = {"run_informe": run_informe}
