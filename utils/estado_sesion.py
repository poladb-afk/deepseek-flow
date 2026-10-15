"""Estado de sesión mínimo: el último mensaje del usuario (plumbing, exp/44).

El juez de riesgo necesita la EVIDENCIA DE INTENCIÓN —el último mensaje del
usuario del chat— para juzgar si el comando propuesto se alinea con lo pedido
(ley de la casa: el estado lleva la evidencia de intención, NUNCA el
razonamiento del propio agente). Los módulos de tools no ven `shared`, así que
esa evidencia vive acá, en un módulo mínimo con dos funciones.

Contrato: `recordar_usuario` no valida ni decide (es plumbing); `ultimo_usuario`
devuelve '' si nunca se sembró. El docstring del módulo no promete más de lo
que hay.
"""
_ultimo = {"mensaje": ""}


def recordar_usuario(texto):
    """El último mensaje del usuario del chat (evidencia de intención
    para el juez de riesgo). Lo siembra GetQuestion.post."""
    _ultimo["mensaje"] = "" if texto is None else str(texto)[:1000]


def ultimo_usuario():
    """El último mensaje recordado ('' si nunca)."""
    return _ultimo["mensaje"]
