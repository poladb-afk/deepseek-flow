"""Módulo `rag`: búsqueda semántica como capacidad del chat.

rag_index (re)indexa una carpeta en el índice local; rag_search devuelve
los fragmentos más parecidos a una consulta. El índice vive en
rag_index/ del proyecto."""
import re

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
        salida = buscar(consulta, k=int(k))
    except RuntimeError as e:
        return f"ERROR: {e}"
    return _prefiltrar(consulta, salida, k)


def _prefiltrar(consulta, salida, k):
    """Con RAG_PREFILTRO=1, un filtro local (Laya) poda los fragmentos
    tangenciales ANTES de que viajen al modelo. Sin Laya disponible, o sin
    índice con fragmentos parseables, la salida queda intacta: el prefiltro
    es no-op y no se pierde recall (regla de hierro)."""
    from utils.call_llm import _setting

    if _setting("RAG_PREFILTRO", "1") != "1":
        return salida
    try:
        maximo = int(_setting("RAG_PREFILTRO_N", str(k)))
    except (TypeError, ValueError):
        maximo = k
    if maximo <= 0:
        return salida
    fragments = _extraer_fragmentos(salida)
    if fragments is None or len(fragments) <= maximo:
        return salida
    try:
        from utils.contexto import elegir_por_laya

        elegidos = elegir_por_laya(consulta, fragments, maximo)
    except Exception:  # el prefiltro nunca rompe rag_search
        return salida
    if len(elegidos) >= len(fragments):
        return salida
    # la línea de resumen original de buscar() ("N fragmentos indexados...")
    # se conserva: el prefiltro avisa cuántos quedaron, no reescribe el shape
    resumen = salida[:salida.index(fragments[0])].strip()
    cabecera = f"[prefiltro Laya: {len(fragments)} → {len(elegidos)} fragmentos]"
    return "\n".join([resumen, cabecera] + elegidos)


# Un fragmento en la salida de buscar(): "--- <path> (score ...) ---\n<texto>".
_RE_FRAGMENTO = re.compile(r"(?m)^--- .* ---$")


def _extraer_fragmentos(salida):
    """Separa la salida de `buscar()` en fragmentos atómicos con su cabecera
    `--- path (score) ---`. Devuelve None si la forma no matchea (p. ej. el
    índice está vacío): el prefiltro no actúa."""
    if not isinstance(salida, str):
        return None
    partes = _RE_FRAGMENTO.split(salida)
    cabeceras = _RE_FRAGMENTO.findall(salida)
    if not cabeceras:
        return None
    # partes[0] es la línea de resumen; cada fragmento es cabecera + cuerpo.
    fragmentos = []
    for i, cabecera in enumerate(cabeceras):
        cuerpo = partes[i + 1].strip() if i + 1 < len(partes) else ""
        fragmentos.append(f"{cabecera}\n{cuerpo}".strip())
    return fragmentos


def rag_index(carpeta=None, glob="*"):
    try:
        indice = indexar(carpeta or ".", glob)
    except ValueError as e:
        return f"ERROR: {e}"
    return f"Indexado en {indice}. Usa rag_search para consultar."


IMPL = {"rag_search": rag_search, "rag_index": rag_index}
