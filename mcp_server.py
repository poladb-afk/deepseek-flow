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
import sys

from nodes import MODULE_IMPLS, TOOLS
from utils import fs_tools
from utils.call_llm import _setting

DEFAULT_EXPOSE = "list_files,read_file,search_files,rag_search,rag_index,answer_verified"


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
        **MODULE_IMPLS,
    }
    descripciones = {t["function"]["name"]: t["function"]["description"] for t in TOOLS}

    permitir = {c.strip() for c in (args.expose or _setting("MCP_EXPOSE", DEFAULT_EXPOSE)).split(",") if c.strip()}
    server = FastMCP("deepseek-flow")
    expuestas = []
    for nombre in permitir:
        fn = impls.get(nombre)
        if fn is None:
            continue
        server.tool(fn, name=nombre, description=descripciones.get(nombre, ""))
        expuestas.append(nombre)

    # stdout es el canal del protocolo MCP: todo aviso va a stderr
    print(f"[mcp-server] exponiendo {len(expuestas)}: {', '.join(sorted(expuestas))}",
          file=sys.stderr, flush=True)
    server.run()


if __name__ == "__main__":
    main()
