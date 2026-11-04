"""Módulo `rag`: búsqueda semántica como capacidad del chat.

rag_index (re)indexa una carpeta en el índice local; rag_search devuelve
los fragmentos más parecidos a una consulta. El índice vive en
rag_index/ del proyecto."""
from rag import buscar, indexar

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": "Búsqueda semántica sobre el índice RAG local: devuelve los fragmentos de documentos más parecidos a la consulta (con su ruta). Mejor que search_files para preguntas de significado; si no hay índice te lo dirá.",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Qué buscar, en lenguaje natural"},
                    "k": {"type": "integer", "description": "Cuántos fragmentos devolver (default 4)"},
                },
                "required": ["consulta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_index",
            "description": "(Re)indexa una carpeta para búsqueda semántica (trocea, vectoriza con embeddings locales y guarda el índice). Úsalo cuando rag_search indique que no hay índice o el usuario quiera indexar carpetas nuevas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "carpeta": {"type": "string", "description": "Carpeta a indexar (default: este proyecto)"},
                    "glob": {"type": "string", "description": "Patrón de archivos (default: todos)"},
                },
                "required": [],
            },
        },
    },
]


def rag_search(consulta, k=4):
    try:
        return buscar(consulta, k=int(k))
    except RuntimeError as e:
        return f"ERROR: {e}"


def rag_index(carpeta=None, glob="*"):
    try:
        indice = indexar(carpeta or ".", glob)
    except ValueError as e:
        return f"ERROR: {e}"
    return f"Indexado en {indice}. Usa rag_search para consultar."


IMPL = {"rag_search": rag_search, "rag_index": rag_index}
