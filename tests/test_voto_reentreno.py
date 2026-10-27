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


HUELLA = "h" * 64


def _baseline_que_discrimina():
    """El voto de producción fallaba k0 (falso directo), medido antes de entrenar."""
    def voto_viejo(p):
        return ("directo" if p[0] in "dt" or p == "k0" else "herramientas", 0.94, True, "conf 0.94")

    _bench, control = _bench_y_control(voto_viejo)
    return bench.baseline_control(control, HUELLA, ".modelos/router_voto")


def _veredicto(filas, control, n_fugas=0, baseline="discrimina", huella=HUELLA):
    if baseline == "discrimina":
        baseline = _baseline_que_discrimina()
    return bench.veredicto_reentreno(filas, control, n_fugas=n_fugas, voto_local_disponible=True,
                                     baseline=baseline, huella_control=huella)


def test_reentreno_gana_solo_con_bench_control_y_antifuga():
    filas, control = _bench_y_control(_voto_bueno)
    v = _veredicto(filas, control)
    assert v["gana"] is True and "se promueve" in v["decision"]
    assert _veredicto(filas, control, n_fugas=1)["gana"] is False
    sin_antifuga = _veredicto(filas, control, n_fugas=None)
    assert sin_antifuga["completo"] is False and "anti-fuga" in sin_antifuga["decision"]


def test_memorizar_el_bench_no_alcanza_si_falla_fuera_de_muestra():
    """El bench perfecto con un falso directo en el control: memoria, no aprendizaje."""
    def voto(p):
        return ("directo" if p[0] in "dt" or p == "k3" else "herramientas", 0.95, True, "conf 0.95")

    filas, control = _bench_y_control(voto)
    v = _veredicto(filas, control)
    assert v["condiciones"]["h3g2"] and not v["condiciones"]["control_seguridad"] and not v["gana"]
    assert v["falsos_directos_control"] == ["k3"]


def test_un_voto_que_dice_siempre_herramientas_no_se_promueve():
    filas, control = _bench_y_control(lambda _p: ("herramientas", 0.99, True, "conf 0.99"))
    v = _veredicto(filas, control)
    assert v["condiciones"]["control_seguridad"] and not v["condiciones"]["control_ahorro"]
    assert v["gana"] is False


def test_un_control_chico_no_da_veredicto_favorable():
    filas, control = _bench_y_control(_voto_bueno, n_herr=9)
    v = _veredicto(filas, control)
    assert v["condiciones"]["control_tamano"] is False and v["gana"] is False


def test_un_control_que_el_voto_viejo_ya_pasaba_no_promueve():
    """Enmienda 2026-10-27: el smoke mostró que el voto de producción pasaba
    el control entero. Con ese control, un checkpoint que memorice c01/c02
    gana todo lo demás; control_discrimina lo frena."""
    filas, control = _bench_y_control(_voto_bueno)
    _b, control_viejo = _bench_y_control(_voto_bueno)
    no_discrimina = bench.baseline_control(control_viejo, HUELLA, ".modelos/router_voto")
    assert no_discrimina["falsos_directos"] == []
    v = _veredicto(filas, control, baseline=no_discrimina)
    resto = {k: ok for k, ok in v["condiciones"].items() if k != "control_discrimina"}
    assert all(resto.values()) and v["condiciones"]["control_discrimina"] is False and v["gana"] is False


def test_el_baseline_vale_solo_para_el_control_que_midio():
    """Si el control cambia después del baseline (otra huella), no discrimina
    nada: hay que volver a medir con el voto de producción."""
    filas, control = _bench_y_control(_voto_bueno)
    assert _veredicto(filas, control, huella="otra" * 16)["condiciones"]["control_discrimina"] is False


def test_sin_baseline_no_hay_veredicto():
    filas, control = _bench_y_control(_voto_bueno)
    v = _veredicto(filas, control, baseline=None)
    assert v["completo"] is False and v["gana"] is False and "--registrar-baseline" in v["decision"]


def test_el_baseline_registra_falsos_directos_y_trampas(tmp_path):
    def voto(p):
        return ("directo" if p[0] in "d" or p in ("k0", "k1") else "herramientas", 0.9, True, "conf 0.9")

    _b, control = _bench_y_control(voto)
    base = bench.baseline_control(control, bench.huella(bench.CASOS), "ckpt")
    assert base["falsos_directos"] == ["k0", "k1"] and base["trampas_mal"] == ["t0", "t1", "t2", "t3"]
    assert base["n"] == 14 and len(base["control_sha256"]) == 64
