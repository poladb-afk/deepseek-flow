import hashlib
import json
import re
import time
from types import SimpleNamespace

from pocketflow import Node

from modules import discover
from utils.call_llm import _setting, call_llm_agent, call_llm_agent_stream
from utils.fs_tools import MAX_TOOL_ROUNDS, run_tool_call
from utils.fs_tools import TOOLS as CORE_TOOLS
from utils.terminal import colorear, progreso_ronda
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


def nota_presupuesto(ronda, maximo):
    """La nota que ve el MODELO al entrar a la anteúltima ronda: su única
    vista del presupuesto (el ⚙ de la terminal no llega a la conversación).
    None en toda otra ronda — una nota por pregunta alcanza."""
    if ronda == maximo - 1:
        return (
            f"⚙ ronda {ronda}/{maximo} completada — la próxima es tu ÚLTIMA "
            "con tools (después se retiran): si no te alcanza, usala para "
            "cerrar el estado y pedí continuación — un mensaje nuevo del "
            "usuario reinicia el presupuesto."
        )
    return None


MENSAJE_DSML_AGOTADO = (
    "(sin texto: emitiste tool-calls con el presupuesto agotado — decí "
    "'seguí' para reiniciarlo)"
)


# ---------------------------------------------------------------------------
# Techo adaptativo de rondas por operación (exp/13, opción C del consejo).
# MAX_TOOL_ROUNDS sigue siendo el DEFAULT y el símbolo parcheable por tests.
# presupuesto() lo lee del global VIVO de este módulo (globals()) — no como
# default de argumento ni capturándolo en import — así patch('nodes.
# MAX_TOOL_ROUNDS') (o cualquier asignación al global) sí tiene efecto.
# Los PERFILES y UMBRAL_SIN_PROGRESO, en cambio, se leen con _setting al
# importar: cambiar el .env con el proceso vivo NO los mueve (hay que
# reiniciar).
# ---------------------------------------------------------------------------
PERFILES_PRESUPUESTO = {
    "consulta":   int(_setting("MAX_TOOL_ROUNDS_CONSULTA", "8")),
    "banco":      int(_setting("MAX_TOOL_ROUNDS_BANCO", "25")),
    "aplicacion": int(_setting("MAX_TOOL_ROUNDS_APLICACION", "40")),
}

# repeticiones idénticas de una ronda de tools antes de cortar por inanición
UMBRAL_SIN_PROGRESO = int(_setting("UMBRAL_SIN_PROGRESO", "3"))


def presupuesto(shared):
    """Techo de rondas de tools para ESTA pregunta. Si el invocador declaró
    shared['operacion'] con perfil, se usa; si no, MAX_TOOL_ROUNDS. El
    default se lee EN RUNTIME del global del módulo (nodes), de modo que
    patch('nodes.MAX_TOOL_ROUNDS') —o un .env distinto— sí se respeta; un
    perfil declarado gana sobre el default, pero nunca sobre un override
    explícito que el llamador ponga en shared['max_tool_rounds']."""
    override = shared.get("max_tool_rounds")
    if override is not None:
        return int(override)
    perfil = PERFILES_PRESUPUESTO.get(shared.get("operacion", ""))
    if perfil is not None:
        return perfil
    return globals().get("MAX_TOOL_ROUNDS", MAX_TOOL_ROUNDS)


def fingerprint(tool_calls):
    """Hash estable de (nombre, argumentos) de una ronda de tools. NO mira
    el resultado: el resultado cambia aunque la llamada sea idéntica. Al
    incluir arguments, la paginación legítima (offset=1,2,3) da hashes
    distintos y NO dispara el no-progreso."""
    pares = sorted(
        (tc["function"]["name"], tc["function"].get("arguments") or "")
        for tc in (tool_calls or [])
    )
    return hashlib.sha1(
        json.dumps(pares, ensure_ascii=False).encode()
    ).hexdigest()


MENSAJE_SIN_RESPUESTA = (
    "(sin respuesta: el stream se cortó sin contenido — reintentá el pedido)"
)


MENSAJE_DSML_SIN_TOOLS = (
    "(sin texto: emitiste tool-calls en la ruta directa, donde no hay "
    "herramientas disponibles — respondé sin ellas)"
)


def dsml_con_presupuesto_agotado(content, parseados, tools, ofrece_tools=True):
    """(nuevo_content, avisar): la recuperación DSML no re-armó tools que
    el tope retiró (ley L8 — medido en exp/4 que sí las ejecutaba: el
    write_file corría después del retiro). Con tools presentes la
    recuperación de siempre; sin tools, el markup se corta y el mensaje
    que queda es honesto y accionable.

    `ofrece_tools=False` (DirectAnswer) distingue "nunca se ofrecieron" de
    "las retiró el tope": el mensaje de presupuesto agotado era FALSO en la
    ruta directa y descartaba la llamada (medido, exp/36)."""
    if tools is not None or not parseados:
        return content, False
    m = RE_DSML.search(content or "")
    limpio = (content or "")[: m.start()].rstrip() if m else ""
    if not limpio:
        return (MENSAJE_DSML_AGOTADO if ofrece_tools else MENSAJE_DSML_SIN_TOOLS), True
    return limpio, True


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
            # UX (mesa 8): /aprobaciones es un comando de TERMINAL. Se atiende
            # acá, en el bucle de entrada: devolverlo por post() lo mandaba al
            # modelo con el historial intacto y sin reiniciar el presupuesto
            # (medido en la barrida: una llamada extra no pedida).
            if text.strip().lower() == "/aprobaciones":
                from utils.aprobaciones import resumen

                print("\n" + resumen())
                continue
            if text:
                return text

    def post(self, shared, prep_res, exec_res):
        if exec_res.lower() in EXIT_WORDS:
            return "exit"
        # Todo presupuesto es POR PREGUNTA (ley L8): el techo de rondas y el
        # contador de no-progreso se reinician acá. Sin este reset, un corte
        # por no-progreso dejaba las tools retiradas para el resto de la
        # sesión (el contador solo se reseteaba en ExecuteTools.post, que ya
        # no corría) y el protocolo de continuación de exp/4 quedaba falso.
        # (/aprobaciones no llega hasta acá: lo atiende exec(), sin gastar turno.)
        shared["tool_rounds"] = 0
        shared["no_progress"] = 0
        shared.pop("_fp", None)
        shared["messages"].append({"role": "user", "content": exec_res})
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
        # Compacción de contexto (Mesa 6, 12-factor #5): si el historial
        # serializado supera COMPACTION_CHARS, la zona fría se reemplaza por
        # un resumen-instrucción (código puro, sin LLM) ANTES de llamar al
        # modelo. Nunca se separa un assistant con tool_calls de sus tools ni
        # se toca el system: los invariantes del modo thinking quedan dados
        # por utils/compaccion.compactar. El costo se paga UNA vez por ronda:
        # la huella del historial compactado evita re-compactar si coincide.
        from utils.compaccion import PREFIJO_COMPACCION, compactar, huella, serializar

        tope = int(_setting("COMPACTION_CHARS", "60000"))
        mensajes = shared["messages"]
        if tope > 0 and len(serializar(mensajes)) > tope:
            h = huella(mensajes)
            if shared.get("_compaccion_huella") != h:
                nuevo = compactar(mensajes, tope)
                if nuevo is not mensajes and len(nuevo) < len(mensajes):
                    frios = len(mensajes) - len(nuevo) + 1  # +1: el propio resumen
                    print(
                        f"{PREFIJO_COMPACCION} zona fría: {frios} mensajes → "
                        f"resumen; ventana caliente: {len(nuevo) - 1}"
                    )
                    shared["messages"] = nuevo
                    shared["compacciones"] = shared.get("compacciones", 0) + 1
                    shared["_compaccion_huella"] = huella(nuevo)
        # Techo adaptativo por operación (exp/13) + escape por no-progreso:
        # si el modelo repite la MISMA ronda de tools demasiadas veces, se
        # retiran las tools sin esperar el techo — el loop no se paga hasta
        # el máximo. presupuesto() lee MAX_TOOL_ROUNDS en runtime.
        tope = presupuesto(shared)
        agotado = shared.get("tool_rounds", 0) >= tope
        sin_progreso = shared.get("no_progress", 0) >= UMBRAL_SIN_PROGRESO
        if sin_progreso and not agotado:
            # incidente visible desde .runs: el corte NO fue por techo
            evento_tool("corte_no_progreso", True, 0.0)
        # Al llegar al límite de rondas se retiran las tools: el modelo debe responder ya.
        tools = None if (agotado or sin_progreso) else TOOLS
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
            # ley L8: retiradas las tools, el texto DSML no las re-arma —
            # el presupuesto no se by-pasea desde el canal de texto (exp/12)
            exec_res.content, avisar = dsml_con_presupuesto_agotado(
                exec_res.content, parseados, tools,
                ofrece_tools=getattr(self, "ofrece_tools", True))
            if avisar:
                print(colorear("  [DSML] tool calls como texto: IGNORADOS "
                               "(presupuesto agotado; 'seguí' lo reinicia)", "aviso"))
            elif parseados:
                print(colorear("  [recuperación] tool calls llegaron como texto (DSML) → ejecutando", "aviso"))
                # el historial queda canónico: tool_calls, sin el markup crudo
                exec_res.content = None
                exec_res.tool_calls = parseados
        if not getattr(exec_res, "tool_calls", None) and not (exec_res.content or "").strip():
            # el stream se cortó sin deltas (401/429/red): sin esto el usuario
            # ve el rótulo vacío y queda content:null en el historial (medido)
            exec_res.content = MENSAJE_SIN_RESPUESTA
        if not getattr(exec_res, "tool_calls", None):
            contenido, cortado = sanitizar(exec_res.content or "")
            if cortado:
                print(colorear("  [sanitizado] la respuesta descarriló a un prompt ajeno: cortada", "aviso"))
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
            nombre = tc["function"]["name"]
            # pulido de terminal (mesa 8): una ronda larga no debe parecer
            # colgada, así que la tool EN CURSO se anuncia antes de correr.
            print(colorear(f"  → {nombre}", "tool"), flush=True)
            r = run_tool_call(tc, MODULE_IMPLS)
            ok = not r["content"].startswith("ERROR")
            evento_tool(nombre, ok, time.time() - inicio)
            resultados.append(r)
        return resultados

    def post(self, shared, prep_res, exec_res):
        shared["tool_rounds"] = shared.get("tool_rounds", 0) + 1
        ronda = shared["tool_rounds"]
        tope = presupuesto(shared)
        # No-progreso (exp/13, opción D): se compara la HUELLA de esta ronda
        # de tools con la anterior. Igual → acumula; distinta → resetea. El
        # warning viaja en la conversación (misma vía que la nota), no en la
        # terminal: es lo único que el modelo lee.
        fp = fingerprint(prep_res)
        if fp == shared.get("_fp"):
            shared["no_progress"] = shared.get("no_progress", 0) + 1
        else:
            shared["no_progress"] = 0
        shared["_fp"] = fp
        if shared["no_progress"] >= 1 and exec_res:
            exec_res[-1]["content"] = (
                f"{exec_res[-1]['content']}\n⚠ Sin progreso: repetiste la "
                f"misma llamada {shared['no_progress'] + 1}ª vez — cambiá de "
                "estrategia o cerrá el estado."
            )
        # la nota de presupuesto viaja en la conversación (no en la
        # terminal): es la única vista del tope que tiene el modelo.
        nota = nota_presupuesto(ronda, tope)
        if nota and exec_res:
            exec_res[-1]["content"] = f"{exec_res[-1]['content']}\n{nota}"
        shared["messages"].extend(exec_res)
        # pulido de terminal (mesa 8): la ronda consumida se etiqueta para
        # que una secuencia de varias rondas muestre su avance (n/MAX).
        print(colorear("  " + progreso_ronda(ronda, tope), "info"), flush=True)
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
        # el umbral del voto es propio (0.7): la curva del veto da 96% de
        # precisión con 83% de cobertura a 0.7, y subirlo junto al router le
        # cortaría la mitad de las decisiones locales.
        if resp in ("herramientas", "directo") and veredicto(
            conf, alto=float(_setting("LAYA_UNSURE_HIGH_VOTO", "0.7"))
        ) == "met":
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
        try:
            resp, conf = preguntar(estado, PREGUNTA_ROUTER)["necesita_herramientas"]
        except Exception as e:
            # Frontera de integración (C14): una excepción de inferencia
            # salía del Flow y MATABA el chat (main solo atrapa
            # KeyboardInterrupt). Mismo default seguro que "sin checkpoint".
            print(f"  [laya] falló ({type(e).__name__}) → herramientas")
            return ("herramientas", 0.0)
        # El checkpoint es un modelo, no una garantía: se valida el contrato
        # antes de que una etiqueta rara cierre el chat en silencio
        # ("Flow ends: 'quizas' not found").
        if resp not in ("directo", "herramientas"):
            print(f"  [laya] respuesta fuera de contrato ({resp!r}) → herramientas")
            return ("herramientas", 0.0)
        if not isinstance(conf, (int, float)) or conf != conf or not 0.0 <= conf <= 1.0:
            print(f"  [laya] confianza inválida ({conf!r}) → herramientas")
            return ("herramientas", 0.0)
        return resp, float(conf)

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

    ofrece_tools = False  # el DSML acá es texto: nunca se ofrecieron tools

    def prep(self, shared):
        # Reusa el prep de AgentStep (compacción incluida): la ruta directa
        # mandaba el historial entero sin techo (medido, exp/36) y solo se
        # salva por la ventana de caracteres del API. Sin tools.
        mensajes, _ = super().prep(shared)
        return mensajes, None
