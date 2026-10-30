"""Evals: linter de trazas y costos (PR 4; el bench del router se fue en X106)."""
from conftest import RAIZ


def test_evals_tool_del_chat(tmp_path, monkeypatch):
    """La tool evals del chat corre el pipeline y devuelve la ruta del informe."""
    import modules.evals as me

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    runs = tmp_path / "runs"
    runs.mkdir()
    # una traza mínima válida: par (nodo, accion) canónico, sin violaciones
    (runs / "sesion.jsonl").write_text(
        '{"nodo": "GetQuestion", "accion": "exit", "seg": 1.0}\n', encoding="utf-8")
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

# Evals (mesa 1, replay-evals): linter de trazas y costos


def _linea(nodo, accion, seg=0.0, ts=0.0):
    return {"ts": ts, "nodo": nodo, "accion": accion, "seg": seg}

def test_evals_linter_traza_limpia_sin_falsos_positivos():
    """Una traza del chat bien formada (skills → tool → ExecuteTools →
    answer) pasa el linter sin violaciones."""
    from evals import linter_traza

    eventos = [
        _linea("GetQuestion", "continue"),
        _linea("Skills", "continue"),
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
        _linea("Skills", "continue"),
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
        _linea("Skills", "continue"),
        _linea("NodoInventado", "hace_algo"),
        _linea("AgentStep", "answer"),
    ]
    viol = linter_traza(eventos)
    assert any(v[0] == "c" and "NodoInventado" in v[2] for v in viol), viol
    # y un par conocido no dispara (c)
    assert not any(v[0] == "c" for v in linter_traza([
        _linea("GetQuestion", "continue"),
        _linea("Skills", "continue"),
        _linea("ExecuteTools", "default"),
    ]))

def test_evals_linter_detecta_executetools_largo_sin_tools():
    """(d) ExecuteTools > 120s sin eventos de tools propios (el ciego viejo)."""
    from evals import linter_traza

    eventos = [
        _linea("GetQuestion", "continue"),
        _linea("Skills", "continue"),
        _linea("AgentStep", "tool"),
        _linea("ExecuteTools", "default", seg=300.0),  # largo y sin tools
        _linea("AgentStep", "answer"),
    ]
    viol = linter_traza(eventos)
    assert any(v[0] == "d" for v in viol), viol
    # con una tool propia, deja de ser ciego
    con_tool = [
        _linea("GetQuestion", "continue"),
        _linea("Skills", "continue"),
        _linea("AgentStep", "tool"),
        _linea("run_command", "ok", seg=200.0),  # evento propio
        _linea("ExecuteTools", "default", seg=300.0),
        _linea("AgentStep", "answer"),
    ]
    assert not any(v[0] == "d" for v in linter_traza(con_tool))


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
        _linea("Skills", "continue"),
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


def test_el_linter_acepta_la_caminata_con_contexto():
    """X95: Contexto (la compacción antes de cada llamada) es una acción
    canónica del chat; una traza del grafo nuevo no viola ningún invariante."""
    from evals import linter_traza

    traza = [{"nodo": n, "accion": a, "seg": 0.1} for n, a in (
        ("GetQuestion", "continue"), ("PreFetch", "continue"), ("Skills", "continue"),
        ("Contexto", "herramientas"), ("AgentStep", "tool"), ("read_file", "ok"),
        ("ExecuteTools", "default"), ("Contexto", "herramientas"), ("AgentStep", "answer"))]
    assert linter_traza(traza) == []


def test_el_linter_no_cuenta_los_eventos_de_bookkeeping():
    """X97: desde exp/89 cada llamada al LLM deja `llm/usage` en la traza, y
    el HITL y las políticas dejan los suyos; el linter los contaba como
    acción desconocida (c) — una violación falsa por llamada al modelo."""
    from evals import linter_traza

    traza = [{"nodo": n, "accion": a, "seg": 0.0} for n, a in (
        ("GetQuestion", "continue"), ("PreFetch", "continue"), ("Skills", "continue"),
        ("Contexto", "herramientas"), ("llm", "usage"), ("AgentStep", "tool"),
        ("hitl_comando", "aprobado"), ("run_command", "ok"), ("ExecuteTools", "default"),
        ("Observar", "default"), ("corte_no_progreso", "politica"), ("Contexto", "cierre"),
        ("llm", "usage"), ("Cierre", "answer"), ("VerificarCitas", "default"))]
    assert linter_traza(traza) == []
    assert linter_traza([{"nodo": "llm", "accion": "rechazado", "seg": 0.0}]) == [
        ("c", 0, "acción desconocida: llm/rechazado")]


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


def test_un_turno_cerrado_por_presupuesto_es_canonico():
    """X96: un turno que agota el presupuesto termina en Cierre/answer, una
    acción canónica (c): sin violaciones."""
    from evals import linter_traza

    traza = [{"nodo": n, "accion": a, "seg": 0.1} for n, a in (
        ("GetQuestion", "continue"), ("PreFetch", "continue"), ("Skills", "continue"),
        ("Contexto", "herramientas"), ("AgentStep", "tool"), ("read_file", "ok"),
        ("ExecuteTools", "default"), ("Observar", "default"), ("Contexto", "cierre"),
        ("Cierre", "answer"), ("VerificarCitas", "default"))]
    assert linter_traza(traza) == []


def test_las_trazas_viejas_del_router_siguen_siendo_canonicas():
    """X106: el linter juzga el cableado de cada traza; las de antes del un
    solo camino (router y ruta directa) no se vuelven violaciones."""
    from evals import linter_traza

    vieja = [{"nodo": n, "accion": a, "seg": 0.1} for n, a in (
        ("GetQuestion", "continue"), ("LayaRouter", "directo"), ("Contexto", "directo"),
        ("DirectAnswer", "answer"), ("GetQuestion", "continue"), ("LayaRouter", "herramientas"),
        ("Contexto", "herramientas"), ("AgentStep", "answer"))]
    assert linter_traza(vieja) == []
