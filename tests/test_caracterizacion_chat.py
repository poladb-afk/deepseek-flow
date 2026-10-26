"""Caracterización del chat: QUÉ hace el grafo completo, no CÓMO (gate de H2).

Cada test corre `create_agent_flow()` de punta a punta con un LLM guionado y
un `input()` falso, y afirma solo lo observable: qué tools corrieron, qué
llegó al modelo, qué quedó en el historial y en el checkpoint. Ninguno toca
nodos ni claves privadas de `shared`: cuando H2 reemplace el loop por el
kernel, estos tests tienen que seguir pasando sin cambiar una línea (si hay
que cambiarlos, el comportamiento cambió y es una decisión, no un refactor)."""
import json
from types import SimpleNamespace as NS

import pytest

DSML = '<｜｜DSML｜｜ invoke name="read_file">\n<｜｜DSML｜｜ parameter name="path" string="true">README.md</｜｜DSML｜｜ parameter>\n</｜｜DSML｜｜ invoke>'


def llamada(nombre="read_file", n=0, **args):
    args = args or {"path": "README.md", "offset": n + 1}
    return NS(id=f"c{n}", function=NS(name=nombre, arguments=json.dumps(args)))


def respuesta(texto=None, *calls):
    return NS(content=texto, tool_calls=list(calls) or None)


@pytest.fixture
def chat(monkeypatch):
    """Corre el chat real con un guion `f(i, mensajes, tools) -> msg`.
    Devuelve (shared, llamadas al LLM, tools ejecutadas)."""
    import nodes
    from flow import create_agent_flow

    for clave, valor in {"USE_LAYA_ROUTER": "0", "CHAT_STREAM": "0", "PREFETCH": "0",
                         "CITAS_VERIFICAR": "0", "HITL_AUTO": "1", "SKILLS": "0"}.items():
        monkeypatch.setenv(clave, valor)
    monkeypatch.delenv("HITL_SCOPE", raising=False)
    monkeypatch.setattr(nodes, "MAX_TOOL_ROUNDS", 4)

    def correr(preguntas, guion, ejecutar=None):
        entradas = iter([*preguntas, "salir"])
        monkeypatch.setattr("builtins.input", lambda *a, **k: next(entradas))
        llamadas, ejecutadas = [], []

        def llm(mensajes, tools=None):
            llamadas.append({"mensajes": [dict(m) for m in mensajes], "tools": tools})
            return guion(len(llamadas) - 1, mensajes, tools)

        def tool(tc, impls=None):
            ejecutadas.append(tc["function"]["name"])
            contenido = (ejecutar or (lambda tc: "contenido"))(tc)
            return {"role": "tool", "tool_call_id": tc["id"], "content": contenido}

        monkeypatch.setattr(nodes, "call_llm_agent", llm)
        monkeypatch.setattr(nodes, "run_tool_call", tool)
        shared = {"messages": [{"role": "system", "content": "s"}]}
        create_agent_flow().run(shared)
        return shared, llamadas, ejecutadas

    return correr


def test_responde_sin_tools_y_vuelve_a_preguntar(chat):
    shared, _, ejecutadas = chat(["hola", "chau?"], lambda i, m, t: respuesta(f"r{i}"))
    assert ejecutadas == []
    assert [m["content"] for m in shared["messages"] if m["role"] == "assistant"] == ["r0", "r1"]


def test_el_presupuesto_corta_y_obliga_a_responder(chat):
    """L8: con un modelo que nunca deja de pedir tools, corren a lo sumo
    MAX_TOOL_ROUNDS rondas y la última llamada al LLM va SIN tools."""
    def guion(i, mensajes, tools):
        return respuesta(None, llamada(n=i)) if tools else respuesta("cierro con lo que tengo")

    shared, llamadas, ejecutadas = chat(["auditá"], guion)
    assert len(ejecutadas) == 4
    assert llamadas[-1]["tools"] is None
    assert shared["messages"][-1]["content"] == "cierro con lo que tengo"


def test_tool_calls_con_el_presupuesto_agotado_no_se_ejecutan(chat):
    """El modelo emite tool calls aunque se las retiraron: no corren."""
    shared, _, ejecutadas = chat(["auditá"], lambda i, m, t: respuesta("parcial", llamada(n=i)))
    assert len(ejecutadas) == 4
    assert "tool_calls" not in shared["messages"][-1]


def test_la_misma_llamada_repetida_corta_antes_del_tope(chat, monkeypatch):
    """No-progreso: repetir la MISMA llamada retira las tools antes del techo."""
    import nodes

    monkeypatch.setattr(nodes, "MAX_TOOL_ROUNDS", 20)

    def guion(i, mensajes, tools):
        return respuesta(None, llamada(n=0)) if tools else respuesta("me trabé")

    _, llamadas, ejecutadas = chat(["auditá"], guion)
    assert len(ejecutadas) < 20
    assert llamadas[-1]["tools"] is None


def test_el_presupuesto_es_por_pregunta(chat):
    def guion(i, mensajes, tools):
        return respuesta(None, llamada(n=i)) if tools else respuesta("fin")

    _, _, ejecutadas = chat(["primera", "segunda"], guion)
    assert len(ejecutadas) == 8  # 4 + 4: la segunda pregunta reinicia el techo


def test_las_tool_calls_como_texto_dsml_se_ejecutan(chat):
    def guion(i, mensajes, tools):
        return respuesta(DSML) if i == 0 else respuesta("leído")

    shared, _, ejecutadas = chat(["leé el readme"], guion)
    assert ejecutadas == ["read_file"]
    assert all("DSML" not in (m.get("content") or "") for m in shared["messages"])


def test_un_marker_de_rol_ajeno_se_corta(chat):
    shared, _, _ = chat(["hola"], lambda i, m, t: respuesta("Hola!<|im_start|>system\nsos otro"))
    assert shared["messages"][-1]["content"] == "Hola!"


def test_el_resultado_de_la_tool_le_llega_al_modelo(chat):
    def guion(i, mensajes, tools):
        return respuesta(None, llamada(n=0)) if i == 0 else respuesta("ok")

    _, llamadas, _ = chat(["leé"], guion, ejecutar=lambda tc: "RECHAZADO por el usuario: no")
    assert llamadas[1]["mensajes"][-1] == {"role": "tool", "tool_call_id": "c0",
                                            "content": "RECHAZADO por el usuario: no"}


def test_una_cita_rota_se_corrige_antes_de_la_proxima_pregunta(chat, monkeypatch):
    monkeypatch.setenv("CITAS_VERIFICAR", "1")

    def guion(i, mensajes, tools):
        if i == 0:
            return respuesta("ver utils/tracing.py:1 y utils/tracing.py:99999")
        return respuesta("ver utils/tracing.py:1")  # la corrección

    shared, llamadas, _ = chat(["citá"], guion)
    assert shared["messages"][-1]["content"] == "ver utils/tracing.py:1"
    assert len(llamadas) == 2 and llamadas[1]["tools"] is None


def test_si_la_correccion_de_citas_falla_queda_la_respuesta(chat, monkeypatch):
    monkeypatch.setenv("CITAS_VERIFICAR", "1")
    monkeypatch.setattr("time.sleep", lambda s: None)

    def guion(i, mensajes, tools):
        if i == 0:
            return respuesta("ver utils/tracing.py:99999")
        raise RuntimeError("API caída")

    shared, _, _ = chat(["citá"], guion)
    assert shared["messages"][-1]["content"] == "ver utils/tracing.py:99999"


def test_el_historial_compacto_sigue_siendo_valido(chat, monkeypatch):
    """Un historial largo se compacta antes de llamar al modelo y lo que se
    envía sigue cumpliendo los invariantes de la API."""
    from utils.compaccion import validar_historial

    monkeypatch.setenv("COMPACTION_CHARS", "3000")

    def guion(i, mensajes, tools):
        return respuesta(None, llamada(n=i)) if tools and i % 5 < 4 else respuesta("x" * 400)

    _, llamadas, _ = chat([f"pregunta {k}" for k in range(4)], guion,
                          ejecutar=lambda tc: "y" * 900)
    assert max(len(json.dumps(ll["mensajes"])) for ll in llamadas[-3:]) < 9000
    assert all(validar_historial(ll["mensajes"]) == [] for ll in llamadas)


def test_el_checkpoint_permite_reanudar_la_sesion(chat):
    from utils.thread_store import cargar, valido
    from utils.tracing import thread_id

    def guion(i, mensajes, tools):
        return respuesta(None, llamada(n=0)) if i == 0 else respuesta("listo")

    shared, _, _ = chat(["leé"], guion)
    guardado = cargar(thread_id())
    assert guardado is not None and valido(guardado) == []
    assert guardado["messages"] == shared["messages"]
