"""Rutas compartidas por las sondas: una sola fuente.

El default de BMO_TASKS_DIR vivía copiado en sonda_laya.py, sonda_router.py y
sonda_supervisor.py — tres copias del mismo default, cada una libre de derivar
sin que ningún test lo notara.
"""
from pathlib import Path

from utils.call_llm import _setting

BMO_TASKS_DEFAULT = Path.home() / "Documentos" / "00_IA" / "bmo" / "train" / "tasks"


def tasks_dir():
    """Directorio de tareas del banco: BMO_TASKS_DIR, o el default histórico."""
    return Path(_setting("BMO_TASKS_DIR", str(BMO_TASKS_DEFAULT)))
