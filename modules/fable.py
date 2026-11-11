"""Módulo `fable`: verificación adversarial de trabajo terminado.

Expone la pieza fable_judge.py (F1 del port de fable-method) como tool del
chat: el reporte de un trabajo es un conjunto de claims que se juzgan por
diff contra la referencia y por re-ejecución, no creyéndolos.

X195: la capacidad declara su arista en el template de X194 (produce
`veredicto`) y sus dos etapas del modelo corren en `kernel.loop`; el
conector es la MISMA tool, por el despacho único."""
from fable_judge import verificar_trabajo as juzgar
from utils.conector import Conector
from utils.fs_tools import run_tool_call
from utils.kernel import Tool

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
                    "sector": {"type": "string", "description": "Dominio para trabajo no-código (ej.: marketing, data-analysis, research): juzga con la tabla de fraudes y fuentes del dominio"},
                },
                "required": ["trabajo", "reporte"],
            },
        },
    },
]


def _por_el_kernel(llamada, _ctx):
    """La tool de la arista: el mismo verificar_trabajo, por run_tool_call."""
    return run_tool_call(llamada, IMPL)["content"]


CONECTORES = (
    Conector(Tool(TOOLS[0]["function"]["name"], TOOLS[0], _por_el_kernel),
             "veredicto", ("pregunta",)),
)


def verificar_trabajo(trabajo, pristine=None, reporte=None, sector=None):
    try:
        texto, advertencia = juzgar(trabajo, pristine, reporte, sector=sector)
    except ValueError as e:
        return f"ERROR: {e}"
    if advertencia:
        texto += f"\n\n(⚠️ {advertencia})"
    return texto


IMPL = {"verificar_trabajo": verificar_trabajo}
