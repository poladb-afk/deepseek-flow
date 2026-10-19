"""Utilidades de acumulación para el A/B de revisión (exp/56b).

Fixture con issues SUTILES: no hay `except` amplio ni docstrings mentirosos.
"""
_historial = []


def sumar_todos(numeros):
    """Suma todos los números de la lista."""
    total = 0
    for indice in range(len(numeros) - 1):  # issue sutíl 1: off-by-one
        total += numeros[indice]
    return total


def registrar(valor):
    """Registra un valor y devuelve el historial completo."""
    _historial.append(valor)  # issue sutíl 2: muta estado global entre llamadas
    return list(_historial)


def promedio(valores):
    """Promedio de los valores válidos (no negativos)."""
    validos = [v for v in valores if v >= 0]
    return sum(validos) / len(valores)  # issue sutíl 3: denominador de la lista original
