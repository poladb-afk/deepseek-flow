"""X198: el catálogo de capacidades y su uso (D1–D4 del pre-registro).

El primer request lleva, además de las tools del CORE, solo estas dos: el
`catalogo` lista las capacidades de los módulos presentes (nombre, para qué
sirve y parámetros) y `usar` ejecuta una por `run_tool_call`, el despacho
único (hooks, política y HITL igual que en el chat). Los esquemas de los
módulos ya no viajan en el prompt: el manifiesto sale de `discover()` cuando
el modelo lo pide, y el prefijo queda estable (P1, X173).
"""
import json

from utils.fs_tools import TOOLS as CORE_TOOLS
from utils.fs_tools import run_tool_call

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "catalogo",
            "description": "Lista las capacidades disponibles: nombre, para qué sirve y parámetros. Consultalo cuando no sepas qué capacidad resuelve el pedido.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "usar",
            "description": "Ejecuta una capacidad del catálogo con los argumentos que el catálogo declara.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre de la capacidad, tal como lo lista el catálogo"},
                    "argumentos": {"type": "object", "description": "Argumentos de la capacidad, con los nombres del catálogo"},
                },
                "required": ["nombre", "argumentos"],
            },
        },
    },
]


def _manifiesto(tools):
    """El catálogo que ve el modelo: una entrada por capacidad de módulo."""
    return json.dumps({"capacidades": [
        {"nombre": t["function"]["name"],
         "descripcion": t["function"].get("description", ""),
         "parametros": t["function"].get("parameters", {"type": "object", "properties": {}})}
        for t in tools]}, ensure_ascii=False)


def catalogo_de(tools, impls):
    """Las dos tools fijas y sus impls, cableadas a los módulos presentes.
    `tools` son sus esquemas y `impls` sus implementaciones."""
    def catalogo(**_):
        return _manifiesto(tools)

    def usar(nombre, argumentos=None):
        nombre = str(nombre)
        if nombre not in impls:
            return f"ERROR: capacidad desconocida: {nombre!r} (el catálogo las lista)"
        argumentos = argumentos or {}
        if isinstance(argumentos, str):
            try:
                argumentos = json.loads(argumentos)
            except json.JSONDecodeError:
                return "ERROR: los argumentos de la capacidad no son JSON"
        llamada = {"function": {"name": nombre,
                                "arguments": json.dumps(argumentos, ensure_ascii=False)}}
        return run_tool_call(llamada, impls)["content"]

    return TOOLS, {"catalogo": catalogo, "usar": usar}


def tools_de_request(tools, impls):
    """Las tools del primer request: el CORE más `catalogo` y `usar`."""
    fijas, _ = catalogo_de(tools, impls)
    return CORE_TOOLS + fijas


def despachar(llamada, tools, impls):
    """El despacho del chat: las capacidades de los módulos y el catálogo por
    el camino único (`run_tool_call`)."""
    _, del_catalogo = catalogo_de(tools, impls)
    return run_tool_call(llamada, {**impls, **del_catalogo})
