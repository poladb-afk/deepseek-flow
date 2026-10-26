"""Estado de SESIÓN del proceso: lo que no vive en `shared` y un resume debe recuperar.

Tres piezas viven fuera del grafo porque las tools y el LLM no ven `shared`:
la evidencia de intención del juez de riesgo (el último mensaje del usuario,
exp/44), el uso de tokens de la sesión (`utils.call_llm`) y el historial de
aprobaciones HITL (`utils.aprobaciones`). Este módulo es su ÚNICO dueño para
guardar y restaurar: `capturar()` las junta en un dict JSON que el checkpoint
escribe junto al `shared`, y `restaurar()` las repone al rehidratar.

Medido (auditoría de elegancia, F5): tras `resume`, el costo de la sesión,
`/aprobaciones` y la intención del juez arrancaban de cero.
"""
_ultimo = {"mensaje": ""}


def recordar_usuario(texto):
    """El último mensaje del usuario del chat (evidencia de intención
    para el juez de riesgo). Lo siembra GetQuestion.post."""
    _ultimo["mensaje"] = "" if texto is None else str(texto)[:1000]


def ultimo_usuario():
    """El último mensaje recordado ('' si nunca)."""
    return _ultimo["mensaje"]


def capturar():
    """El estado de sesión del proceso, como dict JSON."""
    from utils import aprobaciones, call_llm

    return {"usuario": _ultimo["mensaje"],
            "uso": dict(call_llm.USO),
            "uso_por_modelo": {m: dict(f) for m, f in call_llm.USO_POR_MODELO.items()},
            "aprobaciones": aprobaciones.eventos()}


def restaurar(estado):
    """Repone lo capturado (un checkpoint viejo sin sesión no cambia nada).
    Los acumuladores se REEMPLAZAN, no se suman: el proceso nuevo arranca de
    cero y el checkpoint trae el total de la sesión hasta ese punto."""
    from utils import aprobaciones, call_llm

    if not isinstance(estado, dict):
        return
    _ultimo["mensaje"] = str(estado.get("usuario") or "")[:1000]
    call_llm.USO.update({k: int(v) for k, v in (estado.get("uso") or {}).items()})
    call_llm.USO_POR_MODELO.clear()
    call_llm.USO_POR_MODELO.update({m: dict(f) for m, f in (estado.get("uso_por_modelo") or {}).items()})
    aprobaciones.limpiar()
    aprobaciones.reponer(estado.get("aprobaciones") or [])
