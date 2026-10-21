import importlib
import sys
from pathlib import Path

from flow import create_agent_flow
from utils.fs_tools import allowed_roots

WELCOME = "Agente con DeepSeek V4.1 Flash — pedidos sobre tus archivos y tu código ('salir' o Ctrl+C para terminar)."


# Directiva de FORMA del código que el harness genera. Es una palanca medida:
# en "Show and Tell" (arXiv 2511.13972) las instrucciones explícitas de
# concisión bajaron 56–70% los tokens del código y persistieron en el turno
# siguiente; un pedido genérico de "mejorar" inflaba todo. El A/B propio está
# en banco/probes/forma_codigo.py y la bitácora (exp/51).
DIRECTIVA_FORMA = (
    "Cuando escribas o edites código, escribí el mínimo que funciona y con la "
    "forma del repo: sin defensas ni docstrings que el pedido no exija, sin "
    "abstracciones especulativas, sin comentarios que narren lo que el código "
    "ya dice. Validación, seguridad y accesibilidad no se recortan."
)


# Directiva de exp/72 F0 (brazo "prosa"): el método de fable como PROSA en el
# system prompt, destilado de Sahir619/fable-method @9924067 (MIT). No enforza
# nada (los gates/nodos son F2); sirve para medir si la prosa sola transfiere.
# Default 0: el chat de producción no cambia hasta que haya medición propia.
DIRECTIVA_FABLE = (
    "Antes de actuar, clasificá el pedido: pregunta/assessment (solo hallazgos "
    "y una recomendación, no edites), tarea (cambio verificado) o plan-first "
    "(alcance ambiguo o acción irreversible: plan y esperá aprobación). Definí "
    'en una línea qué significa "hecho" y cómo se verifica. Evidencia de fuentes '
    "primarias (leé el archivo real; no cites de memoria); dos rondas de búsqueda "
    "alcanzan. Una sola recomendación. Antes de cambiar comportamiento escribí "
    "`INTENT: el código hace X; el check espera Y; la spec dice Z`; si X/Y/Z no "
    "coinciden, el desacuerdo es el hallazgo: no edites. Para acciones outward "
    "(deploy, push, publicar, borrar datos compartidos) escribí `AUTH: el "
    'usuario dijo "..."`; sin cita, no actúes y dejala como próximo paso. Cambio '
    "mínimo y quirúrgico. Verificá observando (correr, no inferir) el criterio "
    "de hecho y el sistema alrededor; si arreglaste un defecto, buscá el mismo "
    "patrón en todo el repo y escribí `TWINS: busqué <patrón> — encontré N "
    "sitios: <archivos o none>`. Máximo 3 ciclos de fix-verify; si no, parás y "
    "reportás lo intentado. Reportá outcome-first, en lenguaje llano, con "
    "caveats honestos, y `PENDING: <acción> — esperando tu autorización` si un "
    "follow-up prescripto no se hizo."
)


def system_prompt(incluir_forma: bool | None = None, incluir_fable: bool | None = None):
    """El prompt del chat; `incluir_forma=None` respeta el setting PROMPT_FORMA.

    PROMPT_FORMA=0 quita la directiva de forma (palanca del A/B exp/51 en el
    chat real vía banco; default 1). PROMPT_FABLE=1 agrega la directiva de
    exp/72 (brazo prosa del A/B; default 0: producción sin cambios)."""
    # REGLA de estabilidad: el prefijo debe ser byte-estable durante la
    # sesión para no romper el KV-cache (DeepSeek Harness lo midió: una
    # sección dinámica recalcularía ~99% del contexto por turno). Nada
    # variable —fecha, hora, contadores— entra jamás acá. La memoria entre
    # sesiones NO se inyecta: es una biblioteca que el agente consulta por
    # tools cuando el pedido lo justifica.
    from utils.call_llm import _setting

    if incluir_forma is None:
        incluir_forma = _setting("PROMPT_FORMA", "1") != "0"
    if incluir_fable is None:
        incluir_fable = _setting("PROMPT_FABLE", "0") != "0"
    roots = "\n".join(f"- {r}" for r in allowed_roots())
    # el CWD del proceso: sin esto, "¿en qué carpeta estamos?" se responde
    # adivinando la raíz permitida (medido en producción)
    cwd = Path.cwd()
    forma = f"\n\n{DIRECTIVA_FORMA}" if incluir_forma else ""
    fable = f"\n\n{DIRECTIVA_FABLE}" if incluir_fable else ""
    return f"""Agente de resolución de pedidos con tools disponibles.

Trabajás en {cwd} y sus subdirectorios.

Alcance máximo de las tools de archivos:
{roots}

Respondé en el idioma de cada pedido (español o inglés).

Si el pedido es una auditoría o análisis amplio del repo, acotá el alcance y respondé con hallazgos y límites; no intentes leer todo.

Cuando cites archivo:línea, verificá esa línea en el archivo antes de afirmarla; si no la verificaste, decila como no verificada. Citá siempre como ruta/archivo.py:línea (ruta relativa al repo, sin "líneas ~X").

Para leer, listar o buscar archivos usá read_file, list_files o search_files; no uses cat, grep ni find por run_command.{forma}{fable}"""


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
    "bench_juez": "bench_juez",
    "replay": "replay",
    "ratchet": "ratchet",
    "resume": "resume",
    "webhook": "utils.hitl_web",
}


def _preguntas_reales(mensajes):
    """Cuenta los user-role que son PREGUNTAS: excluye los mensajes sintéticos
    de prefetch y el marcador de compacción (medido en vivo: con 1 pregunta +
    1 pre-fetch el resumen se disparaba igual, contradiciendo el docstring)."""
    from utils.compaccion import PREFIJO_COMPACCION
    from utils.prefetch import PREFIJO_PREFETCH
    from utils.skills import PREFIJO_SKILL

    return sum(
        1 for m in mensajes
        if m.get("role") == "user"
        and not str(m.get("content", "")).startswith(
            (PREFIJO_PREFETCH, PREFIJO_COMPACCION, PREFIJO_SKILL))
    )


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
    n_users = _preguntas_reales(mensajes)
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


CATALOGO_MAX = 8


def catalogo_memoria():
    """Muestra el CATÁLOGO de la biblioteca de memoria al arrancar (mesa 8):
    cuántas notas hay y las más recientes, SIN inyectar su contenido al
    contexto — el arranque vacío es regla (la memoria es una biblioteca que el
    agente consulta, no contexto automático). Con MEMORIA=0 o si la biblioteca
    está vacía, no imprime nada. Nunca rompe el arranque (best-effort)."""
    from utils.call_llm import _setting

    if _setting("MEMORIA", "1") != "1":
        return
    try:
        from modules.memoria import _archivos_md

        archivos = _archivos_md()
        if not archivos:
            return
        # lista completa = spam de arranque (medido: 229 de 234 notas eran
        # respaldos de compacción y tapaban las útiles): van solo las últimas.
        # mtime desempata a favor de lo recién guardado; el nombre (que trae la
        # fecha) ordena determinísticamente cuando los mtime empatan.
        recientes = sorted(archivos, key=lambda p: (p.stat().st_mtime, p.name),
                           reverse=True)[:CATALOGO_MAX]
        print(f"\n[memoria] biblioteca: {len(archivos)} notas; "
              f"las {len(recientes)} más recientes:")
        for p in recientes:
            print(f"  - {p.name}")
        print("  (consultá cualquier nota con memory_search)")
    except Exception:  # noqa: BLE001 (mostrar el catálogo nunca corta el arranque)
        pass


def main():
    from utils.tracing import activar

    activar()
    if len(sys.argv) > 1 and sys.argv[1] in SUBCOMANDOS:
        modulo = importlib.import_module(SUBCOMANDOS[sys.argv[1]])
        # los subcomandos devuelven un código de salida (o un valor no-int, que
        # se ignora: informes, rutas...). `resume` lo usa: exit 1 en error.
        codigo = modulo.main(sys.argv[2:])
        if isinstance(codigo, int) and not isinstance(codigo, bool):
            sys.exit(codigo)
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
