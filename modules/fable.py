"""Módulo `fable`: verificación adversarial de trabajo terminado.

Expone la pieza fable_judge.py (F1 del port de fable-method) como tool del
chat: el reporte de un trabajo es un conjunto de claims que se juzgan por
diff contra la referencia y por re-ejecución, no creyéndolos. El import de
la pieza es perezoso (el top-level corre discover() al cargarse)."""
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "verificar_trabajo",
            "description": (
                "Juzga adversarialmente un trabajo terminado (p. ej. hecho por otro agente): "
                "extrae los claims del reporte, diff-inea el trabajo contra la referencia "
                "pre-tarea, re-ejecuta las verificaciones que el reporte afirma haber corrido "
                "y caza los fraudes clásicos (checks debilitados, false completion, scope "
                "creep, acción sin autorización, spec betrayal, debris). Devuelve un veredicto "
                "VERIFIED / VERIFIED WITH CAVEATS / REFUTED con la tabla de claims y fraudes. "
                "Úsalo cuando el usuario pida verificar o auditar trabajo ya hecho y su reporte."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trabajo": {"type": "string", "description": "Directorio con el trabajo hecho"},
                    "pristine": {"type": "string", "description": "Directorio de referencia pre-tarea (default: git diff del propio trabajo)"},
                    "reporte": {"type": "string", "description": "Ruta al reporte a juzgar, o el texto del reporte"},
                },
                "required": ["trabajo", "reporte"],
            },
        },
    },
]


def verificar_trabajo(trabajo, pristine=None, reporte=None):
    from fable_judge import verificar_trabajo as juzgar

    try:
        texto, advertencia = juzgar(trabajo, pristine, reporte)
    except ValueError as e:
        return f"ERROR: {e}"
    if advertencia:
        texto += f"\n\n(⚠️ {advertencia})"
    return texto


IMPL = {"verificar_trabajo": verificar_trabajo}
