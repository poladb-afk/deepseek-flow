"""Módulo `supervisor`: orquestación de piezas como capacidad del chat.

Corre el flujo Planificar→EjecutarPasos→Sintetizar (el mismo action space,
planificado) y devuelve la síntesis con la ruta del informe."""
from supervisor import supervisar

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_supervisor",
            "description": "Descompone una tarea compuesta en pasos, ejecuta cada uno con la herramienta adecuada (auditoría, debate, research, sql, ...) y sintetiza el cierre. Úsalo para tareas multi-paso que combinen varias capacidades de una vez.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tarea": {"type": "string", "description": "La tarea compuesta a orquestar"},
                    "salida": {"type": "string", "description": "Archivo de salida (default: supervisor.md)"},
                },
                "required": ["tarea"],
            },
        },
    },
]


def run_supervisor(tarea, salida="supervisor.md"):
    ruta = supervisar(tarea, salida)
    return f"Síntesis del supervisor escrita: {ruta}. Lee el archivo con read_file."


IMPL = {"run_supervisor": run_supervisor}
