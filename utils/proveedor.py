"""Lo que el proveedor devuelve, normalizado a la forma canónica (H2).

Los descarrilos de DeepSeek medidos en producción son del ADAPTADOR, no del
grafo: tool calls que llegan como texto con su markup interno (DSML), markers
de rol ajenos y tags HTML que parten palabras. Viven acá una sola vez y los
usan el chat (`nodes.py`) y el kernel (`utils/kernel.py`)."""
import json
import re
from types import SimpleNamespace

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


MENSAJE_DSML_AGOTADO = (
    "(sin texto: emitiste tool-calls con el presupuesto agotado — decí "
    "'seguí' para reiniciarlo)"
)


def dsml_con_presupuesto_agotado(content, parseados, tools):
    """(nuevo_content, avisar): la recuperación DSML no re-armó tools que
    el tope retiró (ley L8 — medido en exp/4 que sí las ejecutaba: el
    write_file corría después del retiro). Con tools presentes la
    recuperación de siempre; sin tools, el markup se corta y el mensaje
    que queda es honesto y accionable."""
    if tools is not None or not parseados:
        return content, False
    m = RE_DSML.search(content or "")
    limpio = (content or "")[: m.start()].rstrip() if m else ""
    if not limpio:
        return MENSAJE_DSML_AGOTADO, True
    return limpio, True


MENSAJE_SIN_RESPUESTA = (
    "(sin respuesta: el stream se cortó sin contenido — reintentá el pedido)"
)


# Lo que pasó al normalizar, para quien lo muestre (el chat lo imprime; el
# kernel lo ignora). Los textos del chat son contrato del banco (MARCADORES).
AVISOS = {
    "dsml_ignorado": "  [DSML] tool calls como texto: IGNORADOS (presupuesto agotado; 'seguí' lo reinicia)",
    "dsml_recuperado": "  [recuperación] tool calls llegaron como texto (DSML) → ejecutando",
    "l8": "  [L8] tool calls con las tools retiradas: IGNORADAS",
    "sanitizado": "  [sanitizado] la respuesta descarriló a un prompt ajeno: cortada",
}


def normalizar(msg, tools):
    """La respuesta del proveedor en forma canónica. Devuelve (msg, avisos).

    Una sola normalización para el chat y el kernel (H2 PR 4b): antes el
    kernel tenía una versión más gruesa que, por ejemplo, devolvía como
    respuesta un "solo markup de rol" en vez de re-preguntar. En orden:
    - DSML como texto → tool calls, salvo que las tools estén retiradas (L8:
      el presupuesto no se by-pasea por el canal de texto, exp/12);
    - tool calls nativas con las tools retiradas → se descartan (L8);
    - sin texto ni tool calls (stream cortado) → mensaje honesto, no null;
    - markers de rol ajenos → se corta; si no queda nada, `ValueError` para
      que el retry del nodo re-pregunte."""
    avisos = []
    if not getattr(msg, "tool_calls", None) and RE_DSML.search(msg.content or ""):
        parseados = dsml_a_tool_calls(msg.content)
        contenido, ignorado = dsml_con_presupuesto_agotado(msg.content, parseados, tools)
        if ignorado:
            msg.content = contenido
            avisos += ["dsml_ignorado", "reemplazado"]
        elif parseados:
            msg.content, msg.tool_calls = None, parseados
            avisos.append("dsml_recuperado")
    if tools is None and getattr(msg, "tool_calls", None):
        msg.tool_calls = None
        avisos.append("l8")
        if not (msg.content or "").strip():
            msg.content = MENSAJE_DSML_AGOTADO
            avisos.append("reemplazado")
    if getattr(msg, "tool_calls", None):
        return msg, avisos
    if not (msg.content or "").strip():
        msg.content = MENSAJE_SIN_RESPUESTA
        avisos.append("reemplazado")
    contenido, cortado = sanitizar(msg.content)
    if cortado:
        if not contenido:
            raise ValueError("respuesta descarrilada (solo markup de rol)")
        msg.content = contenido
        avisos.append("sanitizado")
    return msg, avisos
