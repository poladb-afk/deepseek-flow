"""Gate previo de la fase 3 (banco/specs/fase3.md): la sonda thinking_tools
sin red. Clava que usa el MISMO builder que produccion, las ocho secuencias y
el veredicto redefinido (A–E y G deciden; F y H informan)."""
from types import SimpleNamespace as NS

import pytest

from banco.probes import thinking_tools as tt
from utils.call_llm import _kwargs_agente


def test_pensar_preserva_el_reasoning_y_habilita_thinking_con_tools():
    mensajes = [{"role": "user", "content": "x"},
                {"role": "assistant", "content": None, "reasoning_content": "pienso",
                 "tool_calls": [{"id": "1", "type": "function",
                                 "function": {"name": "list_files", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "1", "content": "a.py"}]
    con = _kwargs_agente(mensajes, [{"function": {"name": "list_files"}}], pensar=True)
    assert con["extra_body"] == {"thinking": {"type": "enabled"}}
    assert con["messages"][1]["reasoning_content"] == "pienso"
    # el camino de hoy no cambia: thinking OFF y el reasoning no viaja
    hoy = _kwargs_agente(mensajes, [{"function": {"name": "list_files"}}])
    assert hoy["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_content" not in hoy["messages"][1]


def _ultimo_usuario(mensajes):
    return max((i for i, m in enumerate(mensajes) if m.get("role") == "user"), default=-1)


class ClienteFalso:
    """Pide UNA tool cuando el último mensaje es del usuario; si no, responde.
    `regla` modela qué exige la API con thinking ON:
      None      — nada (acepta todo)
      "turno"   — el reasoning de los assistant con tool_calls POSTERIORES al
                  último user (la hipótesis que sale de E ok + F 400)
      "siempre" — el de TODOS los assistant con tool_calls (la lectura literal
                  de la doc: "todas las requests subsiguientes")"""

    def __init__(self, regla=None):
        self.regla, self.requests = regla, []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        mensajes = kwargs["messages"]
        pensando = kwargs["extra_body"]["thinking"]["type"] == "enabled"
        desde = _ultimo_usuario(mensajes) + 1 if self.regla == "turno" else 0
        sin_razon = any(m.get("tool_calls") and not m.get("reasoning_content") for m in mensajes[desde:])
        if self.regla and pensando and sin_razon:
            raise _Error400()
        ultimo = mensajes[-1]
        pide = kwargs.get("tools") and (getattr(self, "insistente", False) or (
            ultimo["role"] == "user" and "Respondé AHORA" not in ultimo["content"]))
        calls = [NS(id=f"c{len(self.requests)}", function=NS(name="list_files", arguments="{}"))] if pide else None
        return NS(choices=[NS(message=NS(content=None if pide else "listo", tool_calls=calls,
                                         reasoning_content="razono"))])


class _Error400(Exception):
    status_code = 400


def test_las_ocho_secuencias_pasan_con_una_api_que_acepta():
    """Las ocho (A–H): con una API que acepta todo, todas ok y el gate pasa.
    B y H cierran sin tools; F y la primera parte de G van con thinking OFF."""
    sonda = tt.Sonda(ClienteFalso())
    tt.secuencias(sonda)
    pasa, resumen = tt.veredicto(sonda.pasos)
    assert pasa and set(resumen) == set("ABCDEFGH")
    assert all(v == "ok" for v in resumen.values())
    assert any(p["secuencia"] == "B" and p["paso"] == "cierre sin tools" and not p["tools"]
               for p in sonda.pasos)
    cierre_h = next(p for p in sonda.pasos if p["secuencia"] == "H" and not p["tools"])
    assert cierre_h["pensar"] is False
    assert [p["pensar"] for p in sonda.pasos if p["secuencia"] == "G"] == [False, False, True, True]


def test_la_regla_del_turno_reproduce_la_primera_corrida_y_el_gate_pasa():
    """La hipótesis (E ok + F 400 en vivo): el reasoning se exige solo en el
    turno en curso. Con esa API, F da 400 — informativa — y G pasa: el modo
    puede cambiar ENTRE preguntas. El gate redefinido pasa."""
    sonda = tt.Sonda(ClienteFalso(regla="turno"))
    tt.secuencias(sonda)
    pasa, resumen = tt.veredicto(sonda.pasos)
    assert resumen["F"] == "400" and resumen["E"] == resumen["G"] == "ok"
    assert pasa


def test_un_400_tumba_el_gate_y_se_ve_donde():
    """Con la regla literal (el reasoning de TODA la conversación), E y G dan
    400: la fase 3 tendría que conservar el reasoning para siempre
    (compacción y resume) — el gate no pasa y dice dónde."""
    sonda = tt.Sonda(ClienteFalso(regla="siempre"))
    tt.secuencias(sonda)
    pasa, resumen = tt.veredicto(sonda.pasos)
    assert not pasa
    assert resumen["E"] == resumen["F"] == resumen["G"] == "400"
    assert resumen["A"] == resumen["B"] == resumen["C"] == resumen["D"] == "ok"


@pytest.mark.parametrize(("status", "esperado"), [(429, "sin veredicto"), (None, "sin veredicto")])
def test_un_error_que_no_es_400_deja_la_secuencia_sin_veredicto(status, esperado):
    pasos = [{"secuencia": s, "ok": True, "status": 200} for s in "ABCDEFH"]
    pasos.append({"secuencia": "G", "ok": False, "status": status})
    pasa, resumen = tt.veredicto(pasos)
    assert not pasa and resumen["G"] == esperado


def test_las_informativas_no_deciden_el_gate():
    pasos = [{"secuencia": s, "ok": True, "status": 200} for s in "ABCDEG"]
    pasos += [{"secuencia": s, "ok": False, "status": 400} for s in "FH"]
    pasa, resumen = tt.veredicto(pasos)
    assert pasa and resumen["F"] == resumen["H"] == "400"


# ── X103: la fase 3 en el chat (PENSAR_TOOLS, default 0) ─────────────────


def test_el_stream_junta_el_reasoning_sin_imprimirlo(monkeypatch, capsys):
    """El banco corre con streaming: sin juntar el reasoning de los deltas,
    la 3a daba 400 en la primera ronda (la secuencia F). Se junta APARTE:
    ni a stdout ni a content (el contrato de exp/38 sigue)."""
    import utils.call_llm as c

    def chunk(content=None, reasoning=None):
        return NS(choices=[NS(delta=NS(content=content, reasoning_content=reasoning, tool_calls=None))])

    class Completions:
        def create(self, **kwargs):
            self.kwargs = kwargs
            return iter([chunk(reasoning="pien"), chunk(reasoning="so"), chunk(content="hola")])

    comp = Completions()
    monkeypatch.setattr(c, "_client", lambda: NS(chat=NS(completions=comp)))
    msg = c.call_llm_agent_stream([{"role": "user", "content": "x"}], pensar=True)
    assert msg.content == "hola" and msg.reasoning_content == "pienso"
    assert "pien" not in capsys.readouterr().out
    assert comp.kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


def test_el_reasoning_vive_solo_en_el_turno_en_curso():
    """El invariante 1 nuevo: reasoning en assistant después del último user,
    nunca antes; y al llegar la pregunta nueva se descarta el de antes."""
    from utils.compaccion import sin_razonamiento_previo, validar_historial

    turno_viejo = [{"role": "system", "content": "s"}, {"role": "user", "content": "q1"},
                   {"role": "assistant", "content": None, "reasoning_content": "r1",
                    "tool_calls": [{"id": "1", "type": "function",
                                    "function": {"name": "list_files", "arguments": "{}"}}]},
                   {"role": "tool", "tool_call_id": "1", "content": "a.py"}]
    assert validar_historial(turno_viejo) == []
    con_pregunta = turno_viejo + [{"role": "user", "content": "q2"}]
    assert validar_historial(con_pregunta) == ["[2] arrastra reasoning_content"]
    limpio = sin_razonamiento_previo(con_pregunta)
    assert validar_historial(limpio) == []
    assert "reasoning_content" in turno_viejo[2]  # pura: no muta el original
    assert validar_historial([{"role": "system", "content": "s"},
                              {"role": "user", "content": "q", "reasoning_content": "x"}])


def test_con_pensar_el_modo_no_cambia_dentro_de_la_pregunta(monkeypatch):
    """La secuencia F (400 en vivo) queda IMPOSIBLE por construcción: todas
    las llamadas de una pregunta — rondas con tools y el Cierre por
    presupuesto — van con el mismo modo, el reasoning del turno en curso
    viaja, y una pregunta nueva arranca sin el reasoning de la anterior.
    El cliente falso con la regla del turno (la de la API) no da ningún 400."""
    import nodes
    from flow import create_agent_flow

    for clave, valor in {"USE_LAYA_ROUTER": "0", "CHAT_STREAM": "0", "PREFETCH": "0",
                         "CITAS_VERIFICAR": "0", "HITL_AUTO": "1", "SKILLS": "0",
                         "PENSAR_TOOLS": "1"}.items():
        monkeypatch.setenv(clave, valor)
    monkeypatch.delenv("HITL_SCOPE", raising=False)
    monkeypatch.setattr(nodes, "MAX_TOOL_ROUNDS", 2)
    api = ClienteFalso(regla="turno")
    api.insistente = True  # pide tools mientras las haya: agota el presupuesto
    modos = []

    def llm(mensajes, tools=None, pensar=False):
        from utils.call_llm import _kwargs_agente

        modos.append(pensar)
        return api.create(**_kwargs_agente(mensajes, tools, pensar)).choices[0].message

    entradas = iter(["listá", "¿y ahora?", "salir"])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(entradas))
    monkeypatch.setattr(nodes, "call_llm_agent", llm)
    monkeypatch.setattr(nodes, "run_tool_call",
                        lambda tc, impls=None: {"role": "tool", "tool_call_id": tc["id"], "content": "a.py"})
    shared = {"messages": [{"role": "system", "content": "s"}]}
    create_agent_flow().run(shared)

    from utils.compaccion import validar_historial

    assert modos and all(modos)              # ninguna llamada de la pregunta cambió de modo
    assert len(api.requests) == len(modos)   # y ninguna dio 400 contra la regla del turno
    assert any(r["messages"][-1]["content"].startswith("(presupuesto") for r in api.requests)
    assert validar_historial(shared["messages"]) == []


def test_sin_pensar_el_chat_es_el_de_siempre(monkeypatch):
    """PENSAR_TOOLS=0 (default): ningún reasoning entra al historial aunque
    el proveedor lo devuelva, y el cliente se llama con la firma vieja."""
    import nodes

    monkeypatch.setenv("CHAT_STREAM", "0")
    vistos = []
    monkeypatch.setattr(nodes, "call_llm_agent",
                        lambda m, t=None, **extra: vistos.append(extra) or NS(
                            content="ok", tool_calls=None, reasoning_content="r"))
    shared = {"messages": [{"role": "user", "content": "x"}], "turno": nodes.nuevo_turno()}
    nodes.AgentStep()._run(shared)
    assert vistos == [{}] and "reasoning_content" not in shared["messages"][-1]
