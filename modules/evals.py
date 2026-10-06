"""Módulo `evals`: el harness juzgándose a sí mismo como capacidad del chat.

Corre el pipeline de evals.py (bench del router + linter de trazas + costo por
sesión) y devuelve la ruta del informe markdown. La pieza sigue utilizable
sola: `main.py evals [--dir .runs] [--salida salidas/evals]`.
El informe no se imprime en la terminal: se escribe a disco y se lee con
read_file, igual que run_informe.
"""
from evals import DIR_RUNS, DIR_SALIDA, generar
from utils.fs_tools import _resolve


def _arg(ruta, default):
    """resuelve una ruta contra las raíces permitidas; si viene vacía usa el
    default del módulo. Devuelve (Path, error) con error legible."""
    if not ruta:
        return default, None
    resuelta, err = _resolve(ruta)
    return resuelta, err


def evals(dir_runs=None, salida=None):
    carpeta, err = _arg(dir_runs, DIR_RUNS)
    if err:
        return f"ERROR: {err}"
    if not carpeta.is_dir():
        return f"ERROR: no es una carpeta de trazas: {carpeta}"
    destino_dir = salida or DIR_SALIDA
    try:
        # sin actualizar el baseline: el ancla de medición no se pisa desde el chat
        destino = generar(dir_runs=carpeta, dir_salida=destino_dir, actualizar_baseline=False)
    except Exception as e:  # noqa: BLE001 (una excepción no debe tumbar el chat)
        return f"ERROR: no se pudo generar el informe de evals ({type(e).__name__}: {e})"
    return (
        f"Informe de evals generado: {destino} "
        "(bench del router + linter de trazas + costo por sesión)."
    )


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "evals",
            "description": (
                "Corre los evals del harness: bench del router (acierto con "
                "compuerta, crudo y ECE contra el baseline), linter de "
                "invariantes estructurales sobre las trazas .jsonl y costo por "
                "sesión. Escribe un informe markdown y devuelve su ruta; leelo "
                "con read_file para el detalle."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dir_runs": {
                        "type": "string",
                        "description": f"Carpeta de trazas .jsonl (default: {DIR_RUNS})",
                    },
                    "salida": {
                        "type": "string",
                        "description": f"Carpeta de salida del informe (default: {DIR_SALIDA})",
                    },
                },
                "required": [],
            },
        },
    },
]


IMPL = {"evals": evals}
