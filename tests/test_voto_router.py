"""Tests puros del umbral del voto local (Mesa 3) — sin modelo ni red.

El voto local es el segundo voto del router: decide acuerdos Y desacuerdos
confiables antes del árbitro DeepSeek. La política vive en
utils.laya_routing.decide_voto (PURO) y su configuración en config_voto;
acá se clava el límite del umbral, el camino conformal (q) y la degradación
de config_voto ante settings rotos. No se toca Laya ni la red.
"""
import pytest

from utils.laya_routing import RouterConfig, config_voto, decide_voto


def test_umbral_fijo_incluye_el_limite():
    """conf >= umbral confía; un pelo abajo, no. El límite decide el lado
    confiable (justo 0.7 es confiable)."""
    config = RouterConfig(umbral=0.7)
    confiable, causa = decide_voto("herramientas", 0.7, config)
    assert confiable is True
    assert "umbral" in causa and "0.70" in causa

    confiable, causa = decide_voto("herramientas", 0.6999, config)
    assert confiable is False
    assert "umbral" in causa


def test_umbral_fijo_conf_baja_no_confiable():
    config = RouterConfig(umbral=0.9)
    assert decide_voto("directo", 0.5, config)[0] is False
    assert decide_voto("directo", 0.9, config)[0] is True


def test_conjunto_conformal_confia_solo_si_colapsa():
    """Con q calibrado, la decisión local es confiable solo si el conjunto de
    hipótesis colapsa sobre la elegida (piso = 1 - q)."""
    config = RouterConfig(umbral=0.7, q=0.60)   # piso 0.40
    assert decide_voto("herramientas", 0.70, config)[0] is True
    assert "colapsa" in decide_voto("herramientas", 0.70, config)[1]
    # por debajo del piso el conjunto queda ambiguo -> no confiable
    assert decide_voto("herramientas", 0.30, config)[0] is False
    assert "ambiguo" in decide_voto("herramientas", 0.30, config)[1]


def test_conformal_tiene_prioridad_sobre_umbral():
    """Con q presente, el umbral fijo NO se consulta: conf 0.65 < umbral 0.7
    pero >= piso conformal 0.4 -> confiable igual. El camino conformal manda."""
    config = RouterConfig(umbral=0.7, q=0.60)
    assert decide_voto("directo", 0.65, config)[0] is True


def test_decide_voto_devuelve_tupla_bool_str():
    """Contrato: (confiable, causa) con bool e incluyendo el número en la causa
    para trazabilidad del print."""
    resultado = decide_voto("directo", 0.8, RouterConfig(umbral=0.7))
    assert isinstance(resultado, tuple) and len(resultado) == 2
    assert isinstance(resultado[0], bool)
    assert isinstance(resultado[1], str)


def test_config_voto_umbral_por_setting(monkeypatch):
    """El umbral sale de LAYA_UNSURE_HIGH_VOTO."""
    from utils import call_llm

    monkeypatch.setattr(
        call_llm, "_setting",
        lambda nombre, default=None: "0.9" if nombre == "LAYA_UNSURE_HIGH_VOTO" else default,
    )
    config = config_voto()
    assert config.umbral == pytest.approx(0.9)
    assert config.modo == "enforce" and config.q is None


def test_config_voto_umbral_roto_cae_a_default(monkeypatch):
    """Un umbral no numérico no rompe: cae al 0.7 de siempre."""
    from utils import call_llm

    monkeypatch.setattr(
        call_llm, "_setting",
        lambda nombre, default=None: "no_un_numero" if nombre == "LAYA_UNSURE_HIGH_VOTO" else default,
    )
    assert config_voto().umbral == pytest.approx(0.7)


def test_config_voto_calibracion_inexistente_cae_a_umbral_fijo(monkeypatch):
    """Si LAYA_CALIBRACION_VOTO apunta a algo ilegible, q queda None y se usa
    el umbral fijo (degrada, no rompe)."""
    from utils import call_llm

    ajustes = {"LAYA_CALIBRACION_VOTO": "/ruta/que/no/existe.jsonl"}
    monkeypatch.setattr(
        call_llm, "_setting", lambda nombre, default=None: ajustes.get(nombre, default)
    )
    config = config_voto()
    assert config.q is None
    assert config.umbral == pytest.approx(0.7)
