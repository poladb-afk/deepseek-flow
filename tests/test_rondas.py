"""exp/52-A — la forma del loop del chat (sonda offline de rondas).

Clavan el agrupamiento por pregunta (GetQuestion → answer), el counterfactual
de topes y las estadísticas que sostienen el pre-registro de exp/52-B.
"""
import sys

from conftest import RAIZ

sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import rondas  # noqa: E402


def _ev(nodo, accion="None", seg=0.0):
    return {"nodo": nodo, "accion": accion, "seg": seg, "ts": 0.0}


def test_es_sesion_chat_por_getquestion():
    assert rondas.es_sesion_chat([_ev("GetQuestion", "continue")])
    assert not rondas.es_sesion_chat([_ev("CarpetaScan"), _ev("AnalizeFile")])


def test_ciclos_agrupa_rondas_por_pregunta():
    eventos = [
        _ev("GetQuestion", "continue"),
        _ev("AgentStep", "tool", 1.0), _ev("ExecuteTools", "default", 2.0),
        _ev("AgentStep", "tool", 1.0), _ev("ExecuteTools", "default", 0.5),
        _ev("AgentStep", "answer", 3.0),
        _ev("GetQuestion", "continue"),
        _ev("AgentStep", "answer", 1.0),
        _ev("GetQuestion", "exit"),
    ]
    ciclos = rondas.ciclos(eventos)
    assert len(ciclos) == 2
    assert ciclos[0]["rondas"] == 2 and ciclos[0]["respondio"] is True
    assert ciclos[0]["seg_agente"] == 7.5
    assert ciclos[1]["rondas"] == 0 and ciclos[1]["respondio"] is True


def test_ciclos_registran_pregunta_sin_answer():
    eventos = [_ev("GetQuestion", "continue"), _ev("AgentStep", "tool", 2.0)]
    ciclos = rondas.ciclos(eventos)
    assert len(ciclos) == 1 and ciclos[0]["respondio"] is False
    assert rondas.resumen(ciclos)["sin_responder"] == 1


def test_simular_cap_solo_toca_la_cola():
    ciclos = [{"rondas": r, "respondio": True, "seg_agente": 1.0, "eventos": 1}
              for r in (1, 2, 5, 8)]
    sim = rondas.simular_cap(ciclos, 3)
    assert sim["rondas_recortadas"] == 7      # (5-3) + (8-3)
    assert sim["ciclos_afectados"] == 2
    assert sim["toca_cortos"] == 0


def test_resumen_cuenta_la_cola():
    ciclos = [{"rondas": r, "respondio": True, "seg_agente": 1.0, "eventos": 1}
              for r in (0, 2, 5, 6)]
    r = rondas.resumen(ciclos)
    assert r["ciclos"] == 4 and r["directos"] == 1
    assert r["ciclos_cola"] == 2 and r["rondas_cola"] == 11
    assert r["rondas_totales"] == 13
    assert r["seg_cola"] == 2.0
