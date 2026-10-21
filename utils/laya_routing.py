"""La POLÍTICA del router, separada de la clasificación (exp/35).

Laya ESTIMA (opción + probabilidades); Python DECIDE (qué ruta se aplica).
Mezclar las dos cosas fue el defecto de la primera versión: la compuerta vivía
dentro de LayaRouter.post, sin registro y sin forma de medir sin cambiar la
conducta.

Modos (LAYA_MODO):
- off: no se ejecuta Laya; la ruta es herramientas (el chat previo al router).
- shadow: se ejecuta y se REGISTRA la decisión, pero la ruta sigue siendo
  herramientas. Es el modo para juntar evidencia sin tocar el comportamiento.
- enforce (default): se aplica la propuesta — el comportamiento de siempre.

Reglas de decisión:
- Respuesta inválida = ABSTENCIÓN, nunca "directo" por defecto. Se EXIGEN las
  dos probabilidades, finitas, en [0, 1] y que sumen ~1: answer_confidence es
  max(p) y confidence es entropía normalizada (magnitudes distintas), así que
  la cascada del wrapper viejo podía mezclarlas.
- Con calibración (LAYA_CALIBRACION_ROUTER + LAYA_ALPHA): se acepta directo
  solo si el conjunto conformal COLAPSA (utils/conformal, exp/30/31), usando
  las probabilidades reales de cada etiqueta.
- Sin calibración: umbral fijo (LAYA_UNSURE_HIGH), como hasta hoy.

Código puro salvo la lectura de settings/calibración y el registro de la
decisión (bookkeeping: si falla, no rompe el chat).
"""
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

ETIQUETAS = ("directo", "herramientas")
MODOS = ("off", "shadow", "enforce")

# exp/46: la recencia no la juzga Laya (límite de familia documentado en el
# manual de Jev: sin fechas). Detección en código, generosa a propósito:
# falso-herramientas es barato (el modelo con tools puede responder directo).
RE_TEMPORAL = re.compile(
    r"(?i)\b(?:últim[oa]s?|ultim[oa]s?|actual(?:es|mente)?|actuales|"
    r"hoy|ahora|recientes?|novedades?|noticias?|latest|current|today|"
    r"20[2-3]\d)\b"
)


# exp/54: imperativos de CAPACIDAD (los falso-directo del router con acción).
# Solo la primera palabra: alta precisión sin imitar semántica. Los creativos
# ("escribime un haiku", "contame un cuento") quedan FUERA para no romper la
# trampa inversa; "generá" exige además un objeto de capacidad (informe,
# reporte, evaluación, métricas, documentación), porque "generá un poema" es
# directo. Encontro el hueco el bench del voto (exp/53, caso c01).
_IMPERATIVOS_CAPACIDAD = frozenset({
    "debatí", "debati", "debatir",
    "investigá", "investiga", "investigar",
    "buscá", "busca", "buscame", "buscáme",
    "leé", "lee", "leeme", "leéme",
    "corré", "corre",
    "editá", "edita",
    "medí", "mide",
    "analizá", "analiza",
    "documentá", "documenta",
    "revisá", "revisa",
    "aplicá", "aplica",
    "usá", "usa",
    "listá", "lista", "listame", "listáme",
    "mostrá", "muestra", "mostrame", "mostráme",
    "verificá", "verifica",
    "ejecutá", "ejecuta",
    "extraé", "extrae",
})

_RE_OBJETO_CAPACIDAD = re.compile(
    r"(?i)\b(informes?|reportes?|eval(?:s|uaci[oó]n)?|m[eé]tric(?:a|as)|"
    r"documentaci[oó]n|informe)\b"
)

_RELLENOS = frozenset({"por", "favor", "dale", "ahora", "primero", "después",
                       "despues", "luego", "entonces", "andá", "anda"})


def _primera_palabra(pregunta):
    """Primera palabra significativa, en minúsculas y sin ¿¡ ni comas."""
    for palabra in (pregunta or "").lower().replace("¿", " ").replace("¡", " ").split():
        limpia = palabra.strip(",.;:!?()[]")
        if limpia and limpia not in _RELLENOS:
            return limpia
    return ""


def regla_imperativo_capacidad(pregunta):
    """True si la pregunta ES una orden de capacidad (debatí, leé, corré…).

    Precedente `regla_temporal` de exp/46: la regla dura va ANTES del modelo.
    Acota el falso-directo del voto local (exp/53 c01: conf 0,94 en "debatí…")
    sin tocar los creativos, que se responden directo. PURA, testeable."""
    primera = _primera_palabra(pregunta)
    if primera in _IMPERATIVOS_CAPACIDAD:
        return True
    if primera in ("generá", "genera", "generar"):
        return bool(_RE_OBJETO_CAPACIDAD.search(pregunta or ""))
    return False


def regla_temporal(pregunta):
    """True si la pregunta pide recencia/hechos actuales: va al lado seguro
    (herramientas) sin consultar a Laya. PURA, testeable."""
    return bool(RE_TEMPORAL.search(pregunta or ""))


@dataclass(frozen=True)
class RouterConfig:
    """Lo que la política necesita saber, resuelto una vez por decisión."""

    modo: str = "enforce"
    umbral: float = 0.85
    q: float | None = None
    calibracion: str = ""
    version: str = ""


def version_laya() -> str:
    """La versión del paquete que produjo la decisión (trazabilidad)."""
    try:
        import importlib.metadata as md

        return md.version("laya")
    except Exception:  # noqa: BLE001 (laya no instalada: version desconocida (trazabilidad))
        return "desconocida"


def _umbral(nombre, default):
    """Un umbral de probabilidad VÁLIDO: finito y en [0, 1]. Cualquier otra
    cosa (typo, NaN, 1.5) usa el default — medido: LAYA_UNSURE_HIGH=nan hacía
    que `p < nan` diera False y el router eligiera directo."""
    from utils.call_llm import _setting

    try:
        valor = float(_setting(nombre, str(default)))
    except (TypeError, ValueError):
        return default
    if valor != valor or not 0.0 <= valor <= 1.0:
        print(f"  [laya] {nombre}={valor!r} fuera de [0, 1] -> {default}")
        return default
    return valor


def config_router() -> RouterConfig:
    """Modo, umbral fijo, q conformal y versión de laya, desde settings."""
    from utils.call_llm import _setting

    modo = (_setting("LAYA_MODO", "enforce") or "enforce").strip().lower()
    if modo not in MODOS:
        print(f"  [laya] LAYA_MODO desconocido ({modo!r}) -> enforce")
        modo = "enforce"
    umbral = _umbral("LAYA_UNSURE_HIGH", 0.85)
    calibracion = _setting("LAYA_CALIBRACION_ROUTER", "") or ""
    q = None
    if calibracion:
        try:
            from utils.conformal import leer_calibracion, q_de_calibracion

            alpha = float(_setting("LAYA_ALPHA", "0.10"))
            q = q_de_calibracion(leer_calibracion(calibracion), alpha)
        except (OSError, ValueError, TypeError) as e:  # noqa: BLE001 (calibracion no utilizable: umbral fijo)
            print(f"  [laya] calibración no utilizable ({type(e).__name__}) -> umbral fijo")
            q = None
    return RouterConfig(
        modo=modo, umbral=umbral, q=q, calibracion=calibracion, version=version_laya()
    )


def config_voto() -> RouterConfig:
    """Modo (no aplica), umbral fijo y q conformal del VOTO local (Mesa 3).

    Mismo patrón que config_router(), una capa abajo: el voto local decide los
    acuerdos y desacuerdos confiables ANTES del árbitro DeepSeek, y su umbral
    (LAYA_UNSURE_HIGH_VOTO=0.7) también puede salir de los datos. La cota acá
    es sobre la confianza ESCALAR del voto (answer_confidence), no sobre el
    vector de probabilidades: el artefacto {conf, correcto} de
    banco/probes/calibrar_voto.py es exactamente lo que consume
    utils.conformal.conjunto. Sin calibración, umbral fijo de siempre."""
    from utils.call_llm import _setting

    umbral = _umbral("LAYA_UNSURE_HIGH_VOTO", 0.7)
    calibracion = _setting("LAYA_CALIBRACION_VOTO", "") or ""
    q = None
    if calibracion:
        try:
            from utils.conformal import leer_calibracion, q_de_calibracion

            alpha = float(_setting("LAYA_ALPHA_VOTO", "0.10"))
            q = q_de_calibracion(leer_calibracion(calibracion), alpha)
        except (OSError, ValueError, TypeError) as e:  # noqa: BLE001 (calibracion no utilizable: umbral fijo (voto))
            print(f"  [voto] calibración no utilizable ({type(e).__name__}) -> umbral fijo")
            q = None
    return RouterConfig(
        modo="enforce", umbral=umbral, q=q, calibracion=calibracion, version=version_laya()
    )


def decide_voto(resp, conf, config):
    """(confiable, causa). PURA: sin I/O. Acepta la decisión local del voto
    solo si el conjunto conformal COLAPSA sobre la opción elegida; sin
    calibración, si conf >= umbral fijo. Devuelve (bool, str) — la causa va al
    print para trazabilidad."""
    from utils.conformal import conjunto

    if config.q is not None:
        if conjunto(float(conf), config.q) == ("elegida",):
            return True, f"conjunto colapsa (q={config.q:.3f})"
        return False, f"conjunto ambiguo (q={config.q:.3f})"
    if float(conf) >= config.umbral:
        return True, f"conf {float(conf):.2f} >= umbral {config.umbral:.2f}"
    return False, f"conf {float(conf):.2f} < umbral {config.umbral:.2f}"


def _numero(valor):
    """Un float finito en [0, 1], o None. Un bool NO es un número acá."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    numero = float(valor)
    if numero != numero or numero in (float("inf"), float("-inf")):
        return None
    if not 0.0 <= numero <= 1.0:
        return None
    return numero


def probabilidades(respuesta):
    """(p_directo, p_herramientas) o None si la respuesta no es utilizable."""
    if not isinstance(respuesta, dict):
        return None
    crudas = respuesta.get("probabilities")
    if not isinstance(crudas, dict):
        return None
    valores = [_numero(crudas.get(etiqueta)) for etiqueta in ETIQUETAS]
    if any(valor is None for valor in valores):
        return None
    p_directo, p_herramientas = valores
    if abs((p_directo + p_herramientas) - 1.0) > 0.05:
        return None
    return p_directo, p_herramientas


def decide(respuesta, config):
    """(propuesta, causa, p_directo). PURA: sin I/O ni efectos."""
    if config.modo == "off":
        return "herramientas", "modo off: Laya no se ejecuta", None
    if not isinstance(respuesta, dict) or not respuesta:
        return "herramientas", "respuesta inválida: sin detalle de Laya", None
    par = probabilidades(respuesta)
    if par is None:
        return "herramientas", "respuesta inválida: probabilidades ausentes o no usables", None
    p_directo, p_herramientas = par
    eleccion = respuesta.get("choice") or respuesta.get("answer")
    if eleccion not in ETIQUETAS:
        return "herramientas", f"etiqueta fuera de contrato: {eleccion!r}", p_directo
    if eleccion != "directo":
        return "herramientas", "laya eligió herramientas", p_directo
    if config.q is not None:
        # conjunto conformal con las probabilidades REALES de cada etiqueta
        piso = 1.0 - config.q
        plausibles = [
            etiqueta
            for etiqueta, p in (("directo", p_directo), ("herramientas", p_herramientas))
            if p >= piso
        ]
        if plausibles != ["directo"]:
            return "herramientas", f"conjunto no decide directo {plausibles} (q={config.q:.3f})", p_directo
        return "directo", f"conjunto colapsa en directo (q={config.q:.3f})", p_directo
    if p_directo < config.umbral:
        return "herramientas", f"p(directo)={p_directo:.3f} < umbral {config.umbral:.2f}", p_directo
    return "directo", f"p(directo)={p_directo:.3f} >= umbral {config.umbral:.2f}", p_directo


def ruta_aplicada(propuesta, config):
    """La ruta que EJECUTA el grafo: en enforce se aplica, en off y shadow no."""
    return propuesta if config.modo == "enforce" else "herramientas"


def registrar_decision(evento, pregunta=None, ruta=None):
    """Una línea JSON por decisión. Bookkeeping: nunca rompe el chat.

    La pregunta NO se guarda por default (privacidad): con LAYA_LOG_PREGUNTA=1
    se agregan sus primeros 200 caracteres, normalizados. Eso es lo que une los
    dos registros: el etiquetador del router
    (banco/probes/etiquetar_router.py --extra salidas/routing.jsonl) lee
    justamente la clave "pregunta", así que una corrida en modo sombra deja el
    set completo (pregunta + propuesta + confianza + ruta aplicada).

    exp/43: el `id` que une esta decisión con su resultado viaja DENTRO del
    evento (lo genera nodes.LayaRouter.post); acá no se toca. La línea lleva
    `origen` (`banco`/`web`/`terminal`, exp/71b): la flywheel no cuenta el
    tráfico sintético."""
    from utils.call_llm import _setting
    from utils.riesgo import origen

    if _setting("LAYA_LOG_DECISIONES", "1") != "1":
        return
    if pregunta and _setting("LAYA_LOG_PREGUNTA", "0") == "1":
        evento = {**evento, "pregunta": " ".join(str(pregunta).split())[:200]}
    try:
        destino = Path(ruta or _setting("LAYA_LOG_ARCHIVO", "salidas/routing.jsonl"))
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"ts": round(time.time(), 3), "origen": origen(), **evento},
                ensure_ascii=False,
            ) + "\n")
    except OSError:
        pass


def registrar_resultado(id_decision, rondas, ruta=None):
    """La ETIQUETA ambiental de una pregunta (exp/43): una línea "resultado"
    en el MISMO archivo que las decisiones, unida a su decisión por `id`.

    Qué mide: en modo shadow la ruta aplicada es SIEMPRE herramientas, así que
    DeepSeek corre con tools; si responde SIN llamar ninguna (rondas == 0) la
    pregunta era "directo" EN LA PRÁCTICA. Es una etiqueta gratis, en la
    distribución exacta de producción, que crece sola con el uso.

    LÍMITE HONESTO (documentar en el código, spec exp/43): mide lo que DeepSeek
    HIZO, no lo que la pregunta NECESITABA — un modelo que responde de memoria
    una pregunta de archivos etiqueta "directo" aunque otro hubiese leído. Es
    ruido declarado; el volumen lo compensa.

    Misma ley que registrar_decision: gated por LAYA_LOG_DECISIONES y
    bookkeeping (cualquier fallo —disco, permisos— se traga; nunca rompe el
    chat)."""
    from utils.call_llm import _setting

    if _setting("LAYA_LOG_DECISIONES", "1") != "1":
        return
    if not id_decision:  # sin decisión no hay a qué unir el resultado
        return
    try:
        rondas = int(rondas)
    except (TypeError, ValueError):
        return
    try:
        destino = Path(ruta or _setting("LAYA_LOG_ARCHIVO", "salidas/routing.jsonl"))
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "evento": "resultado",
                    "id": id_decision,
                    "uso_tools": rondas > 0,
                    "rondas": rondas,
                },
                ensure_ascii=False,
            ) + "\n")
    except OSError:
        pass
