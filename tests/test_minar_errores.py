"""Tests deterministas de la minería de errores de tools (minar_errores.py).

El módulo mina cientos de trazas: por eso el cálculo (timeout, rechazo HITL,
destino del reintento, agregados) se verifica acá sobre listas de eventos
SINTÉTICAS, sin abrir ningún archivo. Si la lógica de "¿se autocorrigió?"
miente, este test lo avisa antes de gastar una corrida sobre .runs real."""
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def _ev(nodo, accion, seg, ts):
    return {"nodo": nodo, "accion": accion, "seg": seg, "ts": ts}


def test_es_timeout_solo_castiga_errores_largos():
    from minar_errores import es_timeout

    assert es_timeout({"accion": "error", "seg": 120.0}) is True
    assert es_timeout({"accion": "error", "seg": 100.0}) is True, "borde exacto incluido"
    assert es_timeout({"accion": "error", "seg": 0.3}) is False
    # un ok LARGO no es timeout: es trabajo, no ceguera
    assert es_timeout({"accion": "ok", "seg": 300.0}) is False


def test_es_rechazo_probable_es_solo_run_command_ok_instantaneo():
    from minar_errores import es_rechazo_probable

    assert es_rechazo_probable({"nodo": "run_command", "accion": "ok", "seg": 0.1}) is True
    # un ok lento de run_command corrió de verdad, no fue rechazado
    assert es_rechazo_probable({"nodo": "run_command", "accion": "ok", "seg": 5.0}) is False
    # otra tool con seg ~0 no es rechazo HITL (eso es de run_command)
    assert es_rechazo_probable({"nodo": "read_file", "accion": "ok", "seg": 0.0}) is False
    # un error no es un rechazo (los errores van por su propio carril)
    assert es_rechazo_probable({"nodo": "run_command", "accion": "error", "seg": 0.0}) is False


def test_destino_reintento_distingue_exito_abandono_y_otra_tool():
    from minar_errores import destino_del_reintento

    err = _ev("edit_file", "error", 0.0, 10.0)

    con_exito = [err, _ev("edit_file", "ok", 0.2, 12.0)]
    d = destino_del_reintento(con_exito, err)
    assert d["ok"] is True and d["delta_seg"] == pytest.approx(2.0)

    # vuelve a llamar a la MISMA tool y vuelve a fallar: hubo reintento, sin éxito
    refalla = [err, _ev("edit_file", "error", 0.1, 11.0)]
    d = destino_del_reintento(refalla, err)
    assert d["ok"] is False

    # no hay próxima llamada a la tool: abandono
    assert destino_del_reintento([err, _ev("read_file", "ok", 0.1, 11.0)], err) is None


def test_minar_sesion_cuenta_autocorreccion_y_abandono_por_separado():
    from minar_errores import minar_sesion

    eventos = [
        _ev("edit_file", "error", 0.0, 1.0),   # reintenta con éxito
        _ev("edit_file", "ok", 0.2, 2.0),
        _ev("search_files", "error", 0.1, 3.0),  # abandona (nunca más se llama)
        _ev("run_command", "error", 130.0, 4.0),  # timeout que abandona
        _ev("run_command", "ok", 0.05, 5.0),    # rechazo-probable (no es de este error)
    ]
    res = minar_sesion(eventos)
    e = res["por_tool"]["edit_file"]
    assert e["errores"] == 1 and e["reintentos"] == 1 and e["reintentos_ok"] == 1
    assert e["delta_mediano_seg"] == pytest.approx(1.0)
    s = res["por_tool"]["search_files"]
    assert s["errores"] == 1 and s["reintentos"] == 0 and s["abandono"] == 1
    rc = res["por_tool"]["run_command"]
    assert rc["timeouts"] == 1, "el error de 130 s es timeout"
    # el ok de run_command con seg 0.05 cae en rechazo-probable, NO en el error
    assert res["rechazos_probables"] == 1


def test_minar_sesion_sin_errores_no_inventa_tools():
    from minar_errores import minar_sesion

    res = minar_sesion([_ev("read_file", "ok", 0.1, 1.0), _ev("read_file", "ok", 0.1, 2.0)])
    assert res["por_tool"] == {}
    assert res["rechazos_probables"] == 0


def test_escribir_md_preceda_con_el_limite_honesto_y_la_tasa():
    from minar_errores import escribir_md

    informe = {
        "sesiones_total": 1, "sesiones_con_error": 1, "errores_total": 1,
        "errores_por_sesion": 1.0, "timeouts_total": 0,
        "reintentos_total": 1, "reintentos_ok_total": 1, "abandono_total": 0,
        "rechazos_probables_total": 0, "tasa_autocorreccion": 1.0,
        "trazas_ilegibles": [],
        "por_tool": {"edit_file": {
            "errores": 1, "timeouts": 0, "reintentos": 1, "reintentos_ok": 1,
            "abandono": 0, "delta_mediano_seg": 1.0}},
    }
    md = escribir_md(informe, "abc1234", "2026-10-06T00:00:00")
    assert "## Límite honesto" in md
    assert "NUNCA se suma a los errores reales" in md, "el caveat HITL va en el informe"
    # el límite honesto aparece ANTES que la tasa
    assert md.index("## Límite honesto") < md.index("## Tasa de autocorrección")
    assert "100.0%" in md and "edit_file" in md


def test_minar_runs_saltea_trazas_ilegibles_sin_romper(tmp_path):
    from minar_errores import minar_runs

    (tmp_path / "ok.jsonl").write_text(
        '{"ts": 1.0, "nodo": "edit_file", "accion": "error", "seg": 0.0}\n'
        '{"ts": 2.0, "nodo": "edit_file", "accion": "ok", "seg": 0.2}\n',
        encoding="utf-8",
    )
    (tmp_path / "roto.jsonl").write_text("{esto no es json}\n", encoding="utf-8")
    (tmp_path / "vacio.jsonl").write_text("", encoding="utf-8")

    informe = minar_runs(tmp_path)
    assert informe["sesiones_total"] == 1, "la vacía no cuenta como sesión"
    assert informe["errores_total"] == 1
    assert informe["tasa_autocorreccion"] == pytest.approx(1.0)
    assert informe["trazas_ilegibles"] == ["roto.jsonl"], "la rota se reporta, no se cae"
