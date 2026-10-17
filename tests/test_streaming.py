"""Streaming del chat: deltas en vivo, thinking pegajoso, interrupción y cortes (PR 4)."""
import pytest


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

def test_stream_alimenta_historial_canonico_y_dsml(monkeypatch):
    """El mensaje del stream es drop-in del clásico: historiarlo da el dict
    canónico (sin reasoning) y el transcript DSML en vivo se recupera como
    tool calls estructuradas."""
    from types import SimpleNamespace

    import nodes
    import utils.call_llm as c

    def chunk(content=None, reasoning=None):
        delta = SimpleNamespace(content=content, reasoning_content=reasoning,
                                tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

    def fake_stream(chunks):
        class FakeCompletions:
            def create(self, **kwargs):
                return iter(chunks)

        class FakeClient:
            chat = SimpleNamespace(completions=FakeCompletions())

        monkeypatch.setattr(c, "_client", lambda: FakeClient())

    # 1) respuesta de texto: historiarla da el canónico sin reasoning
    fake_stream([chunk(reasoning="no viaja "), chunk(content="Hola"), chunk(content=" mundo")])
    msg = c.call_llm_agent_stream([{"role": "user", "content": "x"}])
    h = nodes.historiar(msg)
    assert h == {"role": "assistant", "content": "Hola mundo"}
    assert "reasoning_content" not in h

    # 2) DSML emitido como texto: llega fragmentado por el stream y la
    #    recuperación (en AgentStep.exec) lo vuelve tool_calls estructuradas
    dsml = '<｜DSML｜｜ invoke name="db_schema">\n</｜DSML｜｜ invoke>'
    fake_stream([chunk(dsml[:20]), chunk(dsml[20:])])
    reactivado = {"via": False}

    def en_stream(msgs, tools=None):
        reactivado["via"] = True
        return c.call_llm_agent_stream(msgs, tools)

    monkeypatch.setattr(nodes, "call_llm_agent_stream", en_stream)
    monkeypatch.setenv("CHAT_STREAM", "1")
    # con tools OFRECIDAS la recuperación corre: markup → tool_calls
    out = nodes.AgentStep().exec(([{"role": "user", "content": "esquema"}], ["tool"]))
    assert reactivado["via"]
    assert out.content is None  # el markup crudo no queda en el historial
    assert out.tool_calls[0].function.name == "db_schema"
    # con tools RETIRADAS (tope L8) el markup NO se re-arma (exp/12):
    # queda el mensaje honesto y no hay tool_calls que ejecutar
    out2 = nodes.AgentStep().exec(([{"role": "user", "content": "esquema"}], None))
    assert out2.tool_calls is None
    assert "seguí" in out2.content

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

def test_agent_step_post_no_reimprime_con_stream(monkeypatch, capsys):
    """Con streaming el contenido ya se imprimió en vivo (deltas); post NO
    debe repetir la respuesta completa — solo cierra la línea. Con la
    versión clásica, sí la imprime con el prefijo."""
    from types import SimpleNamespace

    import nodes

    mensaje = SimpleNamespace(content="respuesta en vivo", tool_calls=None)

    monkeypatch.setenv("CHAT_STREAM", "1")
    nodes.AgentStep().post({"messages": []}, None, mensaje)
    salida = capsys.readouterr().out
    assert "respuesta en vivo" not in salida  # no se repite
    assert salida == "\n"  # solo cierra la línea

    monkeypatch.setenv("CHAT_STREAM", "0")
    nodes.AgentStep().post({"messages": []}, None, mensaje)
    salida = capsys.readouterr().out
    assert "DeepSeek: respuesta en vivo" in salida

def test_call_llm_agent_stream_interrupcion(monkeypatch, capsys):
    """Ctrl+C durante la generación: con CHAT_STREAM_INTERRUPT=1 (default)
    se corta el stream, se devuelve lo acumulado (el chat sigue) y se avisa;
    con 0, el KeyboardInterrupt se propaga (main lo trata como salida)."""
    from types import SimpleNamespace

    import utils.call_llm as c

    def chunk(content):
        return SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content=content, reasoning_content=None, tool_calls=None))])

    class FakeCompletions:
        def create(self, **kwargs):
            def gen():
                yield chunk("Hola ")
                yield chunk("mundo")
                raise KeyboardInterrupt  # el usuario aprieta Ctrl+C acá

            return gen()

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_client", lambda: FakeClient())

    # activada (default): devuelve lo parcial sin explotar
    monkeypatch.setenv("CHAT_STREAM_INTERRUPT", "1")
    msg = c.call_llm_agent_stream([{"role": "user", "content": "hola"}])
    assert msg.content == "Hola mundo"
    salida = capsys.readouterr().out
    assert "Hola mundo" in salida and "[interrumpido]" in salida

    # desactivada: el KeyboardInterrupt viaja (no lo traga el stream)
    monkeypatch.setenv("CHAT_STREAM_INTERRUPT", "0")
    with pytest.raises(KeyboardInterrupt):
        c.call_llm_agent_stream([{"role": "user", "content": "hola"}])

def test_stream_error_sin_contenido_no_es_mudo(monkeypatch, capsys):
    """Fragilidad medida en la caza: el except genérico del stream devolvía
    lo acumulado, así que un 401/429/error de red con CERO contenido daba una
    respuesta vacía sin causa visible. Ahora la causa se imprime cuando no
    quedó nada; con contenido parcial el corte no agrega ruido."""
    from types import SimpleNamespace

    import utils.call_llm as c

    def chunk(content):
        return SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content=content, reasoning_content=None, tool_calls=None))])

    class RuntimeException(Exception):
        pass

    # 1) falla ANTES de cualquier chunk: no hay contenido → se imprime la causa
    class FakeCompletionsCrudo:
        def create(self, **kwargs):
            def gen():
                raise RuntimeException("API caída: 401 no autorizado")
                yield  # nunca llega (gen con raise adentro)

            return gen()

    class FakeClient1:
        chat = SimpleNamespace(completions=FakeCompletionsCrudo())

    monkeypatch.setattr(c, "_client", lambda: FakeClient1())
    msg = c.call_llm_agent_stream([{"role": "user", "content": "hola"}])
    assert msg.content is None
    salida = capsys.readouterr().out
    assert "[stream]" in salida and "RuntimeException" in salida
    assert "401 no autorizado" in salida

    # 2) falla DESPUÉS de emitir contenido: no se imprime la causa (benigno)
    class FakeCompletionsParcial:
        def create(self, **kwargs):
            def gen():
                yield chunk("Hola ")
                raise RuntimeException("corte de red")  # contenido ya hubo

            return gen()

    class FakeClient2:
        chat = SimpleNamespace(completions=FakeCompletionsParcial())

    monkeypatch.setattr(c, "_client", lambda: FakeClient2())
    msg = c.call_llm_agent_stream([{"role": "user", "content": "hola"}])
    assert msg.content == "Hola "
    salida = capsys.readouterr().out
    assert "[stream]" not in salida  # se conserva parcial, sin ruido de causa

def test_stream_agrega_etiqueta_deepseek(monkeypatch, capsys):
    """La respuesta streameada llega con su rótulo (nit de UX, mesa 8)."""
    from types import SimpleNamespace

    import nodes

    def fake_stream(msgs, tools=None):
        print("hola", end="", flush=True)  # el stream real imprime los deltas
        return SimpleNamespace(content="hola", tool_calls=None)

    monkeypatch.setattr(nodes, "call_llm_agent_stream", fake_stream)
    shared = {"messages": [{"role": "user", "content": "q"}], "tool_rounds": 0}
    accion = nodes.AgentStep()._run(shared)
    assert accion == "answer"
    salida = capsys.readouterr().out
    assert "DeepSeek: " in salida and "hola" in salida


def test_stream_reenvia_tools_y_mensajes_al_request(monkeypatch):
    """El pedido del stream debe llevar el MISMO tools/messages que el
    clásico; el ensamblado de deltas estaba probado, el contrato del request
    no. Evidencia: mutantes que reemplazaban tools por None sobrevivían
    (Fase 1, M4)."""
    from types import SimpleNamespace

    import utils.call_llm as c

    capturado = {}

    class FakeCompletions:
        def create(self, **kwargs):
            capturado.update(kwargs)

            def gen():
                delta = SimpleNamespace(content="ok", reasoning_content=None, tool_calls=None)
                yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

            return gen()

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_client", lambda: FakeClient())
    tools = [{"type": "function", "function": {"name": "read_file", "parameters": {}}}]
    mensajes = [{"role": "user", "content": "hola"}]
    msg = c.call_llm_agent_stream(mensajes, tools=tools)
    assert msg.content == "ok"
    assert capturado["tools"] == tools
    assert capturado["messages"] == mensajes
