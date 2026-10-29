import hashlib
import json
import re
import time
from pathlib import Path

from pocketflow import Node

from modules import discover, ganchos
from utils.call_llm import _entero, _setting, call_llm_agent, call_llm_agent_stream
from utils.compaccion import PREFIJO_COMPACCION, compactar, huella, recortar_tools_viejos, serializar
from utils.fs_tools import MAX_TOOL_ROUNDS, run_tool_call
from utils.fs_tools import TOOLS as CORE_TOOLS
from utils.proveedor import (  # noqa: F401  (re-export: tests y banco los importan de nodes)
    AVISOS,
    MENSAJE_DSML_AGOTADO,
    MENSAJE_DSML_SIN_TOOLS,
    MENSAJE_SIN_RESPUESTA,
    RE_DSML,
    dsml_a_tool_calls,
    dsml_con_presupuesto_agotado,
    normalizar,
    sanitizar,
)
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
    salidas/preguntas.jsonl, que está en .gitignore). Cada línea lleva
    `origen` (web/terminal, exp/71b); el banco escribe este log aparte
    (`salidas/banco/`, X93) y no se mezcla con el humano."""
    if _setting("PREGUNTAS_LOG", "1") != "1":
        return
    from utils.riesgo import origen

    try:
        destino = Path(ruta or _setting("PREGUNTAS_ARCHIVO", "salidas/preguntas.jsonl"))
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"ts": round(time.time(), 3), "origen": origen(), "pregunta": texto[:4000]},
                ensure_ascii=False,
            ) + "\n")
    except Exception:  # bookkeeping: nunca corta el chat  # noqa: BLE001 (bookkeeping de traza: nunca corta el chat)
        pass

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


# repeticiones idénticas de una ronda de tools antes de cortar por inanición
UMBRAL_SIN_PROGRESO = _entero("UMBRAL_SIN_PROGRESO", 3)

# exp/86 — presupuesto dinámico determinista: un pedido AMPLIO sube el tope.
# El tope es un CAP, no un gasto (X21: p50 2 rondas): bajarlo no ahorra nada
# y solo arriesga cortar; el hueco real era el contrario (A37: el alcance
# amplio agota 8 y queda corto). Por eso la regla solo puede SUBIR.
MAX_TOOL_ROUNDS_AMPLIO = _entero("MAX_TOOL_ROUNDS_AMPLIO", 16)
AMPLIO_ARCHIVOS = 10  # un directorio mencionado con esta cantidad ya es amplio
# 300 calibrado por el contrafáctico de exp/86 sobre la masa que el agente
# ve (el banco copia los fixtures sin la answer sheet): las familias que agotaban el cap quedan arriba
# con margen (s18 347 · s19 587 · s20 930) y las cómodas muy abajo (máx 111).
AMPLIO_LINEAS = 300
# todo token del pedido que trae al menos una barra (archivo o directorio)...
_TOKEN_RUTA = re.compile(r"[\w./~-]*/[\w./~-]+")
# ...y también un nombre de archivo CON EXTENSIÓN a secas, sin barra (dogfood
# exp/87: "auditá fable_judge.py" mencionaba 872 líneas y no resolvía)
_TOKEN_ARCHIVO = re.compile(r"\b[\w.-]+\.(?:py|md|json|csv|js|yaml|jsonl|txt|sh)\b")
_EXTS_ALCANCE = {".py", ".md", ".json", ".csv", ".js", ".yaml", ".jsonl", ".txt", ".sh"}


def _lineas_de(ruta):
    """La masa de los archivos de código mencionados. Corta al cruzar los
    umbrales: la respuesta es amplio sí/no, no el conteo exacto, y
    un directorio enorme se recorría entero en CADA ronda (auditoría F3)."""
    total, archivos = 0, 0
    for f in ruta.rglob("*"):
        if archivos >= AMPLIO_ARCHIVOS or total >= AMPLIO_LINEAS:
            break
        if f.is_file() and f.suffix in _EXTS_ALCANCE:
            archivos += 1
            try:
                total += len(f.read_text(errors="replace").splitlines())
            except OSError:
                continue
    return archivos, total


def alcance_amplio(pregunta, raiz=None):
    """True si el pedido es de alcance amplio — DETERMINISTA, sin LLM: los
    datos exactos (cuántos archivos, cuántas líneas) los cuenta el código
    contra el disco. Dos señales: un directorio mencionado con
    >=AMPLIO_ARCHIVOS archivos de código, o masa mencionada >=AMPLIO_LINEAS.
    (Hasta X104 había una tercera, una regex de palabras de totalidad: el
    contrafáctico de la fase 4b-mín midió que no decidía ningún caso.) Contrafáctico contra las corridas de exp/72-80 (bitácora
    exp/86): las tareas que agotaban el cap clasifican amplio; las cómodas
    no; y como la regla solo sube el tope, no puede cortar nada."""
    raiz = Path(raiz) if raiz else Path.cwd()
    texto = str(pregunta or "")
    masa = 0  # suma de líneas de los ARCHIVOS mencionados (spec: la masa, no cada uno)
    tokens = _TOKEN_RUTA.findall(texto) + _TOKEN_ARCHIVO.findall(texto)
    from utils.fs_tools import allowed_roots

    roots = allowed_roots()
    for token in dict.fromkeys(tokens):  # único: un nombre puede aparecer dos veces
        p = (raiz / token.rstrip(".,;:)")).resolve()
        # solo la masa que el agente PUEDE leer: `/usr` no es alcance del pedido
        # (y recorrerlo costaba ~3 s por ronda, auditoría F3)
        if not p.exists() or not any(p == r or r in p.parents for r in roots):
            continue
        if p.is_dir():
            archivos, lineas = _lineas_de(p)
            if archivos >= AMPLIO_ARCHIVOS or (archivos and lineas >= AMPLIO_LINEAS):
                return True
        elif p.suffix in _EXTS_ALCANCE:
            try:
                masa += len(p.read_text(errors="replace").splitlines())
            except OSError:
                continue
    return masa >= AMPLIO_LINEAS


def nuevo_turno():
    """El estado de UNA pregunta: todo lo que vale hasta la próxima.

    GetQuestion lo reemplaza ENTERO al recibir una pregunta. Antes eran diez
    claves sueltas en `shared` y un `pop` por cada una: una clave nueva sin su
    `pop` se filtraba a la pregunta siguiente y nada lo detectaba (auditoría
    de elegancia, 2026-10-26). Lo de la sesión (`messages`, compacción,
    respaldo) y lo de la tarea (`_objetivo`, que sobrevive a un "seguí")
    quedan fuera de la caja a propósito. Todo es JSON: viaja en el checkpoint."""
    return {
        "rondas": 0,             # rondas de tools gastadas (ley L8)
        "sin_progreso": 0,       # repeticiones de la MISMA ronda (exp/13)
        "huella": None,          # huella de la última ronda
        "huellas_vistas": [],    # novedad acumulada (exp/52-B)
        "racha_sin_novedad": 0,
        "skill": None,           # id del skill activo (exp/55)
        "router_pendiente": None,  # id de la decisión shadow a etiquetar (exp/43)
        "uso_inicio": None,      # desglose de tokens al empezar (exp/90)
        "ruta": "herramientas",  # la arista que toma Contexto (la fija el router)
    }


def turno(shared):
    """La caja de la pregunta en curso (la crea si el shared no la trae)."""
    return shared.setdefault("turno", nuevo_turno())


def presupuesto(shared):
    """Techo de rondas de tools para ESTA pregunta: el override explícito de
    shared['max_tool_rounds'] si lo hay; si no, un pedido de alcance amplio
    sube a MAX_TOOL_ROUNDS_AMPLIO (exp/86); si no, MAX_TOOL_ROUNDS, leído EN
    RUNTIME del global del módulo (patch('nodes.MAX_TOOL_ROUNDS') se respeta)."""
    override = shared.get("max_tool_rounds")
    if override is not None:
        return int(override)
    # _objetivo es la tarea VIGENTE (GetQuestion; una continuación "seguí"
    # no la pisa): el presupuesto amplio sobrevive a la continuación, que es
    # justo cuando más rondas hacen falta.
    if alcance_amplio(shared.get("_objetivo")):
        # max(): si el default ya sube más que el tope amplio, se respeta
        return max(MAX_TOOL_ROUNDS, MAX_TOOL_ROUNDS_AMPLIO)
    return MAX_TOOL_ROUNDS


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
    t = turno(shared)
    nuevas = [h for h in dict.fromkeys(huella_llamada(tc) for tc in tool_calls or [])
              if h not in t["huellas_vistas"]]
    t["huellas_vistas"].extend(nuevas)
    t["racha_sin_novedad"] = 0 if nuevas else t["racha_sin_novedad"] + 1
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
    t = turno(shared)
    return t["rondas"] >= minimo and t["racha_sin_novedad"] >= k


def motivo_de_cierre(shared):
    """Por qué se acabó el presupuesto de ESTA pregunta (ley L8), o None si
    sigue: el tope de rondas, la misma ronda repetida (no-progreso, exp/13) o,
    con CORTE_NOVEDAD, rondas sin llamadas nuevas (exp/52-B). Lo evalúa
    Contexto antes de cada llamada al modelo (X96). Un corte que NO es el
    techo deja su evento de política: visible desde .runs."""
    t = turno(shared)
    if t["rondas"] >= presupuesto(shared):
        return "tope"
    if t["sin_progreso"] >= UMBRAL_SIN_PROGRESO:
        evento_politica("corte_no_progreso")
        return "sin_progreso"
    if corte_por_novedad_activo(shared):
        evento_politica("corte_sin_novedad", f"{t['racha_sin_novedad']} rondas sin llamadas nuevas")
        return "sin_novedad"
    return None


AVISO_CIERRE = (
    "(presupuesto de herramientas agotado) Respondé AHORA con lo que tengas: "
    "hallazgos, límites y qué falta. No emitas tool calls; si te falta "
    "información, decilo como límite."
)


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
        # Todo lo de la pregunta anterior muere acá, de una vez: presupuesto
        # (L8), no-progreso, novedad, skill, aviso de cierre y la decisión del
        # router. El costo de la anterior se cierra con su `uso_inicio`.
        # (/aprobaciones no llega hasta acá: lo atiende exec(), sin gastar turno.)
        anterior = turno(shared)
        shared["turno"] = nuevo_turno()
        # exp/44: el último mensaje del usuario queda como EVIDENCIA DE
        # INTENCIÓN para el juez de riesgo (import perezoso; los módulos no
        # ven `shared`). Plumbing, no decide nada.
        from utils.estado_sesion import recordar_usuario

        recordar_usuario(exec_res)
        # Tarea vigente para la compacción: una continuación no pisa el objetivo.
        if exec_res.strip().lower() not in {"seguí", "segui", "continúa", "continua", "continue"}:
            shared["_objetivo"] = exec_res
        shared["messages"].append({"role": "user", "content": exec_res})
        # exp/90: el costo POR PREGUNTA se cierra acá — se vuelve por
        # "answer", así que la pregunta anterior ya respondió: su costo es
        # el delta del desglose desde su propio arranque. La última nunca
        # pasa de nuevo por acá: la cierra el reporte de salida.
        from utils.call_llm import desglose_de_sesion
        from utils.costos import delta_desglose

        if anterior["uso_inicio"] is not None:
            shared.setdefault("tokens_por_pregunta", []).append(
                delta_desglose(anterior["uso_inicio"], desglose_de_sesion()))
        shared["turno"]["uso_inicio"] = desglose_de_sesion()
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


def _aviso_ventana_caliente(shared, tamano, tope):
    """exp/88: si ni compactando se baja del tope, la masa está en la
    ventana caliente — decílo UNA vez por sesión: el marcador de compacción
    repitiéndose sin esta línea era indescifrable (kill del operador)."""
    if tamano <= tope or shared.get("_aviso_ventana_caliente"):
        return
    shared["_aviso_ventana_caliente"] = True
    print(colorear(
        "[compacción] la ventana caliente sola supera el tope "
        f"({tamano} > {tope} chars): la compacción no puede bajarlo — "
        "recortá lecturas o subí COMPACTION_CHARS", "aviso"), flush=True)


def _recortar_si_sigue_sobre_el_tope(shared, tope):
    """exp/91: si tras compactar (exitosa o no-op) el historial sigue sobre el
    tope, la masa está en el CONTENIDO de la ventana caliente — recortá el de
    los tool results VIEJOS (estructura intacta). La línea de terminal es
    propia y visible: la causa invisible mató la sesión de exp/88.

    Se evalúa DESPUÉS del respaldo de zona fría (A17) y no genera respaldo
    propio: un tool result se re-obtiene re-corriendo la tool."""
    mensajes = shared["messages"]
    if len(serializar(mensajes)) <= tope:
        return
    nuevo = recortar_tools_viejos(mensajes)
    if nuevo == mensajes:
        return
    recortados = sum(1 for a, b in zip(mensajes, nuevo, strict=True) if a is not b)
    print(
        f"{PREFIJO_COMPACCION} recorte: {recortados} resultados viejos → marcadores",
        flush=True,
    )
    shared["messages"] = nuevo
    shared["_compaccion_huella"] = huella(nuevo)


class Contexto(Node):
    """El contexto que viaja al modelo, una vez antes de CADA llamada (al
    entrar por el router y tras cada ronda de tools). Si el historial supera
    COMPACTION_CHARS: la zona fría se respalda (gancho `al_compactar`) y se
    reemplaza por un marcador (código puro, sin LLM; los invariantes del modo
    thinking los da utils/compaccion.compactar); si ni así baja, se recortan
    los tool results viejos (exp/91) y se avisa una vez (X51). La huella evita
    re-compactar la misma ronda. Sale por la ruta que eligió el router, o por
    `cierre` si el presupuesto de la pregunta se acabó (X96): venga de donde
    venga, la próxima llamada es la última y va sin tools."""

    def prep(self, shared):
        tope = _entero("COMPACTION_CHARS", 60000)
        mensajes = shared["messages"]
        if tope <= 0 or len(serializar(mensajes)) <= tope:
            return
        if shared.get("_compaccion_huella") != huella(mensajes):
            respaldo = next(filter(None, (g(mensajes, shared) for g in ganchos("al_compactar"))), None)
            nuevo = compactar(mensajes, tope, respaldo=respaldo, objetivo=shared.get("_objetivo"))
            if nuevo is not mensajes and len(nuevo) < len(mensajes):
                frios = len(mensajes) - len(nuevo) + 1  # +1: el propio resumen
                print(f"{PREFIJO_COMPACCION} zona fría: {frios} mensajes → "
                      f"resumen; ventana caliente: {len(nuevo) - 1}")
                shared["messages"] = nuevo
                shared["compacciones"] = shared.get("compacciones", 0) + 1
                shared["_compaccion_huella"] = huella(nuevo)
        _recortar_si_sigue_sobre_el_tope(shared, tope)
        _aviso_ventana_caliente(shared, len(serializar(shared["messages"])), tope)

    def post(self, shared, prep_res, exec_res):
        if motivo_de_cierre(shared):
            return "cierre"
        if turno(shared).get("ruta") == "directo":
            return "directo"
        return "herramientas"


class AgentStep(Node):
    def prep(self, shared):
        # El cierre por presupuesto ya no pasa por acá: Contexto lo decide y
        # sale a Cierre (X96). AgentStep siempre ofrece tools.
        tools = TOOLS
        skill_id = turno(shared)["skill"]
        if skill_id:
            # exp/55: mientras el skill está activo se anuncia SOLO su subset
            # (guía, no sandbox: el action space completo sigue existiendo).
            # En shared viaja el ID (JSON): el objeto Skill se guardaba como su
            # repr y un resume lo cargaba roto (auditoría 2026-10-26, F4).
            from utils.skills import disponibles, filtrar_tools

            skill = next((h for h in disponibles() if h.id == skill_id), None)
            tools = filtrar_tools(tools, skill) if skill else tools
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
        # La normalización va en exec, NO en post: los max_retries de
        # PocketFlow envuelven exec(), así que un raise acá SÍ re-pregunta; en
        # post() cortaría el chat (bug medido). Es la misma del kernel.
        exec_res, avisos = normalizar(exec_res, tools, getattr(self, "ofrece_tools", True))
        for aviso in avisos:
            if aviso in AVISOS:
                print(colorear(AVISOS[aviso], "aviso"))
        if stream and "sanitizado" in avisos:
            # con streaming el crudo ya se imprimió en vivo (a veces con el
            # descarrilo incluido): se imprime también la versión limpia
            print(f"\nDeepSeek (limpio): {exec_res.content}")
        if stream and "reemplazado" in avisos:
            # con streaming el crudo ya se imprimió; si exec() lo REEMPLAZÓ
            # (fallback/aviso), el usuario tiene que verlo o queda sin respuesta.
            print(f"\nDeepSeek (aviso): {exec_res.content}")
        return exec_res

    def post(self, shared, prep_res, exec_res):
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
        t = turno(shared)
        pendiente, t["router_pendiente"] = t["router_pendiente"], None
        if pendiente is not None:
            from utils.laya_routing import registrar_resultado

            rondas = t["rondas"]
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
        shared["messages"].extend(exec_res)
        return "default"


class Observar(Node):
    """Lo que deja una ronda de tools, contado por código (X96): la ronda, su
    huella (no-progreso, exp/13), la novedad acumulada (exp/52-B) y lo que el
    MODELO tiene que leer — el aviso de sin-progreso y la nota de presupuesto
    viajan en el último resultado, porque la terminal no le llega. Después el
    checkpoint (exp/48, punto seguro 2: la ronda quedó registrada). Si el
    presupuesto se acabó lo decide Contexto, antes de la próxima llamada."""

    def prep(self, shared):
        return next((m["tool_calls"] for m in reversed(shared["messages"])
                     if m.get("role") == "assistant" and m.get("tool_calls")), [])

    def post(self, shared, llamadas, _):
        t = turno(shared)
        t["ruta"] = "herramientas"  # tras una ronda de tools se vuelve a AgentStep
        t["rondas"] += 1
        tope = presupuesto(shared)
        huella_ronda = fingerprint(llamadas)
        t["sin_progreso"] = t["sin_progreso"] + 1 if huella_ronda == t["huella"] else 0
        t["huella"] = huella_ronda
        actualizar_novedad(shared, llamadas)
        notas = [nota_presupuesto(t["rondas"], tope)]
        if t["sin_progreso"]:
            notas.insert(0, f"⚠ Sin progreso: repetiste la misma llamada {t['sin_progreso'] + 1}ª vez "
                            "— cambiá de estrategia o cerrá el estado.")
        ultimo = shared["messages"][-1] if shared["messages"] else {}
        if ultimo.get("role") == "tool":
            ultimo["content"] = "\n".join([ultimo["content"], *filter(None, notas)])
        print(colorear("  " + progreso_ronda(t["rondas"], tope), "info"), flush=True)
        checkpoint(thread_id(), "Observar", "default", shared)
        return "default"


class VerificarCitas(Node):
    """Cita archivo:línea → se comprueba contra el disco; si alguna no
    coincide, UNA corrección sin tools reemplaza la respuesta (A40).

    Es un nodo del grafo (answer → citas → ask) y no un paso dentro de
    AgentStep.post: post no tiene retry en PocketFlow y la llamada de
    corrección corría ahí envuelta en un except amplio (auditoría F6). Acá la
    llamada vive en exec (con reintentos) y el "best effort" es el
    exec_fallback explícito: si no se pudo corregir, queda la respuesta."""

    def prep(self, shared):
        ultimo = shared["messages"][-1] if shared.get("messages") else {}
        contenido = (ultimo.get("content") or "").strip()
        if (_setting("CITAS_VERIFICAR", "1") != "1" or ultimo.get("role") != "assistant"
                or ultimo.get("tool_calls") or not contenido):
            return None
        return shared["messages"][:-1], contenido

    def exec(self, entrada):
        if entrada is None:
            return None
        from utils.citas import reporte, verificar_citas

        mensajes, contenido = entrada
        resultado = verificar_citas(contenido)
        if not resultado["total"]:
            return None
        print(colorear(f"  [citas] {resultado['ok']}/{resultado['total']} verificadas", "info"), flush=True)
        if not resultado["mal"]:
            return None
        detalle = reporte(resultado)
        print(colorear(detalle, "aviso"), flush=True)
        corregido = call_llm_agent(list(mensajes) + [
            {"role": "assistant", "content": contenido},
            {"role": "user", "content": (
                "Verificá y corregí la respuesta. Estas citas NO coinciden con "
                "el archivo real:\n" + detalle + "\n\nReescribí la respuesta "
                "usando solo citas verificadas (o marcá como no verificado lo "
                "que no puedas verificar). No agregues hallazgos nuevos; "
                "devolvé solo la respuesta final.")},
        ])
        return (getattr(corregido, "content", None) or "").strip() or None

    def exec_fallback(self, prep_res, exc):
        print(colorear(f"  [citas] la corrección falló ({type(exc).__name__}): queda la respuesta",
                       "aviso"), flush=True)
        return None

    def post(self, shared, prep_res, exec_res):
        if exec_res:
            shared["messages"][-1]["content"] = exec_res
            print(f"\nDeepSeek (citas corregidas): {exec_res}", flush=True)
            checkpoint(thread_id(), "VerificarCitas", "default", shared)


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
        from utils.laya_routing import config_router, regla_imperativo_capacidad, regla_temporal

        # exp/46: la recencia no la juzga Laya (límite de familia: sin fechas).
        # La regla dura va ANTES del modelo. En enforce corta acá sin gastar a
        # Laya; en shadow NO corta: Laya corre igual para que la flywheel junte
        # la etiqueta de esta clase y la regla se valide contra realidad.
        modo = config_router().modo
        if modo == "enforce" and regla_temporal(estado.get("pregunta")):
            return "regla:temporal"
        # exp/54: la orden de capacidad tampoco la decide el modelo: es el
        # hueco medido por el bench del voto (c01: voto local directo 0,94).
        if modo == "enforce" and regla_imperativo_capacidad(estado.get("pregunta")):
            return "regla:imperativo"
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
        pregunta = prep_res.get("pregunta") if isinstance(prep_res, dict) else None
        # exp/55: skills declarativas. En enforce, un disparo declarativo manda
        # al lado seguro, inyecta el prompt del skill y anuncia el recorte de
        # tools. En shadow NO cambia conducta (solo observa), igual que las reglas.
        skill = None
        if config.modo == "enforce" and _setting("SKILLS", "1") != "0" and pregunta:
            from utils.skills import disponibles, mensaje, skill_para

            skill = skill_para(pregunta, disponibles())
        if skill is not None:
            propuesta, causa, p_directo = (
                "herramientas",
                f"skill {skill.id}: disparo declarativo",
                None,
            )
            turno(shared)["skill"] = skill.id
            shared["messages"].append({"role": "user", "content": mensaje(skill)})
            print(colorear(f"  [skill] {skill.id} activo — {skill.descripcion}", "info"),
                  flush=True)
        elif exec_res == "regla:temporal":
            # exp/46: la regla dura ya decidió ANTES del modelo (Laya no se
            # llamó en enforce). Causa explícita, sin p_directo (no hay par
            # (p, etiqueta) calibrable → sin pendiente que etiquetar).
            propuesta, causa, p_directo = (
                "herramientas",
                "regla temporal (exp/46): recencia no la juzga Laya",
                None,
            )
        elif exec_res == "regla:imperativo":
            # exp/54: misma vía que la temporal, para órdenes de capacidad.
            propuesta, causa, p_directo = (
                "herramientas",
                "regla imperativo (exp/54): orden de capacidad no la juzga Laya",
                None,
            )
        else:
            propuesta, causa, p_directo = decide(exec_res, config)
        aplicada = ruta_aplicada(propuesta, config)
        from uuid import uuid4

        id_decision = uuid4().hex[:8]
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
            turno(shared)["router_pendiente"] = id_decision
        # la ruta viaja en el turno: Contexto la lee después de compactar
        turno(shared)["ruta"] = "herramientas" if aplicada != "directo" else "directo"
        if aplicada != "directo":
            return "herramientas"  # off, shadow y veto conservan las herramientas
        return "directo"


class Cierre(AgentStep):
    """La última llamada de la pregunta: sin tools y con el aviso de cierre
    (X96). Antes era un flag dentro de AgentStep.prep (`aviso_cierre`) para que
    el aviso no se duplicara; ahora corre UNA vez por construcción — después
    viene la respuesta. Las tool calls que el modelo emita igual se descartan
    (normalizar con las tools retiradas, L8)."""

    def prep(self, shared):
        # Mensaje EFÍMERO (no entra al historial): medido en vivo, sin esto
        # el modelo sigue emitiendo tool calls en vez de cerrar la respuesta.
        return list(shared["messages"]) + [{"role": "user", "content": AVISO_CIERRE}], None


class DirectAnswer(AgentStep):
    """AgentStep sin herramientas: la pregunta se responde de una."""

    ofrece_tools = False  # el DSML acá es texto: nunca se ofrecieron tools

    def prep(self, shared):
        # La compacción ya corrió en Contexto (la ruta directa mandaba el
        # historial entero sin techo, exp/36). Sin tools.
        return shared["messages"], None
