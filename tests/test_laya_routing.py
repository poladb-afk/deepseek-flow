"""Tests de la política del router (exp/35) — puros, sin modelo ni red.

La clasificación (Laya) y la decisión (Python) están separadas justamente
para poder clavar la segunda acá: respuestas inválidas, límites del umbral,
conjunto conformal y los tres modos.
"""
import json

import pytest

from utils.laya_routing import (
    RouterConfig,
    config_router,
    decide,
    probabilidades,
    registrar_decision,
    ruta_aplicada,
)


def detalle(p_directo, eleccion="directo"):
    return {"choice": eleccion,
            "probabilities": {"directo": p_directo, "herramientas": 1.0 - p_directo}}


@pytest.mark.parametrize("respuesta", [
    None,
    {},
    {"choice": "directo"},
    {"choice": "directo", "probabilities": {}},
    {"choice": "directo", "probabilities": {"directo": 0.9}},          # falta una
    {"choice": "directo", "probabilities": {"directo": 0.9, "herramientas": 0.5}},  # no suman 1
    {"choice": "directo", "probabilities": {"directo": float("nan"), "herramientas": 0.1}},
    {"choice": "directo", "probabilities": {"directo": float("inf"), "herramientas": 0.0}},
    {"choice": "directo", "probabilities": {"directo": True, "herramientas": 0.0}},
    {"choice": "directo", "probabilities": {"directo": "0.9", "herramientas": 0.1}},
    {"choice": "directo", "probabilities": {"directo": 1.2, "herramientas": -0.2}},
])
def test_respuesta_invalida_abstiene_nunca_directo(respuesta):
    """La regla dura: sin probabilidades usables no hay ruta directa. Un fallo
    del clasificador no puede habilitar la ruta que ahorra la llamada."""
    propuesta, causa, p_directo = decide(respuesta, RouterConfig())
    assert propuesta == "herramientas"
    assert "inválida" in causa or "contrato" in causa
    assert p_directo is None or isinstance(p_directo, float)


def test_etiqueta_fuera_de_contrato_abstiene():
    respuesta = {"choice": "quizas",
                 "probabilities": {"directo": 0.9, "herramientas": 0.1}}
    propuesta, causa, _ = decide(respuesta, RouterConfig())
    assert propuesta == "herramientas"
    assert "fuera de contrato" in causa


def test_umbral_fijo_incluye_el_limite():
    """p(directo) >= umbral decide directo; un pelo abajo, no."""
    config = RouterConfig(umbral=0.85)
    assert decide(detalle(0.85), config)[0] == "directo"
    assert decide(detalle(0.8499), config)[0] == "herramientas"
    assert "umbral" in decide(detalle(0.5), config)[1]


def test_conjunto_conformal_decide_por_colapso():
    """Con q calibrado, la ruta directa exige que el conjunto de etiquetas
    plausibles colapse en directo (piso = 1 - q)."""
    config = RouterConfig(q=0.60)          # piso 0.40
    assert decide(detalle(0.70), config)[0] == "directo"
    assert decide(detalle(0.55), config)[0] == "herramientas"   # ambas >= 0.40
    assert decide(detalle(0.30), config)[0] == "herramientas"   # conjunto vacío


def test_modos_off_shadow_enforce():
    """off no ejecuta Laya; shadow registra pero conserva herramientas;
    enforce aplica la propuesta."""
    respuesta = detalle(0.99)
    assert decide(respuesta, RouterConfig(modo="off"))[0] == "herramientas"
    assert decide(respuesta, RouterConfig(modo="shadow"))[0] == "directo"
    assert ruta_aplicada("directo", RouterConfig(modo="shadow")) == "herramientas"
    assert ruta_aplicada("directo", RouterConfig(modo="enforce")) == "directo"
    assert ruta_aplicada("herramientas", RouterConfig(modo="enforce")) == "herramientas"


def test_probabilidades_rechaza_bool_y_texto():
    assert probabilidades({"probabilities": {"directo": True, "herramientas": 0}}) is None
    assert probabilidades({"probabilities": {"directo": "0.9", "herramientas": 0.1}}) is None
    assert probabilidades(detalle(0.9)) == (0.9, pytest.approx(0.1))


def test_config_router_modo_desconocido_cae_a_enforce(monkeypatch):
    from utils import call_llm

    monkeypatch.setattr(call_llm, "_setting",
                        lambda nombre, default=None: "vaya_uno_a_saber" if nombre == "LAYA_MODO" else default)
    assert config_router().modo == "enforce"


def test_registrar_decision_escribe_y_no_rompe(tmp_path, monkeypatch):
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    monkeypatch.setattr(call_llm, "_setting", lambda nombre, default=None: default)
    registrar_decision({"modo": "shadow", "propuesta": "directo"}, ruta=archivo)
    linea = json.loads(archivo.read_text(encoding="utf-8").strip())
    assert linea["propuesta"] == "directo" and linea["modo"] == "shadow"
    assert "ts" in linea

    # apagado por setting: no escribe
    monkeypatch.setattr(call_llm, "_setting",
                        lambda nombre, default=None: "0" if nombre == "LAYA_LOG_DECISIONES" else default)
    registrar_decision({"modo": "off"}, ruta=archivo)
    assert len(archivo.read_text(encoding="utf-8").strip().splitlines()) == 1

    # destino imposible (un directorio): se traga, no rompe el chat
    monkeypatch.setattr(call_llm, "_setting", lambda nombre, default=None: default)
    registrar_decision({"modo": "off"}, ruta=tmp_path)


def test_registrar_decision_no_guarda_texto_por_default(tmp_path, monkeypatch):
    """Privacidad: sin LAYA_LOG_PREGUNTA=1 el evento no lleva la pregunta."""
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    monkeypatch.setattr(call_llm, "_setting", lambda nombre, default=None: default)
    registrar_decision(
        {"modo": "shadow"}, pregunta="¿quién ganó el último mundial?", ruta=archivo
    )
    assert "pregunta" not in json.loads(archivo.read_text(encoding="utf-8").strip())


def test_registrar_decision_con_pregunta_opt_in(tmp_path, monkeypatch):
    """Con LAYA_LOG_PREGUNTA=1 el evento lleva la pregunta normalizada y
    recortada a 200: es lo que une el registro con el etiquetador."""
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    monkeypatch.setattr(
        call_llm, "_setting",
        lambda nombre, default=None: "1" if nombre == "LAYA_LOG_PREGUNTA" else default,
    )
    registrar_decision({"modo": "shadow"}, pregunta="  hola\n  mundo  ", ruta=archivo)
    assert json.loads(archivo.read_text(encoding="utf-8").strip())["pregunta"] == "hola mundo"

    registrar_decision({"modo": "shadow"}, pregunta="x" * 500, ruta=archivo)
    ultima = json.loads(archivo.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert len(ultima["pregunta"]) == 200


def test_el_nodo_pasa_la_pregunta_al_registro(tmp_path, monkeypatch):
    """exp/35: en modo sombra, con la pregunta habilitada, el evento sale del
    nodo completo (pregunta + propuesta + confianza + ruta aplicada): el set
    que después etiqueta banco/probes/etiquetar_router.py."""
    import nodes
    from utils import call_llm, laya

    archivo = tmp_path / "routing.jsonl"
    ajustes = {
        "LAYA_MODO": "shadow",
        "LAYA_LOG_ARCHIVO": str(archivo),
        "LAYA_LOG_PREGUNTA": "1",
    }
    monkeypatch.setattr(
        call_llm, "_setting", lambda nombre, default=None: ajustes.get(nombre, default)
    )
    monkeypatch.setattr(laya, "disponible", lambda *a, **k: True)
    router = nodes.LayaRouter()
    respuesta = {
        "choice": "directo",
        "probabilities": {"directo": 0.99, "herramientas": 0.01},
    }
    assert router.post({}, {"pregunta": "leé el archivo X"}, respuesta) == "herramientas"
    linea = json.loads(archivo.read_text(encoding="utf-8").strip())
    assert linea["pregunta"] == "leé el archivo X"
    assert linea["propuesta"] == "directo" and linea["aplicada"] == "herramientas"
    assert linea["p_directo"] == 0.99 and linea["modo"] == "shadow"
