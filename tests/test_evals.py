"""Evals: bench del router, linter de trazas, costos y baseline (PR 4)."""
import pytest
from conftest import RAIZ


@pytest.fixture(autouse=True)
def _bench_en_shadow(monkeypatch):
    """El bench del router mide calibración/modelo: corre en SHADOW. La suite
    no puede depender del .env local (exp/45 puso enforce + calibración ahí y
    movía el veredicto de estos tests). Los tests que necesitan otro modo lo
    fijan explícitamente con monkeypatch (gana el último setenv)."""
    monkeypatch.setenv("LAYA_MODO", "shadow")


def test_evals_tool_del_chat(tmp_path, monkeypatch):
    """La tool evals del chat corre el pipeline y devuelve la ruta del informe."""
    import modules.evals as me

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    runs = tmp_path / "runs"
    runs.mkdir()
    # una traza mínima válida: par (nodo, accion) canónico, sin violaciones
    (runs / "sesion.jsonl").write_text(
        '{"nodo": "GetQuestion", "accion": "exit", "seg": 1.0}\n', encoding="utf-8")
    # bench sin test de router (la ruta externa no existe en el test) y sin LLM
    monkeypatch.setattr(me, "DIR_RUNS", runs)
    salida = tmp_path / "evals_out"
    r = me.evals(dir_runs=str(runs), salida=str(salida))
    assert "Informe de evals generado" in r
    informes = list(salida.glob("evals_*.md"))
    assert informes, "no se escribió el informe de evals"
    assert "evals" in {t["function"]["name"] for t in me.TOOLS}

def test_evals_tool_rechaza_carpeta_inexistente(tmp_path, monkeypatch):
    """Una carpeta de trazas que no existe devuelve ERROR, no excepción."""
    import modules.evals as me

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    r = me.evals(dir_runs=str(tmp_path / "no_existe"))
    assert r.startswith("ERROR:")

# Evals (mesa 1, replay-evals): bench del router, linter de trazas, costos

def _bench_con(fake_agente):
    """Corre correr_bench() con un agente fake (system_one), sin cargar laya."""
    from evals import TEST_ROUTER, correr_bench

    if not TEST_ROUTER.is_file():
        pytest.skip(f"falta el test del router: {TEST_ROUTER} (BMO_TASKS_DIR)")

    return correr_bench(agente=fake_agente)

@pytest.mark.bmo
def test_evals_bench_score_y_ece_ok():
    """Un agente perfecto: score con compuerta y crudo = 100%, ECE = 0."""

    # el fake responde SIEMPRE lo esperado con confianza 1.0
    import json

    from evals import TEST_ROUTER
    from nodes import PREGUNTA_ROUTER  # noqa: F401  (contrato importado)

    if not TEST_ROUTER.is_file():
        pytest.skip(f"falta el test del router: {TEST_ROUTER}")

    esperados = {}
    for linea in TEST_ROUTER.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            c = json.loads(linea)
            esperados[c["fields"]["pregunta"]] = c["answers"]["necesita_herramientas"]

    class AgentePerfecto:
        def system_one(self, estado, preguntas, lang="es"):
            esperado = esperados[estado["pregunta"]]
            # la política de producción (utils.laya_routing.decide) lee el PAR
            # de probabilidades, no solo answer_confidence: el fake devuelve lo
            # mismo que devuelve preguntar_detalle()
            otras = {"directo": "herramientas", "herramientas": "directo"}
            return {"answers": {"necesita_herramientas":
                                {"choice": esperado,
                                 "probabilities": {esperado: 1.0,
                                                   otras[esperado]: 0.0}}}}

    bench, err = _bench_con(AgentePerfecto())
    assert err is None and bench["estado"] == "ok"
    assert bench["score"] == 1.0 and bench["score_crudo"] == 1.0
    assert bench["ece"] == 0.0

@pytest.mark.bmo
def test_evals_bench_ece_pesimista():
    """Un agente que dice directo con conf 1.0 pero se equivoca siempre: ECE
    alto, calcularlo a mano sobre la decisión cruda."""

    from nodes import PREGUNTA_ROUTER  # noqa: F401

    class AgenteMalCalibrado:
        def system_one(self, estado, preguntas, lang="es"):
            return {"answers": {"necesita_herramientas":
                                {"choice": "directo", "answer_confidence": 1.0}}}

    bench, err = _bench_con(AgenteMalCalibrado())
    assert err is None
    # casos esperado=directo (13) aciertan crudo; esperado=herramientas (17) no
    assert abs(bench["score_crudo"] - 13 / 30) < 1e-4
    # ECE = |1.0 - 13/30| porque todo cae en el bin [0.9, 1.0]
    assert abs(bench["ece"] - (1 - 13 / 30)) < 1e-3

def test_evals_bench_contra_baseline_mejora_y_regresion(tmp_path):
    """comparar_baseline: PRIMERA CORRIDA sin archivo, OK si mejora,
    REGRESIÓN si el score baja (con el mismo shape del bench)."""
    from evals import comparar_baseline

    ruta = tmp_path / "bench_router.json"
    nuevo = {"score": 0.9, "score_crudo": 0.9, "ece": 0.05}
    # sin baseline
    assert comparar_baseline(nuevo, ruta=ruta)["veredicto"] == "PRIMERA CORRIDA"

    # baseline peor → OK
    ruta.write_text('{"score": 0.8, "ece": 0.10}', encoding="utf-8")
    r = comparar_baseline(nuevo, ruta=ruta)
    assert r["veredicto"] == "OK"
    assert r["delta"]["score"] == 0.1 and r["delta"]["ece"] == -0.05

    # baseline mejor → REGRESIÓN
    ruta.write_text('{"score": 0.95, "ece": 0.02}', encoding="utf-8")
    r = comparar_baseline(nuevo, ruta=ruta)
    assert r["veredicto"] == "REGRESIÓN"
    assert r["delta"]["score"] < 0

    # baseline sin score (corrida degradada) no es referencia
    ruta.write_text('{"score": null, "ece": null}', encoding="utf-8")
    assert comparar_baseline(nuevo, ruta=ruta)["veredicto"] == "PRIMERA CORRIDA"

@pytest.mark.bmo
def test_evals_bench_laya_ausente_degrada(monkeypatch):
    """Sin laya: correr_bench devuelve estado 'no disponible' y un motivo, sin
    crashear (la degradación prometida)."""
    import evals

    if not evals.TEST_ROUTER.is_file():
        pytest.skip(f"falta el test del router: {evals.TEST_ROUTER}")

    def revienta(*a, **k):
        raise RuntimeError("laya no disponible: prueba")

    monkeypatch.setattr("utils.laya.agente", revienta)
    bench, motivo = evals.correr_bench()
    assert bench["estado"] == "no disponible"
    assert bench["score"] is None and "laya no disponible" in motivo

def _linea(nodo, accion, seg=0.0, ts=0.0):
    return {"ts": ts, "nodo": nodo, "accion": accion, "seg": seg}

def test_evals_linter_traza_limpia_sin_falsos_positivos():
    """Una traza del chat bien formada (router → tool → ExecuteTools →
    answer) pasa el linter sin violaciones."""
    from evals import linter_traza

    eventos = [
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("AgentStep", "tool"),
        _linea("read_file", "ok", 0.001),
        _linea("ExecuteTools", "default", 0.01),
        _linea("AgentStep", "answer"),
        _linea("GetQuestion", "exit"),
        _linea("ExitChat", "None"),
    ]
    assert linter_traza(eventos) == []

def test_evals_linter_detecta_agentstep_sin_executetools():
    """(a) AgentStep tool seguido de otro AgentStep sin ExecuteTools."""
    from evals import linter_traza

    eventos = [
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("AgentStep", "tool"),
        _linea("AgentStep", "tool"),  # nunca hubo ExecuteTools
        _linea("AgentStep", "answer"),
    ]
    viol = linter_traza(eventos)
    assert any(v[0] == "a" for v in viol), viol

def test_evals_linter_detecta_accion_desconocida():
    """(c) un par (nodo, accion) fuera del conjunto canónico."""
    from evals import linter_traza

    eventos = [
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("NodoInventado", "hace_algo"),
        _linea("AgentStep", "answer"),
    ]
    viol = linter_traza(eventos)
    assert any(v[0] == "c" and "NodoInventado" in v[2] for v in viol), viol
    # y un par conocido no dispara (c)
    assert not any(v[0] == "c" for v in linter_traza([
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("ExecuteTools", "default"),
    ]))

def test_evals_linter_detecta_executetools_largo_sin_tools():
    """(d) ExecuteTools > 120s sin eventos de tools propios (el ciego viejo)."""
    from evals import linter_traza

    eventos = [
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("AgentStep", "tool"),
        _linea("ExecuteTools", "default", seg=300.0),  # largo y sin tools
        _linea("AgentStep", "answer"),
    ]
    viol = linter_traza(eventos)
    assert any(v[0] == "d" for v in viol), viol
    # con una tool propia, deja de ser ciego
    con_tool = [
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("AgentStep", "tool"),
        _linea("run_command", "ok", seg=200.0),  # evento propio
        _linea("ExecuteTools", "default", seg=300.0),
        _linea("AgentStep", "answer"),
    ]
    assert not any(v[0] == "d" for v in linter_traza(con_tool))

def test_evals_linter_detecta_turno_sin_router():
    """(b) con router activo en la traza, un turno que salta de GetQuestion a
    AgentStep answer sin pasar por LayaRouter."""
    from evals import linter_traza

    eventos = [
        _linea("GetQuestion", "continue"),
        _linea("AgentStep", "answer"),  # sin LayaRouter
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),  # este turno sí
        _linea("AgentStep", "answer"),
        _linea("GetQuestion", "exit"),
    ]
    viol = linter_traza(eventos)
    assert any(v[0] == "b" for v in viol), viol

def test_evals_linter_runs_reporta_por_invariante(tmp_path):
    """linter_runs agrupa violaciones por invariante y por archivo."""
    import json

    import evals

    limpia = tmp_path / "limpia.jsonl"
    limpia.write_text(json.dumps(_linea("GetQuestion", "exit")) + "\n"
                      + json.dumps(_linea("ExitChat", "None")) + "\n", encoding="utf-8")
    sucia = tmp_path / "sucia.jsonl"
    sucia.write_text("\n".join(json.dumps(e) for e in [
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("AgentStep", "tool"),
        _linea("AgentStep", "answer"),  # (a): sin ExecuteTools
    ]) + "\n", encoding="utf-8")

    resumen = evals.linter_runs(tmp_path)
    assert resumen["total"] == 2
    assert resumen["por_invariante"].get("a", 0) == 1
    assert resumen["por_archivo"]["sucia.jsonl"]
    assert not resumen["por_archivo"].get("limpia.jsonl")

def test_evals_costos_ordena_por_costo(tmp_path):
    """costos_runs ordena de más caro a más barato y calcula nodo dominante."""
    import json

    import evals

    def _escribir(nombre, eventos):
        (tmp_path / nombre).write_text(
            "\n".join(json.dumps(e) for e in eventos) + "\n", encoding="utf-8")

    _escribir("20260101_100000.jsonl", [
        _linea("AgentStep", "answer", seg=2.0),
        _linea("read_file", "ok", seg=1.0),
    ])
    _escribir("20260101_110000.jsonl", [
        _linea("AgentStep", "tool", seg=10.0),
        _linea("ExecuteTools", "default", seg=5.0),
        _linea("read_file", "ok", seg=0.0),
    ])

    sesiones = evals.costos_runs(tmp_path)
    assert [s["archivo"] for s in sesiones] == [
        "20260101_110000.jsonl", "20260101_100000.jsonl"]
    cara = sesiones[0]
    # Contrato nuevo (A22): "total" es la PARED estimada — el AgentStep de 10 s
    # envuelve al ExecuteTools de 5 s, que envuelve a la tool. Sumar los
    # inclusivos daba 15 s para 10 s de corrida; la suma cruda sigue disponible
    # en "total_inclusivo" y lo anidado se cuenta aparte.
    assert cara["total"] == 10.0
    assert cara["total_inclusivo"] == 15.0
    assert cara["anidados"] == 2
    assert cara["dominante"] == "AgentStep"
    assert cara["tools"] == 1
    assert cara["fecha"] == "2026-01-01 11:00:00"

def test_tool_evals_no_pisa_el_baseline(monkeypatch, tmp_path):
    """exp/2: la tool del chat corre el pipeline de evals COMPARANDO contra
    el baseline pero sin guardarlo — el ancla de medición no se sobrescribe
    desde una conversación (el CLI sí actualiza, como siempre)."""
    import modules.evals as mod

    llamadas = {"guardar": 0}
    monkeypatch.setattr("evals.correr_bench", lambda agente=None: ({"score": 1.0}, None))
    monkeypatch.setattr("evals.comparar_baseline", lambda b: {"veredicto": "OK"})
    monkeypatch.setattr("evals.guardar_baseline", lambda *a, **k: llamadas.__setitem__("guardar", llamadas["guardar"] + 1))
    monkeypatch.setattr("evals.linter_runs", lambda d=None: {})
    monkeypatch.setattr("evals.costos_runs", lambda d=None: [])
    monkeypatch.setattr("evals.informe_markdown", lambda *a, **k: "# evals")

    # .runs puede no existir en una PC nueva: el default apunta a uno vacío.
    # Todo en tmp: el tmp de pytest es raíz permitida (conftest) y el test no
    # ensucia salidas/banco (review de exp/71).
    vacio = tmp_path / "runs_vacio"
    vacio.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod, "DIR_RUNS", vacio)
    r = mod.evals(dir_runs=None, salida=str(tmp_path / "banco"))
    assert "Informe de evals generado" in r
    assert llamadas["guardar"] == 0, "la tool del chat NO guarda baseline"

def test_el_linter_acepta_la_caminata_con_contexto():
    """X95: Contexto (la compacción antes de cada llamada) es una acción
    canónica del chat; una traza del grafo nuevo no viola ningún invariante."""
    from evals import linter_traza

    traza = [{"nodo": n, "accion": a, "seg": 0.1} for n, a in (
        ("GetQuestion", "continue"), ("PreFetch", "continue"), ("LayaRouter", "herramientas"),
        ("Contexto", "herramientas"), ("AgentStep", "tool"), ("read_file", "ok"),
        ("ExecuteTools", "default"), ("Contexto", "herramientas"), ("AgentStep", "answer"),
        ("LayaRouter", "directo"), ("Contexto", "directo"), ("DirectAnswer", "answer"))]
    assert linter_traza(traza) == []


def test_el_linter_no_cuenta_los_eventos_de_bookkeeping():
    """X97: desde exp/89 cada llamada al LLM deja `llm/usage` en la traza, y
    el HITL y las políticas dejan los suyos; el linter los contaba como
    acción desconocida (c) — una violación falsa por llamada al modelo."""
    from evals import linter_traza

    traza = [{"nodo": n, "accion": a, "seg": 0.0} for n, a in (
        ("GetQuestion", "continue"), ("PreFetch", "continue"), ("LayaRouter", "herramientas"),
        ("Contexto", "herramientas"), ("llm", "usage"), ("AgentStep", "tool"),
        ("hitl_comando", "aprobado"), ("run_command", "ok"), ("ExecuteTools", "default"),
        ("Observar", "default"), ("corte_no_progreso", "politica"), ("Contexto", "cierre"),
        ("llm", "usage"), ("Cierre", "answer"), ("VerificarCitas", "default"))]
    assert linter_traza(traza) == []
    assert linter_traza([{"nodo": "llm", "accion": "rechazado", "seg": 0.0}]) == [
        ("c", 0, "acción desconocida: llm/rechazado")]


def test_un_turno_cerrado_por_presupuesto_cuenta_como_respuesta():
    """X96: un turno que agota el presupuesto termina en Cierre/answer. El
    linter tiene que reconocerlo como respuesta (invariante b) y como acción
    canónica (c); sin eso el turno quedaba "sin respuesta" — el mismo punto
    ciego que X95 encontró con PreFetch y VerificarCitas."""
    from evals import _turno_del_chat, linter_traza

    traza = [{"nodo": n, "accion": a, "seg": 0.1} for n, a in (
        ("GetQuestion", "continue"), ("PreFetch", "continue"), ("LayaRouter", "herramientas"),
        ("Contexto", "herramientas"), ("AgentStep", "tool"), ("read_file", "ok"),
        ("ExecuteTools", "default"), ("Observar", "default"), ("Contexto", "cierre"),
        ("Cierre", "answer"), ("VerificarCitas", "default"))]
    assert linter_traza(traza) == []
    assert _turno_del_chat(traza, 0) == (True, True, True)


def test_el_linter_reconoce_las_acciones_y_tools_que_faltaban():
    """exp/37: el linter marcaba como desconocidas una arista real del juez
    (Judge/retry, juez.py:233) y cuatro tools de módulos (visión y a2a), lo que
    inflaba las violaciones de 214 trazas (27 de 38)."""
    from evals import _accion_valida

    assert _accion_valida("Judge", "retry")
    assert all(_accion_valida(t, "ok") for t in ("ver_imagen", "ver_pdf", "agentes_remotos", "a2a_tarea"))
    # el README ya no documenta un subcomando que no existe
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert "main.py carga_trazas" not in readme
    assert "python3 carga_trazas.py" in readme
