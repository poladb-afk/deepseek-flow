"""Módulo `debate`: debate multi-agente como capacidad del chat.

Corre el debate de debate.py (proponente y crítico por colas + juez) y
devuelve el veredicto. El transcript completo se imprime en la terminal."""
from debate import debatir

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "debate",
            "description": "Debate multi-agente sobre un tema: un proponente y un crítico discuten N rondas y un juez dictamina ganador y síntesis. Úsalo cuando el usuario quiera explorar dos lados de una cuestión.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tema": {"type": "string", "description": "Tema o afirmación a debatir"},
                    "rondas": {"type": "integer", "description": "Rondas de intercambio (default 2)"},
                },
                "required": ["tema"],
            },
        },
    },
]


def debate(tema, rondas=2):
    veredicto = debatir(tema, rondas=int(rondas))
    return f"Ganador: {veredicto['ganador']}\n\nSíntesis del juez:\n{veredicto['sintesis']}"


IMPL = {"debate": debate}
