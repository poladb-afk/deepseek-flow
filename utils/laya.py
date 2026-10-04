"""Laya: juicios cerrados locales con probabilidades — los "ifs inteligentes".

Carga perezosa del checkpoint (LAYA_MODEL). Default: el checkpoint BASE
multilingual de laya — el fine-tune de bmo (train/runs-kaggle) está
especializado en su Choose y responde casi al azar a preguntas de routing
fuera de distribución (medido: 0.52/0.48), así que NO es buen default
aquí; puedes apuntarlo con LAYA_MODEL si algún día afinas para esto.

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
_agente = None
_error = None

DEFAULT_MODEL = "convaiinnovations/laya-multilingual"


def agente():
    global _agente, _error
    if _agente is None and _error is None:
        with _lock:
            if _agente is None and _error is None:
                try:
                    modelo = _setting("LAYA_MODEL", DEFAULT_MODEL)
                    if Path(modelo).exists():
                        # ANTES de importar laya: huggingface_hub lee estas
                        # variables al importarse, y con path local igual
                        # consulta el Hub (y puede colgar en red).
                        os.environ.setdefault("HF_HUB_OFFLINE", "1")
                        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                    import laya

                    _agente = laya.load(modelo)
                except Exception as e:  # sin modelo local: degradar, no romper
                    _error = f"{type(e).__name__}: {e}"
    if _error:
        raise RuntimeError(f"laya no disponible: {_error}")
    return _agente


def disponible():
    try:
        agente()
        return True
    except RuntimeError:
        return False


def _confianza(respuesta):
    if respuesta.get("answer_confidence") is not None:
        return respuesta["answer_confidence"]
    if "probabilities" in respuesta:
        return max(respuesta["probabilities"].values())
    return respuesta.get("confidence", 0.0)


def preguntar(estado, preguntas):
    """Una pasada local. Devuelve {id: (respuesta, confianza)}."""
    with _lock:
        resultado = agente().system_one(str(estado), preguntas, lang="es")
    return {
        pid: (r.get("choice", r.get("answer")), _confianza(r))
        for pid, r in resultado["answers"].items()
    }


def veredicto(confianza):
    alto = float(_setting("LAYA_UNSURE_HIGH", "0.7"))
    bajo = float(_setting("LAYA_UNSURE_LOW", "0.3"))
    if confianza >= alto:
        return "met"
    if confianza <= bajo:
        return "not met"
    return "uncertain"
