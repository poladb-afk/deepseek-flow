"""Rutas compartidas por las sondas: una sola fuente.

El default de BMO_TASKS_DIR vivía copiado en sonda_laya.py, sonda_router.py (retirada en X106) y
sonda_supervisor.py — tres copias del mismo default, cada una libre de derivar
sin que ningún test lo notara.
"""
from pathlib import Path

from utils.call_llm import _setting

BMO_TASKS_DEFAULT = Path.home() / "Documentos" / "00_IA" / "bmo" / "train" / "tasks"


RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

# Carpetas de trabajo del harness (relativas al CWD del proyecto, que es la
# convención de los CLI). Una sola definición para los cuatro que las copiaban.
DIR_RUNS = Path(".runs")
DIR_SALIDA = Path("salidas/evals")


def tasks_dir():
    """Directorio de tareas del banco: BMO_TASKS_DIR, o el default histórico."""
    return Path(_setting("BMO_TASKS_DIR", str(BMO_TASKS_DEFAULT)))
