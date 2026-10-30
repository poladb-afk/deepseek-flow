"""Rutas compartidas del harness: una sola fuente para las carpetas de trabajo."""
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

# Carpetas de trabajo del harness (relativas al CWD del proyecto, que es la
# convención de los CLI). Una sola definición para los cuatro que las copiaban.
DIR_RUNS = Path(".runs")
DIR_SALIDA = Path("salidas/evals")
