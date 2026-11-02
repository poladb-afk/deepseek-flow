import hashlib
import json
import re
import time
from pathlib import Path

from pocketflow import Node

from modules import discover, ganchos
from utils import estado_sesion
from utils.aprobaciones import resumen
from utils.call_llm import _entero, _setting, call_llm_agent, call_llm_agent_stream, desglose_de_sesion
from utils.citas import reporte, verificar_citas
from utils.compaccion import PREFIJO_COMPACCION, compactar, huella, recortar_tools_viejos, serializar
from utils.costos import delta_desglose
from utils.fs_tools import MAX_TOOL_ROUNDS, run_tool_call
from utils.fs_tools import TOOLS as CORE_TOOLS
from utils.historial import historiar
from utils.prefetch import PREFIJO_PREFETCH, decidir
from utils.prefetch import mensaje as mensaje_prefetch
from utils.proveedor import (  # noqa: F401  (re-export: tests y banco los importan de nodes)
    AVISOS,
    MENSAJE_DSML_AGOTADO,
    MENSAJE_SIN_RESPUESTA,
    RE_DSML,
    dsml_a_tool_calls,
    dsml_con_presupuesto_agotado,
    normalizar,
    sanitizar,
)
from utils.riesgo import origen
from utils.skills import PREFIJO_SKILL, disponibles, filtrar_tools, skill_para
from utils.skills import mensaje as mensaje_skill
from utils.terminal import colorear, progreso_ronda
from utils.thread_store import checkpoint
from utils.tracing import evento_tool, thread_id

EXIT_WORDS = {"salir", "exit", "quit"}


def registrar_pregunta(texto, ruta=None):
    """Guarda la pregunta del usuario en un JSONL local (exp/34).

    Para qué: el trace (.runs) guarda nodo/acción/segundos pero NUNCA el texto,
    y los logs del banco corren con echo off — sin esto no hay forma de armar
    un set de calibración con el tráfico REAL (exp/33 tuvo que usar escenarios,
    y salió sesgado a "herramientas"). Una línea acá y en una semana hay
    muestra natural del tráfico real.

    Es bookkeeping: la ruta la fija el operador (no el modelo) y cualquier
    fallo —disco, permisos— se traga para no romper el chat. PREGUNTAS_LOG=0
    lo apaga y PREGUNTAS_ARCHIVO elige el destino (default
    salidas/preguntas.jsonl, que está en .gitignore). Cada línea lleva
    `origen` (web/terminal, exp/71b); el banco escribe este log aparte
    (`salidas/banco/`, X93) y no se mezcla con el humano."""
    if _setting("PREGUNTAS_LOG", "1") != "1":
        return

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


# S6 (X132): un solo techo de rondas por pregunta (MAX_TOOL_ROUNDS, default
# 16) y un único saldo en `turno`. Las tres políticas que había —alcance
# amplio por disco (exp/86), no-progreso (exp/13) y corte por novedad
# (exp/52-B)— se borraron con su código y sus settings; el A/B
# (banco/specs/s6_un_techo.md) decide si el reemplazo entra.


def nuevo_turno():
    """El estado de UNA pregunta: todo lo que vale hasta la próxima.

    GetQuestion lo reemplaza ENTERO al recibir una pregunta. Antes eran diez
    claves sueltas en `shared` y un `pop` por cada una: una clave nueva sin su
    `pop` se filtraba a la pregunta siguiente y nada lo detectaba (auditoría
    de elegancia, 2026-10-26). Lo de la sesión (`messages`, compacción,
    respaldo) y lo de la tarea (`_objetivo`, que sobrevive a un "seguí")
    quedan fuera de la caja a propósito. Todo es JSON: viaja en el checkpoint.
    Desde S6 (X132) `rondas` es el ÚNICO saldo de la pregunta: se descuenta
    por ronda y el techo es el único corte."""
    return {
        "rondas": 0,             # rondas de tools gastadas (L8): el saldo único
        "skill": None,           # id del skill activo (exp/55)
        "uso_inicio": None,      # desglose de tokens al empezar (exp/90)
    }


def turno(shared):
    """La caja de la pregunta en curso (la crea si el shared no la trae)."""
    return shared.setdefault("turno", nuevo_turno())


def presupuesto(shared):
    """Techo de rondas de tools para ESTA pregunta: el override explícito de
    shared['max_tool_rounds'] si lo hay; si no, MAX_TOOL_ROUNDS, leído EN
    RUNTIME del global del módulo (patch('nodes.MAX_TOOL_ROUNDS') se respeta).
    Desde S6 (X132) es el ÚNICO techo: no hay presupuesto amplio."""
    override = shared.get("max_tool_rounds")
    if override is not None:
        return int(override)
    return MAX_TOOL_ROUNDS


def huella_llamada(tc):
    """Hash corto (sin contenido) de (nombre, argumentos) de UNA tool."""
    funcion = tc.get("function") or {}
    clave = json.dumps([funcion.get("name") or "?", funcion.get("arguments") or ""],
                       ensure_ascii=False)
    return hashlib.sha1(clave.encode()).hexdigest()[:8]


def motivo_de_cierre(shared):
    """Por qué se acabó el presupuesto de ESTA pregunta (ley L8), o None si
    sigue: el techo único de rondas. Lo evalúa Contexto antes de cada llamada
    al modelo (X96). Desde S6 (X132) es el único corte: no hay no-progreso ni
    corte por novedad."""
    t = turno(shared)
    if t["rondas"] >= presupuesto(shared):
        return "tope"
    return None


AVISO_CIERRE = (
    "(presupuesto de herramientas agotado) Respondé AHORA con lo que tengas: "
    "hallazgos, límites y qué falta. No emitas tool calls; si te falta "
    "información, decilo como límite."
)


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
                print("\n" + resumen())
                continue
            if text:
                return text

    def post(self, shared, prep_res, exec_res):
        if exec_res.lower() in EXIT_WORDS:
            return "exit"
        # exp/34: la pregunta real queda registrada: tráfico natural para
        # calibrar (bookkeeping; nunca corta el chat).
        registrar_pregunta(exec_res)
        # Todo lo de la pregunta anterior muere acá, de una vez: el saldo de
        # rondas (L8) y el skill. El costo de la anterior se cierra con su
        # `uso_inicio`.
        # (/aprobaciones no llega hasta acá: lo atiende exec(), sin gastar turno.)
        anterior = turno(shared)
        shared["turno"] = nuevo_turno()
        # El último mensaje del usuario acompaña cada decisión HITL en el log
        # de riesgo (los módulos no ven `shared`). Plumbing, no decide nada.
        estado_sesion.recordar_usuario(exec_res)
        # Tarea vigente para la compacción: una continuación no pisa el objetivo.
        if exec_res.strip().lower() not in {"seguí", "segui", "continúa", "continua", "continue"}:
            shared["_objetivo"] = exec_res
        shared["messages"].append({"role": "user", "content": exec_res})
        # exp/90: el costo POR PREGUNTA se cierra acá — se vuelve por
        # "answer", así que la pregunta anterior ya respondió: su costo es
        # el delta del desglose desde su propio arranque. La última nunca
        # pasa de nuevo por acá: la cierra el reporte de salida.
        if anterior["uso_inicio"] is not None:
            shared.setdefault("tokens_por_pregunta", []).append(
                delta_desglose(anterior["uso_inicio"], desglose_de_sesion()))
        shared["turno"]["uso_inicio"] = desglose_de_sesion()
        # exp/48: punto seguro 1 — la pregunta del usuario quedó registrada.
        # Checkpoint del shared COMPLETO (bookkeeping: jamás corta el chat).
        checkpoint(thread_id(), "GetQuestion", "continue", shared)
        return "continue"


def pregunta_en_curso(messages):
    """La última pregunta del usuario: el último `user` que no sea un mensaje
    que la entrada del chat inyectó (pre-fetch o skill)."""
    for m in reversed(messages):
        contenido = str(m.get("content", ""))
        if m.get("role") == "user" and not contenido.startswith((PREFIJO_PREFETCH, PREFIJO_SKILL)):
            return contenido
    return ""


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
        return pregunta_en_curso(shared.get("messages", []))

    def post(self, shared, prep_res, _exec_res):
        decididos = decidir(prep_res)
        texto = mensaje_prefetch(decididos)
        if texto:
            shared["messages"].append({"role": "user", "content": texto})
            for path, _ in decididos:
                print(colorear(f"  [pre-fetch] {path}", "info"))
        return "continue"


class Skills(Node):
    """exp/55: el skill de la pregunta, una vez, a la entrada (fase 3b, X106).

    Vivía dentro del router y solo corría en enforce; sin router es un nodo
    propio entre `PreFetch` y `Contexto`. `skill_para` decide por la condición
    del YAML (determinista, sin LLM) hasta la 5b, que la cambia por activación
    por descripción. Si dispara: el id va al turno (AgentStep recorta las tools
    a su subset) y su prompt entra como mensaje `[skill]`. `SKILLS=0` lo apaga.
    Siempre "continue"."""

    def prep(self, shared):
        return pregunta_en_curso(shared.get("messages", []))

    def exec(self, pregunta):
        if _setting("SKILLS", "1") == "0" or not pregunta:
            return None
        return skill_para(pregunta, disponibles())

    def post(self, shared, prep_res, exec_res):
        if exec_res is not None:
            turno(shared)["skill"] = exec_res.id
            shared["messages"].append({"role": "user", "content": mensaje_skill(exec_res)})
            print(colorear(f"  [skill] {exec_res.id} activo — {exec_res.descripcion}", "info"),
                  flush=True)
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
    entrar la pregunta y tras cada ronda de tools). Si el historial supera
    COMPACTION_CHARS: la zona fría se respalda (gancho `al_compactar`) y se
    reemplaza por un marcador (código puro, sin LLM; los invariantes del modo
    thinking los da utils/compaccion.compactar); si ni así baja, se recortan
    los tool results viejos (exp/91) y se avisa una vez (X51). La huella evita
    re-compactar la misma ronda. Sale a `herramientas` (la llamada con
    tools), o por `cierre` si el presupuesto de la pregunta se acabó (X96): venga de donde
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
        exec_res, avisos = normalizar(exec_res, tools)
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
        # exp/48: punto seguro 3 — la respuesta quedó registrada (Cierre hereda
        # este post y su checkpoint usa el nombre de la clase real).
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
    """Lo que deja una ronda de tools, contado por código (X96): la ronda y lo
    que el MODELO tiene que leer — la nota de presupuesto viaja en el último
    resultado, porque la terminal no le llega. Después el checkpoint (exp/48,
    punto seguro 2: la ronda quedó registrada). Si el presupuesto se acabó lo
    decide Contexto, antes de la próxima llamada. Desde S6 (X132) el saldo es
    uno solo: no hay aviso de no-progreso ni corte por novedad."""

    def prep(self, shared):
        return next((m["tool_calls"] for m in reversed(shared["messages"])
                     if m.get("role") == "assistant" and m.get("tool_calls")), [])

    def post(self, shared, llamadas, _):
        t = turno(shared)
        t["rondas"] += 1
        tope = presupuesto(shared)
        notas = [nota_presupuesto(t["rondas"], tope)]
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


