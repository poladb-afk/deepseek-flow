"""Los instrumentos leen la traza del chat REAL, no una escrita a mano (X136).

`banco/probes/rondas.py` (la forma del loop) y el linter de `evals.py` se
probaban con trazas sintéticas con los nombres de nodo de cuando se
escribieron. Después de S9b A′ el chat emite PasoChat/ActuarChat/CierreChat:
`rondas.ciclos` contaba 0 rondas y "sin responder" en cada traza nueva, y el
linter marcaba una violación por respuesta, con sus tests en verde. Acá la
traza sale del grafo real (`create_agent_flow`) con el tracing de producción:
si el loop cambia de nombres otra vez, estos tests fallan en vez de mentir."""
import json
import sys
from types import SimpleNamespace as NS

import pytest
from conftest import RAIZ

sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import rondas  # noqa: E402


@pytest.fixture
def traza_del_chat(tmp_path, monkeypatch):
    """Corre el chat real (dos preguntas, techo 3, un modelo que siempre pide
    tools) con el tracing de producción y devuelve los eventos."""
    import builtins

    import pocketflow

    import flow
    import nodes
    import utils.tracing as tracing
    from instrumentos import leer_eventos

    for clave, valor in {"CHAT_STREAM": "0", "PREFETCH": "0", "CITAS_VERIFICAR": "0",
                         "SKILLS": "0", "TRACE": "1"}.items():
        monkeypatch.setenv(clave, valor)
    monkeypatch.setattr(nodes, "MAX_TOOL_ROUNDS", 3)  # se lee al importar: el setting no alcanza
    contador = iter(range(1000))

    def llm(mensajes, tools=None):
        n = next(contador)
        if tools:
            return NS(content=None, tool_calls=[NS(id=f"c{n}", function=NS(
                name="read_file", arguments=json.dumps({"path": "README.md", "offset": n + 1})))])
        return NS(content="cierro con lo que tengo", tool_calls=None)

    monkeypatch.setattr(nodes, "call_llm_agent", llm)
    monkeypatch.setattr(nodes.catalogo, "despachar",
                        lambda tc, tools, impls: {"role": "tool", "tool_call_id": tc["id"], "content": "ok"})
    entradas = iter(["auditá", "y ahora?", "salir"])
    monkeypatch.setattr(builtins, "input", lambda *a, **k: next(entradas))
    respaldo = (tracing._salida, tracing._ruta_salida, tracing._activo, tracing._id_thread)
    run_original = pocketflow.BaseNode._run
    try:
        tracing._activo = False
        archivo = tracing.activar(ruta_base=str(tmp_path))
        flow.create_agent_flow().run({"messages": [{"role": "system", "content": "s"}]})
    finally:
        pocketflow.BaseNode._run = run_original
        if tracing._salida is not None and not tracing._salida.closed:
            tracing._salida.close()
        tracing._salida, tracing._ruta_salida, tracing._activo, tracing._id_thread = respaldo
    return leer_eventos(archivo)


def test_rondas_cuenta_las_rondas_y_la_respuesta_del_chat_real(traza_del_chat):
    ciclos = rondas.ciclos(traza_del_chat)
    assert [(c["rondas"], c["respondio"]) for c in ciclos] == [(3, True), (3, True)]
    assert all(c["tools_por_ronda"] == [["read_file"]] * 3 for c in ciclos)


def test_el_linter_no_marca_nada_en_la_traza_del_chat_real(traza_del_chat):
    import evals

    assert {e["nodo"] for e in traza_del_chat} >= {"PasoChat", "ActuarChat", "CierreChat", "VerificarCitas"}
    assert evals.linter_traza(traza_del_chat) == []
