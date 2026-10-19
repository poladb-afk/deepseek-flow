import hashlib
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

from pocketflow import Node

from modules import discover
from utils.call_llm import _entero, _setting, call_llm_agent, call_llm_agent_stream
from utils.fs_tools import MAX_TOOL_ROUNDS, run_tool_call
from utils.fs_tools import TOOLS as CORE_TOOLS
from utils.terminal import colorear, progreso_ronda
from utils.thread_store import checkpoint
from utils.tracing import evento_politica, evento_tool, thread_id

EXIT_WORDS = {"salir", "exit", "quit"}


def registrar_pregunta(texto, ruta=None):
    """Guarda la pregunta del usuario en un JSONL local (exp/34).

    Para qué: el trace (.runs) guarda nodo/acción/segundos pero NUNCA el texto,
    y los logs del banco corren con echo off — sin esto no hay forma de armar
    un set de calibración con el tráfico REAL (exp/33 tuvo que usar escenarios,
    y salió sesgado a "herramientas"). Una línea acá y en una semana hay
    muestra natural para recalibrar el α del router.

    Es bookkeeping: la ruta la fija el operador (no el modelo) y cualquier
    fallo —disco, permisos— se traga para no romper el chat. PREGUNTAS_LOG=0
    lo apaga y PREGUNTAS_ARCHIVO elige el destino (default
    salidas/preguntas.jsonl, que está en .gitignore)."""
    if _setting("PREGUNTAS_LOG", "1") != "1":
        return
    try:
        destino = Path(ruta or _setting("PREGUNTAS_ARCHIVO", "salidas/preguntas.jsonl"))
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"ts": round(time.time(), 3), "pregunta": texto[:4000]},
                ensure_ascii=False,
            ) + "\n")
    except Exception:  # bookkeeping: nunca corta el chat  # noqa: BLE001 (bookkeeping de traza: nunca corta el chat)
        pass

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


# Techo adaptativo de rondas por operación (exp/13, opción C del consejo).
# MAX_TOOL_ROUNDS sigue siendo el DEFAULT y el símbolo parcheable por tests.
# presupuesto() lo lee del global VIVO de este módulo (globals()) — no como
# default de argumento ni capturándolo en import — así patch('nodes.
# MAX_TOOL_ROUNDS') (o cualquier asignación al global) sí tiene efecto.
# Los PERFILES y UMBRAL_SIN_PROGRESO, en cambio, se leen con _setting al
# importar: cambiar el .env con el proceso vivo NO los mueve (hay que
# reiniciar).
PERFILES_PRESUPUESTO = {
    "consulta":   _entero("MAX_TOOL_ROUNDS_CONSULTA", 8),
    "banco":      _entero("MAX_TOOL_ROUNDS_BANCO", 25),
    "aplicacion": _entero("MAX_TOOL_ROUNDS_APLICACION", 40),
}

# repeticiones idénticas de una ronda de tools antes de cortar por inanición
UMBRAL_SIN_PROGRESO = _entero("UMBRAL_SIN_PROGRESO", 3)


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


def huella_llamada(tc):
    """Hash corto (sin contenido) de (nombre, argumentos) de UNA tool."""
    funcion = tc.get("function") or {}
    clave = json.dumps([funcion.get("name") or "?", funcion.get("arguments") or ""],
                       ensure_ascii=False)
    return hashlib.sha1(clave.encode()).hexdigest()[:8]


def actualizar_novedad(shared, tool_calls):
    """exp/52-B: novedad ACUMULADA por pregunta (tool+argumentos).

    A diferencia del no-progreso (misma ronda repetida), acá una ronda sin
    NINGUNA llamada nueva (p. ej. A, B, A, B) también cuenta como sin novedad.
    Devuelve True si la ronda no estrenó ninguna llamada.
    """
    vistas = shared.setdefault("_huellas_vistas", set())
    nuevas = [h for h in (huella_llamada(tc) for tc in tool_calls or []) if h not in vistas]
    vistas.update(nuevas)
    if nuevas:
        shared["_racha_sin_novedad"] = 0
    else:
        shared["_racha_sin_novedad"] = shared.get("_racha_sin_novedad", 0) + 1
    return not nuevas


def corte_por_novedad_activo(shared):
    """exp/52-B: `CORTE_NOVEDAD=k` (default 0 = off) corta tras k rondas
    consecutivas sin llamadas nuevas, con mínimo `CORTE_NOVEDAD_MIN` rondas.

    Default OFF a propósito: la regla se activa recién cuando el A/B del banco
    valide que baja rondas sin bajar turnos OK. Se lee en runtime para que el
    banco la prenda por escenario.
    """
    k = _entero("CORTE_NOVEDAD", 0)
    if k <= 0:
        return False
    minimo = _entero("CORTE_NOVEDAD_MIN", 3)
    return (shared.get("tool_rounds", 0) >= minimo
            and shared.get("_racha_sin_novedad", 0) >= k)


MENSAJE_SIN_RESPUESTA = (
    "(sin respuesta: el stream se cortó sin contenido — reintentá el pedido)"
)


MENSAJE_DSML_SIN_TOOLS = (
    "(sin texto: emitiste tool-calls en la ruta directa, donde no hay "
    "herramientas disponibles — respondé sin ellas)"
)

AVISO_CIERRE = (
    "(presupuesto de herramientas agotado) Respondé AHORA con lo que tengas: "
    "hallazgos, límites y qué falta. No emitas tool calls; si te falta "
    "información, decilo como límite."
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
        # exp/34: la pregunta real queda registrada para calibrar el router con
        # tráfico natural (bookkeeping; nunca corta el chat).
        registrar_pregunta(exec_res)
        # Todo presupuesto es POR PREGUNTA (ley L8): el techo de rondas y el
        # contador de no-progreso se reinician acá. Sin este reset, un corte
        # por no-progreso dejaba las tools retiradas para el resto de la
        # sesión (el contador solo se reseteaba en ExecuteTools.post, que ya
        # no corría) y el protocolo de continuación de exp/4 quedaba falso.
        # (/aprobaciones no llega hasta acá: lo atiende exec(), sin gastar turno.)
        shared["tool_rounds"] = 0
        shared["no_progress"] = 0
        shared.pop("_fp", None)
        shared.pop("_router_pendiente", None)
        shared.pop("_aviso_cierre", None)
        # exp/52-B: la novedad es POR PREGUNTA (misma ley L8 que el presupuesto).
        shared.pop("_huellas_vistas", None)
        shared.pop("_racha_sin_novedad", None)
        shared.pop("_corte_novedad", None)
        # exp/44: el último mensaje del usuario queda como EVIDENCIA DE
        # INTENCIÓN para el juez de riesgo (import perezoso; los módulos no
        # ven `shared`). Plumbing, no decide nada.
        from utils.estado_sesion import recordar_usuario

        recordar_usuario(exec_res)
        # Tarea vigente para la compacción: una continuación no pisa el objetivo.
        if exec_res.strip().lower() not in {"seguí", "segui", "continúa", "continua", "continue"}:
            shared["_objetivo"] = exec_res
        shared["messages"].append({"role": "user", "content": exec_res})
        # exp/48: punto seguro 1 — la pregunta del usuario quedó registrada.
        # Checkpoint del shared COMPLETO (bookkeeping: jamás corta el chat).
        checkpoint(thread_id(), "GetQuestion", "continue", shared)
        return "continue"


class PreFetch(Node):
    """exp/50: pre-fetch como POLÍTICA declarativa del chat (apéndice 13).

    Corre una vez por mensaje user NUEVO (está entre GetQuestion y el paso —
    la estructura del grafo ya lo garantiza) y lee, DETERMINÍSTICAMENTE, los
    archivos que la pregunta menciona: si el modelo casi seguro va a pedirlos,
    se los damos ya leídos en el contexto (utils/prefetch, PURO).

    Ley de ausencia: sin match no appendea nada (no-op). El mensaje prefetch
    es un user normal del historial — la compacción lo compacta como a
    cualquiera, y user-tras-user es legal para la API (validar_historial verde
    antes y después: candado de este nodo). Siempre devuelve "continue" (una
    arista, sin decisión)."""

    def prep(self, shared):
        # La última pregunta del usuario en el historial (el último user que
        # no sea un mensaje prefetch de una vuelta anterior, si lo hubiera).
        from utils.prefetch import PREFIJO_PREFETCH

        for m in reversed(shared.get("messages", [])):
            if m.get("role") == "user" and not str(m.get("content", "")).startswith(PREFIJO_PREFETCH):
                return str(m.get("content", ""))
        return ""

    def exec(self, pregunta):
        from utils.prefetch import decidir

        return decidir(pregunta)

    def post(self, shared, prep_res, exec_res):
        from utils.prefetch import mensaje

        texto = mensaje(exec_res)
        if texto:
            shared["messages"].append({"role": "user", "content": texto})
            for path, _ in exec_res:
                print(colorear(f"  [pre-fetch] {path}", "info"))
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


def _respaldar_zona_fria(mensajes):
    """Guarda en memoria/ los mensajes que la compacción va a descartar (A17).

    Sin LLM a propósito: una transcripción literal es barata, no suma latencia
    al turno ni un modo de fallo nuevo (y el resumen real de la sesión ya se
    hace al salir, en main.resumen_de_sesion). Devuelve la ruta o None."""
    from utils.compaccion import MAX_RESPALDO_CHARS, serializar, zona_fria

    frios = zona_fria(mensajes)
    if not frios:
        return None
    from datetime import datetime

    from modules.memoria import guardar_nota

    cuerpo = serializar(frios)
    aviso = ""
    if len(cuerpo) > MAX_RESPALDO_CHARS:
        cuerpo = cuerpo[:MAX_RESPALDO_CHARS]
        aviso = "\n\n[... transcripción truncada por tamaño ...]"
    titulo = f"Compactación {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    destino = guardar_nota(titulo, cuerpo + aviso)
    return str(destino) if destino else None


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

        tope = _entero("COMPACTION_CHARS", 60000)
        mensajes = shared["messages"]
        if tope > 0 and len(serializar(mensajes)) > tope:
            h = huella(mensajes)
            if shared.get("_compaccion_huella") != h:
                # A17: la zona fría se RESPALDA antes de descartarla, así el
                # marcador puede decir la verdad y memory_search la encuentra.
                respaldo = _respaldar_zona_fria(mensajes)
                nuevo = compactar(mensajes, tope, respaldo=respaldo,
                                  objetivo=shared.get("_objetivo"))
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
        corte_novedad = shared.pop("_corte_novedad", False)
        if sin_progreso and not agotado:
            # incidente visible desde .runs: el corte NO fue por techo
            evento_politica("corte_no_progreso")
        elif corte_novedad and not agotado:
            evento_politica(
                "corte_sin_novedad",
                f"{shared.get('_racha_sin_novedad', 0)} rondas sin llamadas nuevas",
            )
        # Al llegar al límite de rondas se retiran las tools: el modelo debe responder ya.
        tools = None if (agotado or sin_progreso or corte_novedad) else TOOLS
        if tools is None and not shared.get("_aviso_cierre"):
            shared["_aviso_cierre"] = True
            # Mensaje EFÍMERO (no entra al historial): medido en vivo, sin esto
            # el modelo sigue emitiendo tool calls en vez de cerrar la respuesta.
            return list(shared["messages"]) + [{"role": "user", "content": AVISO_CIERRE}], None
        return shared["messages"], tools

    def exec(self, inputs):
        messages, tools = inputs
        stream = _setting("CHAT_STREAM", "1") == "1"
        reemplazado = False  # contenido reemplazado DESPUÉS del streaming en vivo
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
                reemplazado = True
            elif parseados:
                print(colorear("  [recuperación] tool calls llegaron como texto (DSML) → ejecutando", "aviso"))
                # el historial queda canónico: tool_calls, sin el markup crudo
                exec_res.content = None
                exec_res.tool_calls = parseados
        if tools is None and getattr(exec_res, "tool_calls", None):
            # ley L8 por el canal NATIVO (la mitad DSML ya estaba cerrada en
            # exp/12): retiradas las tools, una tool call que el modelo emita
            # igual NO se ejecuta (medido: tool_rounds=99 → acción "tool" y la
            # implementación corría). Mismo mensaje honesto que el DSML.
            print(colorear("  [L8] tool calls con las tools retiradas: IGNORADAS", "aviso"))
            exec_res.tool_calls = None
            if not (exec_res.content or "").strip():
                exec_res.content = (MENSAJE_DSML_AGOTADO if getattr(self, "ofrece_tools", True)
                                    else MENSAJE_DSML_SIN_TOOLS)
                reemplazado = True
        if not getattr(exec_res, "tool_calls", None) and not (exec_res.content or "").strip():
            # el stream se cortó sin deltas (401/429/red): sin esto el usuario
            # ve el rótulo vacío y queda content:null en el historial (medido)
            exec_res.content = MENSAJE_SIN_RESPUESTA
            reemplazado = True
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
        if stream and reemplazado:
            # con streaming el crudo ya se imprimió; si exec() lo REEMPLAZÓ
            # (fallback/aviso), el usuario tiene que verlo o queda sin respuesta.
            print(f"\nDeepSeek (aviso): {exec_res.content}")
        return exec_res

    def _verificar_citas(self, shared, exec_res):
        """Cita archivo:línea: se comprueba contra el disco; si alguna no
        coincide, se pide UNA segunda pasada de corrección (sin tools). Best
        effort: un fallo de verificación o de la llamada no rompe la respuesta."""
        contenido = (exec_res.content or "").strip()
        if not contenido or _setting("CITAS_VERIFICAR", "1") != "1":
            return exec_res
        from utils.citas import reporte, verificar_citas

        try:
            resultado = verificar_citas(contenido)
        except Exception:  # noqa: BLE001 (verificación: nunca corta la respuesta)
            return exec_res
        if not resultado["total"]:
            return exec_res
        print(colorear(f"  [citas] {resultado['ok']}/{resultado['total']} verificadas", "info"), flush=True)
        if not resultado["mal"]:
            return exec_res
        detalle = reporte(resultado)
        print(colorear(detalle, "aviso"), flush=True)
        try:
            mensajes = list(shared.get("messages", [])) + [
                {"role": "assistant", "content": contenido},
                {"role": "user", "content": (
                    "Verificá y corregí la respuesta. Estas citas NO coinciden con "
                    "el archivo real:\n" + detalle + "\n\nReescribí la respuesta "
                    "usando solo citas verificadas (o marcá como no verificado lo "
                    "que no puedas verificar). No agregues hallazgos nuevos; "
                    "devolvé solo la respuesta final.")},
            ]
            corregido = call_llm_agent(mensajes)
            nuevo = (getattr(corregido, "content", None) or "").strip()
        except Exception:  # noqa: BLE001 (la corrección es best-effort)
            return exec_res
        if nuevo:
            exec_res.content = nuevo
            if _setting("CHAT_STREAM", "1") == "1":
                print(f"\nDeepSeek (citas corregidas): {nuevo}", flush=True)
        return exec_res

    def post(self, shared, prep_res, exec_res):
        if not getattr(exec_res, "tool_calls", None):
            exec_res = self._verificar_citas(shared, exec_res)
        shared["messages"].append(historiar(exec_res))
        if getattr(exec_res, "tool_calls", None):
            # exp/49: punto seguro 4 — la SELECCIÓN: las llamadas quedaron
            # elegidas pero no ejecutadas (la pausa exacta del factor 8).
            # Con el cierre de ronda de exp/48 son dos checkpoints por ronda.
            checkpoint(thread_id(), type(self).__name__, "tool", shared)
            return "tool"
        if _setting("CHAT_STREAM", "1") == "1":
            # con streaming el contenido ya se imprimió en vivo (deltas sin
            # salto): acá solo se cierra la línea, sin repetir la respuesta.
            print()
        else:
            print(f"\nDeepSeek: {exec_res.content}")
        pendiente = shared.pop("_router_pendiente", None)
        if pendiente is not None:
            from utils.laya_routing import registrar_resultado

            rondas = shared.get("tool_rounds", 0)
            registrar_resultado(pendiente, rondas)
            etiqueta = "herramientas" if rondas else "directo"
            print(colorear(f"  [router] etiqueta ambiental: {etiqueta} ({rondas} rondas)", "info"))
        # exp/48: punto seguro 3 — la respuesta quedó registrada. El nodo es
        # AgentStep (DirectAnswer hereda este post y su checkpoint usa el
        # nombre de la clase real).
        checkpoint(thread_id(), type(self).__name__, "answer", shared)
        return "answer"


_EXIT_NO_CERO = re.compile(r"^exit (?!0\b)-?\d+")


def resultado_ok(contenido):
    """Lo que la traza registra como ok/error de una tool. Un RECHAZADO del
    humano o un comando con exit != 0 NO son éxitos (medido: los dos quedaban
    'ok' en .runs y el linter/costos los contaban como sanos)."""
    contenido = contenido or ""
    return not (contenido.startswith(("ERROR", "RECHAZADO")) or _EXIT_NO_CERO.match(contenido))


def codigo_error(contenido):
    """Discriminador CORTO y sin contenido para la traza (F4: las trazas no
    podían atribuir causas). Se guarda con la tool en .runs: `ERROR:TypeError`,
    `ERROR:JSONDecodeError`, `ERROR:herramienta`, `RECHAZADO`, `exit_1`, o ""."""
    contenido = (contenido or "").strip()
    if contenido.startswith("RECHAZADO"):
        return "RECHAZADO"
    if contenido.startswith("ERROR"):
        resto = contenido[5:].lstrip(": ").strip()
        palabra = re.split(r"[:\s]", resto, maxsplit=1)[0] if resto else "?"
        return "ERROR:" + (palabra[:40] or "?")
    golpe = _EXIT_NO_CERO.match(contenido)
    if golpe:
        return golpe.group(0).strip().replace(" ", "_")
    return ""


class ExecuteTools(Node):
    def prep(self, shared):
        return shared["messages"][-1]["tool_calls"]

    def exec(self, tool_calls):
        # cada tool deja su evento propio en la traza (nombre + ok/error +
        # código de causa; ver evento_tool): sin eso, una ronda larga es
        # inatribuible desde .runs (auditoría)
        resultados = []
        for tc in tool_calls:
            inicio = time.time()
            nombre = (tc.get("function") or {}).get("name") or "?"  # A27: sin KeyError
            # pulido de terminal (mesa 8): una ronda larga no debe parecer
            # colgada, así que la tool EN CURSO se anuncia antes de correr.
            print(colorear(f"  → {nombre}", "tool"), flush=True)
            r = run_tool_call(tc, MODULE_IMPLS)
            ok = resultado_ok(r["content"])
            evento_tool(nombre, ok, time.time() - inicio,
                        codigo=codigo_error(r["content"]),
                        huella=huella_llamada(tc))
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
        # exp/52-B: novedad acumulada (tool+argumentos). Con CORTE_NOVEDAD=k
        # (default 0=off) el loop se corta tras k rondas sin ninguna llamada
        # nueva; la calidad se valida en el A/B del banco, no acá.
        sin_novedad = actualizar_novedad(shared, prep_res or [])
        if sin_novedad and corte_por_novedad_activo(shared) and not shared.get("_corte_novedad"):
            shared["_corte_novedad"] = True
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
        # exp/48: punto seguro 2 — la ronda de tools quedó registrada.
        checkpoint(thread_id(), "ExecuteTools", "default", shared)
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


PROMPT_ARBITRO_VOTO = (
    "Pregunta del usuario:\n{pregunta}\n\n"
    "¿Responderla requiere USAR HERRAMIENTAS (leer/buscar archivos, web, "
    "ejecutar una capacidad: debate, investigación, informe, sql...) o se "
    "responde DIRECTO de conocimiento? Un imperativo de acción (debatá, "
    "investigá, generá, medí...) casi siempre es herramientas.\n\n"
    "Responde SOLO yaml:\n```yaml\nveredicto: herramientas|directo\n```"
)


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
    from utils.laya import disponible, preguntar
    from utils.laya_routing import config_voto, decide_voto

    if _setting("USE_VOTACION", "1") != "1":
        return "directo"  # apagado: la palabra de Laya es final
    if disponible("LAYA_MODEL_VOTO"):
        estado = {"pregunta": str(pregunta)[:1000]}
        resp, conf = preguntar(estado, PREGUNTA_VOTO, setting="LAYA_MODEL_VOTO")["confirma_herramientas"]
        # el umbral del voto es propio (0.7 por defecto): la curva del veto da
        # 96% de precisión con 83% de cobertura a 0.7. Con LAYA_CALIBRACION_VOTO
        # el umbral sale de los datos (cota conformal), igual que el router.
        config = config_voto()
        confiable, causa = decide_voto(resp, conf, config)
        if resp in ("herramientas", "directo") and confiable:
            # acuerdo confiable (directo→directo, el ahorro) o desacuerdo
            # confiable (herramientas→lado seguro): DeepSeek no hace falta
            print(f"  [voto] laya local: {resp} (conf {conf:.2f}) — {causa}")
            return resp
        print(f"  [voto] laya local duda ({resp}, conf {conf:.2f}; {causa}) → arbitra DeepSeek")
    r = extraer_yaml(call_llm(PROMPT_ARBITRO_VOTO.format(pregunta=pregunta)))
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
        # exp/50: el mensaje `[pre-fetch]` entra ANTES del router (user tras
        # user), así que `messages[-1]` puede ser el PREFETCH y no la pregunta.
        # Saltamos los mensajes de pre-fetch para leer la PREGUNTA real: el
        # router decide y el voto se confirman sobre la pregunta, no sobre el
        # contexto que la política le inyectó.
        from utils.prefetch import PREFIJO_PREFETCH

        pregunta = ""
        for m in reversed(shared["messages"]):
            if m.get("role") != "user":
                continue
            contenido = str(m.get("content", ""))
            if contenido.startswith(PREFIJO_PREFETCH):
                continue  # pre-fetch: no es la pregunta
            pregunta = contenido
            break
        return {"pregunta": pregunta[:1000]}

    def exec(self, estado):
        from utils.laya import disponible, preguntar_detalle
        from utils.laya_routing import config_router, regla_temporal

        # exp/46: la recencia no la juzga Laya (límite de familia: sin fechas).
        # La regla dura va ANTES del modelo. En enforce corta acá sin gastar a
        # Laya; en shadow NO corta: Laya corre igual para que la flywheel junte
        # la etiqueta de esta clase y la regla se valide contra realidad.
        modo = config_router().modo
        if modo == "enforce" and regla_temporal(estado.get("pregunta")):
            return "regla:temporal"
        if modo == "off" or not disponible():
            return None
        try:
            return preguntar_detalle(estado, PREGUNTA_ROUTER).get("necesita_herramientas")
        except Exception as e:  # noqa: BLE001 (frontera de integracion Laya: degrada al router DeepSeek)
            # Frontera de integración (exp/25): una excepción de inferencia no
            # puede matar el chat; la política la lee como abstención.
            print(f"  [laya] falló ({type(e).__name__}) → herramientas")
            return None

    def post(self, shared, prep_res, exec_res):
        from utils.laya_routing import (
            config_router,
            decide,
            registrar_decision,
            ruta_aplicada,
        )

        # La POLÍTICA vive en utils/laya_routing (exp/35): acá solo se ejecuta
        # su resultado. La clasificación (Laya) y la decisión (Python) están
        # separadas y la segunda se testea sin modelo.
        config = config_router()
        if exec_res == "regla:temporal":
            # exp/46: la regla dura ya decidió ANTES del modelo (Laya no se
            # llamó en enforce). Causa explícita, sin p_directo (no hay par
            # (p, etiqueta) calibrable → sin pendiente que etiquetar).
            propuesta, causa, p_directo = (
                "herramientas",
                "regla temporal (exp/46): recencia no la juzga Laya",
                None,
            )
        else:
            propuesta, causa, p_directo = decide(exec_res, config)
        aplicada = ruta_aplicada(propuesta, config)
        from uuid import uuid4

        id_decision = uuid4().hex[:8]
        pregunta = prep_res.get("pregunta") if isinstance(prep_res, dict) else None
        print(f"  [laya] {propuesta} — {causa} (modo {config.modo})")

        # A04/A05: el voto corre ANTES de registrar y recibe la PREGUNTA, no el
        # dict del prep (que se re-serializaba como "{'pregunta': '...'}" y le
        # cambiaba la entrada al checkpoint). El log guarda la ruta FINAL, con
        # el voto y el veto como campos propios: antes decía "aplicada: directo"
        # aunque el voto la vetara dos líneas después.
        voto, veto = None, None
        if aplicada == "directo":
            # post() NO tiene retry en PocketFlow: si el voto revienta (YAML
            # roto del modelo), caemos al lado seguro en vez de cortar el chat.
            try:
                voto = voto_confirmacion_router(pregunta)
            except Exception as e:  # noqa: BLE001 (frontera del voto Laya: degrada al voto DeepSeek)
                voto, veto = "herramientas", f"el voto falló ({type(e).__name__})"
                print(f"  [voto] falló ({type(e).__name__}) → herramientas")
            if voto != "directo":  # 2-de-2: desacuerdo → lado seguro
                veto = veto or f"el voto dijo {voto}"
                print(f"  [voto] deepseek dice {voto} → herramientas")
                aplicada = "herramientas"

        registrar_decision(
            {
                "modo": config.modo,
                "id": id_decision,
                "propuesta": propuesta,
                "aplicada": aplicada,
                "causa": causa,
                "voto": voto,
                "veto": veto,
                "p_directo": p_directo,
                "q": config.q,
                "umbral": config.umbral,
                "laya": config.version,
            },
            pregunta=pregunta,
        )
        if (
            config.modo == "shadow"
            and p_directo is not None
            and _setting("LAYA_LOG_DECISIONES", "1") == "1"
        ):
            shared["_router_pendiente"] = id_decision
        if aplicada != "directo":
            return "herramientas"  # off, shadow y veto conservan las herramientas
        return "directo"


class DirectAnswer(AgentStep):
    """AgentStep sin herramientas: la pregunta se responde de una."""

    ofrece_tools = False  # el DSML acá es texto: nunca se ofrecieron tools

    def prep(self, shared):
        # Reusa el prep de AgentStep (compacción incluida): la ruta directa
        # mandaba el historial entero sin techo (medido, exp/36) y solo se
        # salva por la ventana de caracteres del API. Sin tools.
        mensajes, _ = super().prep(shared)
        return mensajes, None
