"""H3-B: el runner aplica el criterio pre-registrado sin LLM (banco/specs/h3b_swarm.md)."""
import importlib.util

from conftest import RAIZ


def _h3b():
    spec = importlib.util.spec_from_file_location("h3b_swarm", RAIZ / "banco" / "probes" / "h3b_swarm.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _fila(brazo, escenario, calidad, tokens, explorar=0, seed=1):
    return {"brazo": brazo, "escenario": escenario, "seed": seed, "calidad": calidad,
            "tokens": tokens, "exploraciones": explorar, "seg": 1.0, "error": None}


ESC = ("s17-scale-audit", "s18-real-audit")


def test_gana_solo_si_adopta_en_todos_y_la_calidad_sube_mas_que_el_costo():
    h = _h3b()
    base = [_fila("chat", e, 1, 100_000) for e in ESC]
    gana = base + [_fila("supervisor", e, 2, 150_000, explorar=1) for e in ESC]
    assert h.veredicto(gana)["gana"] is True

    # calidad sube pero MENOS que el costo (×2 calidad, ×3 tokens): no gana
    caro = base + [_fila("supervisor", e, 2, 300_000, explorar=1) for e in ESC]
    v = h.veredicto(caro)
    assert v["condiciones"]["calidad"] and not v["condiciones"]["calidad_por_token"] and not v["gana"]

    # más barato pero no mejor: no gana (la condición de calidad es estricta)
    igual = base + [_fila("supervisor", e, 1, 50_000, explorar=1) for e in ESC]
    assert h.veredicto(igual)["gana"] is False


def test_sin_adopcion_en_un_escenario_no_gana_aunque_la_calidad_suba():
    """La regla de los gates: el brazo tiene que probar que la pieza CORRIÓ."""
    h = _h3b()
    filas = [_fila("chat", e, 1, 100_000) for e in ESC]
    filas += [_fila("supervisor", ESC[0], 2, 100_000, explorar=2),
              _fila("supervisor", ESC[1], 2, 100_000, explorar=0)]
    v = h.veredicto(filas)
    assert v["adopcion"] == {ESC[0]: 2, ESC[1]: 0}
    assert v["condiciones"]["adopcion"] is False and v["gana"] is False
    assert "se borra" in v["decision"]


def test_sin_datos_de_un_brazo_no_hay_veredicto():
    h = _h3b()
    v = h.veredicto([_fila("chat", ESC[0], 1, 100_000)])
    assert v["completo"] is False and v["gana"] is False and "faltan datos" in v["decision"]


def test_lee_tokens_y_exploraciones():
    h = _h3b()
    assert h.tokens_del_log("…\n[tokens] sesión: 7 llamadas — 61.234 prompt + 1.500 completion (~$0,01)") == (7, 62_734)
    assert h.tokens_del_log("sin la línea") is None
    informe = "## Pasos\n\n- 1 read_file(path=a) -> x\n- 2 explorar(pregunta=y) -> z\n- 3 explorar(pregunta=w) -> v\n"
    assert h.exploraciones(informe) == 2 and h.exploraciones("") == 0


def test_el_resumen_declara_el_criterio_y_el_veredicto():
    h = _h3b()
    filas = [_fila("chat", e, 1, 100_000) for e in ESC] + [_fila("supervisor", e, 1, 100_000) for e in ESC]
    texto = h.resumen(filas)
    assert "banco/specs/h3b_swarm.md" in texto and "NO GANA" in texto and "adopcion: ❌" in texto


def test_bench_fable_sin_salir_queda_igual():
    """El turno "salir" es opcional: los benches de siempre no cambian."""
    import inspect

    spec = importlib.util.spec_from_file_location("bench_fable", RAIZ / "banco" / "probes" / "bench_fable.py")
    bf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bf)
    assert inspect.signature(bf.correr_uno).parameters["salir"].default is False
