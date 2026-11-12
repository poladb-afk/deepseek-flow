"""Módulo `research`: deep research como capacidad del chat.

Corre el loop planner→researcher→synthesizer (web + cobertura) y devuelve
la ruta del informe con fuentes.

X197: declara su arista con el template (produce `borrador`, consume
`pregunta`). El conector de la composición devuelve el INFORME (D6=A); el
chat sigue recibiendo la ruta, que es lo que no inunda su contexto."""
from pathlib import Path

from research import investigar
from utils.conector import conector_de_modulo

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


def informe(tema, salida="salidas/research.md"):
    """El artefacto de la composición: corre la pieza y devuelve el informe."""
    return Path(investigar(tema, salida)).read_text(encoding="utf-8", errors="replace")


# X197b: por la fábrica, como `debate` y `fable`: la composición pasa por el
# despacho único (hooks PRE, política) con la misma tool y otro IMPL (D6=A).
CONECTORES = (conector_de_modulo(TOOLS[0], "borrador", ("pregunta",), {"deep_research": informe}),)
