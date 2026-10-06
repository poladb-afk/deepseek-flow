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


# ---------------------------------------------------------------------------
# Triaje determinista de trazas (triaje_trazas.py)
# ---------------------------------------------------------------------------

def _ev_triaje(nodo, accion, seg):
    """Evento mínimo que consumen el linter y el cálculo de duración."""
    return {"nodo": nodo, "accion": accion, "seg": seg}


def test_triaje_seleccionar_clasifica_los_cuatro_casos():
    """Cada combinación (violación × duración) cae en su motivo correcto."""
    from triaje_trazas import seleccionar

    evaluaciones = {
        # limpia y corta: FUERA
        "limpia_corta": [
            _ev_triaje("GetQuestion", "continue", 0.1),
            _ev_triaje("LayaRouter", "directo", 0.2),
            _ev_triaje("AgentStep", "answer", 0.3),
        ],
        # violación (acción desconocida) pero corta: dentro por violaciones
        "con_violacion": [
            _ev_triaje("Fantasma", "accion_rara", 0.1),
        ],
        # larga y limpia (solo acciones canónicas): dentro por duración
        "larga_limpia": [
            _ev_triaje("GetQuestion", "continue", 0.1),
            _ev_triaje("LayaRouter", "herramientas", 50.0),
            _ev_triaje("AgentStep", "tool", 60.0),
            _ev_triaje("ExecuteTools", "default", 30.0),
            _ev_triaje("read_file", "ok", 0.0),
            _ev_triaje("AgentStep", "answer", 40.0),
        ],
        # violación Y larga: dentro por ambos
        "ambos": [
            _ev_triaje("Fantasma", "accion_rara", 0.1),
            _ev_triaje("read_file", "ok", 200.0),
        ],
    }
    sel = seleccionar(evaluaciones, umbral_seg=120.0)
    assert set(sel) == {"con_violacion", "larga_limpia", "ambos"}
    assert "limpia_corta" not in sel, "la limpia y corta queda afuera"
    assert sel["con_violacion"] == "violaciones"
    assert sel["larga_limpia"] == "duración", "sin violaciones pero > 120s entra"
    assert sel["ambos"] == "ambos"


def test_triaje_seleccionar_es_determinista_y_umbral_explicito():
    """Determinista y el umbral es el borde: igual al umbral NO entra."""
    from triaje_trazas import seleccionar

    evaluaciones = {
        "justo_en_umbral": [_ev_triaje("read_file", "ok", 120.0)],
        "pasa_umbral": [_ev_triaje("read_file", "ok", 120.1)],
    }
    assert seleccionar(evaluaciones, umbral_seg=120.0) == {"pasa_umbral": "duración"}
    # dos llamadas iguales → mismo resultado (puro)
    assert seleccionar(evaluaciones, umbral_seg=120.0) == seleccionar(
        evaluaciones, umbral_seg=120.0)


def test_triaje_leyenda_se_ordena_por_severidad():
    """3 trazas seleccionadas: ambos → violaciones → duración."""
    from triaje_trazas import _ORDEN_MOTIVO, _clave_orden

    seleccionadas = {
        "corta_viol": {"motivo": "violaciones", "violaciones": 1, "duracion_seg": 0.5},
        "larga_sola": {"motivo": "duración", "violaciones": 0, "duracion_seg": 300.0},
        "las_dos": {"motivo": "ambos", "violaciones": 2, "duracion_seg": 200.0},
    }
    ordenados = [n for n, _ in sorted(seleccionadas.items(), key=_clave_orden)]
    assert ordenados == ["las_dos", "corta_viol", "larga_sola"]
    # la severidad del motivo es un orden explícito y estable
    assert _ORDEN_MOTIVO["ambos"] < _ORDEN_MOTIVO["violaciones"] < _ORDEN_MOTIVO["duración"]


def test_triaje_mismo_motivo_ordena_por_duracion_desc():
    """Dentro de un mismo motivo, la traza más larga va primero."""
    from triaje_trazas import _clave_orden

    seleccionadas = {
        "b_larga": {"motivo": "duración", "violaciones": 0, "duracion_seg": 500.0},
        "a_corta": {"motivo": "duración", "violaciones": 0, "duracion_seg": 130.0},
    }
    ordenados = [n for n, _ in sorted(seleccionadas.items(), key=_clave_orden)]
    assert ordenados == ["b_larga", "a_corta"]


def test_triaje_evaluar_runs_saltea_ilegibles_y_cuenta_vacias(tmp_path):
    """Sobre archivos reales: legibles/vacías/ilegibles se separan y el ahorro
    se calcula sobre las legibles."""
    from triaje_trazas import evaluar_runs

    (tmp_path / "larga.jsonl").write_text(
        '{"nodo": "read_file", "accion": "ok", "seg": 200.0}\n', encoding="utf-8")
    (tmp_path / "limpia.jsonl").write_text(
        '{"nodo": "read_file", "accion": "ok", "seg": 0.5}\n', encoding="utf-8")
    (tmp_path / "roto.jsonl").write_text("{no es json}\n", encoding="utf-8")
    (tmp_path / "vacia.jsonl").write_text("", encoding="utf-8")

    informe = evaluar_runs(tmp_path, umbral_seg=120.0)
    assert informe["legibles"] == 2
    assert informe["vacias"] == 1
    assert informe["ilegibles"] == ["roto.jsonl"]
    assert informe["total"] == 4
    assert informe["n_seleccionadas"] == 1, "solo la larga entra"
    assert informe["seleccionadas"]["larga.jsonl"]["motivo"] == "duración"
    # 1 de 2 legibles → 50% de ahorro
    assert informe["ahorro_pct"] == pytest.approx(50.0)


def test_triaje_escribir_md_pone_el_limite_honesto_arriba_y_el_ahorro():
    from triaje_trazas import escribir_md

    informe = {
        "total": 4, "legibles": 2, "vacias": 1, "ilegibles": [],
        "n_seleccionadas": 1, "umbral_seg": 120.0, "ahorro_pct": 50.0,
        "seleccionadas": {"larga.jsonl": {
            "motivo": "duración", "violaciones": 0, "duracion_seg": 200.0}},
    }
    md = escribir_md(informe, "abc1234", "2026-10-06T00:00:00")
    assert "## Límite honesto" in md
    assert "NO VE LO SEMÁNTICO" in md.upper().replace("**", ""), \
        "el informe declara lo que el triaje no puede ver"
    assert "auditoría completa sigue disponible" in md.lower()
    # el límite honesto va ANTES del resumen/ahorro
    assert md.index("## Límite honesto") < md.index("## Resumen")
    assert "Ahorro de la auditoría nocturna: 50.0%" in md
    assert "larga.jsonl" in md and "duración" in md


# ---------------------------------------------------------------------------
# Heartbeat: rama triaje determinista vs. default supervisor (exp/17)
# ---------------------------------------------------------------------------

def test_heartbeat_triaje_no_pasa_por_el_supervisor():
    """`correr` con tipo=triaje corre el triaje determinista (cero LLM) y
    devuelve la ruta escrita, sin tocar el supervisor."""
    from heartbeat import correr

    resultado = correr({
        "tipo": "triaje",
        "tarea": "Triaje de trazas: qué vale la pena auditar hoy",
        "salida": "salidas/banco/triaje.md",
        "cada_horas": 24,
    })
    assert resultado["ok"] is True
    assert Path(resultado["informe"]).is_file()
    assert "Límite honesto" in Path(resultado["informe"]).read_text(encoding="utf-8")


def test_heartbeat_default_sin_tipo_llama_al_supervisor(monkeypatch):
    """Una tarea SIN `tipo` sigue la rama default: pasa por supervisar()."""
    import heartbeat

    llamado = {}

    def supervisar_fake(tarea, salida):
        llamado["tarea"], llamado["salida"] = tarea, salida
        Path(salida).parent.mkdir(parents=True, exist_ok=True)
        Path(salida).write_text("fake", encoding="utf-8")
        return salida

    monkeypatch.setattr("supervisor.supervisar", supervisar_fake)
    resultado = heartbeat.correr({"tarea": "una tarea LLM", "salida": "salidas/banco/fake.md", "cada_horas": 24})
    assert resultado["ok"] is True
    assert llamado["tarea"] == "una tarea LLM", "la rama default NO cambió"
    assert resultado["informe"] == llamado["salida"]
