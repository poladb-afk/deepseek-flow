"""Sonda de tokens sobre las trazas acumuladas (exp/93).

Lee `.runs/*.jsonl` y agrega los eventos `accion: "usage"` (uno por llamada al
LLM, `utils/tracing.py:evento_llm`) por traza: llamadas, prompt y completion
totales, max prompt y la SECUENCIA de prompt_tokens — la curva de contexto: cada
llamada re-envía el historial, así que la secuencia es el costo marginal visible.
Después, p50/p90/max de prompt por llamada sobre TODAS las llamadas.

Límites declarados (exp/93): la traza no lleva cache hit ni modelo (exp/90), y
las trazas pre-exp/89 no tienen usage: se ignoran en silencio. Puro: sin red,
sin LLM, sin escribir nada.

Uso: python3 banco/probes/tokens_runs.py [--runs .runs]
"""
import argparse
import json
import math
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def usos(ruta):
    """Los eventos usage de una traza, en orden de aparición (la secuencia)."""
    filas = []
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    evento = json.loads(linea)
                except ValueError:
                    continue  # línea rota: bookkeeping, no es un dato
                if evento.get("accion") == "usage":
                    filas.append(evento)
    except OSError:
        pass
    return filas


def resumir_traza(usos_traza):
    prompts = [int(u.get("prompt_tokens") or 0) for u in usos_traza]
    return {
        "llamadas": len(prompts),
        "prompt_total": sum(prompts),
        "completion_total": sum(int(u.get("completion_tokens") or 0) for u in usos_traza),
        "max_prompt": max(prompts),
        "secuencia": prompts,
    }


def _percentil(valores, p):
    """Nearest-rank: p90 es una llamada OBSERVADA, no una interpolación
    sintética. posición = ceil(p/100 · n) sobre el orden ascendente."""
    ordenados = sorted(valores)
    if not ordenados:
        return 0
    posicion = math.ceil(p / 100 * len(ordenados))
    return ordenados[max(posicion, 1) - 1]


def agregados(trazas):
    prompts = [p for t in trazas for p in t["secuencia"]]
    if not prompts:
        return {"llamadas": 0, "traza": 0, "prompt_total": 0,
                "completion_total": 0, "p50": 0, "p90": 0, "max": 0}
    return {
        "llamadas": len(prompts),
        "traza": len(trazas),
        "prompt_total": sum(t["prompt_total"] for t in trazas),
        "completion_total": sum(t["completion_total"] for t in trazas),
        "p50": round(statistics.median(prompts)),
        "p90": _percentil(prompts, 90),
        "max": max(prompts),
    }


def nombre(ruta):
    return Path(ruta).stem


def barrer(runs):
    """Una fila por traza CON usage; las que no tienen eventos no aparecen."""
    runs = Path(runs)
    trazas = []
    for ruta in sorted(runs.glob("*.jsonl")) if runs.is_dir() else []:
        usos_traza = usos(ruta)
        if not usos_traza:
            continue
        trazas.append({"nombre": nombre(ruta), **resumir_traza(usos_traza)})
    return trazas


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="tokens_runs", description="tokens por llamada y curva de contexto (read-only)"
    )
    parser.add_argument("--runs", default=str(RAIZ / ".runs"))
    args = parser.parse_args(argv)
    trazas = barrer(args.runs)
    print("# Sonda de tokens exp/93 — eventos usage en las trazas (read-only)")
    if not trazas:
        print(f"sin eventos usage en {args.runs}")
        return 1
    _max = max(t["max_prompt"] for t in trazas)
    for t in trazas:
        print(f"{t['nombre']}: {t['llamadas']} llamadas · prompt {t['prompt_total']:,} · "
              f"completion {t['completion_total']:,} · max {t['max_prompt']:,}")
        print(f"  secuencia: {' → '.join(str(p) for p in t['secuencia'])}")
    a = agregados(trazas)
    print(f"global: {a['traza']} trazas · {a['llamadas']} llamadas · "
          f"prompt {a['prompt_total']:,} · completion {a['completion_total']:,}")
    print(f"prompt por llamada: p50 {a['p50']:,} · p90 {a['p90']:,} · max {a['max']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
