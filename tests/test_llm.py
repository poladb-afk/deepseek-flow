"""Cliente LLM: historial canónico, filtrado de reasoning y lectura del .env (PR 4)."""
import pytest


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


def test_get_api_key_error_solo_ofrece_las_fuentes_del_proyecto(monkeypatch):
    """A68/X109: el error lista las fuentes que existen (entorno y el .env de
    este proyecto); el .env de otro proyecto ya no es una opción."""
    import pytest

    import utils.call_llm as c

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(c, "_setting", lambda *a, **k: None)
    with pytest.raises(RuntimeError) as exc:
        c.get_api_key()
    mensaje = str(exc.value)
    assert "DEEPSEEK_API_KEY" in mensaje and ".env de este proyecto" in mensaje
    assert "bmo" not in mensaje.lower()


# ── exp/89: tokens por llamada ──────────────────────────────────────────


def _fake(usage=None, contenido="ok", con_tools=False):
    from types import SimpleNamespace

    class FakeCompletions:
        def create(self, **kwargs):
            mensaje = SimpleNamespace(content=contenido, tool_calls=None)
            if con_tools:
                mensaje.tool_calls = None
            return SimpleNamespace(
                choices=[SimpleNamespace(message=mensaje)], usage=usage)

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    return FakeClient()


def test_call_llm_registra_el_usage_en_acumulador_y_evento(monkeypatch):
    from types import SimpleNamespace

    import utils.call_llm as c
    eventos = []
    monkeypatch.setattr(c, "_client", lambda: _fake(
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50)))
    monkeypatch.setattr("utils.tracing.evento_llm",
                        lambda pt, ct, cache_hit=None: eventos.append((pt, ct, cache_hit)))
    antes = dict(c.USO)

    c.call_llm("hola")

    assert c.USO["llamadas"] == antes["llamadas"] + 1
    assert c.USO["prompt"] == antes["prompt"] + 100
    assert c.USO["completion"] == antes["completion"] + 50
    assert eventos == [(100, 50, None)]  # el proveedor no informó el hit: desconocido, no 0


def test_respuesta_sin_usage_cuenta_cero_y_no_rompe(monkeypatch):
    import utils.call_llm as c

    monkeypatch.setattr(c, "_client", lambda: _fake(usage=None))
    antes = dict(c.USO)
    c.call_llm("hola")
    assert c.USO["llamadas"] == antes["llamadas"] + 1
    assert c.USO["prompt"] == antes["prompt"]  # 0 sumado


def test_el_stream_pide_usage_y_lo_captura_del_ultimo_chunk(monkeypatch):
    from types import SimpleNamespace

    import utils.call_llm as c
    capturado = {}

    class Chunk:
        def __init__(self, content=None, usage=None, choices=None):
            self.choices = choices if choices is not None else (
                [SimpleNamespace(delta=SimpleNamespace(
                    content=content, tool_calls=None))])
            self.usage = usage

    class FakeStream:
        def __iter__(self):
            yield Chunk(content="ho")
            yield Chunk(content="la")
            # el chunk final de usage viene SIN choices
            yield Chunk(usage=SimpleNamespace(
                prompt_tokens=200, completion_tokens=80), choices=[])

    class FakeCompletions:
        def create(self, **kwargs):
            capturado.update(kwargs)
            return FakeStream()

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_client", lambda: FakeClient())
    antes = dict(c.USO)

    r = c.call_llm_agent_stream([{"role": "user", "content": "hola"}])

    assert capturado["stream_options"] == {"include_usage": True}
    assert r.content == "hola"
    assert c.USO["prompt"] == antes["prompt"] + 200
    assert c.USO["completion"] == antes["completion"] + 80


def test_el_usage_acumula_por_modelo_con_split_de_cache(monkeypatch):
    """exp/90: cada respuesta cuenta en el desglose del modelo que la
    atendió, con el split cache hit/miss cuando el proveedor lo trae."""
    from types import SimpleNamespace

    import utils.call_llm as c

    monkeypatch.setattr(c, "_model", lambda: "modelo-falso")
    monkeypatch.setattr(c, "USO_POR_MODELO", {})
    monkeypatch.setattr(c, "_client", lambda: _fake(usage=SimpleNamespace(
        prompt_tokens=100, completion_tokens=10,
        prompt_cache_hit_tokens=60, prompt_cache_miss_tokens=40)))

    c.call_llm("hola")

    fila = c.USO_POR_MODELO["modelo-falso"]
    assert fila["llamadas"] == 1
    assert fila["prompt"] == 100
    assert fila["cache_hit"] == 60
    assert fila["cache_miss"] == 40


def test_sin_split_de_cache_todo_el_prompt_cotiza_como_miss(monkeypatch):
    """Un proveedor que no reporta el split (OpenAI genérico, mocks) no
    subestima: todo el prompt cuenta como cache miss (techo conservador)."""
    from types import SimpleNamespace

    import utils.call_llm as c

    monkeypatch.setattr(c, "_model", lambda: "modelo-falso")
    monkeypatch.setattr(c, "USO_POR_MODELO", {})
    monkeypatch.setattr(c, "_client", lambda: _fake(usage=SimpleNamespace(
        prompt_tokens=100, completion_tokens=10)))

    c.call_llm("hola")

    fila = c.USO_POR_MODELO["modelo-falso"]
    assert fila["cache_hit"] == 0
    assert fila["cache_miss"] == 100


def test_el_stream_contabiliza_en_el_modelo_del_request(monkeypatch):
    """El camino streaming también deja el uso en el modelo que viajó en
    el request (kwargs.get("model"), no una relectura del setting)."""
    from types import SimpleNamespace

    import utils.call_llm as c

    class Chunk:
        def __init__(self, usage=None, choices=None):
            self.choices = choices if choices is not None else (
                [SimpleNamespace(delta=SimpleNamespace(
                    content="ok", tool_calls=None))])
            self.usage = usage

    class FakeStream:
        def __iter__(self):
            yield Chunk(usage=SimpleNamespace(prompt_tokens=50, completion_tokens=5),
                        choices=[])

    class FakeCompletions:
        def create(self, **kwargs):
            return FakeStream()

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_model", lambda: "modelo-stream")
    monkeypatch.setattr(c, "USO_POR_MODELO", {})
    monkeypatch.setattr(c, "_client", lambda: FakeClient())

    c.call_llm_agent_stream([{"role": "user", "content": "hola"}])

    assert c.USO_POR_MODELO["modelo-stream"]["prompt"] == 50


def test_el_evento_de_uso_lleva_cache_hit_y_quien_llamo(tmp_path, monkeypatch):
    """X98: la traza dice cuántos tokens del prompt salieron del KV-cache y
    QUÉ NODO hizo la llamada — sin esto el pre-registro de la fase 2d (¿la
    llamada de Cierre reusa caché?) no tenía instrumento. Sin contenido:
    solo números y un nombre de nodo."""
    import io
    import json
    from types import SimpleNamespace

    from pocketflow import Node

    import utils.call_llm as c
    import utils.tracing as tracing

    monkeypatch.setattr(c, "_client", lambda: _fake(usage=SimpleNamespace(
        prompt_tokens=1000, completion_tokens=20, prompt_cache_hit_tokens=900,
        prompt_cache_miss_tokens=100)))
    salida = io.StringIO()
    monkeypatch.setattr(tracing, "_salida", salida)

    class Cierre(Node):
        def exec(self, _):
            return c.call_llm_agent([{"role": "user", "content": "x"}])

    tracing._en_curso.pila = ["Cierre"]  # lo que hace _run_trazado al entrar
    try:
        Cierre().exec(None)
    finally:
        tracing._en_curso.pila = []
    c.call_llm_agent([{"role": "user", "content": "fuera de un nodo"}])

    lineas = [json.loads(linea) for linea in salida.getvalue().splitlines()]
    assert lineas[0] == {**lineas[0], "cache_hit": 900, "llamador": "Cierre", "prompt_tokens": 1000}
    assert "llamador" not in lineas[1]  # fuera de un flujo no se inventa un nodo
    assert set(lineas[0]) <= {"ts", "nodo", "accion", "seg", "prompt_tokens",
                              "completion_tokens", "cache_hit", "llamador"}


def test_el_tracing_activo_registra_al_nodo_que_llama(tmp_path, monkeypatch):
    """La pila del nodo en curso la llena `_run_trazado` (el patch de
    PocketFlow): una llamada al modelo dentro de un nodo queda atribuida a
    ese nodo, y al salir la pila queda vacía (también si el nodo lanza)."""
    import pocketflow

    import utils.tracing as tracing

    vistos = []

    class Paso(pocketflow.Node):
        def exec(self, _):
            vistos.append(tracing.nodo_en_curso())

    class Roto(pocketflow.Node):
        def exec(self, _):
            raise ValueError("x")

    backup = (tracing._salida, tracing._ruta_salida, tracing._activo, tracing._id_thread)
    original = pocketflow.BaseNode._run
    try:
        tracing._activo = False
        tracing.activar(ruta_base=str(tmp_path))
        Paso()._run({})
        with pytest.raises(ValueError):
            Roto()._run({})
        assert vistos == ["Paso"]
        assert tracing.nodo_en_curso() is None
    finally:
        pocketflow.BaseNode._run = original
        if tracing._salida is not None and not tracing._salida.closed:
            tracing._salida.close()
        tracing._salida, tracing._ruta_salida, tracing._activo, tracing._id_thread = backup
