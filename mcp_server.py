"""Servidor MCP: expone las capacidades del chat a OTROS agentes.

Dirección inversa del módulo mcp: cualquier cliente MCP (otro agente,
bmo, un IDE) puede consumir nuestro action space por stdio. El allowlist
vive en MCP_EXPOSE (.env, separado por comas); el default excluye lo que
exige terminal (write_file y su aprobación HITL) y los pipelines largos.

Uso:
    python3 main.py mcp-server
    # y desde cualquier cliente: MCP_SERVERS=deepseek::python3 .../main.py mcp-server
"""
import argparse
import json
import sys

from nodes import MODULE_IMPLS, TOOLS
from utils import fs_tools
from utils.call_llm import _setting
from utils.laya import juicio

DEFAULT_EXPOSE = ("list_files,read_file,search_files,rag_search,rag_index,"
                  "answer_verified,juicio_laya")

# El juicio local NO es una tool del CHAT (no suma al action space del modelo):
# el producto es ofrecerlo a otros agentes MCP, que sí saben pedirlo.
DESCRIPCION_JUICIO = (
    "Juicio tipado y calibrado LOCAL con Laya: elegí UNA etiqueta para `estado` "
    "según `instrucciones` y los criterios de cada opción (`opciones` es un "
    "objeto JSON {etiqueta: criterio}, mínimo 2). Devuelve JSON "
    "{juicio, confianza, probabilidades, modelo}. Sin checkpoint (LAYA_MODEL) "
    "devuelve ERROR como texto: nunca rompe al cliente."
)


def juicio_laya(estado: str, instrucciones: str, opciones: dict, setting: str = "") -> str:
    """Tool MCP: envuelve utils.laya.juicio y responde TEXTO JSON (contrato de
    las tools del harness: strings, nunca dicts)."""
    try:
        resultado = juicio(estado, instrucciones, opciones, setting or "LAYA_MODEL")
    except ValueError as e:
        return f"ERROR: {e}"
    if resultado is None:
        return "ERROR: Laya no disponible o respuesta no usable (¿LAYA_MODEL?)"
    resultado["modelo"] = _setting(setting or "LAYA_MODEL", "?")
    return json.dumps(resultado, ensure_ascii=False)


def elegir_exposicion(permitir, impls, descripciones):
    """(expuestas, aviso). Devuelve las tools a exponer y un aviso de
    nombres problemáticos del allowlist: sin implementación (typo en
    MCP_EXPOSE) o sin descripción en TOOLS. Degradación, no crash."""
    expuestas, faltantes, sin_desc = [], [], []
    for nombre in sorted(permitir):
        fn = impls.get(nombre)
        if fn is None:
            faltantes.append(nombre)
            continue
        if not descripciones.get(nombre):
            sin_desc.append(nombre)
        expuestas.append(nombre)
    aviso = None
    if faltantes or sin_desc:
        partes = []
        if faltantes:
            partes.append("sin implementación (¿typo en MCP_EXPOSE?): " + ", ".join(faltantes))
        if sin_desc:
            partes.append("sin descripción en TOOLS: " + ", ".join(sin_desc))
        aviso = "[mcp-server] allowlist con problemas — " + "; ".join(partes)
    return expuestas, aviso


def envolver(nombre, fn, impls):
    """La función que se registra en FastMCP: misma firma que la implementación
    (FastMCP arma el schema desde ahí) pero el cuerpo despacha por
    run_tool_call — el ÚNICO camino con HOOKS_PRE (denylist) y HOOKS_POST.
    Antes se registraba la implementación cruda y un run_command expuesto
    salteaba la denylist."""
    import functools
    import inspect
    import json

    @functools.wraps(fn)
    def envuelta(**kwargs):
        tc = {"id": f"mcp-{nombre}", "type": "function",
              "function": {"name": nombre, "arguments": json.dumps(kwargs, ensure_ascii=False)}}
        return fs_tools.run_tool_call(tc, impls)["content"]

    envuelta.__signature__ = inspect.signature(fn)
    return envuelta


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mcp-server", description="Sirve el action space del chat vía MCP (stdio)"
    )
    parser.add_argument("--expose", default=None,
                        help=f"capabilities a exponer, separadas por coma (default: {DEFAULT_EXPOSE})")
    args = parser.parse_args(argv)

    from fastmcp import FastMCP

    impls = {
        "list_files": fs_tools.list_files,
        "read_file": fs_tools.read_file,
        "search_files": fs_tools.search_files,
        "juicio_laya": juicio_laya,
        **MODULE_IMPLS,
    }
    descripciones = {t["function"]["name"]: t["function"]["description"] for t in TOOLS}
    descripciones["juicio_laya"] = DESCRIPCION_JUICIO

    permitir = {c.strip() for c in (args.expose or _setting("MCP_EXPOSE", DEFAULT_EXPOSE)).split(",") if c.strip()}
    expuestas, aviso = elegir_exposicion(permitir, impls, descripciones)
    server = FastMCP("deepseek-flow")
    for nombre in expuestas:
        server.tool(envolver(nombre, impls[nombre], impls), name=nombre,
                    description=descripciones.get(nombre, ""))

    # stdout es el canal del protocolo MCP: todo aviso va a stderr
    if aviso:
        print(aviso, file=sys.stderr, flush=True)
    print(f"[mcp-server] exponiendo {len(expuestas)}: {', '.join(sorted(expuestas))}",
          file=sys.stderr, flush=True)
    server.run()


if __name__ == "__main__":
    main()
