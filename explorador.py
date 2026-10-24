"""Explorador aislado (exp/97): sub-agente de SÓLO LECTURA con contexto fresco.

La brecha que la comparativa SOTA marcó con nombre: el supervisor acumula
TODO en su historial. `explorar(pregunta)` corre un mini-flow síncrono cuyo
`messages` nace con dos entradas — el system del explorador y la pregunta — y
NADA del padre viaja; el historial muere con la exploración y sólo vuelve el
resumen como resultado de la tool.

    Cerrar ──fin──▶ Fin        (el nodo se apunta a sí mismo: rondas)
    Cerrar ──tool─▶ Leer ──default──▶ Cerrar

Mitigaciones:
- OWASP LLM06 (excessive agency): el toolset es una WHITELIST de nombres
  (`PERMITIDAS`) y run_tool_call no conoce otra implementación — `run_command`,
  write_file y edit_file no existen para el explorador.
- Presupuesto propio (MAX_PASOS_EXPLORADOR, `_entero`, default 3): sus rondas
  no consumen las del padre; al agotarlo se retiran las tools (cierre forzado,
  la ley del chat) y el retorno declara "usó N de M".
"""
from pathlib import Path

from pocketflow import Flow, Node

from utils import fs_tools
from utils.call_llm import _entero, call_llm_agent
from utils.fs_tools import TOOLS as BASE_TOOLS
from utils.historial import as_dict, historiar

MAX_PASOS_EXPLORADOR = _entero("MAX_PASOS_EXPLORADOR", 3)

# El permiso es el mapa, no la convención: sólo estos nombres y nada más.
PERMITIDAS = {"read_file", "list_files", "search_files"}
TOOLS = [t for t in BASE_TOOLS if t["function"]["name"] in PERMITIDAS]
REGISTRO = {
    "list_files": fs_tools.list_files,
    "read_file": fs_tools.read_file,
    "search_files": fs_tools.search_files,
}

NOMBRE_TOOL = "explorar"
TOOL_EXPLORAR = {
    "type": "function",
    "function": {
        "name": NOMBRE_TOOL,
        "description": "Delegá una investigación de solo lectura a un sub-agente con contexto FRESCO: "
        "lee, lista y busca por su cuenta y te devuelve un resumen con citas archivo:línea. "
        "Su historial no consume tu contexto ni tus rondas.",
        "parameters": {
            "type": "object",
            "properties": {
                "pregunta": {"type": "string",
                             "description": "Qué hay que averiguar, autocontenido (el sub-agente no ve tu conversación)"},
            },
            "required": ["pregunta"],
        },
    },
}


def system_prompt(pregunta, cwd=None):
    """System del explorador: curado (sin las directivas de escritura del
    chat), sólo lectura, resumen con citas y cierre forzado al agotar el
    presupuesto."""
    from utils.fs_tools import allowed_roots

    roots = "\n".join(f"- {r}" for r in allowed_roots())
    return (
        "Sos un sub-agente de INVESTIGACIÓN con tools de SÓLO LECTURA.\n\n"
        f"Pregunta: {pregunta}\n\n"
        "No podés escribir archivos ni ejecutar comandos: sólo leer, listar y buscar.\n"
        f"Tenés un presupuesto de {MAX_PASOS_EXPLORADOR} rondas de tools; a la última se "
        "retiran y tenés que cerrar igual con lo que hayas leído.\n\n"
        f"Trabajás en {cwd or Path.cwd()} y sus subdirectorios.\n"
        f"Directorio(s) permitido(s):\n{roots}\n\n"
        "Cuando tengas la respuesta, devolvé un RESUMEN en texto, sin llamar más "
        "herramientas: los hechos con sus citas archivo:línea (ruta relativa), y qué "
        "quedó sin verificar."
    )


def semilla(pregunta):
    """El `shared` del explorador: contexto fresco POR CONSTRUCCIÓN — system
    del explorador + pregunta, nada del padre."""
    return {
        "pregunta": pregunta,
        "messages": [
            {"role": "system", "content": system_prompt(pregunta)},
            {"role": "user", "content": pregunta},
        ],
        "rondas": 0,
        "resumen": None,
    }


class Cerrar(Node):
    """Una ronda: el modelo elige tool o cierra. Agotado el presupuesto se
    retiran las tools (cierre forzado) y el turno cierra sí o sí."""

    def prep(self, shared):
        return shared["messages"], shared["rondas"]

    def exec(self, inputs):
        messages, rondas = inputs
        tools = None if rondas >= MAX_PASOS_EXPLORADOR else TOOLS
        return call_llm_agent(messages, tools=tools)

    def post(self, shared, prep_res, exec_res):
        shared["messages"].append(historiar(exec_res))
        contenido = getattr(exec_res, "content", None)
        if getattr(exec_res, "tool_calls", None) and shared["rondas"] < MAX_PASOS_EXPLORADOR:
            shared["_tool_calls"] = [as_dict(tc) for tc in exec_res.tool_calls]
            return "tool"
        shared["resumen"] = contenido
        return "fin"


class Leer(Node):
    """Despacha cada tool_call por run_tool_call con el REGISTRO whitelisteado
    (el único camino con hooks): una tool fuera del mapa vuelve como ERROR."""

    def prep(self, shared):
        return shared.get("_tool_calls") or []

    def exec(self, tool_calls):
        return [fs_tools.run_tool_call(tc, REGISTRO) for tc in tool_calls]

    def post(self, shared, prep_res, exec_res):
        shared["messages"].extend(exec_res)
        shared["rondas"] = shared.get("rondas", 0) + 1
        for m in exec_res:
            print(f"  [explorador] {str(m['content'])[:120]}")
        shared.pop("_tool_calls", None)
        return "default"


class Fin(Node):
    def post(self, shared, prep_res, exec_res):
        shared["_terminado"] = True
        return None


def create_explorador_flow():
    cerrar = Cerrar(max_retries=3, wait=5)
    leer = Leer(max_retries=3, wait=5)
    fin = Fin()
    cerrar - "tool" >> leer
    cerrar - "fin" >> fin
    leer - "default" >> cerrar
    return Flow(start=cerrar)


def explorar(pregunta):
    """Corre el explorador y devuelve SOLO el resumen como texto, declarando
    el presupuesto usado ("usó N de M rondas")."""
    shared = semilla(pregunta)
    create_explorador_flow().run(shared)
    resumen = shared.get("resumen") or "(el explorador no devolvió resumen)"
    return f"{resumen}\n\n[explorador: usó {shared['rondas']} de {MAX_PASOS_EXPLORADOR} rondas]"
