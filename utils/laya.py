"""Laya: juicios cerrados locales con probabilidades — los "ifs inteligentes".

Carga perezosa del checkpoint (LAYA_MODEL). Para el router del chat, el
checkpoint es el fine-tune router_flow (bmo/train/kaggle-router): 27/30
crudo con ECE 0.066 (reproducible: python3 sonda_laya.py router; el 22/24 histórico era el test de 24 casos previo a la curaduría).
Sin LAYA_MODEL, el default es el BASE multilingual — útil como fallback
genérico, pero el router afinado se trae de bmo.

Detalles medidos:
- laya.load con path LOCAL igual consulta HF Hub y puede colgar en red:
  si el path existe, activamos HF_HUB_OFFLINE antes de cargar (13 s).
- La confianza útil es answer_confidence (prob. de la opción elegida);
  "confidence" es otra cosa (margen).
Si laya o el checkpoint no están, disponible() da False y quien llama
degrada a su camino de siempre — Laya es un acelerador, no dependencia."""
import gc
import os
import threading
import time
from pathlib import Path

from utils.call_llm import _entero, _setting

_lock = threading.RLock()  # reentrante: preguntar() lockea y llama a agente(), que lockea de nuevo
_agentes = {}  # setting → agente (router y supervisor cargan checkpoints distintos)
_errores = {}  # setting → (ts, error) (por checkpoint: el fallo de uno no envenena al otro)
_uso = {}  # setting → contador de uso (para desalojar el MENOS usado, no el primero)

DEFAULT_MODEL = "convaiinnovations/laya-multilingual"

# Un fallo de carga (OOM transitorio, checkpoint a medio copiar) se cachea,
# pero VENCE: pasado el cooldown se reintenta la carga en la misma llamada.
# Sin esto, un solo OOM del primer request envenenaba la sesión entera sin
# un solo reintento (medido: 31/37 decisiones sin detalle de Laya).
LAYA_ERROR_COOLDOWN = 60

# La ley medida (exp/7) es un checkpoint por proceso: 2,86 GiB de RSS CADA UNO.
# En un chat son alcanzables cuatro (router, voto, prefiltro y supervisor
# in-process): ~11 GiB. Este tope convierte la ley en contrato — al pasarse,
# se descarga el menos usado y la RAM vuelve al SO. Constante desde X101: como
# setting se leía con int() a secas y un typo en el .env tiraba el import.
MAX_EN_PROCESO = 2


def _descargar(clave):
    """Suelta el agente de esa clave y devuelve su memoria al SO."""
    agente_ = _agentes.pop(clave, None)
    _uso.pop(clave, None)
    if agente_ is not None:
        del agente_
        gc.collect()


def _limpiar_error_vencido(clave):
    """Si el error cacheado ya cumplió el cooldown, lo borra DENTRO del lock
    (antes del try) y la carga se reintenta en esta misma llamada."""
    if clave not in _errores or clave in _agentes:
        return
    with _lock:
        if clave in _errores and clave not in _agentes:
            ts, _msg = _errores[clave]
            if time.monotonic() - ts >= LAYA_ERROR_COOLDOWN:
                del _errores[clave]


def _offline_si_path_local(clave):
    """ANTES de importar laya: huggingface_hub lee estas variables al
    importarse, y con path local igual consulta el Hub (y puede colgar)."""
    if Path(clave).exists():
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _desalojar(clave):
    """Desaloja ANTES de cargar: el pico de memoria no supera el tope (ley
    medida en exp/7: ~2,86 GiB por checkpoint vivo)."""
    while len(_agentes) >= MAX_EN_PROCESO:
        otros = [c for c in _agentes if c != clave]
        if not otros:
            break
        candidato = min(otros, key=lambda c: (_uso.get(c, 0), c))
        print(f"  [laya] tope {MAX_EN_PROCESO} en proceso: descargo "
              f"{Path(candidato).name}")
        _descargar(candidato)


def _cargar_checkpoint(clave):
    """Carga y cachea el agente (bajo lock); un fallo se cachea con
    vencimiento, nunca rompe la sesión."""
    try:
        _offline_si_path_local(clave)
        import laya

        _desalojar(clave)
        _agentes[clave] = laya.load(clave)
        _errores.pop(clave, None)  # el acierto limpia el error residual
    except Exception as e:  # sin modelo local: degradar, no romper  # noqa: BLE001 (sin modelo local: degradar, no romper)
        _errores[clave] = (time.monotonic(), f"{type(e).__name__}: {e}")


def agente(setting="LAYA_MODEL"):
    """El agente del checkpoint que ese setting nombra (caché por setting:
    el router del chat y el Choose del supervisor no son el mismo modelo)."""
    clave = _setting(setting, DEFAULT_MODEL)
    _limpiar_error_vencido(clave)
    if clave not in _agentes and clave not in _errores:
        with _lock:
            if clave not in _agentes and clave not in _errores:
                _cargar_checkpoint(clave)
    if clave in _errores and clave not in _agentes:
        ts, msg = _errores[clave]
        raise RuntimeError(f"laya no disponible (hace {int(time.monotonic() - ts)}s): {msg}")
    _errores.pop(clave, None)  # el acierto (agente presente) limpia el error residual
    _uso[clave] = _uso.get(clave, 0) + 1
    return _agentes[clave]


def disponible(setting="LAYA_MODEL"):
    try:
        agente(setting)
        return True
    except RuntimeError:
        return False


def _confianza(respuesta):
    """Confianza de una respuesta: `answer_confidence` (prob. de la opción
    elegida) o, en su defecto, `max(probabilities)`. Si no hay ninguna de las
    dos, cae a `confidence` (que es MARGEN, no probabilidad): ese fallback NO
    es comparable con `answer_confidence` y no debería usarse para calibrar.
    (A57: el doc del módulo ya aclaraba la diferencia, pero no este fallback.)"""
    if respuesta.get("answer_confidence") is not None:
        return respuesta["answer_confidence"]
    if "probabilities" in respuesta:
        return max(respuesta["probabilities"].values())
    return respuesta.get("confidence", 0.0)


def _extraer(answers):
    """{id: (respuesta, confianza)} de un dict de answers de laya. La
    extracción compartida por preguntar() y preguntar_lote()."""
    return {pid: (r.get("choice", r.get("answer")), _confianza(r)) for pid, r in answers.items()}


def preguntar(estado, preguntas, setting="LAYA_MODEL"):
    """Una pasada local. Devuelve {id: (respuesta, confianza)}.

    `estado` puede ser str, dict o lista (laya serializa el dict a JSON:
    el contrato de los fine-tunes es {"pregunta": ...} / {"tarea", "hechos"}).
    `setting` elige el checkpoint: LAYA_MODEL (router) o
    LAYA_MODEL_SUPERVISOR (Choose del supervisor)."""
    with _lock:
        resultado = agente(setting).system_one(estado, preguntas, lang="es")
    return _extraer(resultado["answers"])


def preguntar_detalle(estado, preguntas, setting="LAYA_MODEL"):
    """La respuesta COMPLETA de laya (choice + probabilities + confianzas).

    preguntar() la reduce a (respuesta, confianza) y pierde el vector, que es
    lo que la política del router necesita para decidir con probabilidades
    reales por etiqueta y no con una confianza reconstruida (exp/35)."""
    with _lock:
        resultado = agente(setting).system_one(estado, preguntas, lang="es")
    return resultado["answers"]


def _probabilidades_usables(detalle, etiquetas):
    """{etiqueta: p} si el vector de probabilidades es usable (todas presentes,
    finitas, en [0,1] y suman ~1); None si no. La calibración es lo que hace
    útil el juicio: una confianza suelta puede ser un MARGEN, no una prob."""
    crudas = detalle.get("probabilities")
    if not isinstance(crudas, dict):
        return None
    valores = {}
    for etiqueta in etiquetas:
        valor = crudas.get(etiqueta)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            return None
        numero = float(valor)
        if not 0.0 <= numero <= 1.0:  # NaN/inf no pasan la comparación
            return None
        valores[etiqueta] = numero
    if abs(sum(valores.values()) - 1.0) > 0.05:
        return None
    return valores


def juicio(estado, instrucciones, opciones, setting="LAYA_MODEL"):
    """Juicio TIPADO y calibrado: elige UNA etiqueta de `opciones`
    ({etiqueta: criterio}) para `estado`, con su confianza y el vector de
    probabilidades. Devuelve {juicio, confianza, probabilidades} o None si
    Laya no está o la respuesta no es usable (el llamador degrada, igual que
    contexto._puntuar).

    Es la forma genérica del "if inteligente" para exponerla por MCP
    (mcp_server.juicio_laya): un agente externo pide el juicio local sin
    cargar un modelo propio."""
    if not isinstance(opciones, dict) or len(opciones) < 2:
        raise ValueError("opciones: dict {etiqueta: criterio} con >= 2 etiquetas")
    contrato = {"juicio": {"type": "choice", "instructions": instrucciones,
                           "criteria": dict(opciones)}}
    try:
        detalle = preguntar_detalle(estado, contrato, setting=setting)["juicio"]
    except (RuntimeError, KeyError, TypeError, AttributeError):
        return None
    eleccion = detalle.get("choice") or detalle.get("answer")
    if eleccion not in opciones:
        return None
    confianza = detalle.get("answer_confidence")
    if isinstance(confianza, bool) or not isinstance(confianza, (int, float)):
        confianza = None
    return {
        "juicio": eleccion,
        "confianza": float(confianza) if confianza is not None else None,
        "probabilidades": _probabilidades_usables(detalle, opciones),
    }


def preguntar_lote(estados, preguntas, setting="LAYA_MODEL"):
    """La versión en lote de preguntar(): los MISMOS contratos evaluados
    sobre N estados en forward(s) compartido(s) (Agent.predict_batch).
    Devuelve una lista alineada con estados: [{id_pregunta: (respuesta,
    confianza)}]. NO degrada acá: propaga cualquier excepción. La degradación
    (default seguro) la hace el llamador, p. ej. contexto._puntuar."""
    # Límite opcional del lote (LAYA_BATCH_SIZE): la dependencia NO acota por
    # su cuenta — con batch_size=None manda TODOS los estados en un forward y
    # el pico de memoria crece con N (el prefiltro puede mandar cientos).
    lote = _entero("LAYA_BATCH_SIZE", 0)
    extra = {"batch_size": lote} if lote > 0 else {}
    with _lock:  # reentrante, igual que preguntar: agente() lockea de nuevo
        resultados = agente(setting).predict_batch(list(estados), preguntas, lang="es", **extra)
    return [_extraer(r["answers"]) for r in resultados]


def veredicto(confianza, alto=None, bajo=None):
    alto = float(alto if alto is not None else _setting("LAYA_UNSURE_HIGH", "0.85"))
    bajo = float(bajo if bajo is not None else _setting("LAYA_UNSURE_LOW", "0.3"))
    if confianza >= alto:
        return "met"
    if confianza <= bajo:
        return "not met"
    return "uncertain"
