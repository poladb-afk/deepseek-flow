"""Gate previo de la fase 3 (banco/specs/fase3.md): la sonda thinking_tools
sin red. Clava que el OFF es el builder de producción, las ocho secuencias y
el veredicto redefinido (A–E y G deciden; F y H informan)."""
from types import SimpleNamespace as NS

import pytest

from banco.probes import thinking_tools as tt
from utils.call_llm import _kwargs_agente


def test_la_sonda_arma_el_on_y_el_off_es_el_de_produccion():
    """La fase 3 se rechazó (A/B): el producto no ofrece thinking con tools.
    La sonda arma ese request ella misma; el OFF es el builder del chat."""
    mensajes = [{"role": "user", "content": "x"},
                {"role": "assistant", "content": None, "reasoning_content": "pienso",
                 "tool_calls": [{"id": "1", "type": "function",
                                 "function": {"name": "list_files", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "1", "content": "a.py"}]
    con = tt.pedido(mensajes, [{"function": {"name": "list_files"}}])
    assert con["extra_body"] == {"thinking": {"type": "enabled"}}
    assert con["messages"][1]["reasoning_content"] == "pienso"
    # el camino del producto: thinking OFF y el reasoning no viaja
    hoy = _kwargs_agente(mensajes, [{"function": {"name": "list_files"}}])
    assert tt.pedido(mensajes, [{"function": {"name": "list_files"}}], pensar=False) == hoy
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
        pide = kwargs.get("tools") and ultimo["role"] == "user" and "Respondé AHORA" not in ultimo["content"]
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

