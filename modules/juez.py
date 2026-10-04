"""Módulo `juez`: respuesta con verificación (evaluator-optimizer).

Corre el flujo Draft→Judge→retry de juez.py y devuelve la respuesta
refinada. El juez verifica citas contra los archivos reales."""
from juez import responder_con_juez

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "answer_verified",
            "description": "Responde una pregunta con control de calidad: un borrador, un juez que evalúa (y verifica citas ruta:línea contra el contenido real de los archivos) y refinamiento automático. Úsalo cuando el usuario pida rigor o respuestas verificadas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pregunta": {"type": "string", "description": "La pregunta a responder con verificación"},
                },
                "required": ["pregunta"],
            },
        },
    },
]


def answer_verified(pregunta):
    respuesta, advertencia = responder_con_juez(pregunta)
    resultado = respuesta
    if advertencia:
        resultado += f"\n\n(⚠️ {advertencia})"
    return resultado


IMPL = {"answer_verified": answer_verified}
