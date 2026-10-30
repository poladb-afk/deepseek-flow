"""El diagrama del README es el grafo que ejecuta el framework, no uno dibujado.

Medido en la auditoría del 2026-10-27: el README mostraba
GetQuestion → AgentStep mientras el chat real pasaba por PreFetch y el router.
`utils.viz.mermaid` ya camina los sucesores; acá se exige que el README diga
lo mismo (regenerarlo: `python3 main.py grafo chat`)."""
import re

from conftest import RAIZ


def test_el_diagrama_del_readme_es_el_grafo_del_chat():
    from flow import create_agent_flow
    from utils.viz import mermaid

    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    bloque = re.search(r"```mermaid\n(.*?)\n```", readme, re.S)
    assert bloque, "el README perdió el diagrama del chat"
    assert bloque.group(1) == mermaid(create_agent_flow()), (
        "el diagrama del README no es el grafo real: regeneralo con `python3 main.py grafo chat`")
