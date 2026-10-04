"""Cliente MCP (Model Context Protocol) vía fastmcp.

Servidores configurados en MCP_SERVERS (.env o entorno), formato:
    nombre::comando argumentos ; nombre2::otro comando
Ejemplo:
    MCP_SERVERS=matematica::python3 /ruta/a/simple_server.py
Cada operación abre una sesión stdio nueva: conectar → operar → cerrar.
Sin servidores configurados, las herramientas lo dicen (el agente se
autocorrige pidiendo la configuración).
"""
import asyncio
import json
import shlex

from utils.call_llm import _setting


def servidores():
    texto = _setting("MCP_SERVERS", "")
    servs = {}
    for bloque in texto.split(";"):
        bloque = bloque.strip()
        if not bloque or "::" not in bloque:
            continue
        nombre, comando = bloque.split("::", 1)
        servs[nombre.strip()] = shlex.split(comando.strip())
    return servs


def _texto(result):
    data = getattr(result, "data", None)
    if data is not None and not isinstance(data, list):
        return str(data)
    partes = [getattr(b, "text", str(b)) for b in getattr(result, "content", None) or []]
    return "\n".join(partes) or str(result)


async def _listar(comando):
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    async with Client(StdioTransport(command=comando[0], args=comando[1:])) as cliente:
        herramientas = await cliente.list_tools()
        return [
            {
                "name": t.name,
                "description": (t.description or "").strip(),
                "esquema": t.inputSchema,
            }
            for t in herramientas
        ]


async def _llamar(comando, herramienta, argumentos):
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    async with Client(StdioTransport(command=comando[0], args=comando[1:])) as cliente:
        resultado = await cliente.call_tool(herramienta, argumentos)
        return _texto(resultado)


def mcp_tools():
    servs = servidores()
    if not servs:
        return (
            "No hay servidores MCP configurados. Define en .env:\n"
            "  MCP_SERVERS=nombre::comando argumentos ; otro::comando2"
        )
    lineas = [f"{len(servs)} servidor(es) MCP configurados:"]
    for nombre, comando in servs.items():
        try:
            herramientas = asyncio.run(_listar(comando))
        except Exception as e:
            lineas.append(f"\n[{nombre}] ERROR ({type(e).__name__}): {e}")
            continue
        lineas.append(f"\n[{nombre}] ({len(herramientas)} herramientas)")
        for h in herramientas:
            desc = f" — {h['description'][:120]}" if h["description"] else ""
            lineas.append(f"  - {h['name']}{desc}")
            lineas.append(f"    args: {json.dumps(h['esquema'], ensure_ascii=False)[:300]}")
    return "\n".join(lineas)


def mcp_call(servidor, herramienta, argumentos=None):
    servs = servidores()
    if servidor not in servs:
        return f"ERROR: servidor '{servidor}' no configurado. Disponibles: {list(servs) or 'ninguno'}"
    if isinstance(argumentos, str):
        try:
            argumentos = json.loads(argumentos or "{}")
        except json.JSONDecodeError as e:
            return f"ERROR: argumentos no son JSON válido: {e}"
    try:
        return asyncio.run(_llamar(servs[servidor], herramienta, argumentos or {}))
    except Exception as e:
        return f"ERROR ({type(e).__name__}): {e}"
