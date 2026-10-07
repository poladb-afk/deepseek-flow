"""Búsqueda web con ddgs (DuckDuckGo): sin API key.

SEARCH_PROVIDER en .env reserva el punto de enchufe para Tavily/Brave
el día que haga falta; hoy solo ddgs está implementado."""
from utils.call_llm import _setting


def search_web(consulta, k=5):
    from ddgs import DDGS

    if _setting("SEARCH_PROVIDER", "ddgs") != "ddgs":
        return f"ERROR: SEARCH_PROVIDER={_setting('SEARCH_PROVIDER')} no implementado; usa ddgs"

    try:
        resultados = DDGS().text(consulta, max_results=int(k)) or []
    except Exception as e:  # noqa: BLE001  (degrada a texto: el resto del
        # harness no se cae por una búsqueda sin red; research ve el error
        # como dato y sigue con las queries que sí pueden salir)
        return f"ERROR: búsqueda web falló ({type(e).__name__}: {e})"
    lineas = []
    for r in resultados:
        url = r.get("href") or r.get("url") or ""
        titulo = r.get("title", "")
        cuerpo = (r.get("body") or "")[:300]
        lineas.append(f"- {titulo}\n  {url}\n  {cuerpo}")
    if not lineas:
        return f"Sin resultados para: {consulta}"
    return "\n\n".join(lineas)


if __name__ == "__main__":
    import sys

    print(search_web(" ".join(sys.argv[1:]) or "PocketFlow framework github"))
