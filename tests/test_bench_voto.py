"""exp/53 — bench del voto: dataset permanente y métricas de la cascada.

El dataset (banco/voto_casos.jsonl) es la parte permanente: casos donde el
voto corrigió a Laya, controles directos y herramientas claras. Los tests
clavan el esquema, las DOS capas (voto local + árbitro; y producto con las
reglas duras del router) y el resumen seguridad/ahorro — sin Laya ni red
(callables inyectables).
"""
import sys

import pytest
from conftest import RAIZ

sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import bench_voto as bench  # noqa: E402


def _fila(**extra):
    """Fila mínima del bench para probar `resumen` sin correr la cascada."""
    base = {"local": "directo", "conf": 0.9, "confiable": True, "causa": "fake",
            "cubierto_por": "", "seg": 0.2}
    base.update(extra)
    return base


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

    filas = bench.medir(casos, voto_local, arbitro, regla=None)
    assert filas[0]["origen_decision"] == "voto" and filas[0]["acierto"]
    assert filas[1]["origen_decision"] == "arbitro" and llamadas_arbitro == ["haiku"]
    assert filas[1]["acierto"] and filas[1]["local"] == "directo"


def test_medir_regla_corrige_un_falso_directo_del_voto():
    """c01: el voto local confía y dice directo (el hueco de exp/53); la regla
    dura de capacidad lo manda a herramientas en la capa producto."""
    casos = [{"id": "c01", "grupo": "correccion", "esperado": "herramientas",
              "pregunta": "debatí en 2 rondas"}]

    filas = bench.medir(
        casos,
        lambda _p: ("directo", 0.94, True, "conf 0.94 >= umbral"),
        lambda _p: "herramientas",
        regla=lambda _p: "regla:imperativo",
    )
    fila = filas[0]
    assert fila["final"] == "herramientas" and fila["acierto"]
    assert fila["regla"] == "regla:imperativo"
    assert fila["final_voto"] == "directo" and not fila["acierto_voto"]
    assert fila["falso_directo"] is False and fila["falso_directo_voto"] is True
    assert fila["cubierto_por_regla"] is True


def test_medir_sin_voto_local_arbitra_todo():
    casos = [{"id": "h01", "grupo": "herramientas", "esperado": "herramientas",
              "pregunta": "leé README"}]
    filas = bench.medir(casos, lambda _p: None, lambda _p: "herramientas", regla=None)
    assert filas[0]["origen_decision"] == "arbitro" and filas[0]["acierto"]


def test_resumen_separa_capas_y_cubre_por_regla():
    filas = [
        _fila(id="c01", grupo="correccion", esperado="herramientas",
              final="herramientas", origen_decision="regla:imperativo",
              final_voto="directo", origen_voto="voto",
              acierto=True, acierto_voto=False,
              falso_directo=False, falso_directo_voto=True,
              regla="regla:imperativo", cubierto_por_regla=True),
        _fila(id="c02", grupo="correccion", esperado="herramientas",
              final="directo", origen_decision="voto",
              final_voto="directo", origen_voto="voto",
              acierto=False, acierto_voto=False,
              falso_directo=True, falso_directo_voto=True,
              regla="", cubierto_por_regla=False),
        _fila(id="d01", grupo="directo", esperado="directo",
              final="directo", origen_decision="voto",
              final_voto="directo", origen_voto="voto",
              acierto=True, acierto_voto=True,
              falso_directo=False, falso_directo_voto=False,
              regla="", cubierto_por_regla=False),
    ]
    resumen = bench.resumen(filas)
    assert resumen["casos"] == 3 and resumen["aciertos"] == 2
    assert resumen["por_grupo"]["correccion"] == {"aciertos": 1, "casos": 2}
    assert resumen["aciertos_voto"] == 1
    assert resumen["falsos_directos"] == ["c02"]
    assert resumen["falsos_directos_voto"] == ["c01", "c02"]
    assert resumen["cubiertos_por_regla"] == ["c01"]
    assert resumen["reglas_disparadas"] == 1
    assert resumen["cobertura_local"] == 3 and resumen["arbitro"] == 0
    assert resumen["errores"] == [{"id": "c02", "esperado": "herramientas", "final": "directo"}]
    assert resumen["seg_mediana"] == pytest.approx(0.2)


def test_calibrar_voto_salta_yaml_que_pyyaml_no_parsea():
    """Los escenarios viejos con formato propio no rompen el etiquetado."""
    import calibrar_voto

    preguntas = calibrar_voto.preguntas_de_escenarios()
    assert preguntas and all(isinstance(p, str) for p in preguntas)


def _bench_h3g2(local):
    casos = [{"id": "c01", "grupo": "correccion", "esperado": "herramientas", "pregunta": "debatí"}]
    casos += [{"id": f"d0{i}", "grupo": "directo", "esperado": "directo", "pregunta": f"haiku {i}"}
              for i in range(1, 7)]
    return bench.medir(casos, local, lambda _p: "herramientas", regla=None)


def test_h3g2_un_falso_directo_del_voto_y_las_reglas_se_quedan():
    """H3-G2: c01 con el voto confiando en directo (lo medido el 2026-10-26)."""
    filas = _bench_h3g2(lambda _p: ("directo", 0.94, True, "conf 0.94"))
    v = bench.veredicto_h3g2(filas, voto_local_disponible=True)
    assert v["condiciones"]["seguridad"] is False and v["gana"] is False
    assert v["falsos_directos_voto"] == ["c01"] and "se quedan" in v["decision"]


def test_h3g2_el_voto_no_gana_diciendo_siempre_herramientas():
    filas = _bench_h3g2(lambda _p: ("herramientas", 0.99, True, "conf 0.99"))
    v = bench.veredicto_h3g2(filas, voto_local_disponible=True)
    assert v["condiciones"]["seguridad"] is True and v["condiciones"]["ahorro"] is False
    assert v["gana"] is False


def test_h3g2_gana_solo_con_el_checkpoint_real():
    def voto(p):
        return ("herramientas" if p == "debatí" else "directo", 0.95, True, "conf 0.95")

    filas = _bench_h3g2(voto)
    assert bench.veredicto_h3g2(filas, voto_local_disponible=True)["gana"] is True
    sin_checkpoint = bench.veredicto_h3g2(filas, voto_local_disponible=False)
    assert sin_checkpoint["condiciones"]["checkpoint"] is False and sin_checkpoint["gana"] is False
