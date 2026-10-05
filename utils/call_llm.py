"""Cliente DeepSeek para PocketFlow (API compatible con OpenAI).

La API key no se copia a este proyecto: se resuelve en tiempo de ejecución
en este orden:
  1. Variable de entorno DEEPSEEK_API_KEY
  2. LLM_API_KEY en el .env de este proyecto
  3. LLM_API_KEY en ~/Documentos/00_IA/bmo/.env
La clave nunca se imprime ni se loguea.
"""
import os
from pathlib import Path
from types import SimpleNamespace

from openai import AsyncOpenAI, OpenAI

DEFAULT_MODEL = "deepseek-flash"  # alias oficial de DeepSeek V4.1-Flash
DEFAULT_BASE_URL = "https://api.deepseek.com"
BMO_ENV = Path.home() / "Documentos" / "00_IA" / "bmo" / ".env"
PROJECT_ENV = Path(__file__).resolve().parent.parent / ".env"


def _from_env_file(path, name):
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip().strip("'\"")
    return None


def _setting(name, default=None):
    value = os.environ.get(name)
    if value:
        return value
    for env_path in (PROJECT_ENV, BMO_ENV):
        value = _from_env_file(env_path, name)
        if value:
            return value
    return default


def get_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY") or _setting("LLM_API_KEY")
    if not key:
        raise RuntimeError(
            "API key de DeepSeek no encontrada. Opciones:\n"
            "  1. export DEEPSEEK_API_KEY=...\n"
            "  2. LLM_API_KEY=... en un .env (este proyecto o ~/Documentos/00_IA/bmo/.env)"
        )
    return key


def _client():
    return OpenAI(
        api_key=get_api_key(),
        base_url=_setting("LLM_BASE_URL", DEFAULT_BASE_URL),
    )


def _model():
    return _setting("LLM_MODEL", DEFAULT_MODEL)


def call_llm(messages):
    """Acepta el historial completo [{"role", "content"}, ...] o un string."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    response = _client().chat.completions.create(
        model=_model(),
        messages=messages,
    )
    return response.choices[0].message.content


def _kwargs_agente(messages, tools=None):
    """Contrato de modo thinking compartido por la versión clásica y la de
    streaming (MISMA lógica: no puede haber deriva entre las dos).

    Thinking: la API rechaza tools+thinking juntos (A1, como bmo) y
    también los FLIPS de modo dentro de una conversación (400
    'reasoning_content must be passed back', medido en ambas direcciones:
    ON→OFF entre turnos, OFF→ON al tope de rondas). El modo es pegajoso:
    con tráfico de tools en el historial va desactivado aunque esta
    llamada no traiga tools; conversación limpia va con thinking normal
    (correr directo en disabled midió descarrilos: prompts ajenos, tags
    que parten palabras)."""
    # el reasoning_content del modo thinking no viaja (parte del mismo
    # contrato de consistencia de modo)
    limpio = [
        {k: v for k, v in m.items() if k != "reasoning_content"}
        if isinstance(m, dict) else m
        for m in messages
    ]
    agentico = any(
        isinstance(m, dict) and (m.get("role") == "tool" or m.get("tool_calls"))
        for m in limpio
    )
    kwargs = {"model": _model(), "messages": limpio}
    if tools or agentico:
        if tools:
            kwargs["tools"] = tools
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return kwargs


def call_llm_agent(messages, tools=None):
    """Una vuelta del agente: devuelve el mensaje del asistente
    (con .tool_calls si pidió herramientas)."""
    response = _client().chat.completions.create(**_kwargs_agente(messages, tools))
    return response.choices[0].message


def call_llm_agent_stream(messages, tools=None):
    """Igual contrato que call_llm_agent (mismo modo thinking pegajoso,
    mismo filtro de reasoning_content) pero con stream=True: imprime EN
    VIVO cada delta de CONTENT a medida que llega (flush, sin saltos de
    línea extra) y NO imprime los deltas de reasoning_content.

    Al terminar devuelve un objeto con la forma que usa hoy el chat:
    .content completo ensamblado y .tool_calls reconstruidos desde los
    fragmentos del stream (llegan partidos con index; id y function.name
    solo en el primer fragmento de cada llamada, function.arguments se
    acumula por concatenación). Si el stream se corta a mitad, devuelve lo
    acumulado sin explotar.

    Interrupción del usuario (roadmap ítem 6): si el usuario aprieta Ctrl+C
    MIENTRAS se genera, con CHAT_STREAM_INTERRUPT=1 (default) se corta el
    stream y se devuelve lo acumulado (el chat sigue, no se cae); se imprime
    un aviso "[interrumpido]". Con 0, el Ctrl+C se propaga como siempre
    (main lo toma como salida). El Ctrl+C fuera del stream no se toca."""
    stream = _client().chat.completions.create(
        **_kwargs_agente(messages, tools), stream=True
    )
    interrumpible = _setting("CHAT_STREAM_INTERRUPT", "1") == "1"
    contenido = []
    por_indice = {}  # index -> {"id", "name", "arguments"}
    cortado = False
    try:
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            texto = getattr(delta, "content", None)
            if texto:
                # en vivo: sin salto extra, flush para que se vea ya
                print(texto, end="", flush=True)
                contenido.append(texto)
            # los deltas de reasoning_content NO se imprimen (se descartan)
            for frag in getattr(delta, "tool_calls", None) or []:
                idx = frag.index if frag.index is not None else 0
                acumulado = por_indice.setdefault(
                    idx, {"id": None, "name": None, "arguments": ""})
                if getattr(frag, "id", None):
                    acumulado["id"] = frag.id  # solo el primer fragmento lo trae
                funcion = getattr(frag, "function", None)
                if funcion is not None:
                    if getattr(funcion, "name", None):
                        acumulado["name"] = funcion.name
                    if getattr(funcion, "arguments", None):
                        acumulado["arguments"] += funcion.arguments
    except KeyboardInterrupt:
        # Ctrl+C durante la generación: si la interrupción está activa se
        # corta acá y se devuelve lo acumulado (el chat sigue vivo); si no,
        # se propaga para que main la trate como salida.
        if not interrumpible:
            raise
        cortado = True
        print("\n  [interrumpido] generación cortada por el usuario")
    except Exception:
        # stream cortado a mitad (red, etc.): se devuelve lo acumulado
        cortado = True
    # cierra el stream si quedó abierto por la interrupción (libera la conexión)
    if cortado:
        cerrar = getattr(stream, "close", None)
        if callable(cerrar):
            try:
                cerrar()
            except Exception:
                pass
    tool_calls = [
        SimpleNamespace(
            id=acum["id"],
            type="function",
            function=SimpleNamespace(name=acum["name"], arguments=acum["arguments"]),
        )
        for _, acum in sorted(por_indice.items())
    ]
    return SimpleNamespace(
        content="".join(contenido) or None,
        tool_calls=tool_calls or None,
    )


async def call_llm_async(messages):
    """Versión async de call_llm: para AsyncParallelBatchNode/Flow,
    donde cada exec_async debe esperar I/O real para que se solapen."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    response = await AsyncOpenAI(
        api_key=get_api_key(),
        base_url=_setting("LLM_BASE_URL", DEFAULT_BASE_URL),
    ).chat.completions.create(
        model=_model(),
        messages=messages,
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    print(call_llm("Responde en una sola frase: ¿qué modelo eres?"))
