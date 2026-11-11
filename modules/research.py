"""Módulo `research`: deep research como capacidad del chat.

Corre el loop planner→researcher→synthesizer (web + cobertura) y devuelve
la ruta del informe con fuentes.

X197: declara su arista con el template (produce `borrador`, consume
`pregunta`). El conector de la composición devuelve el INFORME (D6=A); el
chat sigue recibiendo la ruta, que es lo que no inunda su contexto."""
import json
from pathlib import Path

from research import investigar
from utils.conector import Conector
from utils.kernel import Tool

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "deep_research",
            "description": "Investigación profunda sobre un tema: busca en la web en varias rondas, detecta huecos de cobertura, re-planifica y escribe un informe markdown con fuentes. Úsalo para preguntas amplias que ameritan investigación real (no una simple búsqueda).",
            "parameters": {
                "type": "object",
                "properties": {
                    "tema": {"type": "string", "description": "Tema a investigar"},
                    "salida": {"type": "string", "description": "Archivo de salida (default: salidas/research.md)"},
                },
                "required": ["tema"],
            },
        },
    },
]


def deep_research(tema, salida="salidas/research.md"):
    ruta = investigar(tema, salida)
    return f"Informe de investigación escrito: {ruta}. Lee el archivo con read_file para el detalle."


IMPL = {"deep_research": deep_research}


def _informe(llamada, _ctx):
    """El artefacto de la composición: corre la pieza y devuelve el informe."""
    args = json.loads(llamada["function"].get("arguments") or "{}")
    tema = str(args.get("tema", "") if isinstance(args, dict) else "")
    salida = args.get("salida") if isinstance(args, dict) else None
    return Path(investigar(tema, salida or "salidas/research.md")).read_text(
        encoding="utf-8", errors="replace")


CONECTORES = (Conector(Tool(TOOLS[0]["function"]["name"], TOOLS[0], _informe),
                       "borrador", ("pregunta",)),)
