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


def call_llm_agent(messages, tools=None):
    """Una vuelta del agente: devuelve el mensaje del asistente
    (con .tool_calls si pidió herramientas).

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
    response = _client().chat.completions.create(**kwargs)
    return response.choices[0].message


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
