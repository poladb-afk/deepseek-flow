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
import time
from dataclasses import dataclass
from pathlib import Path

ETIQUETAS = ("directo", "herramientas")
MODOS = ("off", "shadow", "enforce")


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
    except Exception:
        return "desconocida"


def config_router() -> RouterConfig:
    """Modo, umbral fijo, q conformal y versión de laya, desde settings."""
    from utils.call_llm import _setting

    modo = (_setting("LAYA_MODO", "enforce") or "enforce").strip().lower()
    if modo not in MODOS:
        print(f"  [laya] LAYA_MODO desconocido ({modo!r}) -> enforce")
        modo = "enforce"
    try:
        umbral = float(_setting("LAYA_UNSURE_HIGH", "0.85"))
    except (TypeError, ValueError):
        umbral = 0.85
    calibracion = _setting("LAYA_CALIBRACION_ROUTER", "") or ""
    q = None
    if calibracion:
        try:
            from utils.conformal import leer_calibracion, q_de_calibracion

            alpha = float(_setting("LAYA_ALPHA", "0.10"))
            q = q_de_calibracion(leer_calibracion(calibracion), alpha)
        except Exception as e:
            print(f"  [laya] calibración no utilizable ({type(e).__name__}) -> umbral fijo")
            q = None
    return RouterConfig(
        modo=modo, umbral=umbral, q=q, calibracion=calibracion, version=version_laya()
    )


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
    """La ruta que EJECUTA el grafo: en force se aplica, en off y shadow no."""
    return propuesta if config.modo == "enforce" else "herramientas"


def registrar_decision(evento, ruta=None):
    """Una línea JSON por decisión. Bookkeeping: nunca rompe el chat."""
    from utils.call_llm import _setting

    if _setting("LAYA_LOG_DECISIONES", "1") != "1":
        return
    try:
        destino = Path(ruta or _setting("LAYA_LOG_ARCHIVO", "salidas/routing.jsonl"))
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": round(time.time(), 3), **evento}, ensure_ascii=False) + "\n")
    except Exception:
        pass
