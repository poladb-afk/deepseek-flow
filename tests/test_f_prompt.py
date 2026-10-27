"""F (resuelto, X85): el prompt aplica la decisión y el runner conserva el
criterio pre-registrado (banco/specs/f_prompt.md), sin LLM."""
import importlib.util

from conftest import RAIZ


def _f():
    spec = importlib.util.spec_from_file_location("f_prompt", RAIZ / "banco" / "probes" / "f_prompt.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_el_prompt_aplica_la_decision_de_f(monkeypatch):
    """X85: la directiva de alcance se fue (ganó sin ella), la de citas se
    quedó (sin ella bajó la calidad) y ninguna depende ya de un setting."""
    import main

    for nombre in ("PROMPT_CITAS", "PROMPT_ALCANCE"):
        monkeypatch.setenv(nombre, "0")  # perillas borradas: no cambian nada
    texto = main.system_prompt(incluir_forma=False)
    esperado = (
        "Respondé en el idioma de cada pedido (español o inglés).\n\n"
        "Cuando cites archivo:línea, verificá esa línea en el archivo antes de afirmarla; si no la "
        "verificaste, decila como no verificada. Citá siempre como ruta/archivo.py:línea (ruta relativa "
        'al repo, sin "líneas ~X").\n\n'
        "Para leer, listar o buscar archivos usá read_file, list_files o search_files; no uses cat, "
        "grep ni find por run_command."
    )
    assert texto.endswith(esperado)
    assert "acotá el alcance" not in texto
    assert not hasattr(main, "DIRECTIVA_ALCANCE") and not hasattr(main, "DIRECTIVA_CITAS")


def test_el_runner_resuelto_no_vuelve_a_correr():
    import pytest

    f = _f()
    with pytest.raises(SystemExit, match="X85"):
        f.main([])


def test_los_amplios_de_f_son_los_que_alcance_amplio_clasifica(monkeypatch):
    """La ventana de ALCANCE se verifica, no se supone: alcance_amplio da True
    en s17–s20 y False en s15/s16."""
    import os

    import nodes

    f = _f()
    for escenario in f.CITAS:
        fuente = f.bf.fuente_fixture(escenario)
        monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(fuente.resolve()))
        tarea = f.bf.TAREAS[escenario](os.path.relpath(fuente, RAIZ))
        monkeypatch.chdir(RAIZ)
        assert nodes.alcance_amplio(tarea) is (escenario in f.AMPLIOS), escenario


def test_la_evidencia_sale_del_log():
    f = _f()
    log = "⚙ ronda 3/16\n  [citas] 4/5 verificadas\nDeepSeek (citas corregidas): ..."
    assert f.evidencia(log) == {"citas_vistas": True, "tope_amplio": True, "correcciones": 1}
    assert f.evidencia("⚙ ronda 3/8\n  [citas] 0/0 verificadas") == {
        "citas_vistas": False, "tope_amplio": False, "correcciones": 0}


def _fila(brazo, escenario, seed=1, calidad=1, tokens=100_000, invalidas=0, citas=True, tope=True):
    return {"brazo": brazo, "escenario": escenario, "seed": seed, "calidad": calidad,
            "citas_invalidas": invalidas, "tokens": tokens, "citas_vistas": citas,
            "tope_amplio": tope, "correcciones": 0, "rondas": 5, "seg": 1.0, "error": None}


def _corrida(f, brazo, escenarios, **extra):
    return [_fila(brazo, e, s, **extra) for e in escenarios for s in (1, 2, 3)]


def test_empate_de_calidad_y_costo_dentro_del_margen_borra_la_directiva():
    f = _f()
    filas = _corrida(f, "base", f.CITAS) + _corrida(f, "sin_citas", f.CITAS, tokens=109_000)
    v = f.veredicto(filas)["citas"]
    assert v["gana"] is True and "se borra la directiva" in v["decision"]


def test_sin_cobertura_la_directiva_se_queda_aunque_todo_lo_demas_gane():
    """X82 aplicado: si VerificarCitas no vio citas, no decidió nada."""
    f = _f()
    filas = _corrida(f, "base", f.CITAS) + _corrida(f, "sin_citas", f.CITAS, calidad=2)
    for fila in filas:
        if fila["brazo"] == "sin_citas" and fila["escenario"] == "s15-python-bug-hunt" and fila["seed"] > 1:
            fila["citas_vistas"] = False
    v = f.veredicto(filas)["citas"]
    assert v["cobertura"]["s15-python-bug-hunt"] == 1
    assert v["condiciones"]["cobertura"] is False and v["gana"] is False


def test_alcance_se_compara_solo_en_los_amplios_y_el_costo_decide():
    f = _f()
    base = _corrida(f, "base", f.CITAS[:2], calidad=0) + _corrida(f, "base", f.AMPLIOS)
    caro = base + _corrida(f, "sin_alcance", f.AMPLIOS, tokens=120_000)
    v = f.veredicto(caro)["alcance"]
    assert v["medidas"]["base"]["n"] == 12  # s15/s16 no entran en la base de alcance
    assert v["condiciones"]["calidad"] and not v["condiciones"]["costo"] and not v["gana"]
    sin_tope = base + _corrida(f, "sin_alcance", f.AMPLIOS, tope=False)
    assert f.veredicto(sin_tope)["alcance"]["condiciones"]["cobertura"] is False


def test_mas_citas_invalidas_o_menos_calidad_y_se_queda():
    f = _f()
    base = _corrida(f, "base", f.CITAS)
    assert f.veredicto(base + _corrida(f, "sin_citas", f.CITAS, invalidas=1))["citas"]["gana"] is False
    assert f.veredicto(base + _corrida(f, "sin_citas", f.CITAS, calidad=0))["citas"]["gana"] is False


def test_sin_datos_no_hay_veredicto():
    f = _f()
    v = f.veredicto([])
    assert all(not d["completo"] and not d["gana"] for d in v.values())
    assert "F — sacar del prompt" in f.resumen([])
