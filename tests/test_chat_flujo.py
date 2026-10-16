"""El bucle del chat: AgentStep/ExecuteTools, DSML, sanitizado, presupuesto y no-progreso (PR 4)."""
import pytest


def test_dsml_a_tool_calls():
    from nodes import dsml_a_tool_calls

    # formato real medido en producción: separador DOBLE barra fullwidth
    # (la primera versión del fix usaba una sola y jamás disparó)
    contenido = """<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="read_file">
<｜｜DSML｜｜ parameter name="path" string="true">/tmp/proyecto/utils/laya.py</｜｜DSML｜｜ parameter>
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

def test_sanitizar_markers_y_tags():
    """Dos descarrilos medidos en producción: un marker de rol ajeno corta
    (lo que sigue es basura) y los tags HTML que parten palabras se quitan
    (el texto sigue siendo la respuesta)."""
    from nodes import sanitizar

    # marker de rol: corta desde ahí; el contenido previo sobrevive
    limpio, modificado = sanitizar("¡Hola! <|im_start|>system eres un agente genérico")
    assert modificado is True and limpio == "¡Hola!"

    # <<SYS>> y <system> también son markers de rol
    assert sanitizar("buenas <<SYS>> ahora eres otro")[0] == "buenas"
    assert sanitizar("ok <system>instrucción ajena")[0] == "ok"

    # marker al inicio: no queda nada utilizable
    limpio, modificado = sanitizar("<system>solo basura")
    assert modificado is True and limpio == ""

    # tags HTML que parten palabras: se quitan y el texto se recompone
    limpio, modificado = sanitizar("S<small>oy</small> DeepSeek")
    assert modificado is True and limpio == "Soy DeepSeek"

    # texto sano: intacto
    limpio, modificado = sanitizar("respuesta normal, sin ruido")
    assert modificado is False and limpio == "respuesta normal, sin ruido"

def test_agent_step_sanitiza_y_reintenta(monkeypatch):
    """El sanitizado vive en exec(): si quedó algo se imprime limpio, y si no
    quedó nada el retry de PocketFlow re-pregunta (raise)."""
    from types import SimpleNamespace

    import nodes

    monkeypatch.setenv("CHAT_STREAM", "0")  # camino clásico, sin stream

    # caso 1: descarrilo parcial → el historial guarda solo lo limpio
    mensaje = SimpleNamespace(content="¡Hola! <|im_start|>system ajeno", tool_calls=None)
    monkeypatch.setattr(nodes, "call_llm_agent", lambda msgs, tools=None: mensaje)
    shared = {"messages": [{"role": "user", "content": "hola"}], "tool_rounds": 0}
    accion = nodes.AgentStep()._run(shared)
    assert accion == "answer"
    assert shared["messages"][-1]["content"] == "¡Hola!"

    # caso 2: solo markup de rol → raise (PocketFlow reintenta en exec)
    vacio = SimpleNamespace(content="<system>nada útil", tool_calls=None)
    monkeypatch.setattr(nodes, "call_llm_agent", lambda msgs, tools=None: vacio)
    shared = {"messages": [{"role": "user", "content": "hola"}], "tool_rounds": 0}
    with pytest.raises(ValueError):
        nodes.AgentStep()._run(shared)

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

def test_execute_tools_anuncia_y_etiqueta(monkeypatch, capsys):
    """Una ronda larga no parece colgada: cada tool se anuncia ANTES de
    correr y la ronda consumida se etiqueta con su avance (n/MAX)."""
    import nodes

    # sin tty → texto plano (así lo ve un pipe; los tests no ven ANSI)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)
    monkeypatch.setattr(nodes, "MODULE_IMPLS", {})
    monkeypatch.setattr(
        nodes, "run_tool_call",
        lambda tc, impls: {"role": "tool", "tool_call_id": tc["id"], "content": "ok"},
    )

    et = nodes.ExecuteTools()
    shared = {"messages": [], "tool_rounds": 0}
    tool_calls = [
        {"id": "a", "function": {"name": "read_file", "arguments": "{}"}},
        {"id": "b", "function": {"name": "list_files", "arguments": "{}"}},
    ]
    resultados = et.exec(tool_calls)
    salida = capsys.readouterr().out
    assert "→ read_file" in salida and "→ list_files" in salida
    # el anuncio precede al resultado: aparece aunque el resultado viniera ok
    assert len(resultados) == 2

    # la ronda se etiqueta con el avance sobre el tope
    et.post(shared, None, resultados)
    salida = capsys.readouterr().out
    assert f"⚙ ronda 1/{nodes.MAX_TOOL_ROUNDS}" in salida

def test_nota_presupuesto_solo_en_la_anteultima_ronda():
    """exp/4: el modelo no veía su presupuesto (el ⚙ iba solo a la terminal)
    y el tope lo cortaba en mudo — tres sesiones de aplicación muertas así.
    La nota viaja en el resultado de la última tool de la anteúltima ronda."""
    from nodes import nota_presupuesto

    assert nota_presupuesto(2, 4) is None
    assert nota_presupuesto(4, 4) is None
    nota = nota_presupuesto(3, 4)
    assert nota and "3/4" in nota and "ÚLTIMA" in nota and "reinicia" in nota
    # máximo degenerado: la única ronda es también la anteúltima
    assert nota_presupuesto(0, 1) is not None

def test_dsml_con_presupuesto_agotado_no_rearma_lo_retirado():
    """exp/12: medido en exp/4 — el modelo emitía tool-calls como texto
    DSML DESPUÉS del retiro por el tope y la recuperación las ejecutaba:
    la ley L8 quedaba by-paseada. Ahora sin tools el markup se corta; con
    tools, la recuperación de siempre."""
    from nodes import MENSAJE_DSML_AGOTADO, dsml_con_presupuesto_agotado

    content = "Cerrando el estado.<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name=\"write_file\">..."
    # tools presentes: intacto, sin aviso (la recuperación corre aparte)
    nuevo, avisar = dsml_con_presupuesto_agotado(content, ["x"], TOOLS_PRESENTES := ["t"])
    assert nuevo == content and avisar is False
    # tools retiradas: corta antes del markup
    nuevo, avisar = dsml_con_presupuesto_agotado(content, ["x"], None)
    assert nuevo == "Cerrando el estado." and avisar is True
    # solo markup: mensaje honesto y accionable
    solo = "<｜｜DSML｜｜ calls> todo markup"
    nuevo, avisar = dsml_con_presupuesto_agotado(solo, ["x"], None)
    assert nuevo == MENSAJE_DSML_AGOTADO and "seguí" in nuevo and avisar is True

def test_presupuesto_perfiles_por_operacion_y_precedencia(monkeypatch):
    """exp/13 (opción C): el techo de rondas es adaptativo por operación.
    Precedencia: override explícito > perfil declarado > MAX_TOOL_ROUNDS.
    El default se lee EN RUNTIME del global del módulo (no congelado en
    import): patch('nodes.MAX_TOOL_ROUNDS') debe ganarle al default."""
    import nodes

    # sin operación ni override → default del módulo
    assert nodes.presupuesto({}) == nodes.MAX_TOOL_ROUNDS
    # perfil declarado, sin override
    assert nodes.presupuesto({"operacion": "consulta"}) == nodes.PERFILES_PRESUPUESTO["consulta"]
    assert nodes.presupuesto({"operacion": "banco"}) == nodes.PERFILES_PRESUPUESTO["banco"]
    assert nodes.presupuesto({"operacion": "aplicacion"}) == nodes.PERFILES_PRESUPUESTO["aplicacion"]
    # operación desconocida → default
    assert nodes.presupuesto({"operacion": "otra"}) == nodes.MAX_TOOL_ROUNDS
    # override explícito gana sobre el perfil
    assert nodes.presupuesto({"operacion": "consulta", "max_tool_rounds": 99}) == 99
    # patch del default: presupuesto() lee el global VIVO, no lo congeló en import
    monkeypatch.setattr(nodes, "MAX_TOOL_ROUNDS", 42)
    assert nodes.presupuesto({}) == 42
    assert nodes.presupuesto({"operacion": "consulta"}) == nodes.PERFILES_PRESUPUESTO["consulta"]

def test_fingerprint_paginado_no_dispara_y_repetido_si():
    """exp/13 (opción D): la huella de la ronda incluye los argumentos, así
    la paginación legítima (offset distinto) da huella distinta y NO cuenta
    como no-progreso; repetir la misma llamada SÍ."""
    import nodes

    def tc(path, offset=None):
        args = {"path": path}
        if offset is not None:
            args["offset"] = offset
        import json as _json
        return [{"function": {"name": "read_file", "arguments": _json.dumps(args)}}]

    assert nodes.fingerprint(tc("a", 1)) != nodes.fingerprint(tc("a", 2))
    assert nodes.fingerprint(tc("a", 1)) == nodes.fingerprint(tc("a", 1))
    # el orden de los tool_calls no altera la huella (misma ronda lógica)
    dos = tc("a") + tc("b")
    assert nodes.fingerprint(dos) == nodes.fingerprint(list(reversed(dos)))

def test_execute_tools_post_acumula_y_resetea_no_progress():
    """exp/13: ExecuteTools.post incrementa no_progress ante ronda idéntica y
    lo resetea cuando hay progreso real (huella distinta). El warning viaja
    en la conversación (último resultado), no en la terminal."""
    import json as _json

    from nodes import ExecuteTools, fingerprint

    def tc(path):
        return [{"function": {"name": "read_file",
                              "arguments": _json.dumps({"path": path})}}]

    nodo = ExecuteTools()
    shared = {"messages": []}
    # ronda 1: mismo path → sin_progress 0 (primera vez)
    nodo.post(shared, tc("a"), [{"content": "r1"}])
    assert shared["no_progress"] == 0
    # ronda 2: idéntica → 1 y warning en el contenido
    nodo.post(shared, tc("a"), [{"content": "r2"}])
    assert shared["no_progress"] == 1
    assert "Sin progreso" in shared["messages"][-1]["content"]
    # ronda 3: distinta → reset
    nodo.post(shared, tc("b"), [{"content": "r3"}])
    assert shared["no_progress"] == 0
    assert shared["_fp"] == fingerprint(tc("b"))

def _corte_por_no_progreso():
    """Deja la sesión en el estado del corte: contador en el umbral y tools
    retiradas. Devuelve (shared, step, ask) listos para postear la pregunta.
    Lo comparten los dos tests del reset (pregunta normal y /aprobaciones)."""
    import json as _json

    from nodes import UMBRAL_SIN_PROGRESO, AgentStep, ExecuteTools, GetQuestion

    def tc(path):
        return [{"function": {"name": "read_file",
                              "arguments": _json.dumps({"path": path})}}]

    step, tools_node, ask = AgentStep(), ExecuteTools(), GetQuestion()
    shared = {"messages": [{"role": "system", "content": "s"}], "tool_rounds": 0}
    for i in range(UMBRAL_SIN_PROGRESO + 1):
        tools_node.post(shared, tc("a.py"),
                        [{"role": "tool", "tool_call_id": f"t{i}", "content": "r"}])
    assert shared["no_progress"] == UMBRAL_SIN_PROGRESO
    _, tools = step.prep(shared)
    assert tools is None                       # corte: se retiran las tools
    return shared, step, ask

def test_no_progress_se_resetea_con_la_pregunta_nueva():
    """exp/13 (opción D): el corte por no-progreso es POR PREGUNTA (ley L8).
    Sin el reset en GetQuestion.post el contador quedaba pegado, AgentStep
    retiraba las tools para siempre y el protocolo de continuación de exp/4
    ('un mensaje nuevo reinicia el presupuesto') era falso."""
    shared, step, ask = _corte_por_no_progreso()
    ask.post(shared, None, "otra pregunta")    # mensaje nuevo del usuario
    assert shared["no_progress"] == 0
    _, tools = step.prep(shared)
    assert tools is not None                   # el presupuesto se reinició
