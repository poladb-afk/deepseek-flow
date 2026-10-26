"""Explorador aislado (exp/97): sub-agente de SÓLO LECTURA con contexto fresco.

Desde H2 (PR 1) es una instancia del kernel (`utils/kernel.py`), no un loop
propio: `agente()` le da contexto fresco por construcción (system + pregunta,
nada del padre), el cierre por presupuesto es una arista del grafo y sus
lecturas corren en paralelo. Lo que queda acá es lo que lo hace explorador:

- OWASP LLM06 (excessive agency): el toolset es una WHITELIST de nombres
  (`PERMITIDAS`) — `run_command`, write_file y edit_file no existen para él.
- Presupuesto propio (MAX_PASOS_EXPLORADOR, default 3): sus rondas no
  consumen las del padre (supervisor v2 todavía no comparte ledger: PR 2) y
  el retorno declara "usó N de M".
"""
from pathlib import Path

from utils.call_llm import _entero, call_llm_agent
from utils.kernel import Ctx, Ledger, agente, correr, desde_fs

MAX_PASOS_EXPLORADOR = _entero("MAX_PASOS_EXPLORADOR", 3)

# El permiso es el mapa, no la convención: sólo estos nombres y nada más.
PERMITIDAS = ("read_file", "list_files", "search_files")
TOOLS = [desde_fs(nombre) for nombre in PERMITIDAS]

NOMBRE_TOOL = "explorar"
DESCRIPCION = ("Delegá una investigación de solo lectura a un sub-agente con contexto FRESCO: "
               "lee, lista y busca por su cuenta y te devuelve un resumen con citas archivo:línea. "
               "Su historial no consume tu contexto ni tus rondas.")


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


# El explorador como Tool del kernel (con SU system: el que arma con la
# pregunta) y su esquema para el catálogo del supervisor (forma OpenAI).
AGENTE = agente(NOMBRE_TOOL, DESCRIPCION, system_prompt, TOOLS, parametro="pregunta")
TOOL_EXPLORAR = AGENTE.esquema


def explorar(pregunta):
    """Corre el explorador y devuelve SOLO el resumen como texto, declarando
    el presupuesto usado ("usó N de M rondas")."""
    ledger = Ledger(MAX_PASOS_EXPLORADOR)
    resumen, _ = correr(system_prompt(pregunta), pregunta, TOOLS, Ctx(call_llm_agent_vivo, ledger))
    usadas = MAX_PASOS_EXPLORADOR - ledger.rondas
    return f"{resumen or '(el explorador no devolvió resumen)'}\n\n[explorador: usó {usadas} de {MAX_PASOS_EXPLORADOR} rondas]"


def call_llm_agent_vivo(mensajes, tools=None):
    """El LLM se resuelve en cada llamada (los tests lo parchean en el módulo)."""
    return call_llm_agent(mensajes, tools=tools)
