"""Módulo `mcp`: el agente habla el Model Context Protocol.

mcp_tools descubre las herramientas de los servidores configurados;
mcp_call las ejecuta. Con esto el action space deja de ser cerrado: cualquier
servidor MCP del ecosistema se agrega con una línea en .env, sin escribir
módulos. (La dirección inversa —exponer NUESTRAS capacidades como servidor
MCP— vive en mcp_server.py / `main.py mcp-server`.)"""
from utils.mcp_client import mcp_call, mcp_tools

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "mcp_tools",
            "description": "Lista los servidores MCP configurados y sus herramientas (con el esquema de argumentos de cada una). Úsalo antes de mcp_call para descubrir qué hay disponible.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mcp_call",
            "description": "Ejecuta una herramienta de un servidor MCP externo. Consulta mcp_tools primero para conocer nombres y argumentos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "servidor": {"type": "string", "description": "Nombre del servidor MCP configurado"},
                    "herramienta": {"type": "string", "description": "Nombre de la herramienta en ese servidor"},
                    "argumentos": {"type": "object", "description": "Argumentos según el esquema de la herramienta"},
                },
                "required": ["servidor", "herramienta"],
            },
        },
    },
]


IMPL = {"mcp_tools": mcp_tools, "mcp_call": mcp_call}
