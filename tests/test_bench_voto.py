"""exp/53 — bench del voto: dataset permanente y métricas de la cascada.

El dataset (banco/voto_casos.jsonl) es la parte permanente: casos donde el
voto corrigió a Laya, controles directos y herramientas claras. Los tests
clavan el esquema, la cascada (voto local confiable vs árbitro) y el resumen
seguridad/ahorro — sin Laya ni red (callables inyectables).
"""
import sys

import pytest
from conftest import RAIZ

sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import bench_voto as bench  # noqa: E402


def test_dataset_carga_y_esta_balanceado():
    casos = bench.cargar_casos()
    assert len(casos) >= 18
    assert {c["grupo"] for c in casos} == set(bench.GRUPOS)
    correcciones = {c["id"] for c in casos if c["grupo"] == "correccion"}
    assert {"c01", "c02", "c03", "c08"} <= correcciones  # los falso-directo medidos
    assert {c["id"] for c in casos if c["grupo"] == "directo"} >= {"d01"}  # trampa inversa
    assert next(c for c in casos if c["id"] == "c02")["cubierto_por"]  # c02 lo cubre regla_temporal


def test_dataset_rechaza_jsonl_invalido(tmp_path):
    ruta = tmp_path / "casos.jsonl"
    ruta.write_text('{"id": "x", "grupo": "correccion", "esperado": "herramientas"}\n',
                    encoding="utf-8")
    with pytest.raises(ValueError, match="falta pregunta"):
        bench.cargar_casos(ruta)
    ruta.write_text('{"id": "x", "grupo": "otro", "esperado": "herramientas", "pregunta": "p"}\n',
                    encoding="utf-8")
    with pytest.raises(ValueError, match="grupo inválido"):
        bench.cargar_casos(ruta)
    ruta.write_text('{"id": "x", "grupo": "directo", "esperado": "directo", "pregunta": "p"}\n'
                    '{"id": "x", "grupo": "directo", "esperado": "directo", "pregunta": "q"}\n',
                    encoding="utf-8")
    with pytest.raises(ValueError, match="ids repetidos"):
        bench.cargar_casos(ruta)


def test_medir_usa_voto_local_si_es_confiable_y_arbitra_si_duda():
    casos = [
        {"id": "c01", "grupo": "correccion", "esperado": "herramientas", "pregunta": "debatí"},
        {"id": "d01", "grupo": "directo", "esperado": "directo", "pregunta": "haiku"},
    ]
    llamadas_arbitro = []

    def voto_local(pregunta):
        if pregunta == "debatí":
            return ("herramientas", 0.9, True, "conf 0.90 >= umbral")
        return ("directo", 0.55, False, "conf 0.55 < umbral")

    def arbitro(pregunta):
        llamadas_arbitro.append(pregunta)
        return "directo"

    filas = bench.medir(casos, voto_local, arbitro)
    assert filas[0]["origen_decision"] == "voto" and filas[0]["acierto"]
    assert filas[1]["origen_decision"] == "arbitro" and llamadas_arbitro == ["haiku"]
    assert filas[1]["acierto"] and filas[1]["local"] == "directo"


def test_medir_sin_voto_local_arbitra_todo():
    casos = [{"id": "h01", "grupo": "herramientas", "esperado": "herramientas",
              "pregunta": "leé README"}]
    filas = bench.medir(casos, lambda _p: None, lambda _p: "herramientas")
    assert filas[0]["origen_decision"] == "arbitro" and filas[0]["acierto"]


def test_resumen_cuenta_falsos_directos_y_ahorro():
    filas = [
        {"id": "c01", "grupo": "correccion", "esperado": "herramientas",
         "final": "herramientas", "origen_decision": "voto", "acierto": True,
         "falso_directo": False, "cubierto_por": "", "seg": 0.2},
        {"id": "c02", "grupo": "correccion", "esperado": "herramientas",
         "final": "directo", "origen_decision": "arbitro", "acierto": False,
         "falso_directo": True, "cubierto_por": "regla_temporal", "seg": 0.4},
        {"id": "c03", "grupo": "correccion", "esperado": "herramientas",
         "final": "directo", "origen_decision": "voto", "acierto": False,
         "falso_directo": True, "cubierto_por": "", "seg": 0.2},
        {"id": "d01", "grupo": "directo", "esperado": "directo", "final": "directo",
         "origen_decision": "voto", "acierto": True, "falso_directo": False,
         "cubierto_por": "", "seg": 0.2},
    ]
    resumen = bench.resumen(filas)
    assert resumen["casos"] == 4 and resumen["aciertos"] == 2
    assert resumen["por_grupo"]["correccion"] == {"aciertos": 1, "casos": 3}
    assert resumen["cobertura_local"] == 3 and resumen["arbitro"] == 1
    assert resumen["falsos_directos"] == ["c02", "c03"]
    assert resumen["falsos_directos_producto"] == ["c03"]
    assert resumen["cubiertos_por_regla"] == ["c02"]
    assert resumen["errores"] == [
        {"id": "c02", "esperado": "herramientas", "final": "directo"},
        {"id": "c03", "esperado": "herramientas", "final": "directo"},
    ]
    assert resumen["seg_mediana"] == pytest.approx(0.2)


def test_calibrar_voto_salta_yaml_que_pyyaml_no_parsea():
    """Los escenarios viejos con formato propio no rompen el etiquetado."""
    import calibrar_voto

    preguntas = calibrar_voto.preguntas_de_escenarios()
    assert preguntas and all(isinstance(p, str) for p in preguntas)
