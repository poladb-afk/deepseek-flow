"""Reentreno del voto: anti-fuga determinista y criterio pre-registrado
(banco/specs/voto_reentreno.md), sin Laya ni red."""
import sys

from conftest import RAIZ

sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import bench_voto as bench  # noqa: E402
import voto_antifuga as af  # noqa: E402


def test_el_antifuga_atrapa_copias_y_reescrituras_cercanas():
    protegidos = af.protegidos()
    assert any(cid == "c01" for cid, _ in protegidos)
    entrenamiento = [
        {"fields": {"pregunta": "debatí en 2 rondas sobre si conviene migrar el chat a web y dame la síntesis."}},
        {"pregunta": "Quién ganó el ÚLTIMO mundial de futbol?"},          # tildes y mayúsculas
        {"pregunta": "dame la síntesis: debatí 2 rondas si conviene migrar el chat a web"},  # reorden
        {"pregunta": "listá los archivos de configuración del proyecto"},  # caso nuevo: pasa
    ]
    ids = {cid for cid, _texto, _s in af.fugas(entrenamiento, protegidos)}
    assert ids == {"c01", "c02"}
    assert len(af.fugas(entrenamiento, protegidos)) == 3


def test_el_antifuga_cli_falla_con_fugas_y_pasa_limpio(tmp_path, capsys):
    sucio = tmp_path / "sucio.jsonl"
    sucio.write_text('{"pregunta": "¿quién ganó el último mundial de fútbol?"}\n', encoding="utf-8")
    assert af.main([str(sucio)]) == 1
    limpio = tmp_path / "limpio.jsonl"
    limpio.write_text('{"pregunta": "resumí el changelog de la versión nueva"}\n', encoding="utf-8")
    assert af.main([str(limpio)]) == 0
    assert "0 fugas" in capsys.readouterr().out


def test_el_control_existe_y_valida_cuando_se_llena():
    """El control se versiona vacío; cuando el operador lo escribe, pasa por
    la misma validación del bench (id, grupo, esperado, pregunta)."""
    assert bench.CONTROL.is_file()
    bench.cargar_casos(bench.CONTROL)


def _caso(cid, grupo, esperado):
    return {"id": cid, "grupo": grupo, "esperado": esperado, "pregunta": cid}


def _bench_y_control(voto, n_herr=10, n_dir=4):
    bench_casos = [_caso("c01", "correccion", "herramientas")] + [
        _caso(f"d0{i}", "directo", "directo") for i in range(1, 7)]
    control = [_caso(f"k{i}", "correccion", "herramientas") for i in range(n_herr)] + [
        _caso(f"t{i}", "directo", "directo") for i in range(n_dir)]
    medir = lambda casos: bench.medir(casos, voto, lambda _p: "herramientas", regla=None)  # noqa: E731
    return medir(bench_casos), medir(control)


def _voto_bueno(p):
    return ("directo" if p[0] in "dt" else "herramientas", 0.95, True, "conf 0.95")


def test_reentreno_gana_solo_con_bench_control_y_antifuga():
    filas, control = _bench_y_control(_voto_bueno)
    v = bench.veredicto_reentreno(filas, control, n_fugas=0, voto_local_disponible=True)
    assert v["gana"] is True and "se promueve" in v["decision"]
    assert bench.veredicto_reentreno(filas, control, n_fugas=1, voto_local_disponible=True)["gana"] is False
    sin_antifuga = bench.veredicto_reentreno(filas, control, n_fugas=None, voto_local_disponible=True)
    assert sin_antifuga["completo"] is False and "anti-fuga" in sin_antifuga["decision"]


def test_memorizar_el_bench_no_alcanza_si_falla_fuera_de_muestra():
    """El bench perfecto con un falso directo en el control: memoria, no aprendizaje."""
    def voto(p):
        return ("directo" if p[0] in "dt" or p == "k3" else "herramientas", 0.95, True, "conf 0.95")

    filas, control = _bench_y_control(voto)
    v = bench.veredicto_reentreno(filas, control, n_fugas=0, voto_local_disponible=True)
    assert v["condiciones"]["h3g2"] and not v["condiciones"]["control_seguridad"] and not v["gana"]
    assert v["falsos_directos_control"] == ["k3"]


def test_un_voto_que_dice_siempre_herramientas_no_se_promueve():
    filas, control = _bench_y_control(lambda _p: ("herramientas", 0.99, True, "conf 0.99"))
    v = bench.veredicto_reentreno(filas, control, n_fugas=0, voto_local_disponible=True)
    assert v["condiciones"]["control_seguridad"] and not v["condiciones"]["control_ahorro"]
    assert v["gana"] is False


def test_un_control_chico_no_da_veredicto_favorable():
    filas, control = _bench_y_control(_voto_bueno, n_herr=9)
    v = bench.veredicto_reentreno(filas, control, n_fugas=0, voto_local_disponible=True)
    assert v["condiciones"]["control_tamano"] is False and v["gana"] is False
