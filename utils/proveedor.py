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
