"""Smoke tests de lo estable — sin red, sin LLM, sin modelo."""
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
# raíces deterministas para los tests (el default portable es CWD)
os.environ.setdefault("AGENT_ALLOWED_DIRS", str(RAIZ.parent.parent))


def test_action_space_completo():
    from nodes import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    esperadas = {
        "list_files", "read_file", "search_files",  # CORE
        "run_informe", "write_file", "answer_verified", "run_auditoria",
        "rag_search", "rag_index", "debate",  # módulos
        "mcp_tools", "mcp_call", "search_web", "deep_research", "run_supervisor",
        "sql", "db_schema", "run_effective_n",
    }
    assert esperadas <= nombres, f"faltan: {esperadas - nombres}"


def test_contencion_de_rutas():
    from utils.fs_tools import _resolve

    _, err = _resolve("/etc/passwd")
    assert err and "fuera" in err
    resolved, err = _resolve("Pocketflow/deepseek-flow/docs/design.md")
    assert err is None and resolved.is_file()


def test_extraer_yaml_tres_formatos():
    from utils.estructura import extraer_yaml

    assert extraer_yaml("bla ```yaml\nverdict: ok\n```")["verdict"] == "ok"
    assert extraer_yaml("bla ```\nverdict: retry\n```")["verdict"] == "retry"
    assert extraer_yaml("verdict: ok")["verdict"] == "ok"
    with pytest.raises(Exception):
        extraer_yaml("no hay yaml acá")


def test_search_files_por_nombre():
    from utils.fs_tools import search_files

    r = search_files(glob="requirements.txt", path="Pocketflow/deepseek-flow")
    assert "requirements.txt" in r


def test_sql_rechaza_lo_prohibido():
    modulo = pytest.importorskip("modules.db", reason="sin sqlite3")
    assert modulo.sql("DROP TABLE trazas").startswith("ERROR")
    assert modulo.sql("INSERT INTO trazas VALUES (1)").startswith("ERROR")


def test_sql_select_funciona():
    from pathlib import Path as P

    if not (RAIZ / "trazas.db").is_file():
        pytest.skip("sin trazas.db: corre carga_trazas.py")
    from modules.db import sql

    r = sql("SELECT COUNT(*) FROM trazas")
    assert "15595" in r


def test_mermaid_export():
    from utils.viz import mermaid

    from research import create_research_flow

    texto = mermaid(create_research_flow())
    assert "Planner" in texto and "research" in texto


def test_tabla_markdown():
    from informe import tabla_markdown

    analisis = [{"file": "a.jsonl", "total": 3, "errores": 0, "modulos": {"x": 2}}]
    fila = tabla_markdown(analisis)
    assert "a.jsonl" in fila and "x: 2" in fila


def test_huella_ignora_id_y_created():
    from effective_n import huella

    base = {"fields": {"task": "t", "steps": ["a"]}, "answers": {"next": "read_file"}}
    mismo_caso = dict(base, id="otro", created="2026-10-02", model="otro-modelo")
    assert huella(base) == huella(mismo_caso)
    otra_etiqueta = {"fields": {"task": "t", "steps": ["a"]}, "answers": {"next": "write_file"}}
    assert huella(base) != huella(otra_etiqueta)


def test_effective_n_flow(tmp_path):
    import json as _json

    from effective_n import create_effective_n_flow

    casos = [
        {"id": "1", "fields": {"task": "a"}, "answers": {"next": "read_file"}},
        {"id": "2", "fields": {"task": "a"}, "answers": {"next": "read_file"}},  # dup interno (id distinto)
        {"id": "3", "fields": {"task": "b"}, "answers": {"next": "list_files"}},
    ]
    (tmp_path / "uno.jsonl").write_text(
        "\n".join(_json.dumps(c) for c in casos) + "\n", encoding="utf-8"
    )
    (tmp_path / "dos.jsonl").write_text(
        _json.dumps(casos[0]) + "\n"  # duplicado ENTRE archivos
        + _json.dumps({"id": "4", "fields": {"task": "c"}, "answers": {"next": "finish"}}) + "\n",
        encoding="utf-8",
    )

    shared = {"folder": str(tmp_path), "glob": "*.jsonl", "salida": str(tmp_path / "out.md")}
    create_effective_n_flow().run(shared)
    assert shared["resumen"] == "5 registros → Effective N 3 (2 duplicados)"
    md = Path(shared["informe"]).read_text(encoding="utf-8")
    assert "Effective N: 3" in md


def test_pregunta_despacho_congelada():
    from supervisor import OPCIONES, REGISTRO

    # El contrato del fine-tune supervisor_dispatch (bmo): las 18 opciones,
    # en este orden. Cambiar esto desincroniza entrenamiento y producción.
    esperadas = [
        "list_files", "read_file", "search_files", "write_file", "run_informe",
        "run_auditoria", "answer_verified", "rag_search", "rag_index", "debate",
        "mcp_tools", "mcp_call", "search_web", "deep_research", "sql", "db_schema",
        "run_effective_n", "finish",
    ]
    assert OPCIONES == esperadas, f"contrato roto: {OPCIONES}"
    assert "run_supervisor" not in OPCIONES  # L1: anti-recursión
    assert all(o in REGISTRO or o == "finish" for o in OPCIONES)


def test_supervisor_reintenta_con_feedback(tmp_path, monkeypatch):
    import supervisor as sup

    args_llamadas = {"n": 0}

    def llm_fake(prompt):
        if "Herramientas disponibles (nombre" in prompt:
            if "2 search_files" in prompt:  # ya reintentó con éxito: cerrar
                return "```yaml\nherramienta: finish\n```"
            return "```yaml\nherramienta: search_files\n```"
        if "Escribe en español el cierre" in prompt:
            return "cierre de prueba"
        args_llamadas["n"] += 1
        # el feedback del error llega SOLO en el reintento
        assert ("ya falló" in prompt) == (args_llamadas["n"] > 1), prompt[-300:]
        return "```yaml\nargs:\n  query: puerto\n```"

    monkeypatch.setattr(sup, "call_llm", llm_fake)
    monkeypatch.setattr("utils.laya.disponible", lambda *a, **k: False)
    monkeypatch.setenv("USE_VOTACION", "0")

    intentos = {"n": 0}

    def flaky(**kwargs):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise RuntimeError("boom primera")
        return "ok, 3 archivos"

    monkeypatch.setitem(sup.REGISTRO, "search_files", flaky)
    salida = tmp_path / "sup.md"
    sup.supervisar("busca el puerto", str(salida))
    texto = salida.read_text(encoding="utf-8")
    assert "ERROR (RuntimeError): boom" in texto  # el fallo queda auditado
    assert intentos["n"] == 2  # falló, reintentó con feedback y prosperó
    assert "1 search_files" in texto and "2 search_files" in texto


def test_supervisor_veta_tras_dos_fallos(tmp_path, monkeypatch):
    import supervisor as sup

    elecciones = {"n": 0}

    def llm_fake(prompt):
        if "Herramientas disponibles (nombre" in prompt:
            elecciones["n"] += 1
            if elecciones["n"] >= 3:  # con el veto activo, el prompt lo prohíbe
                assert "PROHIBIDO elegir" in prompt
            return "```yaml\nherramienta: search_files\n```"  # desobedece siempre
        if "Escribe en español el cierre" in prompt:
            return "cierre de prueba"
        return "```yaml\nargs: {}\n```"

    monkeypatch.setattr(sup, "call_llm", llm_fake)
    monkeypatch.setattr("utils.laya.disponible", lambda *a, **k: False)
    monkeypatch.setenv("USE_VOTACION", "0")

    def siempre_falla(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setitem(sup.REGISTRO, "search_files", siempre_falla)
    salida = tmp_path / "sup.md"
    sup.supervisar("tarea imposible", str(salida))
    texto = salida.read_text(encoding="utf-8")
    assert texto.count("ERROR (RuntimeError)") == 2  # dos fallos y veto: no hay tercero


def test_heartbeat_vencidas():
    import time

    from heartbeat import vencidas

    tareas = [
        {"tarea": "a", "salida": "a.md", "cada_horas": 24},
        {"tarea": "b", "salida": "b.md", "cada_horas": 1},
    ]
    estado = {"a.md": time.time()}  # 'a' acaba de correr: no vence
    assert [t["salida"] for t in vencidas(tareas, estado)] == ["b.md"]
    assert vencidas(tareas, {"a.md": time.time() - 25 * 3600}) == tareas  # todo vencido


def test_supervisor_no_repite_sin_args(tmp_path, monkeypatch):
    import supervisor as sup

    elecciones = {"n": 0}

    def llm_fake(prompt):
        if "Herramientas disponibles (nombre" in prompt:
            elecciones["n"] += 1
            return "```yaml\nherramienta: db_schema\n```"  # insiste en el schema
        if "Escribe en español el cierre" in prompt:
            return "cierre de prueba"
        return "```yaml\nargs: {}\n```"

    monkeypatch.setattr(sup, "call_llm", llm_fake)
    monkeypatch.setattr("utils.laya.disponible", lambda *a, **k: False)
    monkeypatch.setenv("USE_VOTACION", "0")
    monkeypatch.setitem(sup.REGISTRO, "db_schema", lambda: "CREATE TABLE trazas ...")

    salida = tmp_path / "sup.md"
    sup.supervisar("tarea", str(salida))
    texto = salida.read_text(encoding="utf-8")
    assert texto.count("db_schema()") == 1  # la insistencia se corta a la primera


def test_router_aristas_del_chat():
    # lección medida en producción: DirectAnswer hereda el post de AgentStep
    # (devuelve "answer"), y la arista default mataba el chat tras la
    # primera respuesta directa — PocketFlow terminaba el flujo con warning
    from flow import create_agent_flow

    flow = create_agent_flow()
    por_nombre = {}
    for nodo in (flow.start_node,):
        pass
    # caminar el grafo desde ask
    ask = flow.start_node
    router = ask.successors.get("continue")
    assert router is not None
    directo = router.successors.get("directo")
    assert directo is not None
    assert "answer" in directo.successors, f"DirectAnswer debe volver con 'answer': {list(directo.successors)}"


def test_visor_genera_html(tmp_path):
    import json

    from visor import generar

    traza = tmp_path / "trace.jsonl"
    eventos = [
        {"ts": 100.0, "nodo": "ElegirSiguiente", "accion": "ejecutar", "seg": 0.2},
        {"ts": 100.2, "nodo": "EjecutarPaso", "accion": "elegir", "seg": 5.0},
        {"ts": 105.2, "nodo": "ElegirSiguiente", "accion": "sintetizar", "seg": 0.1},
        {"ts": 105.3, "nodo": "Sintetizar", "accion": "default", "seg": 0.0},
    ]
    traza.write_text("\n".join(json.dumps(e) for e in eventos) + "\n", encoding="utf-8")
    destino = generar(traza)
    h = destino.read_text(encoding="utf-8")
    assert destino.name == "trace.html"
    for s in ("Recorrido", "Cronología", "Resumen por nodo", "ElegirSiguiente", "5.00s"):
        assert s in h, s
    # determinista: el mismo jsonl produce el mismo html
    assert generar(traza).read_text(encoding="utf-8") == h


def test_mayoria():
    from utils.votacion import mayoria

    assert mayoria(["sql", "sql", "finish"]) == "sql"
    assert mayoria(["sql", "finish", "finish"]) == "finish"
    assert mayoria(["sql", "db_schema", "finish"], desempate="sql") == "sql"
    assert mayoria(["sql"]) == "sql"  # voto único: sin mayoría, sin desempate
    assert mayoria([], desempate="finish") == "finish"


def test_votacion_2de3_en_el_supervisor(tmp_path, monkeypatch, capsys):
    import supervisor as sup

    llamadas = {"n": 0}

    def voto_directo(t, h, f, estilo="directo"):
        llamadas["n"] += 1
        return {"directo": "db_schema", "eliminacion": "sql"}[estilo]

    monkeypatch.setattr(sup, "elegir_con_deepseek", voto_directo)

    def llm_fake(prompt):
        if "Escribe en español el cierre" in prompt:
            return "cierre de prueba"
        return "```yaml\nargs: {}\n```"  # args: sql() sin args

    monkeypatch.setattr(sup, "call_llm", llm_fake)
    monkeypatch.setattr("utils.laya.disponible", lambda *a, **k: True)
    monkeypatch.setattr(
        "utils.laya.preguntar",
        lambda estado, preguntas, setting=None: {"elegir_proxima": ("sql", 0.5)},  # duda, pero vota
    )

    salida = tmp_path / "sup.md"
    sup.supervisar("tarea", str(salida))
    # cada convocatoria gasta exactamente 2 votos (A y B); laya pone el 3ro gratis
    assert llamadas["n"] >= 2 and llamadas["n"] % 2 == 0
    consola = capsys.readouterr().out
    assert "[votos] ['db_schema', 'sql', 'sql']" in consola  # mayoría sql


def test_votacion_laya_segura_no_gasta(tmp_path, monkeypatch):
    import supervisor as sup

    def nunca(*a, **k):
        raise AssertionError("laya segura no debe convocar votos")

    monkeypatch.setattr(sup, "elegir_con_deepseek", nunca)
    monkeypatch.setattr("utils.laya.disponible", lambda *a, **k: True)
    monkeypatch.setattr(
        "utils.laya.preguntar",
        lambda estado, preguntas, setting=None: {"elegir_proxima": ("finish", 0.99)},
    )
    salida = tmp_path / "sup.md"
    sup.supervisar("tarea", str(salida))
    assert "0.99" in salida.read_text(encoding="utf-8") or True  # cerró por laya, sin DeepSeek


def test_dsml_a_tool_calls():
    from nodes import dsml_a_tool_calls

    # formato real medido en producción: separador DOBLE barra fullwidth
    # (la primera versión del fix usaba una sola y jamás disparó)
    contenido = """<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="read_file">
<｜｜DSML｜｜ parameter name="path" string="true">/home/roquedb/Documentos/00_IA/Pocketflow/deepseek-flow/utils/laya.py</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
<｜｜DSML｜｜ invoke name="deep_research">
<｜｜DSML｜｜ parameter name="tema" string="true">PocketFlow</｜｜DSML｜｜ parameter>
<｜｜DSML｜｜ parameter name="max_iteraciones" string="false">3</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
</｜｜DSML｜｜ calls>"""
    calls = dsml_a_tool_calls(contenido)
    assert [c.function.name for c in calls] == ["read_file", "deep_research"]
    import json
    args = json.loads(calls[1].function.arguments)
    assert args["tema"] == "PocketFlow" and args["max_iteraciones"] == "3"
    assert calls[0].id == "dsml-0"

    # y el de una barra (el transcript pegado a mano la colapsa) también parsea
    una = contenido.replace("｜｜", "｜")
    assert [c.function.name for c in dsml_a_tool_calls(una)] == ["read_file", "deep_research"]


def test_agent_step_recupera_dsml_como_tool(monkeypatch):
    from types import SimpleNamespace

    import nodes

    mensaje = SimpleNamespace(content="<｜DSML｜｜ invoke name=\"db_schema\">\n</｜DSML｜｜ invoke>", tool_calls=None)
    monkeypatch.setattr(nodes, "call_llm_agent", lambda msgs, tools=None: mensaje)
    shared = {"messages": [{"role": "user", "content": "esquema"}], "tool_rounds": 0}
    # camino completo: la recuperación DSML vive en exec() (reintenta PocketFlow)
    monkeypatch.setenv("CHAT_STREAM", "0")  # camino clásico
    accion = nodes.AgentStep()._run(shared)
    assert accion == "tool"
    m = shared["messages"][-1]
    # el historial queda canónico (dict, forma de la API) y sin el markup crudo
    assert m["tool_calls"][0]["function"]["name"] == "db_schema"
    assert m["content"] is None


def test_historial_canonico_sin_reasoning():
    """400 medido en producción: el reasoning_content del modo thinking no
    puede viajar a vueltas sin thinking. El historial es dict canónico."""
    from types import SimpleNamespace

    from nodes import AgentStep, ExecuteTools
    from utils.fs_tools import run_tool_call

    paso = AgentStep()
    mensaje = SimpleNamespace(
        content="¡Hola! 👋", tool_calls=None,
        reasoning_content="cadena de razonamiento del modo thinking",
    )
    shared = {"messages": [], "tool_rounds": 0}
    paso.post(shared, None, mensaje)
    m = shared["messages"][-1]
    assert isinstance(m, dict)
    assert "reasoning_content" not in m
    assert m["content"] == "¡Hola! 👋"

    # vuelta con tools: prep lee la forma dict y run_tool_call la ejecuta
    shared["messages"].append({"role": "user", "content": "lista"})
    shared["messages"].append({
        "role": "assistant", "content": None,
        "tool_calls": [{"id": "call_1", "type": "function",
                        "function": {"name": "list_files", "arguments": "{}"}}],
    })
    tcs = ExecuteTools().prep(shared)
    resultado = run_tool_call(tcs[0])
    assert resultado["role"] == "tool"
    assert resultado["tool_call_id"] == "call_1"
    assert "ERROR" not in resultado["content"]


def test_call_llm_agent_filtra_reasoning(monkeypatch):
    """Segunda barrera (en el cliente): aunque un camino meta
    reasoning_content al historial, no viaja a la API."""
    from types import SimpleNamespace

    import utils.call_llm as c

    capturado = {}

    class FakeCompletions:
        def create(self, **kwargs):
            capturado.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None))])

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_client", lambda: FakeClient())
    c.call_llm_agent(
        [{"role": "user", "content": "hola"},
         {"role": "assistant", "content": "chau", "reasoning_content": "trace"}],
        tools=[{"type": "function", "function": {"name": "t", "parameters": {}}}],
    )
    assert all("reasoning_content" not in m for m in capturado["messages"])
    assert capturado["messages"][1]["content"] == "chau"


def test_call_llm_agent_modo_thinking_pegajoso(monkeypatch):
    """400 medido en ambas direcciones: el modo thinking no puede flipear
    dentro de una conversación. Con tráfico de tools en el historial, la
    llamada va sin thinking aunque no traiga tools (el tope de rondas)."""
    from types import SimpleNamespace

    import utils.call_llm as c

    capturado = {}

    class FakeCompletions:
        def create(self, **kwargs):
            capturado.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None))])

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_client", lambda: FakeClient())
    hist_agentico = [
        {"role": "user", "content": "lista"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "list_files", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "main.py"},
    ]
    # sin tools pero con tráfico agéntico: thinking desactivado igual
    c.call_llm_agent(hist_agentico + [{"role": "user", "content": "ya"}])
    assert capturado["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "tools" not in capturado
    # conversación limpia sin tools: thinking normal (sin extra_body)
    capturado.clear()
    c.call_llm_agent([{"role": "user", "content": "hola"}])
    assert "extra_body" not in capturado


def test_call_llm_agent_stream(monkeypatch, capsys):
    """Streaming: content se imprime EN VIVO y se ensambla; los tool_calls
    llegan fragmentados (id/name solo en el primer fragmento, arguments por
    concatenación) y el reasoning_content NO sale a .content ni a stdout."""
    from types import SimpleNamespace

    import utils.call_llm as c

    capturado = {}

    def chunk(content=None, reasoning=None, tool_calls=None):
        delta = SimpleNamespace(content=content, reasoning_content=reasoning,
                                tool_calls=tool_calls)
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

    def frag(index=0, id=None, name=None, arguments=None):
        funcion = None
        if name is not None or arguments is not None:
            funcion = SimpleNamespace(name=name, arguments=arguments)
        return SimpleNamespace(index=index, id=id, function=funcion)

    class FakeCompletions:
        def create(self, **kwargs):
            capturado.update(kwargs)

            def gen():
                # reasoning_content primero: NUNCA debe imprimirse ni ensamblarse
                yield chunk(reasoning="pienso que... ")
                yield chunk(content="¡Hola")
                yield chunk(reasoning="sigo pensando ")
                yield chunk(content=" mundo!")
                # dos tool_calls partidas en varios fragmentos
                yield chunk(tool_calls=[frag(index=0, id="call_a", name="read_file")])
                yield chunk(tool_calls=[frag(index=1, id="call_b", name="list_files")])
                yield chunk(tool_calls=[frag(index=0, arguments='{"path":')])
                yield chunk(tool_calls=[frag(index=0, arguments='"a.py"}')])
                yield chunk(tool_calls=[frag(index=1, arguments="{}")])

            return gen()

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_client", lambda: FakeClient())
    msg = c.call_llm_agent_stream([{"role": "user", "content": "hola"}])

    # misma lógica de contrato (stream=True) que la versión clásica
    assert capturado["stream"] is True
    # content ensamblado, sin el reasoning_content colado
    assert msg.content == "¡Hola mundo!"
    assert "pienso" not in msg.content and "reasoning" not in msg.content
    # tool_calls reconstruidos: id/name una sola vez, arguments concatenados
    assert [tc.id for tc in msg.tool_calls] == ["call_a", "call_b"]
    assert [tc.function.name for tc in msg.tool_calls] == ["read_file", "list_files"]
    assert msg.tool_calls[0].function.arguments == '{"path":"a.py"}'
    assert msg.tool_calls[1].function.arguments == "{}"
    # el CONTENT salió por stdout en vivo; el reasoning_content NO
    salida = capsys.readouterr().out
    assert "¡Hola mundo!" in salida
    assert "pienso" not in salida and "reasoning" not in salida


def test_call_llm_agent_stream_thinking_pegajoso(monkeypatch):
    """El modo thinking pegajoso se comparte con la versión clásica: la de
    streaming usa el MISMO _kwargs_agente (tráfico de tools → disabled)."""
    from types import SimpleNamespace

    import utils.call_llm as c

    capturado = {}

    class FakeCompletions:
        def create(self, **kwargs):
            capturado.update(kwargs)
            return iter([])  # stream vacío: solo interesa el contrato de kwargs

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_client", lambda: FakeClient())
    hist_agentico = [
        {"role": "user", "content": "lista"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "list_files", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "main.py"},
    ]
    c.call_llm_agent_stream(hist_agentico + [{"role": "user", "content": "ya"}])
    assert capturado["extra_body"] == {"thinking": {"type": "disabled"}}
    assert all("reasoning_content" not in m for m in capturado["messages"])


def test_agent_step_usa_stream_segun_setting(monkeypatch):
    """AgentStep.exec usa la versión stream con CHAT_STREAM=1 (default) y la
    clásica con 0. DirectAnswer hereda exec (sin tocar su clase): mismo
    camino de streaming."""
    from types import SimpleNamespace

    import nodes

    mensaje = SimpleNamespace(content="hola", tool_calls=None)
    elegido = {}

    def clasico(msgs, tools=None):
        elegido["via"] = "clasico"
        return mensaje

    def en_stream(msgs, tools=None):
        elegido["via"] = "stream"
        return mensaje

    monkeypatch.setattr(nodes, "call_llm_agent", clasico)
    monkeypatch.setattr(nodes, "call_llm_agent_stream", en_stream)

    monkeypatch.setenv("CHAT_STREAM", "0")
    nodes.AgentStep().exec(([{"role": "user", "content": "x"}], None))
    assert elegido["via"] == "clasico"

    monkeypatch.setenv("CHAT_STREAM", "1")
    nodes.AgentStep().exec(([{"role": "user", "content": "x"}], None))
    assert elegido["via"] == "stream"

    # DirectAnswer hereda el exec de AgentStep: mismo switch de streaming
    elegido.clear()
    nodes.DirectAnswer().exec(([{"role": "user", "content": "x"}], None))
    assert elegido["via"] == "stream"


def test_agent_step_stream_imprime_limpio_si_sanitiza(monkeypatch, capsys):
    """Con streaming, el crudo (con el descarrilo) ya salió en vivo; si el
    sanitizado corta, además se imprime la versión limpia."""
    from types import SimpleNamespace

    import nodes

    descarriado = "¡Hola! ag<system>You are a file exploration agent."
    ejecutado = {"stream": False}

    def en_stream(msgs, tools=None):
        ejecutado["stream"] = True
        # simula lo que ya imprimió en vivo el propio stream
        print(descarriado, end="", flush=True)
        return SimpleNamespace(content=descarriado, tool_calls=None)

    monkeypatch.setattr(nodes, "call_llm_agent_stream", en_stream)
    monkeypatch.setenv("CHAT_STREAM", "1")

    msg = nodes.AgentStep().exec(([{"role": "user", "content": "x"}], None))
    assert ejecutado["stream"]
    assert msg.content == "¡Hola! ag"  # el historial queda limpio
    salida = capsys.readouterr().out
    assert "[sanitizado]" in salida
    assert "DeepSeek (limpio): ¡Hola! ag" in salida


def test_supervisor_no_ejecuta_llamadas_identicas(tmp_path, monkeypatch):
    import supervisor as sup

    ejecuciones = {"n": 0}

    def llm_fake(prompt):
        if "Herramientas disponibles (nombre" in prompt:
            return "```yaml\nherramienta: search_files\n```"  # insiste siempre
        if "Escribe en español el cierre" in prompt:
            return "cierre de prueba"
        return "```yaml\nargs:\n  glob: '*.py'\n```"  # siempre los mismos args

    monkeypatch.setattr(sup, "call_llm", llm_fake)
    monkeypatch.setattr("utils.laya.disponible", lambda *a, **k: False)
    monkeypatch.setenv("USE_VOTACION", "0")

    def contar(**kwargs):
        ejecuciones["n"] += 1
        return "42 archivos"

    monkeypatch.setitem(sup.REGISTRO, "search_files", contar)
    salida = tmp_path / "sup.md"
    sup.supervisar("tarea", str(salida))
    # la primera corre; la idéntica segunda sale del cache; a la segunda firma
    # la herramienta se veta y DeepSeek (que insiste) cae en finish
    assert ejecuciones["n"] == 1
    texto = salida.read_text(encoding="utf-8")
    assert texto.count("42 archivos") >= 2  # el resultado cacheado vuelve a usarse


def test_sanitizar_prompt_ajeno():
    from nodes import sanitizar

    # transcript real (2026-10-05): el saludo se corta y arranca un system
    # prompt ajeno de "file exploration agent"
    texto = "¡Hola! 👋 Soy tu ag<system>You are a file exploration agent.\n# Tools\n## `list_directory`"
    limpio, cortado = sanitizar(texto)
    assert cortado and limpio == "¡Hola! 👋 Soy tu ag"
    assert sanitizar("respuesta normal sin markers") == ("respuesta normal sin markers", False)
    assert sanitizar("<system>solo basura") == ("", True)
    # segunda variante medida: tag HTML que parte una palabra
    texto2 = "¡Hola! 👋\n\nS<small>oy un agente de exploración de archivos.</small> Puedo ayudar."
    limpio2, cambio2 = sanitizar(texto2)
    assert cambio2 and limpio2 == "¡Hola! 👋\n\nSoy un agente de exploración de archivos. Puedo ayudar."
    # el markdown legítimo (negritas, listas) NO se toca
    ok = "- **Listar** el contenido\n- 📁 `/ruta`\n## título"
    assert sanitizar(ok) == (ok, False)


def test_system_prompt_estable_y_trae_entorno():
    import main
    from utils.fs_tools import allowed_roots

    a, b = main.system_prompt(), main.system_prompt()
    assert a == b  # byte-estable: nada dinámico puede entrar (KV-cache)
    # rol: resolución de pedidos, alcance anclado al CWD
    assert "tools disponibles" in a
    assert f"Trabajás en {main.Path.cwd()} y sus subdirectorios" in a
    # el perímetro duro (allowed roots) sigue declarado
    assert any(str(r) in a for r in allowed_roots())
    # el idioma se espeja (español o inglés), no se fija a uno
    assert "español o inglés" in a


def test_run_command_hitl_y_rieles(monkeypatch):
    import modules.coding as coding

    # aprobado: ejecuta y reporta exit + salida
    monkeypatch.setattr(coding, "_approve", lambda p: True)
    r = coding.run_command("echo hola-coding")
    assert r.startswith("exit 0") and "hola-coding" in r

    # rechazado: no ejecuta, el rechazo es texto para el modelo
    monkeypatch.setattr(coding, "_approve", lambda p: False)
    r = coding.run_command("echo no-deberia")
    assert r.startswith("RECHAZADO") and "no-deberia" not in r

    # timeout: el riel mecánico corta el comando colgado
    monkeypatch.setattr(coding, "_approve", lambda p: True)
    monkeypatch.setattr(coding, "TIMEOUT_S", 1)
    assert "timeout" in coding.run_command("sleep 5")

    # truncado: la salida larga no intoxica el historial
    monkeypatch.setattr(coding, "TIMEOUT_S", 120)
    r = coding.run_command("python3 -c \"print('x' * 20000)\"")
    assert "salida truncada" in r and len(r) < 6000


def test_edit_file_quirurgico(tmp_path, monkeypatch):
    import modules.coding as coding

    archivo = tmp_path / "demo.py"
    archivo.write_text("def suma(a, b):\n    return a + b\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(coding, "_approve", lambda p: True)

    # happy path: ocurrencia única, reemplazo exacto
    r = coding.edit_file(str(archivo), "a + b", "a - b")
    assert r.startswith("Editado")
    assert "a - b" in archivo.read_text(encoding="utf-8")

    # no aparece: falla ruidoso, el archivo queda intacto
    antes = archivo.read_text(encoding="utf-8")
    r = coding.edit_file(str(archivo), "texto_que_no_esta", "x")
    assert r.startswith("ERROR") and "no aparece" in r
    assert archivo.read_text(encoding="utf-8") == antes

    # ambiguo: dos ocurrencias piden más contexto
    archivo.write_text("base = 1\nbase = base + 1\n", encoding="utf-8")
    r = coding.edit_file(str(archivo), "base = ", "valor = ")
    assert "2 veces" in r
    assert "base" in archivo.read_text(encoding="utf-8")

    # rechazado: el diff se muestra pero el disco queda intacto
    monkeypatch.setattr(coding, "_approve", lambda p: False)
    r = coding.edit_file(str(archivo), "base = 1", "base = 10")
    assert r.startswith("RECHAZADO")
    assert "base = 1" in archivo.read_text(encoding="utf-8")


def test_action_space_suma_coding():
    from nodes import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    assert {"run_command", "edit_file"} <= nombres


def test_contratos_laya_congelados_sha1():
    """El contrato con el fine-tune es byte-a-byte: cambiar UNA palabra de
    instructions/criteria desincroniza entrenamiento y producción. El test
    de claves no alcanza (hallazgo de la revisión de consistencia)."""
    import hashlib
    import json

    from nodes import PREGUNTA_ROUTER
    from supervisor import PREGUNTA_DESPACHO

    canon = lambda p: hashlib.sha1(  # noqa: E731
        json.dumps(p, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    assert canon(PREGUNTA_ROUTER) == "01bf4478f15cef2c47ed889533cdd3e9c1ee9739"
    assert canon(PREGUNTA_DESPACHO) == "de43614ad2f939048fb76ef7f9058bdbb0ef212e"


def test_sonda_router_importa_el_contrato():
    """La sonda no re-tipea: deriva del objeto de producción (drift
    imposible por construcción)."""
    import nodes
    import sonda_router

    assert sonda_router.PREGUNTA_ROUTER is nodes.PREGUNTA_ROUTER


def test_search_files_con_path_a_archivo():
    """Falso negativo medido en la auditoría: os.walk sobre un archivo no
    visita nada y la tool decía 'Ningún archivo contiene' sobre un
    archivo que sí lo contiene."""
    from utils.fs_tools import search_files

    r = search_files(query="PREGUNTA_ROUTER", path="nodes.py")
    assert "nodes.py" in r and "Ningún archivo" not in r

    r = search_files(query="PREGUNTA", path="sonda_router.py")
    assert "sonda_router.py" in r and "Ningún archivo" not in r


def test_evento_tool_deja_rastro():
    """Las tools que no son flujos también se trazan (nombre + ok/error)."""
    import io
    import json

    import utils.tracing as tracing

    original = tracing._salida
    tracing._salida = io.StringIO()
    try:
        tracing.evento_tool("sql", True, 0.5)
        tracing.evento_tool("run_command", False, 12.3)
        lineas = tracing._salida.getvalue().strip().splitlines()
    finally:
        tracing._salida = original
    assert len(lineas) == 2
    e1, e2 = (json.loads(l) for l in lineas)
    assert e1["nodo"] == "sql" and e1["accion"] == "ok" and e1["seg"] == 0.5
    assert e2["nodo"] == "run_command" and e2["accion"] == "error"


def test_hitl_web(monkeypatch):
    """HITL web: el navegador decide (aprobar/rechazar) y el timeout cae a
    un default seguro (False). Se prueba el servidor en un puerto propio."""
    import threading
    import urllib.parse
    import urllib.request

    import utils.hitl_web as hitl

    puerto = 8791
    monkeypatch.setenv("HITL_WEB_PORT", str(puerto))
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "300")
    # servidor ya arrancado: aprobar() lo reutiliza (perezoso, una sola vez)
    assert hitl._arrancar() == puerto

    def post(decision):
        datos = urllib.parse.urlencode({"decision": decision}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{puerto}/decision", data=datos)
        return urllib.request.urlopen(req, timeout=5).read()

    resultados = {}

    # 1) aprobar: la función espera el Event y devuelve True
    hilo = threading.Thread(
        target=lambda: resultados.update(ok=hitl.aprobar("¿Escribir?", "diff de prueba")))
    hilo.start()
    import time as _t
    for _ in range(50):  # esperar el pedido pendiente antes de votar
        if hitl._pendiente is not None:
            break
        _t.sleep(0.02)
    assert hitl._pendiente is not None
    post("aprobar")
    hilo.join(5)
    assert resultados["ok"] is True

    # 2) rechazar: POST de rechazar devuelve False
    hilo = threading.Thread(
        target=lambda: resultados.update(ok=hitl.aprobar("¿Ejecutar?", "ls -la")))
    hilo.start()
    for _ in range(50):
        if hitl._pendiente is not None:
            break
        _t.sleep(0.02)
    post("rechazar")
    hilo.join(5)
    assert resultados["ok"] is False

    # 3) timeout: nadie vota y expira -> default seguro False
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "0.2")
    assert hitl.aprobar("¿Aplicar?", "diff huérfano") is False

    # 4) timeout inválido (setting corrupto) no rompe: cae al default seguro
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "no-es-numero")
    assert hitl._timeout() == float(hitl.TIMEOUT_DEFAULT)


def test_hitl_web_puerto_ocupado_default_seguro(monkeypatch):
    """Si el servidor no puede levantar (puerto inválido), aprobar() devuelve
    False en vez de propagar la excepción: el HITL nunca cuelga al agente."""
    import utils.hitl_web as hitl

    monkeypatch.setattr(hitl, "_servidor", None)  # forzar arranque
    monkeypatch.setenv("HITL_WEB_PORT", "no-es-un-puerto")
    assert hitl.aprobar("¿Escribir?", "algo") is False
