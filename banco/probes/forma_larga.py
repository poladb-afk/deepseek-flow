"""exp/66 — Long Method: ¿tiene el harness la firma de la IA en el LARGO?

Pregunta: la tabla de evidencia (`docs/informes/codigo_ia_vs_humano_2026-10-19.md`,
fila 8) lista **Long Method** como smell de código de IA (arXiv 2605.02741:
Qwen-480B 11 vs 1 humano), pero el gate del repo solo lo proxea con complejidad
(C901). ¿Hay señal de LARGO en nuestro harness contra una referencia humana, o
la lectura previa ("el ruido no son funciones gigantes") se sostiene con números?

**Criterio PRE-REGISTRADO** (escrito ANTES de mirar los números; la sonda es
determinista y la reproduce cualquiera):

- corpus "harness": los `.py` del harness (raíz + `modules/` + `utils/`, sin
  `__init__.py` ni los ignorados del ratchet) — el código que escribimos con
  agente.
- corpus "humano": el fuente instalado de `requests` (librería OSS madura, 18
  archivos; la MISMA referencia humana de la medición de exp/51-research:
  55/39,0% de `except` amplios vs 1/1,6%).
- unidad: toda `FunctionDef`/`AsyncFunctionDef` de cualquier nivel; largo =
  `end_lineno - lineno + 1` (bloque `def..fin`, docstring incluido; igual en
  ambos corpus, es una cota superior uniforme y no premia docstrings).
- umbral P = **p99 de `requests` redondeado HACIA ABAJO a múltiplo de 10**
  (mínimo 10). Se elige de la referencia, no del harness: evita elegir el
  umbral después de ver el resultado.
- **HAY SEÑAL** si la proporción de funciones con largo > P en el harness es
  **>= 2×** la de `requests`. Si no hay señal, NO se agrega métrica al ratchet:
  el resultado negativo se documenta y la lectura previa queda confirmada.

Uso: python3 banco/probes/forma_larga.py [--referencia RUTA]
Solo lectura: escribe el informe en salidas/evals/ (ignorado por git).
"""
import argparse
import ast
import math
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import ratchet  # noqa: E402  (archivos_del_harness: el corpus ya está definido)

FACTOR_SENAL = 2.0


def funciones_de(fuente):
    """[(nombre, largo)] de todas las funciones del fuente, anidadas incluidas."""
    arbol = ast.parse(fuente)
    return [
        (nodo.name, nodo.end_lineno - nodo.lineno + 1)
        for nodo in ast.walk(arbol)
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def largos_de(fuente):
    return sorted(largo for _, largo in funciones_de(fuente))


def percentil(valores, p):
    """Nearest-rank determinista (sin interpolar): muestras chicas y auditable."""
    ordenados = sorted(valores)
    if not ordenados:
        return 0
    return ordenados[max(0, math.ceil(p / 100 * len(ordenados)) - 1)]


def umbral_de_referencia(largos):
    """p99 de la referencia hacia abajo a múltiplo de 10, mínimo 10."""
    return max(10, percentil(largos, 99) // 10 * 10)


def proporcion_mayores(largos, umbral):
    if not largos:
        return 0.0
    return sum(1 for largo in largos if largo > umbral) / len(largos)


def hay_senal(prop_harness, prop_referencia):
    """El criterio pre-registrado: >= 2x la referencia y algo en el harness."""
    return prop_harness > 0 and prop_harness >= FACTOR_SENAL * prop_referencia


def _resumen(largos, umbral):
    return {
        "n": len(largos),
        "p50": percentil(largos, 50),
        "p90": percentil(largos, 90),
        "p99": percentil(largos, 99),
        "max": max(largos) if largos else 0,
        "sobre_umbral": sum(1 for largo in largos if largo > umbral),
        "proporcion": proporcion_mayores(largos, umbral),
    }


def medir(rutas_harness, rutas_referencia):
    """Las distribuciones de ambos corpus y el veredicto del criterio."""
    largos_h = [largo for ruta in rutas_harness for largo in largos_de(ruta.read_text(encoding="utf-8"))]
    largos_r = [largo for ruta in rutas_referencia for largo in largos_de(ruta.read_text(encoding="utf-8"))]
    umbral = umbral_de_referencia(largos_r)
    harness = _resumen(largos_h, umbral)
    referencia = _resumen(largos_r, umbral)
    return {
        "umbral": umbral,
        "harness": harness,
        "referencia": referencia,
        "senal": hay_senal(harness["proporcion"], referencia["proporcion"]),
    }


def informe(resultado, n_archivos):
    """Markdown del veredicto (determinista)."""
    h, r = resultado["harness"], resultado["referencia"]
    umbral = resultado["umbral"]
    lineas = [
        "# exp/66 — Long Method: harness vs referencia humana",
        "",
        f"Fecha {date.today().isoformat()} · harness: {n_archivos[0]} archivos · "
        f"referencia (`requests`): {n_archivos[1]} archivos.",
        "",
        "## Criterio pre-registrado",
        f"Umbral P = p99 de la referencia hacia abajo a múltiplo de 10 → **{umbral} líneas** "
        f"(def..fin, docstring incluido). Hay señal si "
        f"la proporción de funciones > P del harness es >= {FACTOR_SENAL:g}× la de la referencia.",
        "",
        "## Distribución del largo de función (líneas)",
        "| corpus | n | p50 | p90 | p99 | max | > P | proporción |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for nombre, d in (("harness", h), ("`requests`", r)):
        lineas.append(
            f"| {nombre} | {d['n']} | {d['p50']} | {d['p90']} | {d['p99']} | {d['max']} | "
            f"{d['sobre_umbral']} | {d['proporcion']:.1%} |"
        )
    lineas += ["", "## Veredicto"]
    if resultado["senal"]:
        lineas.append(
            f"**HAY SEÑAL**: el harness está en {h['proporcion']:.1%} vs {r['proporcion']:.1%} "
            f"({h['proporcion'] / r['proporcion'] if r['proporcion'] else float('inf'):.1f}×) → "
            f"se justifica gatear `funciones_largas` con umbral {umbral}."
        )
    else:
        lineas.append(
            f"**NO HAY SEÑAL**: {h['proporcion']:.1%} vs {r['proporcion']:.1%} "
            f"(< {FACTOR_SENAL:g}×) → NO se agrega métrica; se documenta el negativo."
        )
    lineas.append(
        "\nLímite: `requests` es UNA referencia humana de librería, no una muestra; "
        "el largo cuenta docstring y funciones anidadas (cota superior uniforme)."
    )
    return "\n".join(lineas) + "\n"


def main_probe(argv=None):
    parser = argparse.ArgumentParser(prog="forma_larga")
    parser.add_argument("--referencia", default=None, help="carpeta de la referencia humana (default: requests)")
    args = parser.parse_args(argv)
    referencia = Path(args.referencia) if args.referencia else _fuente_requests()
    rutas_h = ratchet.archivos_del_harness(RAIZ)
    rutas_r = sorted(referencia.rglob("*.py"))
    resultado = medir(rutas_h, rutas_r)
    destino = RAIZ / "salidas" / "evals" / f"forma_larga_{date.today().isoformat()}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(informe(resultado, (len(rutas_h), len(rutas_r))), encoding="utf-8")
    print(informe(resultado, (len(rutas_h), len(rutas_r))))
    print(f"artefacto: {destino.relative_to(RAIZ).as_posix()}")
    return resultado


def _fuente_requests():
    import requests

    return Path(requests.__file__).resolve().parent


if __name__ == "__main__":
    main_probe()
