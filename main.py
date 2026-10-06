import importlib
import sys
from pathlib import Path

from flow import create_agent_flow
from utils.fs_tools import allowed_roots

WELCOME = "Agente con DeepSeek V4.1 Flash — pedidos sobre tus archivos y tu código ('salir' o Ctrl+C para terminar)."


def system_prompt():
    # REGLA de estabilidad: el prefijo debe ser byte-estable durante la
    # sesión para no romper el KV-cache (DeepSeek Harness lo midió: una
    # sección dinámica recalcularía ~99% del contexto por turno). Nada
    # variable —fecha, hora, contadores— entra jamás acá. La memoria entre
    # sesiones NO se inyecta: es una biblioteca que el agente consulta por
    # tools cuando el pedido lo justifica.
    roots = "\n".join(f"- {r}" for r in allowed_roots())
    # el CWD del proceso: sin esto, "¿en qué carpeta estamos?" se responde
    # adivinando la raíz permitida (medido en producción)
    cwd = Path.cwd()
    return f"""Agente de resolución de pedidos con tools disponibles.

Trabajás en {cwd} y sus subdirectorios.

Alcance máximo de las tools de archivos:
{roots}

Respondé en el idioma de cada pedido (español o inglés)."""


SUBCOMANDOS = {
    "informe": "informe",
    "juez": "juez",
    "juez_lote": "juez_lote",
    "auditoria": "auditoria",
    "index": "rag",
    "debate": "debate",
    "mcp-server": "mcp_server",
    "research": "research",
    "supervisor": "supervisor",
    "effective_n": "effective_n",
    "heartbeat": "heartbeat",
    "visor": "visor",
    "grafo": "utils.viz",
    "evals": "evals",
}


def resumen_de_sesion(shared):
    """Resumen automático al salir (bookkeeping, sin HITL): UNA sola llamada
    a call_llm comprime la conversación y la guarda como
    memoria/sesion_FECHA.md. Con MEMORIA=0 no hace nada; con menos de 2
    preguntas de usuario tampoco. Si la llamada falla, se sale igual sin
    romper nada (es bookkeeping, no una acción nueva)."""
    from utils.call_llm import _setting

    # ninguna ruta es muda: un episodio de resumen silenciosamente ausente
    # no se pudo reproducir (4 intentos) y sin prints es indecidible cuál fue
    if _setting("MEMORIA", "1") != "1":
        print("\n[memoria] desactivada (MEMORIA=0): sin resumen de sesión")
        return
    mensajes = shared.get("messages", [])
    n_users = sum(1 for m in mensajes if m.get("role") == "user")
    if n_users < 2:
        print(f"\n[memoria] sesión corta ({n_users} pregunta): sin resumen")
        return
    try:
        from modules.memoria import guardar_resumen_sesion
        from utils.call_llm import call_llm

        lineas = []
        for m in mensajes:
            rol = m.get("role")
            if rol == "system":
                continue
            contenido = m.get("content")
            if not contenido and m.get("tool_calls"):
                contenido = "(herramientas) " + ", ".join(
                    tc["function"]["name"] for tc in m["tool_calls"])
            if contenido:
                lineas.append(f"{rol}: {contenido}")
        transcript = "\n".join(lineas)
        resumen = call_llm(
            "Resumí esta conversación entre un usuario y un agente, en español, "
            "en pocas líneas y para consulta futura. Incluí: el tema en una línea; "
            "los pedidos del usuario y sus resultados; las decisiones tomadas; los "
            "hallazgos; y los archivos tocados. No repitas saludos ni el texto crudo.\n\n"
            f"--- Conversación ---\n{transcript}"
        )
        destino = guardar_resumen_sesion(resumen)
        if destino:
            print(f"\n[memoria] resumen de sesión guardado en {destino}")
        else:
            print("\n[memoria] el resumen no se pudo escribir (OSError en memoria/)")
    except Exception as e:  # noqa: BLE001  (bookkeeping: nunca corta la salida)
        print(f"\n[memoria] no se pudo guardar el resumen de la sesión ({type(e).__name__})")


def catalogo_memoria():
    """Muestra el CATÁLOGO de la biblioteca de memoria al arrancar (mesa 8):
    qué notas hay, SIN inyectar su contenido al contexto — el arranque vacío
    es regla (la memoria es una biblioteca que el agente consulta, no contexto
    automático). Con MEMORIA=0 o si la biblioteca está vacía, no imprime nada.
    Nunca rompe el arranque (best-effort)."""
    from utils.call_llm import _setting

    if _setting("MEMORIA", "1") != "1":
        return
    try:
        from modules.memoria import _archivos_md

        archivos = _archivos_md()
        if not archivos:
            return
        print(f"\n[memoria] biblioteca: {len(archivos)} notas (consultá con memory_search)")
        for p in archivos:
            print(f"  - {p.name}")
    except Exception:  # noqa: BLE001 (mostrar el catálogo nunca corta el arranque)
        pass


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
    catalogo_memoria()
    try:
        create_agent_flow().run(shared)
    except KeyboardInterrupt:
        print("\n¡Chao! 👋")
    finally:
        resumen_de_sesion(shared)


if __name__ == "__main__":
    main()