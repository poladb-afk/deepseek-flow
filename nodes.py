import json
import re
import time
from types import SimpleNamespace

from pocketflow import Node

from modules import discover
from utils.call_llm import call_llm_agent, call_llm_agent_stream, _setting
from utils.fs_tools import MAX_TOOL_ROUNDS, TOOLS as CORE_TOOLS, run_tool_call
from utils.tracing import evento_tool

EXIT_WORDS = {"salir", "exit", "quit"}

# Recuperación del canal de tools: a veces DeepSeek emite las llamadas como
# TEXTO con su markup interno (DSML) en vez del canal estructurado — el chat
# las imprimiría como respuesta y se quedaría colgado (medido en producción).
# El separador real llega con UNA o DOS barras fullwidth (medido en
# producción: el log trae <｜｜DSML｜｜, el transcript pegado una sola)
_SEP = r"[｜|]{1,2}"
RE_DSML = re.compile(rf"<{_SEP}DSML")
DSML_INVOKE = re.compile(rf'<{_SEP}DSML{_SEP} invoke name="([^"]+)">(.*?)</{_SEP}DSML{_SEP} invoke>', re.DOTALL)
DSML_PARAM = re.compile(rf'<{_SEP}DSML{_SEP} parameter name="([^"]+)"[^>]*>(.*?)</{_SEP}DSML{_SEP} parameter>', re.DOTALL)


def dsml_a_tool_calls(content):
    """El texto DSML de vuelta en objetos con la forma de la API (atributos
    .function.name/.arguments/.id): el camino `tool` existente sigue intacto."""
    calls = []
    for m in DSML_INVOKE.finditer(content):
        args = {k: v.strip() for k, v in DSML_PARAM.findall(m.group(2))}
        calls.append(SimpleNamespace(
            id=f"dsml-{len(calls)}",
            function=SimpleNamespace(name=m.group(1), arguments=json.dumps(args, ensure_ascii=False)),
        ))
    return calls


def historiar(msg):
    """El mensaje del asistente en forma canónica para el historial: solo
    role/content/tool_calls. El reasoning_content del modo thinking NO
    viaja — arrastrarlo a una vuelta sin thinking rompe la API (400
    'reasoning_content must be passed back', medido en producción)."""
    m = {"role": "assistant", "content": msg.content}
    if getattr(msg, "tool_calls", None):
        m["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]
    return m

# Action space = capacidades base del CORE + lo que aporten los módulos.
MODULE_TOOLS, MODULE_IMPLS = discover()
TOOLS = CORE_TOOLS + MODULE_TOOLS


class GetQuestion(Node):
    def exec(self, _):
        while True:
            try:
                text = input("\nTú: ").strip()
            except EOFError:
                return "exit"
            if text:
                return text

    def post(self, shared, prep_res, exec_res):
        if exec_res.lower() in EXIT_WORDS:
            return "exit"
        shared["messages"].append({"role": "user", "content": exec_res})
        shared["tool_rounds"] = 0
        return "continue"


# Markers de rol que el modelo a veces emite a mitad de respuesta cuando
# descarrila (medido en producción: un system prompt ajeno de agente
# genérico apareció pegado al saludo). El chat no debe mostrar ni guardarlos.
MARKERS_ROL = ("<system>", "<<SYS>>", "<|im_start|>", "[INST]", "<｜System｜>")
# Tags HTML espurios que parten palabras (S<small>oy) pero dejan el resto
# utilizable: se quitan y el texto se recompone (segunda medición en prod.)
TAG_HTML = re.compile(
    r"</?(?:small|b|i|em|strong|code|pre|div|span|p|br|sub|sup|u|s|mark|h[1-6]|ul|ol|li)\b[^>]*>")


def sanitizar(texto):
    """(contenido_limpio, se_modifico). Dos descarrilos medidos: un marker de
    rol ajeno (se corta: lo que sigue es basura) y tags HTML que parten
    palabras (se quitan: el texto sigue siendo la respuesta)."""
    for marca in MARKERS_ROL:
        i = texto.find(marca)
        if i >= 0:
            return texto[:i].rstrip(), True
    limpio = TAG_HTML.sub("", texto)
    return limpio, limpio != texto


class AgentStep(Node):
    def prep(self, shared):
        # Al llegar al límite de rondas se retiran las tools: el modelo debe responder ya.
        tools = None if shared.get("tool_rounds", 0) >= MAX_TOOL_ROUNDS else TOOLS
        return shared["messages"], tools

    def exec(self, inputs):
        messages, tools = inputs
        stream = _setting("CHAT_STREAM", "1") == "1"
        if stream:
            # etiqueta antes del primer delta: sin ella las respuestas
            # llegan sin rótulo (nit de UX de la mesa 8, medido en prod)
            print("\nDeepSeek: ", end="", flush=True)
            exec_res = call_llm_agent_stream(messages, tools)
        else:
            exec_res = call_llm_agent(messages, tools)
        # La recuperación DSML y el sanitizado van en exec, NO en post: los
        # max_retries de PocketFlow envuelven exec(), así que un raise acá
        # SÍ re-pregunta; en post() cortaría el chat (bug medido).
        if not getattr(exec_res, "tool_calls", None) and RE_DSML.search(exec_res.content or ""):
            parseados = dsml_a_tool_calls(exec_res.content)
            if parseados:
                print("  [recuperación] tool calls llegaron como texto (DSML) → ejecutando")
                # el historial queda canónico: tool_calls, sin el markup crudo
                exec_res.content = None
                exec_res.tool_calls = parseados
        if not getattr(exec_res, "tool_calls", None):
            contenido, cortado = sanitizar(exec_res.content or "")
            if cortado:
                print("  [sanitizado] la respuesta descarriló a un prompt ajeno: cortada")
                if not contenido:
                    # no quedó nada utilizable: el retry del nodo re-pregunta
                    raise ValueError("respuesta descarrilada (solo markup de rol)")
                # con streaming el crudo ya se imprimió en vivo (a veces con
                # el descarrilo incluido): se imprime también la versión limpia
                if stream and exec_res.content:
                    print(f"\nDeepSeek (limpio): {contenido}")
                exec_res.content = contenido
        return exec_res

    def post(self, shared, prep_res, exec_res):
        shared["messages"].append(historiar(exec_res))
        if getattr(exec_res, "tool_calls", None):
            return "tool"
        if _setting("CHAT_STREAM", "1") == "1":
            # con streaming el contenido ya se imprimió en vivo (deltas sin
            # salto): acá solo se cierra la línea, sin repetir la respuesta.
            print()
        else:
            print(f"\nDeepSeek: {exec_res.content}")
        return "answer"


class ExecuteTools(Node):
    def prep(self, shared):
        return shared["messages"][-1]["tool_calls"]

    def exec(self, tool_calls):
        # cada tool deja su evento propio en la traza (nombre + ok/error):
        # sin eso, una ronda larga es inatribuible desde .runs (auditoría)
        resultados = []
        for tc in tool_calls:
            inicio = time.time()
            r = run_tool_call(tc, MODULE_IMPLS)
            evento_tool(tc["function"]["name"], not r["content"].startswith("ERROR"), time.time() - inicio)
            resultados.append(r)
        return resultados

    def post(self, shared, prep_res, exec_res):
        shared["messages"].extend(exec_res)
        shared["tool_rounds"] = shared.get("tool_rounds", 0) + 1
        return "default"


class ExitChat(Node):
    def post(self, shared, prep_res, exec_res):
        print("\n¡Chao! 👋")


PREGUNTA_ROUTER = {
    "necesita_herramientas": {
        "type": "choice",
        "instructions": "Does answering the request require tools (search/reading files, web, computation) or can it be answered directly?",
        "criteria": {
            "herramientas": "needs local files, documents, current data, or exact computation",
            "directo": "general knowledge, conversation, creativity; no external data needed",
        },
    }
}


PREGUNTA_VOTO = {
    "confirma_herramientas": {
        "type": "choice",
        "instructions": "Second opinion before answering directly — does this request truly require running tools (reading or searching files, web, or executing a capability) — action imperatives almost always do — or is it answerable from knowledge alone?",
        "criteria": {
            "herramientas": "needs local files, web data, or running a capability; imperatives of action included",
            "directo": "pure knowledge, conversation or creativity; nothing to run or look up",
        },
    }
}


def voto_confirmacion_router(pregunta):
    """El segundo voto del router, en tres niveles (Mesa 3): Laya-voto
    local decide los acuerdos Y desacuerdos confiables (costo 0, ms);
    DeepSeek queda como ÁRBITRO de la banda incierta. La independencia de
    errores es el recurso escaso — si ambos checkpoints fallan juntos el
    voto es eco, no voto — así que la promoción del voto local pasó por la
    puerta de correlación del bench (design.md, Mesa 3). Sin
    LAYA_MODEL_VOTO, el voto de DeepSeek de siempre."""
    from utils.call_llm import _setting, call_llm
    from utils.estructura import extraer_yaml
    from utils.laya import disponible, preguntar, veredicto

    if _setting("USE_VOTACION", "1") != "1":
        return "directo"  # apagado: la palabra de Laya es final
    if disponible("LAYA_MODEL_VOTO"):
        estado = {"pregunta": str(pregunta)[:1000]}
        resp, conf = preguntar(estado, PREGUNTA_VOTO, setting="LAYA_MODEL_VOTO")["confirma_herramientas"]
        if resp in ("herramientas", "directo") and veredicto(conf) == "met":
            # acuerdo confiable (directo→directo, el ahorro) o desacuerdo
            # confiable (herramientas→lado seguro): DeepSeek no hace falta
            print(f"  [voto] laya local: {resp} (conf {conf:.2f})")
            return resp
        print(f"  [voto] laya local duda ({resp}, conf {conf:.2f}) → arbitra DeepSeek")
    r = extraer_yaml(call_llm(
        f"Pregunta del usuario:\n{pregunta}\n\n"
        "¿Responderla requiere USAR HERRAMIENTAS (leer/buscar archivos, web, "
        "ejecutar una capacidad: debate, investigación, informe, sql...) o se "
        "responde DIRECTO de conocimiento? Un imperativo de acción (debatá, "
        "investigá, generá, medí...) casi siempre es herramientas.\n\n"
        "Responde SOLO yaml:\n```yaml\nveredicto: herramientas|directo\n```"
    ))
    return r.get("veredicto", "herramientas")


class LayaRouter(Node):
    """If inteligente: Laya (local, ms) decide si la pregunta necesita
    herramientas o se responde directa. La confianza aplica los umbrales
    de bmo; 'uncertain' cae al lado SEGURO (herramientas). Si laya no está
    disponible, también cae a herramientas: degrada, no rompe.

    El estado {"pregunta": ...} y PREGUNTA_ROUTER son el contrato del
    fine-tune (task router_flow de bmo): entrenamiento y producción leen
    lo mismo byte a byte."""

    def prep(self, shared):
        return {"pregunta": str(shared["messages"][-1]["content"])[:1000]}

    def exec(self, estado):
        from utils.laya import disponible, preguntar

        if not disponible():
            return ("herramientas", 0.0)
        resp, conf = preguntar(estado, PREGUNTA_ROUTER)["necesita_herramientas"]
        return resp, conf

    def post(self, shared, prep_res, exec_res):
        from utils.laya import veredicto

        eleccion, confianza = exec_res
        print(f"  [laya] {eleccion} (conf {confianza:.2f})")
        if eleccion == "directo":
            if veredicto(confianza) != "met":
                return "herramientas"  # dudoso: caer al lado seguro
            # post() NO tiene retry en PocketFlow: si el voto revienta (YAML
            # roto del modelo), caemos al lado seguro en vez de cortar el chat.
            try:
                voto = voto_confirmacion_router(prep_res)
            except Exception as e:
                print(f"  [voto] falló ({type(e).__name__}) → herramientas")
                return "herramientas"
            if voto != "directo":  # 2-de-2: desacuerdo → lado seguro
                print(f"  [voto] deepseek dice {voto} → herramientas")
                return "herramientas"
        return eleccion


class DirectAnswer(AgentStep):
    """AgentStep sin herramientas: la pregunta se responde de una."""

    def prep(self, shared):
        return shared["messages"], None
