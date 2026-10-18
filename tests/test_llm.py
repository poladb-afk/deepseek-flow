"""Cliente LLM: historial canónico, filtrado de reasoning y lectura del .env (PR 4)."""


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

def test_from_env_file_tolera_export(tmp_path):
    """Fragilidad medida en la caza: una línea `export KEY=valor` en un .env
    NO matcheaba (key quedaba 'export KEY') y rompía la resolución del
    setting/API key. Ahora se tolera con o sin espacio tras export."""
    import utils.call_llm as c

    env = tmp_path / ".env"
    env.write_text(
        "# comentario\n"
        "export LLM_API_KEY=sk-abc\n"
        "export   OTRA=sin-espacios-raros\n"
        "NORMAL=valor-plano\n"
        "export CON_COMILLAS='citado'\n",
        encoding="utf-8",
    )
    assert c._from_env_file(env, "LLM_API_KEY") == "sk-abc"
    assert c._from_env_file(env, "OTRA") == "sin-espacios-raros"
    assert c._from_env_file(env, "NORMAL") == "valor-plano"
    assert c._from_env_file(env, "CON_COMILLAS") == "citado"
    assert c._from_env_file(env, "NO_EXISTE") is None


def test_get_api_key_error_menciona_bmo_condicional(monkeypatch):
    """A68: el error ofrecía el .env de bmo como fuente incondicional; bmo
    solo se lee con LEER_BMO_ENV=1. El mensaje debe decirlo."""
    import pytest

    import utils.call_llm as c

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(c, "_setting", lambda *a, **k: None)
    with pytest.raises(RuntimeError) as exc:
        c.get_api_key()
    assert "LEER_BMO_ENV=1" in str(exc.value)
