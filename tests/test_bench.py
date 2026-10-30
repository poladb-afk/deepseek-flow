"""Banco: marcadores, bench de respuestas/citas y bench_supervisor (PR 4)."""
import pytest
from conftest import RAIZ


def test_banco_contar_marcadores():
    """El conteo de marcadores es la señal medible del banco: cada línea de la
    terminal se suma al marcador cuya regex matchea."""
    from banco.banco import MARCADORES, contar_marcadores

    # la compacción se anuncia con su propia marca
    conteo = contar_marcadores("[compacción] zona fría: 4 mensajes → resumen")
    assert conteo["compaccion"] == 1

    # varias señales en varias líneas: cada una suma por ocurrencia en su línea
    texto = "  [skill] revision activo — a\n  [skill] tdd activo — b\n⚙ ronda 2/5\n(s/n): 2x"
    conteo = contar_marcadores(texto)
    assert conteo["skill"] == 2 and conteo["ronda"] == 1 and conteo["hitl_prompt"] == 1

    # texto sin señales: no aparece ninguna clave (solo se cuentan > 0)
    conteo = contar_marcadores("charla normal")
    assert conteo == {}
    assert set(MARCADORES)  # el catálogo de señales es no vacío

# exp/20 — candados del bench del juez (funciones puras, sin LLM)

def test_bench_respuesta_ok_todos_uno_y_case_insensitive():
    """respuesta_ok: con TODOS los `contiene` → True; falta uno → False;
    con `contiene_alguno` alcanza uno → True y ninguno → False; y todo el
    matching es case-insensitive."""
    import bench_juez as bj

    # todos los tokens presentes
    assert bj.respuesta_ok("La respuesta menciona OLLAMA y MongoDB.",
                           {"contiene": ["ollama", "mongodb"]}) is True
    # falta uno
    assert bj.respuesta_ok("La respuesta menciona OLLAMA.",
                           {"contiene": ["ollama", "mongodb"]}) is False
    # case-insensitive en ambos sentidos
    assert bj.respuesta_ok("usa ChromaDB", {"contiene": ["chromadb"]}) is True
    assert bj.respuesta_ok("usa chromadb", {"contiene": ["ChromaDB"]}) is True
    # contiene_alguno: uno presente
    assert bj.respuesta_ok("responde con sqlite",
                           {"contiene_alguno": ["sqlite", "postgres"]}) is True
    # contiene_alguno: ninguno presente
    assert bj.respuesta_ok("responde con mysql",
                           {"contiene_alguno": ["sqlite", "postgres"]}) is False
    # combina: contiene (todos) + contiene_alguno (al menos uno)
    caso = {"contiene": ["python"], "contiene_alguno": ["fastapi", "flask"]}
    assert bj.respuesta_ok("python con Flask", caso) is True
    assert bj.respuesta_ok("python con django", caso) is False
    # sin tokens exigidos no hay nada que falle
    assert bj.respuesta_ok("lo que sea", {}) is True

def test_bench_cita_ok_contra_fixture_real(tmp_path):
    """cita_ok contra un fixture REAL en tmp_path: cita correcta → True;
    token en la línea SIGUIENTE a la citada → True (ventana de 2, igual que
    juez.Judge.prep); línea que no contiene el token → False; ruta equivocada
    → False; caso sin cita_archivo → None; línea beyond EOF → False."""
    import bench_juez as bj

    fixture = tmp_path / "modulo.py"
    fixture.write_text("linea uno\nla clave es OLLAMA\nlinea tres\n", encoding="utf-8")

    # 1) cita correcta: SU línea exacta contiene el token
    caso = {"cita_archivo": "modulo.py", "cita_contiene": ["ollama"]}
    assert bj.cita_ok(f"según {fixture}:2 eso queda claro", caso) is True

    # 1b) VENTANA de 2: se cita la línea 1 y el token está en la 2 (siguiente).
    # Producción lee offset=1, limit=2 → verifica; el bench debe coincidir.
    assert bj.cita_ok(f"según {fixture}:1 eso queda claro", caso) is True

    # 2) misma ruta y línea pero SIN el token esperado → False
    caso_token = {"cita_archivo": "modulo.py", "cita_contiene": ["mongodb"]}
    assert bj.cita_ok(f"según {fixture}:2 acá", caso_token) is False

    # 3) ruta equivocada (la cita no termina en cita_archivo) → False
    caso_ruta = {"cita_archivo": "otro.py", "cita_contiene": ["ollama"]}
    assert bj.cita_ok(f"según {fixture}:2 acá", caso_ruta) is False

    # 4) caso sin cita_archivo → None (no aplica)
    assert bj.cita_ok(f"según {fixture}:2 acá", {"cita_contiene": ["ollama"]}) is None

    # 5) línea beyond EOF → False (no explota)
    caso_eof = {"cita_archivo": "modulo.py", "cita_contiene": ["ollama"]}
    assert bj.cita_ok(f"según {fixture}:99 acá", caso_eof) is False

    # sin citas en el texto tampoco: False (el caso pide cita)
    assert bj.cita_ok("no cito nada", {"cita_archivo": "modulo.py"}) is False

def test_bench_baseline_guarda_compara_y_no_pisa(tmp_path, monkeypatch):
    """baseline: guardar → comparar reporta delta; sin la flag NO se pisa
    (guardar una vez, cambiar el score esperado en memoria, verificar que el
    archivo en disco no cambió)."""
    import json

    import bench_juez as bj

    ruta = tmp_path / "bench_juez.json"
    bench = {"n": 3, "respuesta_ok": 0.9, "cita_ok": 0.8, "n_con_cita": 2}
    assert bj.guardar_baseline(bench, ruta=ruta, sha="abc123") is not None

    # comparar contra el guardado: delta 0 → OK
    comp = bj.comparar_baseline({"respuesta_ok": 0.9, "cita_ok": 0.8}, ruta=ruta)
    assert comp["veredicto"] == "OK"
    assert comp["delta"]["respuesta_ok"] == 0.0

    # bajar el score → REGRESIÓN
    comp_baja = bj.comparar_baseline({"respuesta_ok": 0.5, "cita_ok": 0.8}, ruta=ruta)
    assert comp_baja["veredicto"] == "REGRESIÓN"
    assert comp_baja["delta"]["respuesta_ok"] < 0

    # NO se pisa: sin --actualizar-baseline, comparar no toca el archivo
    antes = ruta.read_text(encoding="utf-8")
    bj.comparar_baseline({"respuesta_ok": 0.1, "cita_ok": 0.1}, ruta=ruta)
    assert ruta.read_text(encoding="utf-8") == antes
    assert json.loads(antes)["respuesta_ok"] == 0.9

    # sin baseline guardado → PRIMERA CORRIDA
    comp_nuevo = bj.comparar_baseline({"respuesta_ok": 1.0, "cita_ok": 1.0},
                                      ruta=tmp_path / "no_existe.json")
    assert comp_nuevo["veredicto"] == "PRIMERA CORRIDA"

def test_bench_cargar_casos_errores_claros(tmp_path):
    """preguntas inválidas (JSON roto / falta id o pregunta / archivo
    inexistente / vacío) → SystemExit con mensaje claro, nunca silencio."""
    import pytest

    import bench_juez as bj

    # JSON roto
    roto = tmp_path / "roto.jsonl"
    roto.write_text('{"id": "a", "pregunta": "x"\n', encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        bj.cargar_casos(roto)
    assert "JSON inválido" in str(e.value)

    # falta id
    sin_id = tmp_path / "sin_id.jsonl"
    sin_id.write_text('{"pregunta": "x"}\n', encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        bj.cargar_casos(sin_id)
    assert "id" in str(e.value)

    # falta pregunta
    sin_preg = tmp_path / "sin_preg.jsonl"
    sin_preg.write_text('{"id": "a"}\n', encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        bj.cargar_casos(sin_preg)
    assert "pregunta" in str(e.value)

    # archivo inexistente
    with pytest.raises(SystemExit) as e:
        bj.cargar_casos(tmp_path / "no_esta.jsonl")
    assert "no existe" in str(e.value)

    # vacío
    vacio = tmp_path / "vacio.jsonl"
    vacio.write_text("\n\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        bj.cargar_casos(vacio)
    assert "no tiene casos" in str(e.value)

    # camino feliz: dos casos válidos
    ok = tmp_path / "ok.jsonl"
    ok.write_text('{"id": "a", "pregunta": "uno"}\n{"id": "b", "pregunta": "dos"}\n',
                  encoding="utf-8")
    casos = bj.cargar_casos(ok)
    assert [c["id"] for c in casos] == ["a", "b"]

def test_bench_correr_evalua_y_agrega_con_responder_fake(tmp_path):
    """El runner secuencial con un `responder` inyectado (sin LLM) evalúa
    cada caso con código puro y agrega las métricas. También cubre que
    generar() escribe el informe sin pisar el baseline."""
    import bench_juez as bj

    fixture = tmp_path / "modulo.py"
    fixture.write_text("linea uno\nla clave es OLLAMA\nlinea tres\n", encoding="utf-8")

    casos = [
        {"id": "ok", "pregunta": "q1", "contiene": ["ollama"]},
        {"id": "falla", "pregunta": "q2", "contiene": ["inexistente"]},
    ]
    respuestas = {
        "q1": ("menciona ollama", None),
        "q2": ("no dice nada útil", None),
    }

    def fake(pregunta):
        return respuestas[pregunta]

    bench = bj.correr(casos, responder=fake)
    assert bench["n"] == 2
    assert bench["respuesta_ok"] == 0.5
    # q1 pasó, q2 falló y trae su razón
    por_id = {f["id"]: f for f in bench["filas"]}
    assert por_id["ok"]["respuesta_ok"] is True
    assert por_id["falla"]["respuesta_ok"] is False
    assert any("inexistente" in r for r in por_id["falla"]["razones"])

    # generar() escribe el informe y NO pisa el baseline (sin la flag)
    preguntas = tmp_path / "preguntas.jsonl"
    preguntas.write_text("\n".join(
        __import__("json").dumps(c) for c in casos), encoding="utf-8")
    # estado del baseline REAL antes de escribir el informe: el assert
    # compara contra esto, así que puede fallar de verdad.
    def _baseline():
        return (bj.BASELINE.is_file(),
                bj.BASELINE.stat().st_mtime_ns if bj.BASELINE.is_file() else None)

    baseline_antes = _baseline()
    destino = bj.generar(preguntas=preguntas, dir_salida=tmp_path / "evals",
                         responder=fake, sha="deadbeef")
    assert destino.is_file()
    assert "respuesta_ok" in destino.read_text(encoding="utf-8")
    assert _baseline() == baseline_antes, "generar() sin --baseline tocó el baseline real"

def test_bench_correr_contiene_excepcion_por_caso(tmp_path):
    """CONTENCIÓN por caso (correctivo del exp/20): un responder que Lanza
    para UN caso no mata el bench entero. La fila del caso explosivo queda
    registrada como fallo (respuesta_ok=False, cita_ok=None, respuesta=None)
    con la excepción en razones, y el bench completo devuelve n filas."""
    import bench_juez as bj

    casos = [
        {"id": "bueno1", "pregunta": "q1", "contiene": ["ollama"]},
        {"id": "explosivo", "pregunta": "q2", "contiene": ["x"]},
        {"id": "bueno2", "pregunta": "q3", "contiene": ["ollama"]},
    ]

    def fake(pregunta):
        if pregunta == "q2":
            raise RuntimeError("verdict inválido")
        return ("menciona ollama", None)

    bench = bj.correr(casos, responder=fake)

    # el bench completo devuelve n filas pese al caso explosivo
    assert bench["n"] == 3
    por_id = {f["id"]: f for f in bench["filas"]}
    # los casos sanos siguen evaluándose normalmente
    assert por_id["bueno1"]["respuesta_ok"] is True
    assert por_id["bueno2"]["respuesta_ok"] is True
    # el caso explosivo queda registrado como fallo con la excepción
    exp = por_id["explosivo"]
    assert exp["respuesta_ok"] is False
    assert exp["cita_ok"] is None
    assert exp["respuesta"] is None
    assert len(exp["razones"]) == 1
    assert exp["razones"][0].startswith("excepción: RuntimeError: ")
    assert "verdict inválido" in exp["razones"][0]
    # 2 de 3 pasaron
    assert bench["respuesta_ok"] == round(2 / 3, 4)

def test_bench_correr_recorta_causa_de_excepcion():
    """La causa de la excepción se recorta a ~200 chars para que una traza
    gigante no ensucie la fila."""
    import bench_juez as bj

    def fake(pregunta):
        raise ValueError("E" * 500)

    bench = bj.correr([{"id": "x", "pregunta": "q"}], responder=fake)
    razon = bench["filas"][0]["razones"][0]
    assert razon.startswith("excepción: ValueError: ")
    assert len(razon) == len("excepción: ValueError: ") + 200

# bench_supervisor — verificación pura, contador, agente plano y contención
# (banco/specs/bench_supervisor.md; sin LLM real, todo con fakes)

def _import_bench_supervisor():
    import sys

    sys.path.insert(0, str(RAIZ / "banco"))
    import bench_supervisor
    return bench_supervisor

def test_bench_supervisor_verificaciones_pasan_y_fallan():
    """Cada verificación con un texto que pasa y uno que no — incluida la
    dinámica de contar-utils (el número se calcula AHORA: si cambia la carpeta,
    cambia la verdad)."""
    import sys

    sys.path.insert(0, str(RAIZ / "banco"))
    import bench_supervisor as bs

    # contar-utils: el número REAL de .py en utils/ es la verdad dinámica
    n_utils = len(list((RAIZ / "utils").glob("*.py")))
    assert bs.verificar("contar-utils", f"hay {n_utils} archivos .py") is True
    assert bs.verificar("contar-utils", f"hay {n_utils + 1} archivos .py") is False
    # un número que CONTIENE al correcto como substring no lo satisface
    assert bs.verificar("contar-utils", f"hay {int(f'{n_utils}1')} archivos") is False
    # y la verdad es de verdad dinámica: contando otra carpeta cambia el número
    n_tests = len(list((RAIZ / "tests").glob("*.py")))
    assert n_tests != n_utils, "el fixture se rompería si utils/ y tests/ empataran"

    # constante-max-pasos
    assert bs.verificar("constante-max-pasos", "MAX_PASOS vale 5") is True
    assert bs.verificar("constante-max-pasos", "MAX_PASOS vale 6") is False

    # firma-veredicto: 'met' + uno de {uncertain, not met}
    assert bs.verificar("firma-veredicto", "devuelve 'met' o 'uncertain'") is True
    assert bs.verificar("firma-veredicto", "devuelve MET o NOT MET") is True
    assert bs.verificar("firma-veredicto", "solo devuelve met") is False
    assert bs.verificar("firma-veredicto", "no dice nada") is False

    # linea-marcadores: el número REAL de la definición en banco/banco.py
    lineas = bs._lineas_marcadores()
    assert lineas, "banco/banco.py debería definir MARCADORES"
    assert bs.verificar("linea-marcadores", f"está en banco/banco.py:{lineas[0]}") is True
    assert bs.verificar("linea-marcadores", "está en banco/banco.py:9999") is False

    # tablas-trazas: si hay trazas.db, el conteo real es la verdad; si no, None
    import sqlite3

    db = bs._buscar_db_trazas()
    if db is None:
        assert bs.verificar("tablas-trazas", "lo que sea") is None
    else:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            n_tab = con.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        finally:
            con.close()
        assert bs.verificar("tablas-trazas", f"la base tiene {n_tab} tablas") is True
        assert bs.verificar("tablas-trazas", f"la base tiene {n_tab + 1} tablas") is False

    # conteo-routing: conteo real de salidas/routing.jsonl (o None si no existe)
    routing = RAIZ / "salidas" / "routing.jsonl"
    if routing.is_file():
        n_rut = len(routing.read_text(encoding="utf-8").splitlines())
        assert bs.verificar("conteo-routing", f"son {n_rut} decisiones") is True
        assert bs.verificar("conteo-routing", "son 0 decisiones") == (n_rut == 0)
    else:
        assert bs.verificar("conteo-routing", "cualquier cosa") is None

    # id sin verificación → KeyError (nunca un silencio)
    with pytest.raises(KeyError):
        bs.verificar("no-existe", "texto")

def test_bench_supervisor_contador_envuelve_y_cuenta():
    """El contador envuelve call_llm y call_llm_agent con fakes (sin red) y
    cuenta cada invocación; restaurar() devuelve el módulo a lo original."""
    import sys
    from types import SimpleNamespace

    sys.path.insert(0, str(RAIZ / "banco"))
    import bench_supervisor as bs

    # Un fake con la FORMA de un módulo real: las funciones viven en el
    # `__dict__` del objeto (como los callables de utils.call_llm), así la
    # restauración devuelve el MISMO objeto (identidad estable) y los conteos
    # internos miden que el wrapper envuelve y no reemplaza.
    cuenta = {"llm": 0, "agent": 0}

    def call_llm(messages):
        cuenta["llm"] += 1
        return "respuesta-llm"

    def call_llm_agent(messages, tools=None):
        cuenta["agent"] += 1
        return SimpleNamespace(content="respuesta-agent", tool_calls=None)

    mod = SimpleNamespace(call_llm=call_llm, call_llm_agent=call_llm_agent)
    orig_llm, orig_agent = mod.call_llm, mod.call_llm_agent
    estado, restaurar = bs.contador(mod)

    assert estado["llamadas"] == 0
    assert mod.call_llm("hola") == "respuesta-llm"
    assert mod.call_llm_agent("hola", tools=None).content == "respuesta-agent"
    assert estado["llamadas"] == 2
    # los fakes también incrementan: el contador envuelve, no reemplaza
    assert cuenta["llm"] == 1 and cuenta["agent"] == 1

    restaurar()
    assert mod.call_llm is orig_llm and mod.call_llm_agent is orig_agent
    mod.call_llm("hola")  # ya sin envolver: no cuenta
    assert estado["llamadas"] == 2

class _Msg:
    """Mensaje del asistente fake: content + tool_calls en la forma del SDK."""

    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

class _TC:
    def __init__(self, id, name, arguments):
        self.id = id
        self.function = type("F", (), {"name": name, "arguments": arguments})()

def test_bench_supervisor_agente_plano_dos_rondas_y_tope():
    """El bucle del agente plano con call_llm_agent fake: 2 rondas de tools y
    respuesta → ejecuta las tools (IMPL fake) y devuelve el texto final. El
    conteo de rondas respeta el tope y a la ÚLTIMA ronda se va SIN tools."""
    import sys

    sys.path.insert(0, str(RAIZ / "banco"))
    import bench_supervisor as bs

# camino feliz: 2 rondas de tools y respuesta final ---
    guion = [
        _Msg("busco", [_TC("t1", "read_file", '{"path": "a.py"}')]),
        _Msg("más", [_TC("t2", "sql", '{"consulta": "SELECT 1"}')]),
        _Msg("la respuesta final es 42", None),
    ]
    capturado = {"tools_vistas": []}

    def llm_fake(mensajes, tools=None):
        capturado["tools_vistas"].append(tools)
        return guion.pop(0)

    ejecutadas = []

    def run_fake(tool_call, impls):
        ejecutadas.append(tool_call["function"]["name"])
        return {"role": "tool", "tool_call_id": tool_call["id"], "content": f"ok {tool_call['id']}"}

    r = bs.agente_plano("tarea", llm=llm_fake, impls={}, run=run_fake, max_rondas=8, max_tools=5)
    assert r["texto"] == "la respuesta final es 42"
    assert r["rondas"] == 3
    assert r["tools_ejecutadas"] == 2
    assert ejecutadas == ["read_file", "sql"]
    # todas las rondas intermedias recibieron tools; ninguna tocó el registry real
    assert capturado["tools_vistas"][0] is not None
    assert capturado["tools_vistas"][1] is not None

# tope de rondas: SIEMPRE pide tools, a la última se retiran ---
    guion2 = [_Msg("sigo", [_TC(f"t{i}", "read_file", "{}")]) for i in range(20)]
    tools_por_ronda = []

    def llm_siempre_tools(mensajes, tools=None):
        tools_por_ronda.append(tools)
        return guion2.pop(0)

    def run_noop(tool_call, impls):
        return {"role": "tool", "tool_call_id": tool_call["id"], "content": "ok"}

    r2 = bs.agente_plano("tarea", llm=llm_siempre_tools, impls={}, run=run_noop, max_rondas=8)
    assert r2["rondas"] == 8, "corta en el tope aunque el modelo siga pidiendo tools"
    assert r2["tools_ejecutadas"] == 7, "a la última ronda (sin tools) no ejecuta nada"
    assert tools_por_ronda[-1] is None, "la última ronda va SIN tools"
    assert all(t is not None for t in tools_por_ronda[:-1])

def test_bench_supervisor_tareas_jsonl_cargan_con_verificacion():
    """banco/supervisor_tareas.jsonl carga, tiene las 6 tareas y cada id tiene
    su verificación en VERIFICACIONES. Un id sin verificación es SystemExit."""
    import sys

    sys.path.insert(0, str(RAIZ / "banco"))
    import bench_supervisor as bs

    tareas = bs.cargar_tareas()
    assert len(tareas) == 6
    ids = [t["id"] for t in tareas]
    assert ids == [
        "contar-utils", "constante-max-pasos", "firma-veredicto",
        "tablas-trazas", "linea-marcadores", "conteo-routing",
    ]
    for t in tareas:
        assert t["id"] in bs.VERIFICACIONES
        assert callable(bs.VERIFICACIONES[t["id"]])
        assert t["tarea"].strip()

    # un id sin verificación → SystemExit con mensaje claro
    import json as _json

    ruta = RAIZ / "banco" / "_tmp_tareas_sin_verif.jsonl"
    try:
        ruta.write_text(_json.dumps({"id": "fantasma", "tarea": "x"}) + "\n", encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            bs.cargar_tareas(ruta)
        assert "no tiene verificación" in str(e.value)
    finally:
        ruta.unlink(missing_ok=True)

def test_bench_supervisor_contencion_por_tarea(tmp_path):
    """Un crash de una vía en una tarea NO tira el bench: la celda queda como
    error con el motivo y las otras siguen (patrón exp/20)."""
    import sys
    from types import SimpleNamespace

    sys.path.insert(0, str(RAIZ / "banco"))
    import bench_supervisor as bs

    class ModFake:
        def call_llm(self, messages):
            return "x"

        def call_llm_agent(self, messages, tools=None):
            return SimpleNamespace(content="x", tool_calls=None)

    tareas = [
        {"id": "contar-utils", "tarea": "q1"},
        {"id": "constante-max-pasos", "tarea": "q2"},
    ]

    n_utils = len(list((RAIZ / "utils").glob("*.py")))

    def runner_sup(tarea):
        if tarea == "q2":  # la segunda tarea: el supervisor revienta
            raise RuntimeError("el supervisor explotó")
        return f"hay {n_utils} archivos .py"  # gradúa True en contar-utils

    def runner_plano(tarea):
        return "MAX_PASOS es 5"

    bench = bs.correr(tareas, vias=("supervisor", "plano"),
                      runner_sup=runner_sup, runner_plano=runner_plano, llm_modulo=ModFake())
    assert len(bench["filas"]) == 4
    por_clave = {(f["id"], f["via"]): f for f in bench["filas"]}
    # la celda que reventó queda contenida con motivo
    rota = por_clave[("constante-max-pasos", "supervisor")]
    assert rota["error"] is True
    assert rota["ok"] is False
    assert "RuntimeError" in rota["motivo"]
    # las sanas siguen y se gradúan
    assert por_clave[("contar-utils", "supervisor")]["ok"] is True
    assert por_clave[("constante-max-pasos", "plano")]["ok"] is True

def test_bench_supervisor_baseline_compara_y_no_pisa(tmp_path):
    """Baseline: guardar → comparar reporta delta; bajar la calidad da
    REGRESIÓN; sin --actualizar-baseline NO se pisa; sin baseline → PRIMERA
    CORRIDA; una corrida sin filas no pisa un baseline válido."""
    import json as _json

    import bench_supervisor as bs

    ruta = tmp_path / "bench_supervisor.json"
    bench = {
        "filas": [{"id": "x", "via": "supervisor"}],
        "por_via": {"supervisor": {"calidad": 0.9}, "plano": {"calidad": 0.8}},
        "veredicto": "plano empata o gana → el despacho se simplifica",
    }
    assert bs.guardar_baseline(bench, ruta=ruta, sha="abc123") is not None

    comp = bs.comparar_baseline(bench, ruta=ruta)
    assert comp["veredicto"] == "OK"
    assert comp["delta"]["supervisor"] == 0.0

    baja = {"por_via": {"supervisor": {"calidad": 0.5}, "plano": {"calidad": 0.8}}}
    assert bs.comparar_baseline(baja, ruta=ruta)["veredicto"] == "REGRESIÓN"

    antes = ruta.read_text(encoding="utf-8")
    bs.comparar_baseline(baja, ruta=ruta)
    assert ruta.read_text(encoding="utf-8") == antes  # no se pisa al comparar
    assert _json.loads(antes)["por_via"]["supervisor"]["calidad"] == 0.9

    assert bs.comparar_baseline(bench, ruta=tmp_path / "no.json")["veredicto"] == "PRIMERA CORRIDA"

    # una corrida vacía no pisa un baseline válido
    assert bs.guardar_baseline({"filas": [], "por_via": {}}, ruta=ruta) is None
    assert _json.loads(ruta.read_text(encoding="utf-8"))["por_via"]["supervisor"]["calidad"] == 0.9

def test_bench_supervisor_generar_escribe_md_y_jsonl(tmp_path):
    """generar() corre con runners fake (sin LLM real), escribe el markdown y
    el JSONL crudo al lado, y NO pisa el baseline real sin la flag."""
    import json as _json
    import sys
    from types import SimpleNamespace

    sys.path.insert(0, str(RAIZ / "banco"))
    import bench_supervisor as bs

    class ModFake:
        def call_llm(self, messages):
            return "x"

        def call_llm_agent(self, messages, tools=None):
            return SimpleNamespace(content="x", tool_calls=None)

    def _baseline():
        return (bs.BASELINE.is_file(),
                bs.BASELINE.stat().st_mtime_ns if bs.BASELINE.is_file() else None)

    antes = _baseline()
    destino, jsonl = bs.generar(
        vias=("supervisor", "plano"),
        runner_sup=lambda t: "hay muchos .py",
        runner_plano=lambda t: "MAX_PASOS es 5",
        llm_modulo=ModFake(), sha="deadbeef", dir_salida=tmp_path / "evals",
    )
    texto = destino.read_text(encoding="utf-8")
    assert "# Bench supervisor vs agente plano" in texto
    assert "Veredicto" in texto
    assert destino.name.startswith("bench_supervisor_") and destino.suffix == ".md"
    assert jsonl.is_file()
    filas = [_json.loads(linea) for linea in jsonl.read_text(encoding="utf-8").splitlines()]
    assert len(filas) == 12  # 6 tareas × 2 vías
    assert _baseline() == antes, "generar() sin --actualizar-baseline tocó el baseline real"


def test_bench_cita_ok_ventana_de_grading(tmp_path):
    """A65: el grading ahora tolera ±VENTANA_GRADING líneas (drift del
    modelo): cita a 10 líneas de la evidencia → True; a 11 → False."""
    import bench_juez as bj

    fixture = tmp_path / "modulo.py"
    lineas = [f"linea {i}" for i in range(1, 41)]
    lineas[19] = "la clave es OLLAMA"  # línea 20
    fixture.write_text("\n".join(lineas), encoding="utf-8")
    caso = {"cita_archivo": "modulo.py", "cita_contiene": ["ollama"]}

    assert bj.cita_ok(f"según {fixture}:10 eso", caso) is True   # ±10
    assert bj.cita_ok(f"según {fixture}:9 eso", caso) is False   # ±11
    assert bj.cita_ok(f"según {fixture}:20 eso", caso) is True   # exacta


def test_bench_cita_ok_no_confunde_sufijos(tmp_path):
    """Revisión del último commit (harness): `endswith` aceptaba
    `otro_modulo.py` como si fuera `modulo.py`. La frontera de path lo corta."""
    import bench_juez as bj

    esperado = tmp_path / "modulo.py"
    esperado.write_text("uno\nla clave es OLLAMA\n", encoding="utf-8")
    otro = tmp_path / "otro_modulo.py"
    otro.write_text("uno\nla clave es OLLAMA\n", encoding="utf-8")
    caso = {"cita_archivo": "modulo.py", "cita_contiene": ["ollama"]}

    assert bj.cita_ok(f"según {esperado}:2", caso) is True
    assert bj.cita_ok(f"según {otro}:2", caso) is False


def test_banco_casos_con_cita_tienen_token():
    """A65/revisión: un caso con cita_archivo y cita_contiene vacío daría
    cita_ok=True ante cualquier cita (falso positivo silencioso)."""
    import bench_juez as bj

    for caso in bj.cargar_casos():
        if caso.get("cita_archivo"):
            assert caso.get("cita_contiene"), f"caso sin token: {caso.get('id')}"
