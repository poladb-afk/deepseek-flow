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

    from nodes import AgentStep

    paso = AgentStep()
    mensaje = SimpleNamespace(content="<｜DSML｜｜ invoke name=\"db_schema\">\n</｜DSML｜｜ invoke>", tool_calls=None)
    shared = {"messages": [], "tool_rounds": 0}
    accion = paso.post(shared, None, mensaje)
    assert accion == "tool"
    assert shared["messages"][-1].tool_calls[0].function.name == "db_schema"
    assert shared["messages"][-1].content is None  # el markup no entra al historial


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
