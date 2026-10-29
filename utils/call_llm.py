"""Cliente DeepSeek para PocketFlow (API compatible con OpenAI).

Los settings se resuelven en tiempo de ejecución en este orden:
  1. Variable de entorno del proceso
  2. El .env de ESTE proyecto
  3. El .env de otro proyecto (bmo), SOLO con LEER_BMO_ENV=1 — default 0
El harness es autónomo por default: leer el .env ajeno era una dependencia
invisible (medido: la API key y el modelo salían de ahí sin avisar). La clave
nunca se imprime ni se loguea.

Una variable de entorno VACÍA cuenta como no seteada (`_setting` usa
`if value:`) y se cae al .env: documentado acá porque el consumidor ya lo
sufrió (medido en `utils/riesgo.py`: `LAYA_MODEL_RIESGO=` no apagaba el
checkpoint).
"""
import contextlib
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
        # tolera la forma shell `export KEY=valor`: sin esto, la clave
        # quedaría como 'export LLM_API_KEY' y no matchearía name (frágil
        # medido en la caza: resolvería mal la API key si alguien pega un
        # .env con export). Se tolera con o sin espacio tras export.
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        if key == name:
            return value.strip().strip("'\"")
    return None


def _leer_bmo_env():
    """¿se lee también el .env de bmo? Default 0 (el harness es autónomo).

    Se resuelve SIN _setting() a propósito: _setting es justamente la que lee
    bmo, así que preguntarle a ella sería morderse la cola."""
    valor = os.environ.get("LEER_BMO_ENV")
    if valor is None:
        valor = _from_env_file(PROJECT_ENV, "LEER_BMO_ENV")
    return (valor or "0").strip().lower() in ("1", "true", "si", "sí", "yes")


def _setting(name, default=None):
    value = os.environ.get(name)
    if value:
        return value
    rutas = (PROJECT_ENV, BMO_ENV) if _leer_bmo_env() else (PROJECT_ENV,)
    for env_path in rutas:
        value = _from_env_file(env_path, name)
        if value:
            return value
    return default


def _entero(nombre, default):
    """Un setting entero a prueba de typos: si no parsea, avisa y usa el
    default. Sin esto, un ".env" con "COMPACTION_CHARS=sesenta mil" reventaba
    en AgentStep.prep — que corre FUERA del retry del nodo — y mataba el chat
    (medido en la barrida)."""
    try:
        return int(_setting(nombre, str(default)))
    except (TypeError, ValueError):
        print(f"  [config] {nombre} no es un entero válido → uso {default}")
        return int(default)


def get_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY") or _setting("LLM_API_KEY")
    if not key:
        raise RuntimeError(
            "API key de DeepSeek no encontrada. Opciones:\n"
            "  1. export DEEPSEEK_API_KEY=...\n"
            "  2. LLM_API_KEY=... en el .env de este proyecto "
            "(el de bmo solo si LEER_BMO_ENV=1)"
        )
    return key


def _client():
    return OpenAI(
        api_key=get_api_key(),
        base_url=_setting("LLM_BASE_URL", DEFAULT_BASE_URL),
    )


def _model():
    return _setting("LLM_MODEL", DEFAULT_MODEL)


# exp/89 — uso de tokens por proceso (la traza lleva el evento por
# llamada; este acumulador alimenta el reporte de salida del chat).
USO = {"llamadas": 0, "prompt": 0, "completion": 0}

# exp/90 — el mismo uso desglosado POR MODELO y con el split de cache:
# cada modelo tiene su tarifa y el cache hit paga ~50× menos que el miss,
# así que sin esto el costo en dinero no se puede cotizar.
USO_POR_MODELO = {}


def uso_de_sesion():
    """Copia del uso acumulado (llamadas, prompt, completion)."""
    return dict(USO)


def desglose_de_sesion():
    """Copia del uso acumulado por modelo (para cotizar y por pregunta)."""
    return {modelo: dict(fila) for modelo, fila in USO_POR_MODELO.items()}


def _contabilizar(usage, modelo=None):
    """Registra el usage de UNA respuesta: acumulador + evento de traza.
    Una respuesta sin usage (proveedor viejo, mock) cuenta 0 y no rompe.

    El modelo lo pasa el sitio de llamada (el que viajó en el request).
    Sin split de cache en el usage, todo el prompt cuenta como cache miss:
    techo conservador — el reporte de dinero nunca subestima."""
    pt = int(getattr(usage, "prompt_tokens", 0) or 0)
    ct = int(getattr(usage, "completion_tokens", 0) or 0)
    hit = int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0)
    miss = int(getattr(usage, "prompt_cache_miss_tokens", 0) or 0) or (pt - hit)
    USO["llamadas"] += 1
    USO["prompt"] += pt
    USO["completion"] += ct
    fila = USO_POR_MODELO.setdefault(
        modelo or "(sin modelo)",
        {"llamadas": 0, "prompt": 0, "completion": 0,
         "cache_hit": 0, "cache_miss": 0},
    )
    fila["llamadas"] += 1
    fila["prompt"] += pt
    fila["completion"] += ct
    fila["cache_hit"] += hit
    fila["cache_miss"] += miss
    with contextlib.suppress(Exception):
        from utils.tracing import evento_llm

        informado = getattr(usage, "prompt_cache_hit_tokens", None) is not None
        evento_llm(pt, ct, cache_hit=hit if informado else None)


def call_llm(messages):
    """Una pasada SIMPLE, sin agente: sin tools, sin thinking, sin streaming.

    Acepta el historial completo [{"role", "content"}, ...] o un string (lo
    convierte a un mensaje user). Devuelve SOLO el texto de la respuesta
    (`message.content`): si el proveedor devolviera `tool_calls` o
    `reasoning_content`, se descartan; tampoco manda el `extra_body` de
    thinking. `content` puede ser string o lista de bloques (visión): el
    passthrough de OpenAI lo admite.
    """
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    modelo = _model()
    response = _client().chat.completions.create(
        model=modelo,
        messages=messages,
    )
    _contabilizar(getattr(response, "usage", None), modelo)
    return response.choices[0].message.content


def _kwargs_agente(messages, tools=None):
    """Contrato de modo thinking compartido por la versión clásica y la de
    streaming (MISMA lógica: no puede haber deriva entre las dos).

    Thinking — la regla REAL (docs oficiales, verificados 2026-10-13):
    tools+thinking SÍ son compatibles; lo que exige la API es que, con
    `tools` en el request, el `reasoning_content` se devuelva COMPLETO en
    todas las requests subsecuentes (incluidos turnos sin tool calls).
    El crash histórico 'reasoning_content must be passed back' (A1) era
    esa regla rompiéndose: se desactivaba thinking, quedaba reasoning en
    el historial, y el par (tools, reasoning ausente) no validaba. La
    anotación original decía 'la API rechaza tools+thinking juntos' —
    falso para la API actual; la sonda de exp/38 no reprodujo el rechazo
    (3 llamadas reales, flips ON→OFF→ON con tools: sin 400).

    El modo pegajoso se mantiene como DECISIÓN: este cliente descarta el
    reasoning_content (no lo devuelve nunca), así que thinking debe ir
    desactivado en todo tráfico agéntico — la alternativa documentada
    (preservar reasoning_content en el historial) habilitaría razonar en
    las rondas de tools al costo de reenviar el reasoning en cada vuelta.
    Conversación limpia va con thinking normal (correr directo en
    disabled midió descarrilos: prompts ajenos, tags que parten palabras).

    RESUMEN OPERATIVO: como este cliente NUNCA preserva reasoning_content,
    toda llamada con tools o con historial agéntico viaja con thinking
    DISABLED; no existe acá una combinación tools+thinking activa.

    Medido (fase 3, banco/specs/fase3.md): la combinación es VÁLIDA si el
    reasoning del turno en curso vuelve (sonda banco/probes/thinking_tools.py),
    pero el A/B la rechazó — 2,2×–6,9× el USD por escenario y sin mejora en
    s17/s18. Por eso este builder no la ofrece."""
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
    kwargs = _kwargs_agente(messages, tools)
    response = _client().chat.completions.create(**kwargs)
    _contabilizar(getattr(response, "usage", None), kwargs.get("model"))
    return response.choices[0].message


def _acumular_fragmento(frag, por_indice):
    """Un fragmento de tool_call del stream: id/name en el primero, argumentos
    se concatenan por index."""
    idx = frag.index if frag.index is not None else 0
    acumulado = por_indice.setdefault(idx, {"id": None, "name": None, "arguments": ""})
    if getattr(frag, "id", None):
        acumulado["id"] = frag.id
    funcion = getattr(frag, "function", None)
    if funcion is None:
        return
    if getattr(funcion, "name", None):
        acumulado["name"] = funcion.name
    if getattr(funcion, "arguments", None):
        acumulado["arguments"] += funcion.arguments


def _acumular_delta(delta, contenido, por_indice):
    """Texto de content (se imprime en vivo) + fragmentos de tool_calls."""
    texto = getattr(delta, "content", None)
    if texto:
        print(texto, end="", flush=True)
        contenido.append(texto)
    for frag in getattr(delta, "tool_calls", None) or []:
        _acumular_fragmento(frag, por_indice)


def _cerrar_stream(stream):
    """Libera la conexión si la interrupción dejó el stream abierto."""
    cerrar = getattr(stream, "close", None)
    if callable(cerrar):
        with contextlib.suppress(Exception):
            cerrar()


def _tool_calls_finales(por_indice, cortado):
    """Tool calls armadas, salvo stream cortado o fragmento incompleto."""
    if cortado:
        return []
    return [
        SimpleNamespace(
            id=acum["id"],
            type="function",
            function=SimpleNamespace(name=acum["name"], arguments=acum["arguments"]),
        )
        for _, acum in sorted(por_indice.items())
        if acum["name"] and acum["id"]
    ]


def call_llm_agent_stream(messages, tools=None):
    """Igual contrato que call_llm_agent (mismo modo thinking pegajoso,
    mismo filtro de reasoning_content) pero con stream=True: imprime EN
    VIVO cada delta de CONTENT a medida que llega (flush, sin saltos de
    línea extra) y NO imprime los deltas de reasoning_content.

    Al terminar devuelve un objeto con la forma que usa hoy el chat:
    .content completo ensamblado y .tool_calls reconstruidos desde los
    fragmentos del stream (llegan partidos con index; id y function.name
    suelen venir en el primer fragmento, function.arguments se acumula por
    concatenación). Devuelve .content=None si no hubo deltas y .tool_calls=None
    si no hubo tool calls. Si el stream se corta a mitad, devuelve lo
    acumulado sin explotar y DESCARTA las tool_calls (argumentos truncados).

    Interrupción del usuario (roadmap ítem 6): si el usuario aprieta Ctrl+C
    MIENTRAS se genera, con CHAT_STREAM_INTERRUPT=1 (default) se corta el
    stream y se devuelve lo acumulado (el chat sigue, no se cae); se imprime
    un aviso "[interrumpido]". Con 0, el Ctrl+C se propaga como siempre
    (main lo toma como salida). El Ctrl+C fuera del stream no se toca."""
    kwargs = _kwargs_agente(messages, tools)
    # exp/89: el último chunk trae usage solo si se pide (OpenAI-compat)
    kwargs["stream_options"] = {"include_usage": True}
    stream = _client().chat.completions.create(**kwargs, stream=True)
    interrumpible = _setting("CHAT_STREAM_INTERRUPT", "1") == "1"
    contenido = []
    por_indice = {}  # index -> {"id", "name", "arguments"}
    cortado = False
    uso = None
    try:
        for chunk in stream:
            # el chunk final de usage viene SIN choices: se captura antes
            # del continue (y si un proveedor lo manda con choices, también)
            if getattr(chunk, "usage", None):
                uso = chunk.usage
            if not chunk.choices:
                continue
            # los deltas de reasoning_content NO se imprimen (se descartan)
            _acumular_delta(chunk.choices[0].delta, contenido, por_indice)
    except KeyboardInterrupt:
        # Ctrl+C durante la generación: si la interrupción está activa se
        # corta acá y se devuelve lo acumulado (el chat sigue vivo); si no,
        # se propaga para que main la trate como salida.
        if not interrumpible:
            raise
        cortado = True
        print("\n  [interrumpido] generación cortada por el usuario")
    except Exception as e:  #  # noqa: BLE001 (stream cortado a mitad: se devuelve lo acumulado)
        # stream cortado a mitad (red, 401/429, etc.): se devuelve lo
        # acumulado. Decisión de diseño, PERO no se enmascara la causa
        # (frágil medido en la caza): con un error de la API y sin contenido
        # acumulado, el usuario veía una respuesta vacía sin motivo. Se
        # imprime la causa solo cuando NO hay nada acumulado (con contenido
        # parcial el corte benigno no merece ruido).
        cortado = True
        if not contenido:
            print(f"\n  [stream] se cortó sin contenido ({type(e).__name__}: {e})")
    # cierra el stream si quedó abierto por la interrupción (libera la conexión)
    if cortado:
        _cerrar_stream(stream)
    _contabilizar(uso, kwargs.get("model"))
    # Un stream CORTADO (Ctrl+C o red) no despacha tool calls: sus argumentos
    # pueden estar truncados y el usuario pidió parar (medido: tras Ctrl+C la
    # llamada se conservaba y se ejecutaba). Tampoco viaja un fragmento sin
    # nombre o sin id ("herramienta desconocida: None").
    tool_calls = _tool_calls_finales(por_indice, cortado)
    return SimpleNamespace(
        content="".join(contenido) or None,
        tool_calls=tool_calls or None,
    )


async def call_llm_async(messages):
    """Versión async de call_llm: para AsyncParallelBatchNode/Flow,
    donde cada exec_async debe esperar I/O real para que se solapen."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    modelo = _model()
    response = await AsyncOpenAI(
        api_key=get_api_key(),
        base_url=_setting("LLM_BASE_URL", DEFAULT_BASE_URL),
    ).chat.completions.create(
        model=modelo,
        messages=messages,
    )
    _contabilizar(getattr(response, "usage", None), modelo)
    return response.choices[0].message.content


if __name__ == "__main__":
    print(call_llm("Responde en una sola frase: ¿qué modelo eres?"))
