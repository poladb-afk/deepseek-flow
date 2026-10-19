"""mcp-laya: el juicio tipado y calibrado de Laya como tool MCP (Mesa 6).

Sin checkpoint real: se parchea `utils.laya.preguntar_detalle` (el borde con la
dependencia) y se verifica el contrato completo — qué pregunta se arma, cómo se
valida el vector de probabilidades y qué texto JSON recibe el cliente MCP.
"""
import json

import pytest
from conftest import RAIZ  # noqa: F401  (raíz en sys.path)

from utils import laya


def _detalle(choice="si", confianza=0.9, probabilidades=None):
    respuesta = {"choice": choice}
    if confianza is not None:
        respuesta["answer_confidence"] = confianza
    if probabilidades is not None:
        respuesta["probabilities"] = probabilidades
    return {"juicio": respuesta}


def _preguntar_con(monkeypatch, detalle_):
    visto = {}

    def preguntar_detalle(estado, preguntas, setting="LAYA_MODEL"):
        visto["estado"], visto["preguntas"], visto["setting"] = estado, preguntas, setting
        return detalle_

    monkeypatch.setattr(laya, "preguntar_detalle", preguntar_detalle)
    return visto


def test_juicio_arma_el_contrato_y_devuelve_calibracion(monkeypatch):
    visto = _preguntar_con(monkeypatch, _detalle(probabilidades={"si": 0.9, "no": 0.1}))

    r = laya.juicio({"bloque": "x"}, "¿es relevante?", {"si": "aporta", "no": "no aporta"})

    assert visto["preguntas"] == {
        "juicio": {"type": "choice", "instructions": "¿es relevante?",
                   "criteria": {"si": "aporta", "no": "no aporta"}}}
    assert visto["setting"] == "LAYA_MODEL"
    assert r == {"juicio": "si", "confianza": 0.9,
                 "probabilidades": {"si": 0.9, "no": 0.1}}


def test_juicio_con_probabilidades_invalidas_las_pierde_pero_juzga(monkeypatch):
    """Un vector que no suma 1 no se inventa: probabilidades None, pero la
    etiqueta elegida y su confianza sobreviven."""
    _preguntar_con(monkeypatch, _detalle(probabilidades={"si": 0.7, "no": 0.7}))
    r = laya.juicio("e", "i", {"si": "a", "no": "b"})
    assert r["juicio"] == "si"
    assert r["confianza"] == 0.9
    assert r["probabilidades"] is None


def test_juicio_fuera_de_contrato_degrada_a_none(monkeypatch):
    """Etiqueta que no está en opciones: respuesta no usable, no excepción."""
    _preguntar_con(monkeypatch, _detalle(choice="quizas"))
    assert laya.juicio("e", "i", {"si": "a", "no": "b"}) is None


def test_juicio_sin_checkpoint_degrada_a_none(monkeypatch):
    def preguntar_detalle(estado, preguntas, setting="LAYA_MODEL"):
        raise RuntimeError("laya no disponible")

    monkeypatch.setattr(laya, "preguntar_detalle", preguntar_detalle)
    assert laya.juicio("e", "i", {"si": "a", "no": "b"}) is None


@pytest.mark.parametrize("opciones", [{"si": "única"}, "si,no", ["si", "no"]])
def test_juicio_exige_dos_opciones_tipadas(opciones):
    """`opciones` es contrato, no prosa: dict {etiqueta: criterio} con >= 2."""
    with pytest.raises(ValueError, match="opciones"):
        laya.juicio("e", "i", opciones)


def test_tool_mcp_devuelve_json_con_el_modelo(monkeypatch):
    """El borde MCP: texto JSON (nunca un dict) con la procedencia del
    checkpoint, para que el cliente sepa QUÉ modelo juzgó."""
    import mcp_server

    monkeypatch.setattr(mcp_server, "juicio", lambda *a, **k: {
        "juicio": "si", "confianza": 0.8, "probabilidades": {"si": 0.8, "no": 0.2}})
    monkeypatch.setattr(mcp_server, "_setting", lambda nombre, default=None: "laya-falso")

    salida = json.loads(mcp_server.juicio_laya("estado", "¿sí o no?", {"si": "a", "no": "b"}))

    assert salida == {"juicio": "si", "confianza": 0.8,
                      "probabilidades": {"si": 0.8, "no": 0.2},
                      "modelo": "laya-falso"}


def test_tool_mcp_sin_laya_avisa_por_texto(monkeypatch):
    """Sin checkpoint la tool no rompe al cliente: ERROR como texto (mismo
    contrato que el resto de las tools del harness)."""
    import mcp_server

    monkeypatch.setattr(mcp_server, "juicio", lambda *a, **k: None)
    salida = mcp_server.juicio_laya("estado", "¿sí o no?", {"si": "a", "no": "b"})
    assert salida.startswith("ERROR:") and "Laya" in salida


def test_envolver_despacha_juicio_laya_por_run_tool_call(monkeypatch):
    """La tool se registra con la MISMA envoltura que el resto del action
    space: el cliente MCP la llama por nombre y el despacho pasa por
    run_tool_call (hooks incluidos)."""
    import mcp_server

    monkeypatch.setattr(mcp_server, "juicio", lambda *a, **k: {
        "juicio": "no", "confianza": 0.6, "probabilidades": None})
    monkeypatch.setattr(mcp_server, "_setting", lambda nombre, default=None: "falso")
    impls = {"juicio_laya": mcp_server.juicio_laya}
    salida = mcp_server.envolver("juicio_laya", mcp_server.juicio_laya, impls)(
        estado="x", instrucciones="y", opciones={"si": "a", "no": "b"})
    assert json.loads(salida)["juicio"] == "no"


def test_mcp_expone_el_juicio_por_default_y_sin_aviso():
    """mcp-laya es producto out-of-the-box: entra en el allowlist default y
    tiene descripción propia (si no, elegir_exposicion avisaría)."""
    from mcp_server import DEFAULT_EXPOSE, DESCRIPCION_JUICIO, elegir_exposicion, juicio_laya

    expuestas, aviso = elegir_exposicion(
        {"juicio_laya"}, {"juicio_laya": juicio_laya}, {"juicio_laya": DESCRIPCION_JUICIO})
    assert expuestas == ["juicio_laya"] and aviso is None
    assert "juicio_laya" in DEFAULT_EXPOSE.split(",")
    assert "calibrado" in DESCRIPCION_JUICIO
