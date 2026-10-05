"""Módulo `juez`: respuesta con verificación (evaluator-optimizer) y lote
en paralelo.

Corre el flujo Draft→Judge→retry de juez.py y devuelve la respuesta
refinada. El juez verifica citas contra los archivos reales.
`run_juez_lote` reutiliza ese mismo flujo dentro del fan-out async de
juez_lote.py y mide el speedup (patrón parallel del cookbook)."""
from juez import responder_con_juez
from juez_lote import resolver_archivo, run_juez_lote

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
                    "rondas": {"type": "integer", "description": "Tope de rondas de evaluación (default: 2)"},
                },
                "required": ["pregunta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "juez_lote",
            "description": (
                "Verifica VARIAS preguntas EN PARALELO, cada una con el flujo del juez "
                "(borrador → juez → refinamiento). El argumento es la ruta de un archivo "
                "de texto con una pregunta por línea no vacía. Escribe un informe markdown "
                "con una sección por pregunta (respuesta, citas, veredicto, rondas) y la "
                "medición del speedup (tiempo paralelo vs suma de los tiempos individuales). "
                "Úsalo cuando el usuario pida verificar un lote de preguntas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "preguntas": {"type": "string", "description": "Ruta del archivo con una pregunta por línea no vacía"},
                    "salida": {"type": "string", "description": "Archivo markdown de salida (default: 'salidas/juez_lote.md')"},
                },
                "required": ["preguntas"],
            },
        },
    },
]


def answer_verified(pregunta, rondas=None):
    respuesta, advertencia = responder_con_juez(pregunta, rondas=rondas or 2)
    resultado = respuesta
    if advertencia:
        resultado += f"\n\n(⚠️ {advertencia})"
    return resultado


def juez_lote(preguntas, salida="salidas/juez_lote.md"):
    ruta, err = resolver_archivo(preguntas)
    if err:
        return f"ERROR: {err}"
    return run_juez_lote(ruta, salida)


IMPL = {"answer_verified": answer_verified, "juez_lote": juez_lote}
