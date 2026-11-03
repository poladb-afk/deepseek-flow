"""El veredicto del exp/108 se prueba con filas sintéticas, sin LLM y sin
gastar tokens (mismo método que s6): si el criterio no puede fallar con el
mecanismo andando, no protege nada."""
import sys

from conftest import RAIZ

sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import exp108  # noqa: E402


def _fila(**extras):
    fila = {"informe_ok": True, "busquedas": 3, "urls_inventadas": [],
            "usd": 0.10, "tema": "t", "seed": 1, "urls_vistas": 8, "urls_informe": 5}
    fila.update(extras)
    return fila


def _pares(n=6):
    return [_fila() for _ in range(n)]


def test_pasa_con_todo_verde_y_panel_ganado():
    base, agente = _pares(), _pares()
    pasa, detalle = exp108.criterios(base, agente, preferencias=["g", "e", "p", "g", "p", "p"])
    assert pasa, detalle
    assert detalle["5_panel_ciego"] == (True, "3/6 gana o empata")


def test_una_url_inventada_no_pasa():
    agente = _pares()
    agente[2]["urls_inventadas"] = ["https://inventada.x"]
    pasa, detalle = exp108.criterios(_pares(), agente, ["g"] * 6)
    assert not pasa and not detalle["2_urls_honestas"][0]


def test_el_costo_mayor_no_pasa_y_sin_tarifa_no_se_imputa():
    caras = [_fila(usd=0.20) for _ in range(6)]
    pasa, detalle = exp108.criterios(_pares(), caras, ["g"] * 6)
    assert not pasa and not detalle["3_costo"][0]

    sin_tarifa = [_fila(usd=None) for _ in range(6)]
    pasa, detalle = exp108.criterios(_pares(), sin_tarifa, ["g"] * 6)
    assert not detalle["3_costo"][0]
    assert "sin evaluar" in detalle["3_costo"][1]


def test_el_tope_de_busquedas_es_del_codigo():
    agente = _pares()
    agente[0]["busquedas"] = exp108.TOPE_BUSQUEDAS + 1
    pasa, detalle = exp108.criterios(_pares(), agente, ["g"] * 6)
    assert not pasa and not detalle["4_tope_del_codigo"][0]


def test_un_informe_faltante_no_pasa():
    agente = _pares()
    agente[4]["informe_ok"] = False
    pasa, detalle = exp108.criterios(_pares(), agente, ["g"] * 6)
    assert not pasa and not detalle["1_informe_siempre"][0]


def test_sin_panel_ciego_el_veredicto_queda_pendiente():
    pasa, detalle = exp108.criterios(_pares(), _pares())
    assert not pasa
    assert "pendiente" in detalle["5_panel_ciego"][1]


def test_la_estructura_de_este_arbol_da_limpia():
    """Criterios 6 y 7 sobre el árbol local (la rama del brazo agente): los
    nombres del flujo viejo no existen y la tool deep_research sigue."""
    viejos, interfaz = exp108.estructura()
    assert viejos == []
    assert interfaz
