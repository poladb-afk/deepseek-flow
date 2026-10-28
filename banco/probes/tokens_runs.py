"""Sonda de tokens sobre las trazas acumuladas (exp/93).

Lee `.runs/*.jsonl` y agrega los eventos `accion: "usage"` (uno por llamada al
LLM, `utils/tracing.py:evento_llm`) por traza: llamadas, prompt y completion
totales, max prompt y la SECUENCIA de prompt_tokens — la curva de contexto: cada
llamada re-envía el historial, así que la secuencia es el costo marginal visible.
Después, p50/p90/max de prompt por llamada sobre TODAS las llamadas.

Desde X98 cada evento trae además `cache_hit` (tokens del prompt servidos del
KV-cache; ausente si el proveedor no lo informa) y `llamador` (el nodo que hizo
la llamada): `por_llamador` desglosa llamadas, prompt y cache hit por nodo — así
se lee si la llamada de `Cierre` reusa caché (pre-registro de la fase 2d).

Límites declarados: la traza no lleva el modelo (exp/90); las trazas pre-exp/89
no tienen usage y las pre-X98 no tienen cache_hit ni llamador (cuentan como
`?`, y su hit como desconocido, no como 0). Puro: sin red, sin LLM, sin
escribir nada.

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


def por_llamador(usos_traza):
    """{nodo: {llamadas, prompt, con_hit, cache_hit}}. `con_hit` cuenta las
    llamadas que INFORMAN cache_hit: un hit ausente es desconocido, no 0."""
    tabla = {}
    for u in usos_traza:
        fila = tabla.setdefault(u.get("llamador") or "?",
                                {"llamadas": 0, "prompt": 0, "con_hit": 0, "cache_hit": 0})
        fila["llamadas"] += 1
        fila["prompt"] += int(u.get("prompt_tokens") or 0)
        if u.get("cache_hit") is not None:
            fila["con_hit"] += 1
            fila["cache_hit"] += int(u["cache_hit"])
    return tabla


def resumir_traza(usos_traza):
    prompts = [int(u.get("prompt_tokens") or 0) for u in usos_traza]
    return {
        "llamadas": len(prompts),
        "prompt_total": sum(prompts),
        "completion_total": sum(int(u.get("completion_tokens") or 0) for u in usos_traza),
        "max_prompt": max(prompts),
        "secuencia": prompts,
        "por_llamador": por_llamador(usos_traza),
    }


def _percentil(valores, p):
    """Nearest-rank: p90 es una llamada OBSERVADA, no una interpolación
    sintética. posición = ceil(p/100 · n) sobre el orden ascendente."""
    ordenados = sorted(valores)
    if not ordenados:
        return 0
    posicion = math.ceil(p / 100 * len(ordenados))
    return ordenados[max(posicion, 1) - 1]


def _sumar_llamadores(trazas):
    total = {}
    for t in trazas:
        for nodo, fila in t.get("por_llamador", {}).items():
            acumulado = total.setdefault(nodo, dict.fromkeys(fila, 0))
            for clave, valor in fila.items():
                acumulado[clave] += valor
    return total


def agregados(trazas):
    prompts = [p for t in trazas for p in t["secuencia"]]
    if not prompts:
        return {"llamadas": 0, "traza": 0, "prompt_total": 0,
                "completion_total": 0, "p50": 0, "p90": 0, "max": 0, "por_llamador": {}}
    return {
        "por_llamador": _sumar_llamadores(trazas),
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
    for nodo, fila in sorted(a["por_llamador"].items()):
        hit = (f"cache hit {fila['cache_hit']:,} ({fila['cache_hit'] / fila['prompt']:.0%} del prompt "
               f"en {fila['con_hit']}/{fila['llamadas']} llamadas que lo informan)"
               if fila["con_hit"] and fila["prompt"] else "cache hit sin dato")
        print(f"  {nodo}: {fila['llamadas']} llamadas · prompt {fila['prompt']:,} · {hit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
