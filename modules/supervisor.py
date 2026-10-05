"""Módulo `supervisor`: orquestación de piezas como capacidad del chat.

Corre el bucle reactivo ElegirSiguiente→EjecutarPaso→Sintetizar (Laya
elige la herramienta de cada paso; el mismo action space) y devuelve la
síntesis con la ruta del informe. El import es perezoso: el top-level
`supervisor` corre discover() al cargarse y un import mutuo colgaría
el registro de módulos."""
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
                    "salida": {"type": "string", "description": "Archivo de salida (default: salidas/supervisor.md)"},
                },
                "required": ["tarea"],
            },
        },
    },
]


def run_supervisor(tarea, salida="salidas/supervisor.md"):
    from supervisor import supervisar

    ruta = supervisar(tarea, salida)
    return f"Síntesis del supervisor escrita: {ruta}. Lee el archivo con read_file."


IMPL = {"run_supervisor": run_supervisor}
