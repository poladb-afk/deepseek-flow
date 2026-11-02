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

    # la ronda se etiqueta con el avance sobre el tope (la cuenta Observar, X96)
    et.post(shared, None, resultados)
    nodes.Observar().post(shared, tool_calls, None)
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
    """Precedencia del techo: override explícito > MAX_TOOL_ROUNDS, leído EN
    RUNTIME del global del módulo. Los perfiles por `operacion` (exp/13) se
    borraron en X93: ningún invocador los declaraba; una `operacion` que
    llegue en shared ya no cambia nada."""
    import nodes

    assert nodes.presupuesto({}) == nodes.MAX_TOOL_ROUNDS
    assert nodes.presupuesto({"operacion": "aplicacion"}) == nodes.MAX_TOOL_ROUNDS
    assert nodes.presupuesto({"max_tool_rounds": 99}) == 99
    monkeypatch.setattr(nodes, "MAX_TOOL_ROUNDS", 42)
    assert nodes.presupuesto({}) == 42

def test_run_tool_call_devuelve_error_como_feedback():
    """Los fallos del lado del modelo no rompen el lote: tool inexistente
    (objeto alucinado), argumentos JSON inválidos (generación incompleta) y
    argumento de tipo equivocado (wrong input type) vuelven como texto
    ERROR, no excepción. Evidencia de F3: 255 runs de .runs muestran 68
    errores de tool y 3 llamadas a tools inexistentes (`grep`, `bash`); el
    patrón de Tambon dice que son los fallos típicos de código LLM."""
    import json

    from utils.fs_tools import run_tool_call

    def tc(nombre, args):
        return {"id": "c1", "type": "function",
                "function": {"name": nombre, "arguments": args}}

    r = run_tool_call(tc("herramienta_fantasma", "{}"))
    assert r["content"].startswith("ERROR: herramienta desconocida")

    r = run_tool_call(tc("read_file", "{no-json"))
    assert r["content"].startswith("ERROR:")

    r = run_tool_call(tc("read_file", json.dumps({"inventado": 1})))
    assert r["content"].startswith("ERROR:")


def test_codigo_error_discrimina_sin_contenido():
    """La traza guarda un código corto de la causa, no el texto del error
    (F4/A32: sin esto las causas eran inatribuibles)."""
    from nodes import codigo_error

    assert codigo_error("ERROR: JSONDecodeError: bad") == "ERROR:JSONDecodeError"
    assert codigo_error("ERROR: herramienta desconocida: grep") == "ERROR:herramienta"
    assert codigo_error("ERROR: ruta fuera de los directorios") == "ERROR:ruta"
    assert codigo_error("RECHAZADO por el usuario") == "RECHAZADO"
    assert codigo_error("exit 1\n[stderr] x") == "exit_1"
    assert codigo_error("exit 0\nbien") == ""
    assert codigo_error("hola") == ""


def test_agotado_fuerza_respuesta_sin_tools():
    """Al agotarse el presupuesto la última llamada va sin tools y con un aviso
    efímero de cierre: medido en vivo, sin él el modelo sigue emitiendo tool
    calls en vez de responder (A38). Desde X96 lo garantiza la ESTRUCTURA:
    Contexto sale a `cierre` y el nodo Cierre corre una vez — el flag
    `aviso_cierre` que evitaba duplicarlo ya no existe. La pregunta nueva
    reabre el presupuesto."""
    from nodes import AVISO_CIERRE, MAX_TOOL_ROUNDS, Cierre, Contexto, GetQuestion, nuevo_turno

    shared = {"messages": [{"role": "system", "content": "s"},
                             {"role": "user", "content": "auditá el repo"}],
              "turno": {**nuevo_turno(), "rondas": MAX_TOOL_ROUNDS}}
    assert Contexto()._run(shared) == "cierre"
    mensajes, tools = Cierre().prep(shared)
    assert tools is None
    assert mensajes[-1]["content"] == AVISO_CIERRE
    # el aviso es EFÍMERO: no entra al historial
    assert all(m.get("content") != AVISO_CIERRE for m in shared["messages"])
    assert "aviso_cierre" not in shared["turno"]

    GetQuestion().post(shared, None, "otra pregunta")
    assert Contexto()._run(shared) == "herramientas"


def test_getquestion_cierra_el_costo_de_la_pregunta_anterior(monkeypatch):
    """exp/90: la pregunta nueva cierra la ANTERIOR con el delta del
    desglose (volvió por "answer"); la primera solo deja el snapshot."""
    import utils.call_llm as c
    from nodes import GetQuestion

    def _fila(prompt):
        return {"llamadas": 1, "prompt": prompt, "completion": 0,
                "cache_hit": 0, "cache_miss": prompt}

    uso = {"deepseek-flash": _fila(100)}
    monkeypatch.setattr(c, "USO_POR_MODELO", uso)
    shared = {"messages": [{"role": "system", "content": "s"}]}

    GetQuestion().post(shared, None, "primera")
    assert "tokens_por_pregunta" not in shared
    assert shared["turno"]["uso_inicio"]["deepseek-flash"]["prompt"] == 100

    # la primera pregunta respondió gastando 50 más: la segunda la cierra
    uso["deepseek-flash"] = _fila(150)
    GetQuestion().post(shared, None, "segunda")
    cerradas = shared["tokens_por_pregunta"]
    assert len(cerradas) == 1
    assert cerradas[0]["deepseek-flash"]["prompt"] == 50


def test_preguntas_reales_ignora_prefetch_y_compaccion():
    """El resumen de sesión cuenta preguntas REALES: un mensaje sintético de
    prefetch o el marcador de compacción no lo disparan (medido en vivo)."""
    from modules.memoria import preguntas_reales as _preguntas_reales

    mensajes = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "auditá el repo"},
        {"role": "user", "content": "[pre-fetch] /tmp/x (primeras 5 líneas):\nh"},
        {"role": "user", "content": "[compacción] 3 mensajes anteriores compactados."},
    ]
    assert _preguntas_reales(mensajes) == 1


def test_post_verifica_citas_y_corrige(monkeypatch, capsys):
    """A40: si la respuesta cita una línea inexistente, se detecta contra el
    disco y se pide UNA corrección (sin tools). Evidencia: sesiones reales con
    citas de línea corridas (S5/S6)."""
    from types import SimpleNamespace

    import nodes

    monkeypatch.setenv("CITAS_VERIFICAR", "1")
    monkeypatch.setenv("CHAT_STREAM", "1")
    visto = {}

    def fake_llm(msgs, tools=None):
        visto["msgs"] = msgs
        return SimpleNamespace(content="corregido en utils/tracing.py:1")

    monkeypatch.setattr(nodes, "call_llm_agent", fake_llm)
    shared = {"messages": [{"role": "system", "content": "s"},
                             {"role": "user", "content": "auditá"}]}
    contenido = "hallazgo en utils/tracing.py:1 y malo en utils/tracing.py:99999"
    exec_res = SimpleNamespace(content=contenido, tool_calls=None)
    # F6: la verificación es un NODO del grafo (answer → citas → ask), con retry
    assert nodes.AgentStep().post(shared, None, exec_res) == "answer"
    nodes.VerificarCitas()._run(shared)

    assert shared["messages"][-1]["content"] == "corregido en utils/tracing.py:1"
    salida = capsys.readouterr().out
    assert "[citas]" in salida and "99999" in salida and "corregidas" in salida
    assert visto["msgs"][-2]["content"] == contenido
    assert "99999" in visto["msgs"][-1]["content"]


def test_post_no_corrige_si_las_citas_estan_bien(monkeypatch):
    """Con citas verificadas no hay segunda llamada: la corrección es solo para
    citas que no coinciden (costo cero en el camino feliz)."""
    from types import SimpleNamespace

    import nodes

    monkeypatch.setenv("CITAS_VERIFICAR", "1")
    monkeypatch.setenv("CHAT_STREAM", "0")

    def no_llamar(msgs, tools=None):
        raise AssertionError("no debía pedir corrección con citas válidas")

    monkeypatch.setattr(nodes, "call_llm_agent", no_llamar)
    shared = {"messages": [{"role": "system", "content": "s"},
                             {"role": "user", "content": "auditá"}]}
    exec_res = SimpleNamespace(content="hallazgo en utils/tracing.py:1", tool_calls=None)
    assert nodes.AgentStep().post(shared, None, exec_res) == "answer"
    nodes.VerificarCitas()._run(shared)
    assert shared["messages"][-1]["content"] == "hallazgo en utils/tracing.py:1"


