"""Gate previo de la fase 3 (banco/specs/fase3.md): la sonda thinking_tools
sin red. Clava que usa el MISMO builder que produccion, las seis secuencias y
el veredicto (un 400 no pasa; otro error no es 400 pero deja la secuencia sin
veredicto)."""
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


class ClienteFalso:
    """Pide UNA tool la primera vez de cada secuencia; después responde.
    Con `rechazar`, contesta 400 si el request arrastra un assistant con
    tool_calls sin reasoning y thinking ON (la regla documentada)."""

    def __init__(self, rechazar=False):
        self.rechazar, self.requests = rechazar, []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        mensajes = kwargs["messages"]
        pensando = kwargs["extra_body"]["thinking"]["type"] == "enabled"
        sin_razon = any(m.get("tool_calls") and not m.get("reasoning_content") for m in mensajes)
        if self.rechazar and pensando and sin_razon:
            raise _Error400()
        ultimo = mensajes[-1]
        pide = kwargs.get("tools") and ultimo["role"] == "user" and "Respondé AHORA" not in ultimo["content"]
        calls = [NS(id=f"c{len(self.requests)}", function=NS(name="list_files", arguments="{}"))] if pide else None
        return NS(choices=[NS(message=NS(content=None if pide else "listo", tool_calls=calls,
                                         reasoning_content="razono"))])


class _Error400(Exception):
    status_code = 400


def test_las_seis_secuencias_pasan_con_una_api_que_acepta():
    sonda = tt.Sonda(ClienteFalso())
    tt.secuencias(sonda)
    pasa, resumen = tt.veredicto(sonda.pasos)
    assert pasa and set(resumen) == set("ABCDEF")
    # B: el cierre va sin tools; F: la primera ronda va con thinking OFF
    assert any(p["secuencia"] == "B" and p["paso"] == "cierre sin tools" and not p["tools"]
               for p in sonda.pasos)
    assert any(p["secuencia"] == "F" and not p["pensar"] for p in sonda.pasos)


def test_un_400_tumba_el_gate_y_se_ve_donde():
    """Con la API exigiendo el reasoning, E (la zona fría compactada sin
    reasoning) y F (historial armado con thinking OFF) dan 400: son
    exactamente las dos secuencias que el chat tiene que resolver antes de
    activar la fase 3 (la compacción y el resume de sesiones viejas)."""
    sonda = tt.Sonda(ClienteFalso(rechazar=True))
    tt.secuencias(sonda)
    pasa, resumen = tt.veredicto(sonda.pasos)
    assert not pasa
    assert resumen["E"] == resumen["F"] == "400"
    assert resumen["A"] == resumen["B"] == resumen["C"] == resumen["D"] == "ok"


@pytest.mark.parametrize(("status", "esperado"), [(429, "sin veredicto"), (None, "sin veredicto")])
def test_un_error_que_no_es_400_deja_la_secuencia_sin_veredicto(status, esperado):
    pasos = [{"secuencia": s, "ok": True, "status": 200} for s in "ABCDE"]
    pasos.append({"secuencia": "F", "ok": False, "status": status})
    pasa, resumen = tt.veredicto(pasos)
    assert not pasa and resumen["F"] == esperado
