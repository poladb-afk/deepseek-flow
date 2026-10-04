import importlib
import sys

from flow import create_agent_flow
from utils.fs_tools import allowed_roots

WELCOME = "Agente con DeepSeek V4.1 Flash — pregunta sobre tus archivos ('salir' o Ctrl+C para terminar)."


def system_prompt():
    roots = "\n".join(f"- {r}" for r in allowed_roots())
    return f"""Agente de exploración de archivos.

Directorios permitidos:
{roots}"""


SUBCOMANDOS = {
    "informe": "informe",
    "juez": "juez",
    "auditoria": "auditoria",
    "index": "rag",
    "debate": "debate",
    "mcp-server": "mcp_server",
    "research": "research",
    "supervisor": "supervisor",
    "grafo": "utils.viz",
}


def main():
    from utils.tracing import activar

    activar()
    if len(sys.argv) > 1 and sys.argv[1] in SUBCOMANDOS:
        modulo = importlib.import_module(SUBCOMANDOS[sys.argv[1]])
        modulo.main(sys.argv[2:])
        return
    shared = {
        "messages": [{"role": "system", "content": system_prompt()}],
        "tool_rounds": 0,
    }
    print(WELCOME)
    try:
        create_agent_flow().run(shared)
    except KeyboardInterrupt:
        print("\n¡Chao! 👋")


if __name__ == "__main__":
    main()
