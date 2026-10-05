"""Laya: juicios cerrados locales con probabilidades — los "ifs inteligentes".

Carga perezosa del checkpoint (LAYA_MODEL). Para el router del chat, el
checkpoint es el fine-tune router_flow (bmo/train/kaggle-router): 22/24
con compuerta contra 12/24 del base multilingual (medido, design.md).
Sin LAYA_MODEL, el default es el BASE multilingual — útil como fallback
genérico, pero el router afinado se trae de bmo.

Detalles medidos:
- laya.load con path LOCAL igual consulta HF Hub y puede colgar en red:
  si el path existe, activamos HF_HUB_OFFLINE antes de cargar (13 s).
- La confianza útil es answer_confidence (prob. de la opción elegida);
  "confidence" es otra cosa (margen).
Si laya o el checkpoint no están, disponible() da False y quien llama
degrada a su camino de siempre — Laya es un acelerador, no dependencia."""
import os
import threading
from pathlib import Path

from utils.call_llm import _setting

_lock = threading.RLock()  # reentrante: preguntar() lockea y llama a agente(), que lockea de nuevo
_agentes = {}  # setting → agente (router y supervisor cargan checkpoints distintos)
_errores = {}  # setting → error (por checkpoint: el fallo de uno no envenena al otro)

DEFAULT_MODEL = "convaiinnovations/laya-multilingual"


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
                except Exception as e:  # sin modelo local: degradar, no romper
                    _errores[clave] = f"{type(e).__name__}: {e}"
    if clave in _errores and clave not in _agentes:
        raise RuntimeError(f"laya no disponible: {_errores[clave]}")
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


def preguntar(estado, preguntas, setting="LAYA_MODEL"):
    """Una pasada local. Devuelve {id: (respuesta, confianza)}.

    `estado` puede ser str, dict o lista (laya serializa el dict a JSON:
    el contrato de los fine-tunes es {"pregunta": ...} / {"tarea", "hechos"}).
    `setting` elige el checkpoint: LAYA_MODEL (router) o
    LAYA_MODEL_SUPERVISOR (Choose del supervisor)."""
    with _lock:
        resultado = agente(setting).system_one(estado, preguntas, lang="es")
    return {
        pid: (r.get("choice", r.get("answer")), _confianza(r))
        for pid, r in resultado["answers"].items()
    }


def veredicto(confianza, alto=None, bajo=None):
    alto = float(alto if alto is not None else _setting("LAYA_UNSURE_HIGH", "0.7"))
    bajo = float(bajo if bajo is not None else _setting("LAYA_UNSURE_LOW", "0.3"))
    if confianza >= alto:
        return "met"
    if confianza <= bajo:
        return "not met"
    return "uncertain"
