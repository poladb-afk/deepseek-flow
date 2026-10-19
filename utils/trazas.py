"""Lectura tolerante de trazas .jsonl (una sola fuente para todas las piezas).

Vivía en `evals.py` y las demás piezas la importaban de ahí (import privado
cruzado, con una copia-wrapper en `replay.py`). Una traza corrupta es un
artefacto a saltear, nunca una excepción que tumbe el informe.
"""
import json
from pathlib import Path


def leer_eventos(archivo) -> list[dict]:
    """Eventos de un .jsonl; [] si el archivo es ilegible o una línea no es JSON.

    Tolera el archivo ausente; una línea corrupta descarta el archivo entero
    (la semántica histórica de evals — el contrato es "todo o nada", no
    parcial). La usan evals, replay y triaje_trazas.
    """
    eventos = []
    try:
        for linea in Path(archivo).read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea:
                eventos.append(json.loads(linea))
    except (json.JSONDecodeError, OSError):
        return []
    return eventos
