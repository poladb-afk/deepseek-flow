"""Módulo `websearch`: el agente consulta la web.

ddgs (DuckDuckGo) sin API key; el resultado trae título, URL y resumen
para que el agente cite fuentes."""
from utils.websearch import search_web

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Busca en la web (DuckDuckGo) y devuelve títulos, URLs y resúmenes. Úsalo para preguntas sobre información actual o que no está en los archivos locales; cita la URL de la fuente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Qué buscar (mejor en el idioma de la respuesta esperada)"},
                    "k": {"type": "integer", "description": "Cuántos resultados (default 5)"},
                },
                "required": ["consulta"],
            },
        },
    },
]


def run_search_web(consulta, k=5):
    return search_web(consulta, int(k))


IMPL = {"search_web": run_search_web}
