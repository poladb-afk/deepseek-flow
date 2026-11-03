"""Deep research como composición del kernel (exp/108): un agente más.

Antes: un grafo propio de tres nodos (planificar → buscar por lote →
sintetizar) con el loop de cobertura como arista y tres prompts fijos. Ahora
el mismo loop del
chat (S9b A′) y del supervisor con otra tool y otro prompt (`kernel.correr`):
el modelo planifica, busca, juzga la cobertura y escribe el informe, y las
leyes medidas quedan por construcción:

- **L8, el informe siempre**: agotado el saldo, la próxima llamada va SIN
  tools y el modelo cierra con lo que tiene (la arista `cerrar` del kernel).
- **exp/28, el tope lo aplica el código**: el modelo puede pedir todas las
  búsquedas que quiera; a la N+1 del run la tool responde con el tope como
  ERROR (error-como-información: el modelo se corrige y cierra).
- **exp/37, el fallo de una búsqueda es dato**: `search_web` devuelve su
  error como texto; una tool que devuelve texto no dispara retry de ronda.

La interfaz no cambia: `investigar(tema, salida) -> ruta` (la tool
`deep_research` del chat la usa) y el subcomando de main.

Uso: python3 main.py research "tema" [--salida research.md]
"""
import argparse
import json

from modules.websearch import TOOLS as TOOLS_WEB
from modules.websearch import run_search_web
from utils.call_llm import call_llm_agent
from utils.fs_tools import escribir_salida
from utils.kernel import Ctx, Ledger, Tool, loop, semilla

# El tope del run: 3 consultas × 3 ciclos, el máximo del flujo viejo. El
# código lo aplica (exp/28: con 20 consultas del modelo se buscaban las 20).
MAX_BUSQUEDAS = 9
RESULTADOS_POR_QUERY = 4
# Headroom de rondas de tools sobre las 9 búsquedas posibles (el modelo puede
# buscar de a una o agrupar); el techo real de cómputo es MAX_BUSQUEDAS.
SALDO = 12


def system(tema):
    """El prompt del agente de investigación (tarea-primero, estilo casa)."""
    return f"""Sos un agente de investigación. Tema: "{tema}".

Método: planificá hasta 3 consultas diversas y complementarias; buscálas con
search_web; evaluá si el material cubre las facetas del tema (no una sola
cara); si hay huecos, buscá lo que falta; después escribí el informe.

Presupuesto (por construcción, no negociable): {MAX_BUSQUEDAS} búsquedas en
el run y un saldo de rondas de tools; agotado el saldo, tu próxima llamada
va sin tools y tenés que cerrar el informe con el material que tengas.

Informe final: markdown en español, conciso, una sección por faceta, con las
URLs de las fuentes. No inventes URLs: citá solo las que viste en los
resultados de search_web. Cuando el material alcance (o el presupuesto se
acabe), respondé SOLO el informe, sin llamar más herramientas."""


def tool_search():
    """`search_web` del módulo (una sola definición del contrato) con el tope
    de exp/28 alrededor: el código corta y el texto del error le dice al
    modelo cómo seguir."""
    esquema = next(t for t in TOOLS_WEB if t["function"]["name"] == "search_web")
    estado = {"busquedas": 0}

    def correr_tool(llamada, _ctx):
        if estado["busquedas"] >= MAX_BUSQUEDAS:
            return (f"ERROR: tope de {MAX_BUSQUEDAS} búsquedas del run alcanzado; "
                    "escribí el informe con el material reunido")
        try:
            args = json.loads(llamada["function"].get("arguments") or "{}")
        except ValueError:
            return "ERROR: argumentos ilegibles (se espera JSON con `consulta`)"
        consulta = str(args.get("consulta", "")).strip()
        if not consulta:
            return "ERROR: falta `consulta`"
        estado["busquedas"] += 1
        print(f"  🌐 buscando ({estado['busquedas']}/{MAX_BUSQUEDAS}): {consulta}")
        return run_search_web(consulta, RESULTADOS_POR_QUERY)

    return Tool("search_web", esquema, correr_tool)


def grafo():
    """El loop del agente (el mismo `kernel.loop` del chat y el supervisor):
    `main.py grafo` lo dibuja y `investigar` lo corre. Un grafo NUEVO por
    llamada — cada run lleva su propio saldo y su propio contador de tope."""
    return loop(Ctx(call_llm_agent, Ledger(SALDO)), [tool_search()], wait=5)


def investigar(tema, salida="salidas/research.md"):
    s = semilla(system(tema), f"Investigá: {tema}")
    grafo().run(s)
    respuesta = s["messages"][-1].get("content") or ""
    # L8 de este lado también: sin texto no hay "informe escrito" silencioso
    if not respuesta.strip():
        respuesta = "(el agente cerró sin informe)"
    destino, err = escribir_salida(salida, respuesta)
    if err:
        raise ValueError(f"ERROR: {err}")
    print(f"\n✅ informe escrito: {destino}")
    return str(destino)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="research", description="Deep research: un agente del kernel con search_web"
    )
    parser.add_argument("tema")
    parser.add_argument("--salida", default="salidas/research.md")
    args = parser.parse_args(argv)
    investigar(args.tema, args.salida)


if __name__ == "__main__":
    main()
