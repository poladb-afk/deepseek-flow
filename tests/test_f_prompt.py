"""F: las directivas medibles se apagan por setting sin tocar el prompt de
producción, y el runner aplica el criterio pre-registrado (banco/specs/f_prompt.md)
sin LLM."""
import importlib.util

from conftest import RAIZ


def _f():
    spec = importlib.util.spec_from_file_location("f_prompt", RAIZ / "banco" / "probes" / "f_prompt.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_las_directivas_de_f_se_apagan_por_separado(monkeypatch):
    import main

    monkeypatch.delenv("PROMPT_CITAS", raising=False)
    monkeypatch.delenv("PROMPT_ALCANCE", raising=False)
    produccion = main.system_prompt()
    assert main.DIRECTIVA_CITAS in produccion and main.DIRECTIVA_ALCANCE in produccion
    monkeypatch.setenv("PROMPT_CITAS", "0")
    sin_citas = main.system_prompt()
    assert main.DIRECTIVA_CITAS not in sin_citas and main.DIRECTIVA_ALCANCE in sin_citas
    monkeypatch.setenv("PROMPT_CITAS", "1")
    monkeypatch.setenv("PROMPT_ALCANCE", "0")
    sin_alcance = main.system_prompt()
    assert main.DIRECTIVA_ALCANCE not in sin_alcance and main.DIRECTIVA_CITAS in sin_alcance
    assert "cat, grep ni find" in sin_alcance  # la de herramientas no es de F


def test_el_prompt_de_produccion_no_cambio_de_texto(monkeypatch):
    """Los toggles extraen las dos directivas a constantes; con default 1 el
    texto es el de antes (un cambio de bytes rompe el KV-cache y el A/B)."""
    import main

    monkeypatch.delenv("PROMPT_CITAS", raising=False)
    monkeypatch.delenv("PROMPT_ALCANCE", raising=False)
    texto = main.system_prompt(incluir_forma=False)
    esperado = (
        "Respondé en el idioma de cada pedido (español o inglés).\n\n"
        "Si el pedido es una auditoría o análisis amplio del repo, acotá el alcance y respondé con "
        "hallazgos y límites; no intentes leer todo.\n\n"
        "Cuando cites archivo:línea, verificá esa línea en el archivo antes de afirmarla; si no la "
        "verificaste, decila como no verificada. Citá siempre como ruta/archivo.py:línea (ruta relativa "
        'al repo, sin "líneas ~X").\n\n'
        "Para leer, listar o buscar archivos usá read_file, list_files o search_files; no uses cat, "
        "grep ni find por run_command."
    )
    assert texto.endswith(esperado)


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
