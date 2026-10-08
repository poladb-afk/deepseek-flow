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
from pathlib import Path

from utils.call_llm import _setting

_lock = threading.RLock()  # reentrante: preguntar() lockea y llama a agente(), que lockea de nuevo
_agentes = {}  # setting → agente (router y supervisor cargan checkpoints distintos)
_errores = {}  # setting → error (por checkpoint: el fallo de uno no envenena al otro)
_uso = {}  # setting → contador de uso (para desalojar el MENOS usado, no el primero)

DEFAULT_MODEL = "convaiinnovations/laya-multilingual"

# La ley medida (exp/7) es un checkpoint por proceso: 2,86 GiB de RSS CADA UNO.
# En un chat son alcanzables cuatro (router, voto, prefiltro y supervisor
# in-process): ~11 GiB. Este tope convierte la ley en contrato — al pasarse,
# se descarga el menos usado y la RAM vuelve al SO.
MAX_EN_PROCESO = int(_setting("LAYA_MAX_EN_PROCESO", "2"))


def _descargar(clave):
    """Suelta el agente de esa clave y devuelve su memoria al SO."""
    agente_ = _agentes.pop(clave, None)
    _uso.pop(clave, None)
    if agente_ is not None:
        del agente_
        gc.collect()


def agente(setting="LAYA_MODEL"):
    """El agente del checkpoint que ese setting nombra (caché por setting:
    el router del chat y el Choose del supervisor no son el mismo modelo)."""
    clave = _setting(setting, DEFAULT_MODEL)
    if clave not in _agentes and clave not in _errores:
        with _lock:
            if clave not in _agentes and clave not in _errores:
                try:
                    if Path(clave).exists():
                        # ANTES de importar laya: huggingface_hub lee estas
                        # variables al importarse, y con path local igual
                        # consulta el Hub (y puede colgar en red).
                        os.environ.setdefault("HF_HUB_OFFLINE", "1")
                        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                    import laya

                    _agentes[clave] = laya.load(clave)
                    # desalojo del menos usado; el recién cargado queda
                    # afuera del sorteo (su contador de uso todavía es 0)
                    while len(_agentes) > MAX_EN_PROCESO:
                        otros = [c for c in _agentes if c != clave]
                        if not otros:
                            break
                        candidato = min(otros, key=lambda c: (_uso.get(c, 0), c))
                        print(f"  [laya] tope {MAX_EN_PROCESO} en proceso: descargo "
                              f"{Path(candidato).name}")
                        _descargar(candidato)
                except Exception as e:  # sin modelo local: degradar, no romper
                    _errores[clave] = f"{type(e).__name__}: {e}"
    if clave in _errores and clave not in _agentes:
        raise RuntimeError(f"laya no disponible: {_errores[clave]}")
    _uso[clave] = _uso.get(clave, 0) + 1
    return _agentes[clave]


def disponible(setting="LAYA_MODEL"):
    try:
        agente(setting)
        return True
    except RuntimeError:
        return False


def _confianza(respuesta):
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


def preguntar_lote(estados, preguntas, setting="LAYA_MODEL"):
    """La versión en lote de preguntar(): los MISMOS contratos evaluados
    sobre N estados en forward(s) compartido(s) (Agent.predict_batch).
    Devuelve una lista alineada con estados: [{id_pregunta: (respuesta,
    confianza)}]. Misma ley de degradación: si algo falla, lanza — el
    llamador (contexto._puntuar) cae al default seguro."""
    with _lock:  # reentrante, igual que preguntar: agente() lockea de nuevo
        resultados = agente(setting).predict_batch(list(estados), preguntas, lang="es")
    return [_extraer(r["answers"]) for r in resultados]


def veredicto(confianza, alto=None, bajo=None):
    alto = float(alto if alto is not None else _setting("LAYA_UNSURE_HIGH", "0.85"))
    bajo = float(bajo if bajo is not None else _setting("LAYA_UNSURE_LOW", "0.3"))
    if confianza >= alto:
        return "met"
    if confianza <= bajo:
        return "not met"
    return "uncertain"
