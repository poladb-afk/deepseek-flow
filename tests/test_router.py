"""El router y su voto: aristas del chat, umbrales, conformal y degradación (PR 4)."""
import pytest
from conftest import RAIZ


def test_router_aristas_del_chat(monkeypatch):
    # lección medida en producción: DirectAnswer hereda el post de AgentStep
    # (devuelve "answer"), y la arista default mataba el chat tras la
    # primera respuesta directa — PocketFlow terminaba el flujo con warning.
    # El entorno del banco corre con USE_LAYA_ROUTER=0 (variante degradada):
    # el test fija la variante CON router para probar sus aristas.
    monkeypatch.setenv("USE_LAYA_ROUTER", "1")
    from flow import create_agent_flow

    flow = create_agent_flow()
    # caminar el grafo desde ask — exp/50: PreFetch vive entre ask y el router
    ask = flow.start_node
    prefetch = ask.successors.get("continue")
    assert prefetch is not None
    router = prefetch.successors.get("continue")
    assert router is not None
    directo = router.successors.get("directo")
    assert directo is not None
    assert "answer" in directo.successors, f"DirectAnswer debe volver con 'answer': {list(directo.successors)}"

def test_mayoria():
    from utils.votacion import mayoria

    assert mayoria(["sql", "sql", "finish"]) == "sql"
    assert mayoria(["sql", "finish", "finish"]) == "finish"
    assert mayoria(["sql", "db_schema", "finish"], desempate="sql") == "sql"
    assert mayoria(["sql"]) == "sql"  # voto único: sin mayoría, sin desempate
    assert mayoria([], desempate="finish") == "finish"

def test_voto_confirmacion_tres_niveles(monkeypatch):
    """Mesa 3: acuerdo/desacuerdo confiable lo decide Laya local (sin
    DeepSeek); la banda incierta la arbitra DeepSeek; sin checkpoint,
    DeepSeek como siempre."""

    import nodes
    import utils.laya as laya_mod

    llamadas = {"ds": 0}

    def ds_fake(prompt):
        llamadas["ds"] += 1
        return "```yaml\nveredicto: directo\n```"

    monkeypatch.setattr("utils.call_llm.call_llm", ds_fake)

    def pregunta_con(resp, conf):
        return lambda estado, preguntas, setting="LAYA_MODEL": {
            "confirma_herramientas": (resp, conf)}

    # 1) acuerdo confiable: voto local dice directo 0.95 → directo, DeepSeek NUNCA
    monkeypatch.setattr(laya_mod, "disponible", lambda s: True)
    monkeypatch.setattr(laya_mod, "preguntar", pregunta_con("directo", 0.95))
    assert nodes.voto_confirmacion_router("hola, cómo estás?") == "directo"
    assert llamadas["ds"] == 0

    # 2) desacuerdo confiable: voto local dice herramientas 0.9 → lado seguro, sin DeepSeek
    monkeypatch.setattr(laya_mod, "preguntar", pregunta_con("herramientas", 0.90))
    assert nodes.voto_confirmacion_router("debatí si X") == "herramientas"
    assert llamadas["ds"] == 0

    # 3) banda incierta (0.5): arbitra DeepSeek
    monkeypatch.setattr(laya_mod, "preguntar", pregunta_con("directo", 0.50))
    assert nodes.voto_confirmacion_router("caso límite") == "directo"
    assert llamadas["ds"] == 1

    # 4) sin checkpoint: DeepSeek como siempre
    monkeypatch.setattr(laya_mod, "disponible", lambda s: False)
    assert nodes.voto_confirmacion_router("otro caso") == "directo"
    assert llamadas["ds"] == 2

def test_split_umbrales_router_y_voto(monkeypatch):
    """exp/8: la compuerta del router (LAYA_UNSURE_HIGH) y la del voto
    (LAYA_UNSURE_HIGH_VOTO) son settings SEPARADAS. El test fija el entorno
    con monkeypatch porque _setting lee en cascada nuestro .env y el de bmo
    (BMO_ENV tiene LAYA_UNSURE_HIGH=0.7 heredado, que enmascara el default
    0.85 del código — medido: sin fijar la env, veredicto(0.84) da met)."""
    from utils.laya import veredicto

    # la setting del router manda sobre cualquier cascada
    monkeypatch.setenv("LAYA_UNSURE_HIGH", "0.85")
    assert veredicto(0.84) == "uncertain"
    assert veredicto(0.85) == "met"
    monkeypatch.setenv("LAYA_UNSURE_HIGH", "0.7")
    assert veredicto(0.75) == "met"
    # el voto consulta con su propio alto explícito: nunca hereda al router
    assert veredicto(0.75, alto=0.7) == "met"
    assert veredicto(0.84, alto=0.7) == "met"

def test_router_laya_no_mata_el_chat_si_la_inferencia_falla(monkeypatch):
    """exp/25 (C14 de la auditoría externa): una excepción de inferencia se
    escapaba del Flow (main solo atrapa KeyboardInterrupt) y una etiqueta
    fuera de contrato cerraba el chat en silencio. La frontera devuelve
    siempre una decisión válida: el lado seguro."""
    import nodes
    from utils import laya

    monkeypatch.setattr(laya, "disponible", lambda *a, **k: True)
    router = nodes.LayaRouter()

    def explotar(*a, **k):
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(laya, "preguntar_detalle", explotar)
    assert router.exec({"pregunta": "hola"}) is None     # la excepción no escapa
    # y la POLÍTICA la lee como abstención: el lado seguro (exp/35)
    # registrar_decision entra por import local dentro de post(): se parchea
    # en su módulo, no como atributo de nodes (que no lo tiene).
    monkeypatch.setattr("utils.laya_routing.registrar_decision", lambda *a, **k: None)
    assert router.post({}, {"pregunta": "hola"}, None) == "herramientas"

    for respuesta in (
        {"choice": "quizas", "probabilities": {"quizas": 0.99}},  # fuera de contrato
        {"choice": "directo"},                                   # sin probabilidades
        {"probabilities": {"directo": 0.9}},                     # sin etiqueta
        {},                                                      # contrato incompleto
    ):
        assert router.post({}, {"pregunta": "hola"}, respuesta) == "herramientas"

def test_conformal_evaluar_calibrado_en_otro_conjunto():
    """exp/33: calibrar en A y medir en B — la evaluación honesta de la
    cascada: cobertura (la verdad entra al conjunto) y aceptadas (singleton)."""
    from utils.conformal import evaluar, q_de_calibracion

    A = [{"conf": 0.97, "correcto": True}] * 20 + [{"conf": 0.60, "correcto": False}] * 10
    q = q_de_calibracion(A, 0.10)
    assert q == 0.60                       # índice ceil(31*0.9)=28 sobre 30 casos
    B = [
        {"conf": 0.95, "correcto": True},   # colapsa (0.05 < 0.40): aceptada
        {"conf": 0.70, "correcto": True},   # colapsa (0.30 < 0.40): aceptada
        {"conf": 0.55, "correcto": False},  # 0.45 >= 0.40: ambigua
        {"conf": 0.45, "correcto": True},   # 0.55 >= 0.40: ambigua
    ]
    m = evaluar(B, q)
    assert m["n"] == 4
    assert m["cobertura"] == 1.0
    assert m["aceptadas"] == 0.5
    assert m["precision"] == 1.0
    with pytest.raises(ValueError):
        evaluar([], q)

def test_calibracion_conformal_se_lee_y_no_tolera_basura(tmp_path):
    """exp/31: el artefacto de calibración es un JSONL {"conf", "correcto"};
    sin archivo o vacío se avisa con excepción (el router degrada)."""
    import json as _json

    from utils.conformal import leer_calibracion, q_de_calibracion

    ruta = tmp_path / "calib.jsonl"
    ruta.write_text(
        "\n".join([_json.dumps({"conf": 0.97, "correcto": True})] * 20
                    + [_json.dumps({"conf": 0.60, "correcto": False})] * 10) + "\n",
        encoding="utf-8",
    )
    casos = leer_calibracion(ruta)
    assert len(casos) == 30
    assert q_de_calibracion(casos, 0.10) == 0.60      # índice ceil(31*0.9)=28
    assert q_de_calibracion(casos, 0.02) is None      # sin cota con n=30

    with pytest.raises(FileNotFoundError):
        leer_calibracion(tmp_path / "no-existe.jsonl")
    vacia = tmp_path / "vacia.jsonl"
    vacia.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        leer_calibracion(vacia)

def test_router_usa_el_conjunto_conformal_cuando_hay_calibracion(tmp_path, monkeypatch):
    """exp/31: con calibración, el router decide local por COLAPSO del conjunto
    (acepta 0.70 con q=0.60) donde el umbral fijo 0.85 lo mandaría a
    herramientas; sin calibración, el comportamiento de siempre."""
    import json as _json

    import nodes
    from utils import call_llm, laya

    calib = tmp_path / "calib.jsonl"
    calib.write_text(
        "\n".join([_json.dumps({"conf": 0.97, "correcto": True})] * 20
                    + [_json.dumps({"conf": 0.60, "correcto": False})] * 10) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(laya, "disponible", lambda *a, **k: True)
    monkeypatch.setattr(nodes, "voto_confirmacion_router", lambda *a, **k: "directo")
    router = nodes.LayaRouter()
    apagado = "0"  # el log de decisiones no escribe en los tests

    def detalle(p_directo):
        return {"choice": "directo",
                "probabilities": {"directo": p_directo, "herramientas": 1.0 - p_directo}}

    # sin calibración: 0.70 < 0.85 → herramientas (degradación intacta)
    monkeypatch.setattr(
        call_llm, "_setting",
        lambda nombre, default=None: apagado if nombre == "LAYA_LOG_DECISIONES"
        else ("" if nombre == "LAYA_CALIBRACION_ROUTER" else default),
    )
    assert router.post({}, "¿q?", detalle(0.70)) == "herramientas"

    # con calibración α=0.10 (q=0.60, piso 0.40): 0.70 colapsa → decide local
    monkeypatch.setattr(
        call_llm, "_setting",
        lambda nombre, default=None: apagado if nombre == "LAYA_LOG_DECISIONES"
        else (str(calib) if nombre == "LAYA_CALIBRACION_ROUTER"
              else ("0.10" if nombre == "LAYA_ALPHA" else default)),
    )
    assert router.post({}, "¿q?", detalle(0.70)) == "directo"
    # 0.55 deja las dos etiquetas plausibles (0.45 >= 0.40) → ambiguo → herramientas
    assert router.post({}, "¿q?", detalle(0.55)) == "herramientas"
    # un archivo ilegible no rompe: cae al umbral fijo
    monkeypatch.setattr(
        call_llm, "_setting",
        lambda nombre, default=None: apagado if nombre == "LAYA_LOG_DECISIONES"
        else (str(tmp_path / "roto.jsonl") if nombre == "LAYA_CALIBRACION_ROUTER" else default),
    )
    assert router.post({}, "¿q?", detalle(0.70)) == "herramientas"

def test_conformal_cuantil_y_muestra_finita():
    """exp/30: el umbral SALE de la calibración con la corrección de muestra
    finita; con n chico y alpha exigente no hay cota y se deriva siempre."""
    from utils.conformal import cuantil_conformal

    puntajes = [i / 100 for i in range(1, 31)]      # 0.01 .. 0.30, n=30
    # alpha=0.05 -> índice ceil(31*0.95)=30 -> el máximo de los puntajes
    assert cuantil_conformal(puntajes, 0.05) == 0.30
    # alpha=0.02 -> índice 31 > 30: sin cota posible con este n
    assert cuantil_conformal(puntajes, 0.02) == float("inf")
    with pytest.raises(ValueError):
        cuantil_conformal(puntajes, 0.0)
    with pytest.raises(ValueError):
        cuantil_conformal([], 0.10)

def test_conformal_colapsa_o_deriva():
    """exp/30: la regla de la cascada — se decide local solo si el conjunto
    de etiquetas plausibles es un singleton; vacío o doble = derivar."""
    from utils.conformal import conjunto

    assert conjunto(0.9, 0.2) == ("elegida",)              # 0.9 >= 0.8, 0.1 < 0.8
    assert conjunto(0.5, 0.6) == ("elegida", "otra")       # ambas >= 0.4
    assert conjunto(0.6, 0.2) == ("elegida", "otra")       # 0.6 < 0.8: vacío
    assert conjunto(0.99, float("inf")) == ("elegida", "otra")

def test_conformal_cobertura_loo_respeta_la_cota():
    """exp/30: el LOO recalibra sin el caso evaluado; la cobertura estimada no
    baja de 1-alpha (con margen por ser una estimación con n chico)."""
    from utils.conformal import cobertura_loo

    casos = [{"conf": 0.95 + i / 500, "correcto": True} for i in range(20)]
    casos += [{"conf": 0.60, "correcto": False} for _ in range(10)]
    for alpha in (0.05, 0.20):
        m = cobertura_loo(casos, alpha)
        assert m["cobertura"] >= 1 - alpha - 0.03, (alpha, m)
        assert 0.0 <= m["aceptadas"] <= 1.0
        assert m["precision"] is None or 0.0 <= m["precision"] <= 1.0

@pytest.mark.datos
def test_sonda_conformal_reproduce_la_evidencia_del_router():
    """exp/30: con la evidencia ya medida (30 casos), la regla conformal
    respeta la cobertura prometida; si falta la evidencia, se saltea."""
    import json

    from utils.conformal import cobertura_loo

    ruta = RAIZ / "salidas" / "evals" / "laya_evidencia_router.json"
    if not ruta.is_file():
        pytest.skip("sin evidencia del router: corré sonda_laya.py router")
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    casos = [
        {"conf": c["conf"], "correcto": bool(c["correcto"])} for c in datos["casos"]
    ]
    for alpha in (0.10, 0.20):
        m = cobertura_loo(casos, alpha)
        assert m["cobertura"] >= 1 - alpha - 0.02, (alpha, m)
    assert len([c for c in datos["casos"] if c["conf"] >= 0.85]) == 25
