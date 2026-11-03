"""exp/108 — research sobre el kernel: el instrumento del A/B (no producto).

Pre-registro: `banco/specs/exp108_research_kernel.md`. Corre `investigar`
por tema×seed en el árbol LOCAL (cada brazo en su worktree), intercepta las
búsquedas para contarlas y capturar las URLs que la corrida vio de verdad,
mide tokens/USD por corrida y deja un jsonl; `--comparar` aplica los
criterios del spec tal como están escritos, sin adaptarlos. El panel ciego
(criterio 5) lo completa el operador: una letra por par (g=gana agente,
e=empate, p=pierde) en el orden de los pares.

Uso:
    python3 banco/probes/exp108.py --correr --salida salidas/exp108/agente.jsonl
    python3 banco/probes/exp108.py --comparar salidas/exp108/base.jsonl salidas/exp108/agente.jsonl \
        --preferencias g e g e p g
"""
import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

# Los tres temas del spec, fijos; la seed es etiqueta de repetición (declarado)
TEMAS = (
    "PocketFlow: el framework de agentes de 100 líneas",
    "precios y modelos de DeepSeek hoy",
    "preregistración de estudios en ciencia abierta",
)
SEEDS = (1, 2)
TOPE_BUSQUEDAS = 9          # criterio 4, del spec (no se lee del brazo)
MARGEN_COSTO = 1.25         # criterio 3
PARES = len(TEMAS) * len(SEEDS)

_URL = re.compile(r"https?://[^\s)\]>'\"]+")


def _urls(texto):
    return {u.rstrip(".,;:") for u in _URL.findall(texto or "")}


def _interceptar(vistos):
    """Envuelve los bindings de búsqueda del módulo research (el brazo base
    llama a `search_web`, el agente a `run_search_web`): cuenta y captura lo
    que la corrida vio de verdad. Devuelve cómo deshacer."""
    import research

    originales = {}
    for nombre in ("search_web", "run_search_web"):
        original = getattr(research, nombre, None)
        if original is None or getattr(original, "_espiada", False):
            continue

        def envoltura(consulta, k=4, _original=original):
            texto = _original(consulta, k)
            vistos.append({"consulta": str(consulta), "texto": texto})
            return texto

        envoltura._espiada = True
        originales[nombre] = original
        setattr(research, nombre, envoltura)

    def deshacer():
        for nombre, original in originales.items():
            setattr(research, nombre, original)

    return deshacer


def correr_una(tema, seed, salida_informe):
    """Una corrida del árbol local: fila con lo que el spec pide medir."""
    import research
    from utils.call_llm import _setting, desglose_de_sesion
    from utils.costos import costo_desglose, delta_desglose, precios

    vistos = []
    antes = desglose_de_sesion()
    deshacer = _interceptar(vistos)
    try:
        ruta = research.investigar(tema, str(salida_informe))
    finally:
        deshacer()
    usd, sin_tarifa = costo_desglose(delta_desglose(antes, desglose_de_sesion()),
                                     precios(_setting("PRECIO_TOKENS")))
    informe = Path(ruta).read_text(encoding="utf-8")
    # informe no vacío Y no el guard de cierre sin texto (ese NO es informe)
    informe_ok = bool(informe.strip()) and not informe.startswith("(el agente cerró sin informe)")
    urls_vistas = set().union(*(_urls(v["texto"]) for v in vistos)) if vistos else set()
    urls_informe = _urls(informe)
    return {
        "tema": tema,
        "seed": seed,
        "informe_ok": informe_ok,
        "busquedas": len(vistos),
        "urls_vistas": len(urls_vistas),
        "urls_informe": len(urls_informe),
        "urls_inventadas": sorted(urls_informe - urls_vistas),
        "usd": None if sin_tarifa else usd,
    }


def estructura():
    """Criterio 6: los nombres del flujo viejo dan 0 en el producto LOCAL y
    la tool deep_research sigue (criterio 7)."""
    archivos = [RAIZ / "research.py", RAIZ / "main.py", *sorted((RAIZ / "modules").glob("*.py"))]
    texto = "\n".join(a.read_text(encoding="utf-8") for a in archivos)
    viejos = [n for n in ("Planner", "Researcher", "Synthesizer",
                          "create_research_flow", "MAX_ROUNDS", "MAX_QUERIES")
              if re.search(rf"\b{n}\b", texto)]
    from modules.research import IMPL, TOOLS

    interfaz = any(t["function"]["name"] == "deep_research" for t in TOOLS) \
        and "deep_research" in IMPL
    return viejos, interfaz


def criterios(base, agente, preferencias=None):
    """Los siete del spec, tal como están escritos. Devuelve
    (pasan_todos, detalle por criterio)."""
    usd_base = sum(f["usd"] for f in base if f["usd"] is not None)
    usd_agente = sum(f["usd"] for f in agente if f["usd"] is not None)
    sin_tarifa = any(f["usd"] is None for f in base + agente)
    viejos, interfaz = estructura()
    detalle = {
        "1_informe_siempre": (all(f["informe_ok"] for f in agente),
                              f"{sum(f['informe_ok'] for f in agente)}/{len(agente)}"),
        "2_urls_honestas": (not any(f["urls_inventadas"] for f in agente),
                            f"agente {sum(len(f['urls_inventadas']) for f in agente)} inventadas "
                            f"(base {sum(len(f['urls_inventadas']) for f in base)}, dato)"),
        "3_costo": ((not sin_tarifa) and usd_base > 0 and usd_agente <= MARGEN_COSTO * usd_base,
                    "sin evaluar (falta tarifa)" if sin_tarifa
                    else f"{usd_agente:.4f} vs {usd_base:.4f} (≤ {MARGEN_COSTO}×)"),
        "4_tope_del_codigo": (all(f["busquedas"] <= TOPE_BUSQUEDAS for f in agente),
                              f"max {max((f['busquedas'] for f in agente), default=0)} "
                              f"de {TOPE_BUSQUEDAS}"),
        "5_panel_ciego": ((preferencias is not None
                           and len(preferencias) == PARES
                           and sum(1 for p in preferencias if p in ("g", "e")) >= PARES / 2),
                          "pendiente: panel ciego del operador"
                          if preferencias is None else
                          f"{sum(1 for p in preferencias if p in ('g', 'e'))}/{PARES} gana o empata"),
        "6_estructura_fuera": (not viejos and interfaz,
                               f"nombres viejos: {viejos or 'ninguno'}"),
        "7_interfaz_del_chat": (interfaz, "deep_research intacta" if interfaz else "faltante"),
    }
    return all(ok for ok, _ in detalle.values()), detalle


def main(argv=None):
    parser = argparse.ArgumentParser(prog="exp108", description=__doc__.splitlines()[0])
    parser.add_argument("--correr", action="store_true",
                        help="corre los temas×seeds del spec en el árbol local")
    parser.add_argument("--salida", default="salidas/exp108/local.jsonl", help="jsonl de salida")
    parser.add_argument("--comparar", nargs=2, metavar=("BASE", "AGENTE"),
                        help="aplica los criterios del spec a los dos jsonl")
    parser.add_argument("--preferencias", nargs="+", choices=["g", "e", "p"],
                        help="panel ciego del operador: una letra por par (g/e/p)")
    args = parser.parse_args(argv)

    if args.correr:
        filas = [correr_una(tema, seed, Path(args.salida).parent / f"informe-{i}.md")
                 for i, (tema, seed) in enumerate((t, s) for t in TEMAS for s in SEEDS)]
        Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
        with open(args.salida, "w", encoding="utf-8") as f:
            for fila in filas:
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")
        print(f"{len(filas)} corridas → {args.salida}")
        return 0
    if args.comparar:
        base = [json.loads(linea) for linea
                in Path(args.comparar[0]).read_text(encoding="utf-8").splitlines()]
        agente = [json.loads(linea) for linea
                  in Path(args.comparar[1]).read_text(encoding="utf-8").splitlines()]
        pasa, detalle = criterios(base, agente, args.preferencias)
        for nombre, (ok, texto) in detalle.items():
            print(f"{'✅' if ok else '❌'} {nombre}: {texto}")
        print("\ncriterio 6, lo que queda MANUAL (el instrumento solo mira nombres e interfaz): "
              "`./calidad.sh` verde en la rama, `tests_definidos` no baja y la traza con "
              "Paso/Actuar — va en el reporte del A/B.")
        print("panel ciego: aleatorizá el orden de los pares antes de leerlos "
              "(el instrumento recibe las letras, no arma el orden).")
        print("\nexp/108: PASA" if pasa else "\nexp/108: NO PASA (la rama se revierte)")
        return 0 if pasa else 1
    parser.print_help()
    return 0


if __name__ == "__main__":
    main()
