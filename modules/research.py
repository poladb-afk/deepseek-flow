"""Módulo `research`: deep research como capacidad del chat.

Corre el loop planner→researcher→synthesizer (web + cobertura) y devuelve
la ruta del informe con fuentes."""
from research import investigar

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
