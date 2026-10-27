"""X90: el producto completo del router, capa por capa, sin Laya ni red."""
import sys

from conftest import RAIZ

sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import producto_router as pr  # noqa: E402


def _sin_skill(_p):
    return ""


def test_la_ventana_existe_y_contiene_k13_y_k15():
    """Calculada sin Laya: los dos falsos directos del voto que ninguna regla
    cubre están en la ventana (si no, la medición no ejercitaría nada)."""
    ventana = {c["id"] for c in pr.casos() if pr.en_ventana(c)}
    assert {"k13", "k15"} <= ventana
    assert not {"c02", "k21", "k22", "f04"} & ventana  # los cubre la regla temporal


def test_cada_capa_decide_solo_donde_le_toca():
    llamadas = []

    def router(p):
        llamadas.append(("router", p))
        return "directo"

    def voto(p):
        llamadas.append(("voto", p))
        return "directo", False

    regla = {"id": "x1", "grupo": "correccion", "esperado": "herramientas",
             "pregunta": "¿quién ganó el último mundial?"}
    fila = pr.medir_caso(regla, router, voto, skill=_sin_skill)
    assert fila["capa"] == "regla:temporal" and fila["final"] == "herramientas" and llamadas == []
    abierto = {"id": "k13", "grupo": "correccion", "esperado": "herramientas",
               "pregunta": "discutí en dos vueltas si vale la pena reescribir el router"}
    fila = pr.medir_caso(abierto, router, voto, skill=_sin_skill)
    assert fila["ventana"] and fila["capa"] == "voto" and fila["final"] == "directo"
    assert [capa for capa, _p in llamadas] == ["router", "voto"]
    fila = pr.medir_caso(abierto, lambda _p: "herramientas", voto, skill=_sin_skill)
    assert fila["capa"] == "router" and fila["voto"] is None and fila["final"] == "herramientas"


def test_el_veredicto_nombra_los_falsos_directos_y_la_ventana_vacia_no_da_veredicto():
    caso = {"id": "k13", "grupo": "correccion", "esperado": "herramientas", "pregunta": "discutí en dos vueltas"}
    fila = pr.medir_caso(caso, lambda _p: "directo", lambda _p: ("directo", False), skill=_sin_skill)
    v = pr.veredicto([fila])
    assert v["falsos_directos"] == ["k13"] and "hallazgo abierto" in v["decision"]
    frenado = pr.medir_caso(caso, lambda _p: "directo", lambda _p: ("herramientas", True), skill=_sin_skill)
    assert "no hay agujero" in pr.veredicto([frenado])["decision"]
    assert pr.veredicto([])["completo"] is False
    assert "k13 ⚠" in pr.resumen([fila])
