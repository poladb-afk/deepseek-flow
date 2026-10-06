"""Módulo `effective_n`: expone la deduplicación exacta (effective_n.py)
como herramienta del chat. La pieza sigue utilizable sola:
`main.py effective_n [carpeta ...]`. Código puro: sin LLM, determinista.

Acepta UNA o VARIAS carpetas; con varias corre el flujo por carpeta
(BatchFlow, secuencial a propósito) y escribe un informe conjunto."""
from effective_n import (
    DEFAULT_FOLDER,
    EffectiveNMulti,
    create_effective_n_flow,
)
from utils.fs_tools import _resolve

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_effective_n",
            "description": (
                "Mide el Effective N de trazas .jsonl: deduplicación exacta por contenido "
                "(sha1 de fields+next, ignora id/created), archivos duplicados enteros, "
                "solape por pares y contradicciones de etiqueta. Acepta una o varias carpetas "
                "(con varias: informe conjunto con una sección por carpeta). Escribe un informe "
                "markdown y devuelve el resumen; lee el archivo con read_file para el detalle."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "carpetas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": f"Carpetas a analizar (default: ['{DEFAULT_FOLDER}'])",
                    },
                    "glob": {"type": "string", "description": "Patrón de archivos (default: '*.jsonl')"},
                    "salida": {"type": "string", "description": "Archivo de salida (default: 'salidas/effective_n.md')"},
                },
                "required": [],
            },
        },
    },
]


def run_effective_n(carpetas=None, glob="*.jsonl", salida="salidas/effective_n.md"):
    raw = carpetas or [DEFAULT_FOLDER]
    if isinstance(raw, str):
        raw = [raw]
    resueltas, errores = [], []
    for c in raw:
        folder, err = _resolve(c)
        if err:
            errores.append(f"{c}: {err}")
        elif not folder.is_dir():
            errores.append(f"{c}: no es una carpeta: {folder}")
        else:
            resueltas.append(folder)
    if errores:
        return "ERROR:\n" + "\n".join(errores)

    if len(resueltas) == 1:
        shared = {"folder": str(resueltas[0]), "glob": glob, "salida": salida}
        create_effective_n_flow().run(shared)
    else:
        shared = {"informes": []}
        EffectiveNMulti(resueltas, glob, salida).run(shared)
    return f"Effective N medido: {shared['resumen']}. Informe: {shared['informe']}"


IMPL = {"run_effective_n": run_effective_n}
