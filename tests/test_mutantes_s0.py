"""X183: el instrumento de mutantes de S0 enumera bien y no toca el árbol.

La corrida entera la hace el operador (en serie, `--workers 1`: `test_hitl.py`
fija los puertos 8791–8794 y en paralelo moriría por colisión; unos 20 min); acá
se fija
que el enumerador encuentre los mutantes de las tres fronteras, que **los 305**
compilen y cambien el archivo (un solo nodo mutado por construcción), que los
ids sean únicos y que la suite de S0 que usa exista."""
import importlib.util

from conftest import RAIZ

_spec = importlib.util.spec_from_file_location("mutantes_s0", RAIZ / "banco" / "probes" / "mutantes_s0.py")
assert _spec is not None and _spec.loader is not None  # si no, el probe no está donde este candado cree
mutantes_s0 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mutantes_s0)


def test_enumera_mutantes_en_las_tres_fronteras_y_todos_compilan():
    mutantes = mutantes_s0.enumerar()
    archivos = {m["archivo"] for m in mutantes}
    assert archivos == set(mutantes_s0.OBJETIVOS)
    assert len(mutantes) > 200
    originales = {}
    for m in mutantes:
        compile(m["fuente"], m["archivo"], "exec")
        original = originales.setdefault(m["archivo"], (RAIZ / m["archivo"]).read_text(encoding="utf-8"))
        assert m["fuente"] != original, m["id"]
    assert len({m["id"] for m in mutantes}) == len(mutantes), "los ids tienen que ser únicos para retomar"


def test_cada_funcion_objetivo_existe_y_la_suite_tambien():
    import ast

    for archivo, funciones in mutantes_s0.OBJETIVOS.items():
        definidas = {n.name for n in ast.parse((RAIZ / archivo).read_text(encoding="utf-8")).body
                     if isinstance(n, ast.FunctionDef)}
        assert set(funciones) <= definidas, f"{archivo}: {set(funciones) - definidas}"
    assert all((RAIZ / t).is_file() for t in mutantes_s0.SUITE_S0)
