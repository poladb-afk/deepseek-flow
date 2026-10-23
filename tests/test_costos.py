"""exp/90 — el costo en dinero: tabla de precios, desglose por modelo, el
delta que cierra cada pregunta y el reporte de salida. Sin red: los
acumuladores se falsifican, la tabla es un dato."""

import pytest

import main
import utils.costos as costos
from utils.costos import PRECIOS_MILLON


def _fila(llamadas=1, prompt=0, completion=0, hit=0, miss=0):
    return {"llamadas": llamadas, "prompt": prompt, "completion": completion,
            "cache_hit": hit, "cache_miss": miss}


def test_precios_sin_override_devuelve_copia_de_la_tabla():
    tabla = costos.precios()
    assert tabla == PRECIOS_MILLON
    tabla["intruso"] = (1, 2, 3)
    assert "intruso" not in PRECIOS_MILLON


def test_precios_con_override_pisa_y_agrega():
    tabla = costos.precios('{"deepseek-flash": [1, 2, 3], "otro": [0, 0, 0]}')
    assert tabla["deepseek-flash"] == (1.0, 2.0, 3.0)
    assert tabla["otro"] == (0.0, 0.0, 0.0)
    assert "deepseek-v4-pro" in tabla


@pytest.mark.parametrize("crudo", [
    "esto no es json",
    '{"deepseek-flash": [0.1, 0.2]}',  # JSON válido, forma equivocada
], ids=["basura", "forma-equivocada"])
def test_precios_invalidos_cae_a_defaults_con_aviso(crudo, capsys):
    tabla = costos.precios(crudo)
    assert tabla == PRECIOS_MILLON
    assert "PRECIO_TOKENS" in capsys.readouterr().out


def test_costo_desglose_calcula_con_el_split_de_cache():
    desglose = {"deepseek-flash": _fila(prompt=1_000_000, completion=1_000_000,
                                        hit=600_000, miss=400_000)}
    total, sin_tarifa = costos.costo_desglose(desglose)
    assert sin_tarifa == []
    # 600k a 0,003 + 400k a 0,15 + 1M a 0,60 — todo por 1M de tokens
    esperado = 0.6 * 0.003 + 0.4 * 0.15 + 1.0 * 0.60
    assert abs(total - esperado) < 1e-9


def test_costo_desglose_modelo_sin_tarifa_no_suma_y_se_dice():
    desglose = {"modelo-ajeno": _fila(prompt=100, completion=100)}
    total, sin_tarifa = costos.costo_desglose(desglose)
    assert total == 0.0
    assert sin_tarifa == ["modelo-ajeno"]


def test_delta_desglose_es_la_resta_por_modelo():
    inicio = {"m": _fila(llamadas=2, prompt=100, completion=50, hit=10, miss=90)}
    actual = {"m": _fila(llamadas=5, prompt=400, completion=90, hit=100, miss=300)}
    delta = costos.delta_desglose(inicio, actual)
    assert delta["m"] == {"llamadas": 3, "prompt": 300, "completion": 40,
                          "cache_hit": 90, "cache_miss": 210}


def test_delta_desglose_modelo_nuevo_y_clamp_de_resume():
    # un modelo que aparece recién en el actual: todo su uso es del delta
    delta = costos.delta_desglose({}, {"nuevo": _fila(prompt=10, miss=10)})
    assert delta["nuevo"]["prompt"] == 10
    # resume: el snapshot rehidratado (del proceso anterior) puede ser más
    # grande que el acumulador nuevo → 0, nunca un costo negativo
    inicio = {"m": _fila(prompt=500)}
    delta = costos.delta_desglose(inicio, {"m": _fila(prompt=100)})
    assert delta["m"]["prompt"] == 0


def test_reporte_tokens_imprime_dinero_y_por_pregunta(monkeypatch, capsys):
    import utils.call_llm as c

    monkeypatch.delenv("PRECIO_TOKENS", raising=False)
    monkeypatch.setattr(c, "USO", {"llamadas": 2, "prompt": 5_000, "completion": 300})
    monkeypatch.setattr(c, "USO_POR_MODELO", {
        "deepseek-flash": _fila(llamadas=2, prompt=5_000, completion=300,
                                miss=5_000)})
    shared = {"tokens_por_pregunta": [
        {"deepseek-flash": _fila(prompt=4_000, completion=200, miss=4_000)},
        {"deepseek-flash": _fila(prompt=1_000, completion=100, miss=1_000)},
    ]}
    main._reporte_tokens(shared)
    out = capsys.readouterr().out
    assert "[tokens] sesión: 2 llamadas — 5.000 prompt + 300 completion" in out
    # 5.000 miss × 0,15/1M + 300 × 0,60/1M = 0,00093 → ~$0,0009
    assert "(~$0,0009)" in out
    # por pregunta: tokens prompt+completion (4.000+200 y 1.000+100)
    assert ("[tokens] por pregunta: 4.200 (~$0,0007) / 1.100 (~$0,0002)"
            in out)


def test_reporte_tokens_modelo_sin_tarifa_lo_dice_sin_inventar(monkeypatch, capsys):
    import utils.call_llm as c

    monkeypatch.delenv("PRECIO_TOKENS", raising=False)
    monkeypatch.setattr(c, "USO", {"llamadas": 1, "prompt": 10, "completion": 5})
    monkeypatch.setattr(c, "USO_POR_MODELO", {"modelo-ajeno": _fila(prompt=10, miss=10)})
    main._reporte_tokens({})
    out = capsys.readouterr().out
    assert "sin tarifa: modelo-ajeno" in out
    assert "~$" not in out


def test_reporte_tokens_sin_llamadas_no_imprime_nada(monkeypatch, capsys):
    import utils.call_llm as c

    monkeypatch.setattr(c, "USO", {"llamadas": 0, "prompt": 0, "completion": 0})
    main._reporte_tokens({})
    assert capsys.readouterr().out == ""
