"""Módulo `humano`: el humano como tool call (factor 7, exp/49).

Hasta acá el humano solo participaba por la aprobación HITL (un `s/n`);
acá el modelo PUEDE preguntarle en medio de una tarea — pedir una
aclaración antes de asumir, cuando le falta información que no puede
obtener con tools.

Es UNA línea leída por `input()`: la pregunta se imprime etiquetada como
`[humano]` y el texto tecleado vuelve como resultado de la tool. EOF o
cualquier excepción del `input()` NO es un crash: devuelve un string
`(sin respuesta del humano: {motivo})` — que el modelo lee como dato.

Sin HITL de aprobación (preguntar no es un efecto), sin timeout v1. Un
Ctrl+C durante el input se propaga como siempre en el chat: Ctrl+C es
del usuario, no del agente.
"""
from utils.terminal import colorear

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "request_human_input",
            "description": (
                "Preguntale al usuario cuando te falte información que no "
                "podés obtener con tools. No la uses para reportar avances."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pregunta": {
                        "type": "string",
                        "description": "La pregunta para el humano",
                    },
                },
                "required": ["pregunta"],
            },
        },
    },
]


def request_human_input(pregunta):
    """Imprime la pregunta y devuelve el texto leído por `input()`.

    EOF o excepción → `"(sin respuesta del humano: {motivo})"` (dato, no
    crash). SIGINT durante el input se propaga: Ctrl+C es del usuario."""
    print(colorear(f"  [humano] {pregunta}", "aviso"))
    try:
        return input()
    except KeyboardInterrupt:
        raise  # Ctrl+C es del usuario: se propaga como siempre
    except EOFError:
        return "(sin respuesta del humano: EOF)"
    except (OSError, ValueError) as e:  # cualquier fallo del input es un dato, no un crash  # noqa: BLE001 (fallo del input es un dato, no un crash)
        return f"(sin respuesta del humano: {type(e).__name__}: {e})"


IMPL = {"request_human_input": request_human_input}
