"""H3-G: el runner mide la política de producción y aplica el criterio
pre-registrado (banco/specs/h3g_reglas.md) sin LLM ni Laya."""
import importlib.util

from conftest import RAIZ


def _h3g():
    spec = importlib.util.spec_from_file_location("h3g_reglas", RAIZ / "banco" / "probes" / "h3g_reglas.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _caso(pregunta, esperado, fuente="humana"):
    return {"pregunta": pregunta, "esperado": esperado, "fuente": fuente, "id": ""}


def test_la_politica_del_experimento_es_la_del_router(monkeypatch):
    """El experimento mide PRODUCCIÓN: la misma pregunta con el mismo Laya y
    el mismo voto da la misma ruta en LayaRouter (enforce) y en `politica`."""
    import nodes
    from utils import laya

    h = _h3g()
    monkeypatch.setenv("LAYA_MODO", "enforce")
    monkeypatch.setenv("SKILLS", "0")
    # truthy-inválida a propósito: _setting trata "" como no-seteada y caería
    # al .env de producción (con calibración conformal y alpha), que en la
    # máquina del operador define LAYA_CALIBRACION_ROUTER — una ruta inexistente
    # la desactiva de verdad (aviso "no utilizable" → umbral fijo) en ambos entornos
    monkeypatch.setenv("LAYA_CALIBRACION_ROUTER", "calibracion-no-existe.jsonl")
    monkeypatch.setattr(laya, "disponible", lambda *a, **k: True)
    directo = {"choice": "directo", "probabilities": {"directo": 0.97, "herramientas": 0.03}}
    monkeypatch.setattr(laya, "preguntar_detalle", lambda *a, **k: {"necesita_herramientas": directo})
    casos = ("¿quién ganó el último mundial?", "leé README.md y resumilo", "¿qué es un closure?")
    for voto in ("directo", "herramientas"):
        monkeypatch.setattr(nodes, "voto_confirmacion_router", lambda p, voto=voto: voto)
        for pregunta in casos:
            router = nodes.LayaRouter()
            ruta = router.post({"messages": []}, {"pregunta": pregunta}, router.exec({"pregunta": pregunta}))
            assert ruta == h.politica(h.regla(pregunta), "directo", voto, con_reglas=True), (pregunta, voto)


def test_los_brazos_difieren_solo_en_las_reglas():
    h = _h3g()
    fila = h.medir_caso(_caso("¿quién ganó el último mundial?", "herramientas"),
                        router=lambda p: "directo", voto=lambda p: ("directo", True))
    assert fila["regla"] == "temporal"
    assert fila["final_con"] == "herramientas" and fila["final_sin"] == "directo"
    assert fila["arbitro_con"] is False and fila["arbitro_sin"] is True
    sin_regla = h.medir_caso(_caso("¿qué es un closure?", "directo"),
                             router=lambda p: "directo", voto=lambda p: ("directo", False))
    assert sin_regla["final_con"] == sin_regla["final_sin"] == "directo"


def test_un_solo_falso_directo_nuevo_y_las_reglas_se_quedan():
    """La carga de la prueba está en el borrado (R7)."""
    h = _h3g()
    filas = [h.medir_caso(_caso(f"leé el archivo {i}.py", "herramientas"),
                          router=lambda p: "herramientas", voto=lambda p: (None, False)) for i in range(25)]
    filas.append(h.medir_caso(_caso("¿quién ganó el último mundial?", "herramientas"),
                              router=lambda p: "directo", voto=lambda p: ("directo", True)))
    v = h.veredicto(filas)
    assert v["condiciones"]["cobertura"] and not v["condiciones"]["seguridad"] and not v["gana"]
    assert [f["regla"] for f in v["salvados"]] == ["temporal"]
    assert "se quedan" in v["decision"]


def test_si_el_voto_cubre_todo_las_reglas_se_borran():
    h = _h3g()
    filas = [h.medir_caso(_caso(f"leé el archivo {i}.py", "herramientas"),
                          router=lambda p: "directo", voto=lambda p: ("herramientas", True)) for i in range(25)]
    v = h.veredicto(filas)
    assert v["cobertura"] == 25 and v["gana"] is True and "se borran" in v["decision"]


def test_sin_cobertura_no_hay_borrado():
    """Si las reglas casi no disparan, el experimento no las ejercitó."""
    h = _h3g()
    filas = [h.medir_caso(_caso("¿qué es un closure?", "directo"),
                          router=lambda p: "directo", voto=lambda p: ("directo", False)) for _ in range(30)]
    v = h.veredicto(filas)
    assert v["cobertura"] == 0 and v["condiciones"]["cobertura"] is False and v["gana"] is False


def test_los_casos_del_repo_cargan_sin_repetidos_y_la_etiqueta_humana_gana(tmp_path):
    h = _h3g()
    casos = h.cargar_casos()
    assert len(casos) >= 90 and len({h._normal(c["pregunta"]) for c in casos}) == len(casos)
    assert sum(1 for c in casos if h.regla(c["pregunta"])) >= h.COBERTURA_MIN
    humana, arbitro = tmp_path / "h.jsonl", tmp_path / "a.jsonl"
    humana.write_text('{"pregunta": "Hola", "esperado": "directo"}\n', encoding="utf-8")
    arbitro.write_text('{"pregunta": "hola ", "etiqueta": "herramientas"}\n', encoding="utf-8")
    (unico,) = h.cargar_casos(humana, arbitro)
    assert unico["esperado"] == "directo" and unico["fuente"] == "humana"


def test_el_resumen_nombra_los_casos_salvados():
    h = _h3g()
    filas = [h.medir_caso(_caso("¿quién ganó el último mundial?", "herramientas"),
                          router=lambda p: "directo", voto=lambda p: ("directo", True))]
    texto = h.resumen(filas)
    assert "banco/specs/h3g_reglas.md" in texto and "último mundial" in texto and "NO GANA" in texto


def test_la_cobertura_efectiva_cuenta_donde_la_regla_decide():
    """X82: 25 disparos con Laya ya en herramientas son cobertura 25 para el
    criterio viejo y 0 efectiva; el resumen lo dice al lado del veredicto."""
    h = _h3g()
    filas = [h.medir_caso(_caso(f"leé el archivo {i}.py", "herramientas"),
                          router=lambda p: "herramientas", voto=lambda p: (None, False)) for i in range(25)]
    assert h.veredicto(filas)["gana"] is True  # el criterio viejo, intacto
    assert h.cobertura_efectiva(filas) == 0
    texto = h.resumen(filas)
    assert "cobertura efectiva" in texto and "no autoriza el borrado" in texto
