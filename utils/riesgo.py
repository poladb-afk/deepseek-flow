"""El log de las decisiones humanas de comando: las etiquetas de un juez futuro.

Cada s/n de `run_command` en las bandas que decide un humano
(`preguntar`/`confirmar_doble`) deja una línea con el comando, el último
mensaje del usuario (la evidencia de intención) y la respuesta. La respuesta
ES la etiqueta: cuando haya ≥300 orgánicas y ≥100 rechazos (roadmap, ítem 5;
`banco/probes/estado_riesgo.py`) se pre-registra un juez que DECIDA.

`origen` dice quién decidió: un humano (`terminal`/`web`) o un scope
(`scope`: banco y conductor; no entra al fine-tune).
"""
import json
import time
from pathlib import Path

from utils.call_llm import _setting


def origen():
    """Por dónde llegó el TRÁFICO (pregunta, decisión HITL): `web` o
    `terminal`. El producto no sabe si lo miden: el banco no se distingue con
    una bandera sino escribiendo sus logs aparte (`salidas/banco/`, X93). Los
    logs de antes de X93 traen además `banco` y las sondas lo siguen excluyendo."""
    if _setting("HITL_WEB", "0") == "1":
        return "web"
    return "terminal"


def origen_etiqueta():
    """Quién decidió el s/n que es la ETIQUETA, por el MECANISMO que lo
    decidió: con `HITL_SCOPE` lo decide el scope del archivo (banco y
    conductor; no es juicio humano y no entra al fine-tune) → `scope`; si no,
    un humano en la terminal o la web → `origen()`."""
    if _setting("HITL_SCOPE", ""):
        return "scope"
    return origen()


def registrar(comando, mensaje, aprobado, ruta=None):
    """Una línea en RIESGO_ARCHIVO (default salidas/riesgo.jsonl), gated por
    RIESGO_LOG (default 1). Bookkeeping: nunca rompe la acción.

    {"ts", "comando"[:200], "mensaje"[:200], "aprobado": bool, "origen": scope|web|terminal}"""
    if _setting("RIESGO_LOG", "1") != "1":
        return
    try:
        destino = Path(ruta or _setting("RIESGO_ARCHIVO", "salidas/riesgo.jsonl"))
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "comando": str(comando)[:200],
                    "mensaje": str(mensaje)[:200],
                    "aprobado": bool(aprobado),
                    "origen": origen_etiqueta(),
                },
                ensure_ascii=False,
            ) + "\n")
    except (OSError, TypeError, ValueError):  # bookkeeping: nunca rompe la acción
        pass
