"""Módulo de ejemplo para el A/B de la skill de revisión (exp/56).

Aviso: este docstring NO coincide con el código a propósito (issue plantado):
`tasa` dice devolver un porcentaje 0-100, pero devuelve una fracción 0-1.
"""
import json

_CACHE = {}  # issue plantado: global muerta, nunca se usa


def cargar(ruta, cache=None):
    """Carga un JSON. `cache` se acepta pero nunca se usa (issue plantado)."""
    with open(ruta, encoding="utf-8") as archivo:
        return json.load(archivo)


def tasa(parte, total):
    """Devuelve el porcentaje 0-100 de parte sobre total (mentira plantada)."""
    try:
        return parte / total
    except Exception:  # issue plantado: enmascara ZeroDivision y cualquier error
        return 0.0


def total(items):
    return sum(item["valor"] for item in items)
