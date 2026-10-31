import contextlib
import importlib
import sys
from pathlib import Path

from flow import create_agent_flow
from modules import ganchos
from utils.call_llm import _setting
from utils.costos import costo_desglose
from utils.fs_tools import allowed_roots

WELCOME = "Agente con DeepSeek V4.1 Flash — pedidos sobre tus archivos y tu código ('salir' o Ctrl+C para terminar)."


# Directiva de FORMA del código que el harness genera. Es una palanca medida:
# en "Show and Tell" (arXiv 2511.13972) las instrucciones explícitas de
# concisión bajaron 56–70% los tokens del código y persistieron en el turno
# siguiente; un pedido genérico de "mejorar" inflaba todo. El A/B propio está
# en banco/probes/forma_codigo.py y la bitácora (exp/51). Va siempre: el setting
# que la apagaba era el brazo de ese A/B, cerrado (X112).
DIRECTIVA_FORMA = (
    "Cuando escribas o edites código, escribí el mínimo que funciona y con la "
    "forma del repo: sin defensas ni docstrings que el pedido no exija, sin "
    "abstracciones especulativas, sin comentarios que narren lo que el código "
    "ya dice. Validación, seguridad y accesibilidad no se recortan."
)


# Directiva de exp/78 (auditoría de seguridad): checklist que empuja a buscar
# controles por AUSENCIA — el hueco medido en exp/77 (R1 sort --compress-program,
# R3 tail -f, R2 evasión por -o). Opción del operador: PROMPT_AUDITORIA=1 (default 0).
DIRECTIVA_AUDITORIA = (
    "Cuando audites código buscando bugs de seguridad, además de leer lo que hay, "
    "preguntate qué FALTA: listas de flags o denylists incompletas, normalización de "
    "envoltorios (sudo/nice/timeout/env), validaciones que comparan strings sin "
    "normalizar (mayúsculas, flags reordenados, /bin/rm), redirecciones y descriptores, "
    "y rutas sin canonicalizar. Enumerá las familias de riesgo del archivo (ejecución "
    "de programas, escritura de archivos, descriptores, envoltorios, opciones que toman "
    "valores) y verificá que cada una tenga su control; si un control depende de una "
    "lista, revisá si la lista está completa. Un hardening ausente es un hallazgo de "
    "seguridad: reportalo con archivo:línea, qué falta, cómo se explota y el fix. No "
    "edites archivos."
)


def system_prompt():
    """El prompt del chat: la directiva de forma va siempre (exp/51); el
    checklist de auditoría de exp/78 es opción del operador
    (PROMPT_AUDITORIA=1, default 0)."""
    # REGLA de estabilidad: el prefijo debe ser byte-estable durante la
    # sesión para no romper el KV-cache (DeepSeek Harness lo midió: una
    # sección dinámica recalcularía ~99% del contexto por turno). Nada
    # variable —fecha, hora, contadores— entra jamás acá. La memoria entre
    # sesiones NO se inyecta: es una biblioteca que el agente consulta por
    # tools cuando el pedido lo justifica.
    # F (X85): sin "acotá el alcance" (el tope de rondas ya lo gobierna; medido
    # sin pérdida de calidad). La directiva de citas se quedó: sin ella la
    # calidad bajó aunque VerificarCitas corrija después.
    incluir_auditoria = _setting("PROMPT_AUDITORIA", "0") != "0"
    roots = "\n".join(f"- {r}" for r in allowed_roots())
    # el CWD del proceso: sin esto, "¿en qué carpeta estamos?" se responde
    # adivinando la raíz permitida (medido en producción)
    cwd = Path.cwd()
    auditoria = f"\n\n{DIRECTIVA_AUDITORIA}" if incluir_auditoria else ""
    return f"""Agente de resolución de pedidos con tools disponibles.

Trabajás en {cwd} y sus subdirectorios.

Alcance máximo de las tools de archivos:
{roots}

Respondé en el idioma de cada pedido (español o inglés).

Cuando cites archivo:línea, verificá esa línea en el archivo antes de afirmarla; si no la verificaste, decila como no verificada. Citá siempre como ruta/archivo.py:línea (ruta relativa al repo, sin "líneas ~X").

Para leer, listar o buscar archivos usá read_file, list_files o search_files; no uses cat, grep ni find por run_command.

{DIRECTIVA_FORMA}{auditoria}"""


SUBCOMANDOS = {
    "informe": "informe",
    "juez": "juez",
    "juez_lote": "juez_lote",
    "fable_judge": "fable_judge",
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
    "delegar": "delegar",
    "webhook": "utils.hitl_web",
}


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
    shared = {"messages": [{"role": "system", "content": system_prompt()}]}
    print(WELCOME)
    for gancho in ganchos("al_arrancar"):
        gancho(shared)
    try:
        create_agent_flow().run(shared)
    except KeyboardInterrupt:
        print("\n¡Chao! 👋")
    finally:
        # antes del reporte: el resumen de sesión es una llamada y se cobra
        for gancho in reversed(ganchos("al_salir")):
            gancho(shared)
        _reporte_tokens(shared)


def _miles(n):
    """Separador de miles a la es-AR: 61.234 (mismo formato que exp/89)."""
    return f"{n:,}".replace(",", ".")


def _dinero(usd):
    """USD con coma decimal y `~`: es un estimado off-peak, no una factura."""
    return f"~${usd:.4f}".replace(".", ",")


def _linea_preguntas(preguntas, tabla):
    """La línea de costo por pregunta: tokens y dinero, en orden de llegada."""
    partes = []
    for desglose in preguntas:
        tokens = sum(f["prompt"] + f["completion"] for f in desglose.values())
        usd, sin_tarifa = costo_desglose(desglose, tabla)
        if sin_tarifa:
            partes.append(f"{_miles(tokens)} (sin tarifa)")
        else:
            partes.append(f"{_miles(tokens)} ({_dinero(usd)})")
    return "[tokens] por pregunta: " + " / ".join(partes)


def _reporte_tokens(shared):
    """exp/89: el uso de tokens de la sesión, al salir (bookkeeping
    best-effort: nunca corta la salida). La métrica first-class que faltaba
    — costo_traza medía segundos. exp/90: además el costo estimado en
    dinero (off-peak) y el desglose por pregunta."""
    with contextlib.suppress(Exception):
        from utils.call_llm import _setting, desglose_de_sesion, uso_de_sesion
        from utils.costos import delta_desglose, precios

        uso = uso_de_sesion()
        if not uso["llamadas"]:
            return
        desglose = desglose_de_sesion()
        # la última pregunta nunca vuelve a GetQuestion: se cierra acá.
        # El resumen de memoria corre DESPUÉS y fuera de toda pregunta:
        # cuenta en el total de sesión y en ninguna pregunta (declarado).
        inicio = (shared.get("turno") or {}).get("uso_inicio")
        if inicio is not None:
            shared.setdefault("tokens_por_pregunta", []).append(
                delta_desglose(inicio, desglose))
        tabla = precios(_setting("PRECIO_TOKENS"))
        total, sin_tarifa = costo_desglose(desglose, tabla)
        base = (f"[tokens] sesión: {uso['llamadas']} llamadas — "
                f"{_miles(uso['prompt'])} prompt + "
                f"{_miles(uso['completion'])} completion")
        if sin_tarifa:
            print(f"{base} (sin tarifa: {', '.join(sin_tarifa)})")
        else:
            print(f"{base} ({_dinero(total)})")
        preguntas = shared.get("tokens_por_pregunta") or []
        if preguntas:
            print(_linea_preguntas(preguntas, tabla))


if __name__ == "__main__":
    main()
