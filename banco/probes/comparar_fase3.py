"""Veredicto del A/B de la fase 3 (banco/specs/fase3.md), sin juicio a mano.

Entrada: por brazo, el JSONL de resultados de bench_fable y el directorio de
trazas de ESE brazo (uno por worktree, para que no se mezclen). Las trazas de
chat se emparejan con las filas de resultados por ORDEN de ejecución (el bench
corre secuencial y `guardar_resultado` conserva el orden); si las cuentas no
coinciden, la sonda se niega a decidir.

USD por corrida con las tarifas de `utils.costos` y el split de caché de la
traza (X98): hit × tarifa_hit + (prompt − hit) × tarifa_miss + completion ×
tarifa_completion. Una llamada sin `cache_hit` cuenta como miss entero (techo
conservador, como `_contabilizar`).

Criterios (todos, por escenario contra la base):
  1. s17 + s18: la suma de correct_action sube ≥ 2 puntos;
  2. ningún escenario baja su suma;
  3. mediana de USD por corrida ≤ 1,5 × la de la base;
  4. sin ganancia de calidad no entra (lo cubre 1).

Uso: python3 banco/probes/comparar_fase3.py \
       --base RES_A.jsonl --runs-base DIR_A --pensar RES_E.jsonl --runs-pensar DIR_E \
       [--modelo deepseek-flash]
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from utils.costos import PRECIOS_MILLON  # noqa: E402
from utils.trazas import leer_eventos  # noqa: E402

MEJORAN = ("s17-scale-audit", "s18-real-audit")
SUBA_MINIMA = 2
USD_MAX = 1.5


def resultados(ruta):
    return [json.loads(linea) for linea in Path(ruta).read_text(encoding="utf-8").splitlines()
            if linea.strip()]


def trazas_de_chat(directorio):
    """Las trazas de chat del directorio, en orden de ejecución (el nombre
    lleva el timestamp de inicio)."""
    trazas = []
    for ruta in sorted(Path(directorio).glob("*.jsonl")):
        eventos = leer_eventos(ruta)
        if any(e.get("nodo") == "GetQuestion" for e in eventos):
            trazas.append(eventos)
    return trazas


def usd(eventos, tarifa):
    hit_t, miss_t, comp_t = tarifa
    total = 0.0
    for e in eventos:
        if e.get("accion") != "usage":
            continue
        prompt = int(e.get("prompt_tokens") or 0)
        hit = int(e.get("cache_hit") or 0)
        total += hit * hit_t + (prompt - hit) * miss_t + int(e.get("completion_tokens") or 0) * comp_t
    return total / 1_000_000


def por_escenario(filas, trazas, tarifa):
    if len(filas) != len(trazas):
        raise ValueError(f"{len(filas)} resultados y {len(trazas)} trazas de chat: no se emparejan")
    tabla = {}
    for fila, eventos in zip(filas, trazas, strict=True):
        celda = tabla.setdefault(fila["escenario"], {"ca": [], "usd": []})
        celda["ca"].append(int(fila["correct_action"]))
        celda["usd"].append(usd(eventos, tarifa))
    return tabla


def veredicto(base, pensar):
    """(pasa, filas, motivos)."""
    filas, motivos = [], []
    for esc in sorted(set(base) | set(pensar)):
        b, p = base.get(esc), pensar.get(esc)
        if not b or not p:
            motivos.append(f"{esc}: falta en un brazo")
            continue
        fila = {"escenario": esc, "suma_base": sum(b["ca"]), "suma_pensar": sum(p["ca"]),
                "seeds": (len(b["ca"]), len(p["ca"])),
                "usd_base": statistics.median(b["usd"]), "usd_pensar": statistics.median(p["usd"])}
        fila["razon_usd"] = fila["usd_pensar"] / fila["usd_base"] if fila["usd_base"] else float("inf")
        filas.append(fila)
        if fila["suma_pensar"] < fila["suma_base"]:
            motivos.append(f"{esc}: la calidad baja ({fila['suma_base']} → {fila['suma_pensar']})")
        if fila["razon_usd"] > USD_MAX:
            motivos.append(f"{esc}: USD {fila['razon_usd']:.2f}× > {USD_MAX}×")
    suba = sum(f["suma_pensar"] - f["suma_base"] for f in filas if f["escenario"] in MEJORAN)
    if suba < SUBA_MINIMA:
        motivos.append(f"s17+s18 suben {suba} (hace falta ≥ {SUBA_MINIMA})")
    return not motivos, filas, motivos


def main(argv=None):
    parser = argparse.ArgumentParser(prog="comparar_fase3", description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True)
    parser.add_argument("--runs-base", required=True)
    parser.add_argument("--pensar", required=True)
    parser.add_argument("--runs-pensar", required=True)
    parser.add_argument("--modelo", default="deepseek-flash")
    args = parser.parse_args(argv)
    tarifa = PRECIOS_MILLON[args.modelo]
    base = por_escenario(resultados(args.base), trazas_de_chat(args.runs_base), tarifa)
    pensar = por_escenario(resultados(args.pensar), trazas_de_chat(args.runs_pensar), tarifa)
    pasa, filas, motivos = veredicto(base, pensar)
    print("| escenario | seeds | suma base | suma pensar | USD base (mediana) | USD pensar | × |")
    print("|---|---|---|---|---|---|---|")
    for f in filas:
        print(f"| {f['escenario']} | {f['seeds'][0]}/{f['seeds'][1]} | {f['suma_base']} | "
              f"{f['suma_pensar']} | {f['usd_base']:.4f} | {f['usd_pensar']:.4f} | {f['razon_usd']:.2f} |")
    for m in motivos:
        print(f"- {m}")
    print("FASE 3a: " + ("PASA" if pasa else "NO PASA"))
    return 0 if pasa else 1


if __name__ == "__main__":
    sys.exit(main())
