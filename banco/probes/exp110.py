"""exp/110 — la asimetría medida: runner del A/B (instrumento, no producto).

Pre-registro: `banco/specs/exp110_asimetria.md` (X148). Corre el bench de fable
para los dos brazos —A, el chat de hoy, y F, A más los tres hijos especialistas
montados por `banco/probes/exp110_brazo_f/`— y aplica los cuatro criterios
pre-registrados con `--comparar`. No decide ni adapta el criterio.

Contrato del montaje de F (lo que este runner verifica): al lado del
directorio de cada corrida, `<escenario>-asimetria.json` con

    {"montado": true,
     "tools": ["barrido", "lectura", "sintesis"],
     "delegaciones": {"barrido": int, "lectura": int, "sintesis": int},
     "llamadas_llm": int,   # ctx.ledger.llamadas del árbol
     "saldo": int,          # ctx.ledger.rondas al salir
     "traza": [[profundidad, tool, direccion, argumentos], ...]}

Sin ese archivo en una corrida de F, el brazo está mal montado: el criterio 4
no se evalúa y el A/B no pasa (no es un resultado del mecanismo).

Uso (después del push de X147):
    python3 banco/probes/exp110.py --plan
    python3 banco/probes/exp110.py --humo
    python3 banco/probes/exp110.py --tanda
    python3 banco/probes/exp110.py --comparar salidas/exp110/A.jsonl salidas/exp110/F.jsonl
"""
import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import bench_fable as bf  # noqa: E402
import fractal  # noqa: E402
from s6 import uso_del_log  # noqa: E402  (el parser de la línea `[tokens]`, ya probado en S6)

EXP = "exp110-asimetria"
SPEC = "banco/specs/exp110_asimetria.md"
MODELO = "deepseek-flash"
ANCHOS = ("s13-twin-fleet", "s17-scale-audit", "s18-real-audit", "s19-real-audit-2", "s20-real-audit-3")
CONTROL = ("s2-surprise-trap",)
SEEDS = (1, 2, 3, 4)
ESPECIALISTAS = ("barrido", "lectura", "sintesis")
MONTAJE = RAIZ / "banco" / "probes" / "exp110_brazo_f"
RONDAS = 16
MAX_LLAMADAS_ARBOL = 2 * RONDAS + 1
MARGEN_CALIDAD = 0.5
TOPE_COSTO = 1.25
UMBRE_HUMO = 0.15
SALIDAS = RAIZ / "salidas" / "exp110"
BRAZOS = {
    # PYTHONPATH vacío a propósito: A NO debe heredar del shell un montaje
    # (el del brazo F es solo un directorio; el de A, ninguno).
    "A": {"SKILLS": "0", "LLM_MODEL": MODELO, "MAX_TOOL_ROUNDS": str(RONDAS), "PYTHONPATH": ""},
    "F": {"SKILLS": "0", "LLM_MODEL": MODELO, "MAX_TOOL_ROUNDS": str(RONDAS),
          "PYTHONPATH": str(MONTAJE)},
}


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True,
                              timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def estado_del_arbol():
    kernel = (RAIZ / "utils" / "kernel.py").read_text(encoding="utf-8", errors="replace")
    montaje = (MONTAJE / "sitecustomize.py").is_file() and (MONTAJE / "modulo" / "asimetria.py").is_file()
    return {"arbol": _git("rev-parse", "HEAD")[:12], "rama": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "x147": "hijas" in kernel, "montaje": montaje}


def exigir_instrumento():
    """El experimento depende de X147 y del montaje; sin los dos, no arranca."""
    est = estado_del_arbol()
    if not est["x147"]:
        raise SystemExit(f"[exp110] falta X147 en {est['arbol']}: el kernel no verifica el poder del hijo")
    if not est["montaje"]:
        raise SystemExit(f"[exp110] falta el montaje {MONTAJE} (sitecustomize.py + modulo/asimetria.py)")
    return est


def ruta_asimetria(run):
    """Donde el montaje deja su archivo: al lado del directorio de la corrida."""
    return Path(run).with_name(f"{Path(run).name}-asimetria.json")


def leer_asimetria(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def fila(brazo, seed, escenario, resultado, arbol):
    """Una fila: calidad y costo de la corrida + adopción/Ley 1 del montaje. PURA salvo el disco."""
    log = resultado.pop("log", "")
    uso = uso_del_log(log)
    datos = None
    if brazo == "F":
        run = bf.SALIDAS / "runs" / EXP / brazo / f"s{seed}" / escenario
        datos = leer_asimetria(ruta_asimetria(run))
    delegaciones = (datos or {}).get("delegaciones") or {}
    traza = [(p, tool, tuple(direccion), args) for p, tool, direccion, args in (datos or {}).get("traza") or []]
    medido = fractal.medir(traza, ESPECIALISTAS) if traza else {"divisiones": {}, "fallas": []}
    division = medido["divisiones"].get(())
    return {
        "exp": EXP, "arbol": arbol, "brazo": brazo, "seed": seed, "escenario": escenario,
        "familia": "ancha" if escenario in ANCHOS else "control",
        "correct_action": resultado["correct_action"], "tokens": uso["tokens"],
        "prompt": uso["prompt"], "completion": uso["completion"], "usd": uso["usd"],
        "llamadas": uso["llamadas"], "rondas": resultado.get("rondas"),
        "checks": resultado.get("checks") or {}, "error": resultado.get("error"),
        "seg": resultado.get("seg"),
        "montado": bool((datos or {}).get("montado")),
        "tools": (datos or {}).get("tools") or [],
        "delegaciones": delegaciones,
        "delegaciones_total": sum(int(n or 0) for n in delegaciones.values()),
        "d": None if division is None else round(division, 3),
        "fallas": len(medido["fallas"]),
        "llamadas_arbol": (datos or {}).get("llamadas_llm"),
        "saldo": (datos or {}).get("saldo"),
    }


def correr(brazo, seed, escenario, arbol):
    bf.ENV_POR_BRAZO[brazo] = dict(BRAZOS[brazo])
    resultado = bf.correr_uno(EXP, escenario, brazo, seed, forzar=True, salir=True)
    if resultado is None:
        raise SystemExit(f"[exp110] correr_uno devolvió None para {brazo} s{seed} {escenario}")
    return fila(brazo, seed, escenario, resultado, arbol)


def guardar(filas, ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")


def cargar(ruta):
    return [json.loads(linea) for linea in Path(ruta).read_text(encoding="utf-8").splitlines() if linea.strip()]


def _media(filas, clave):
    valores = [f[clave] for f in filas if f.get(clave) is not None]
    return statistics.mean(valores) if valores else None


def corridas_tanda():
    return [(brazo, seed, escenario) for brazo in BRAZOS for seed in SEEDS
            for escenario in ANCHOS + CONTROL]


def plan():
    est = estado_del_arbol()
    print(f"[exp110] árbol: {est}")
    print(f"[exp110] spec: {SPEC}")
    print(f"[exp110] brazos: A (chat de hoy) · F (A + {', '.join(ESPECIALISTAS)})")
    filas = corridas_tanda()
    print(f"[exp110] tanda: {len(filas)} corridas ({len(filas) // 2} por brazo, "
          f"{len(ANCHOS)} anchos + {len(CONTROL)} control, seeds {SEEDS})")
    exp105 = RAIZ / "salidas" / "fable" / "resultados" / "exp105-fractal-v4pro.jsonl"
    if exp105.is_file():
        base = [f for f in cargar(exp105) if f["brazo"] == "A" and f["escenario"] in ANCHOS + CONTROL]
        por_corrida = statistics.mean(f["tokens"] for f in base)
        tokens_a = por_corrida * len(filas) // 2
        tokens_total = tokens_a * (1 + TOPE_COSTO)
        print(f"[exp110] proyección con tokens del exp/105: {int(por_corrida)} tokens/corrida → "
              f"A {int(tokens_a)} + F ≤{int(tokens_a * TOPE_COSTO)} = {int(tokens_total)} tokens "
              f"(US$0,30–1,00 según cache)")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="exp110", description="exp/110: la asimetría medida")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--humo", action="store_true")
    parser.add_argument("--tanda", action="store_true")
    parser.add_argument("--comparar", nargs=2, metavar=("A", "F"))
    args = parser.parse_args(argv)
    if args.plan:
        plan()
        return 0
    if args.comparar:
        base, asim = cargar(args.comparar[0]), cargar(args.comparar[1])
        texto = resumen(base, asim)
        destino = SALIDAS / "veredicto.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
        print(texto)
        print(f"[exp110] veredicto → {destino}")
        return 0
    est = exigir_instrumento()
    arbol = est["arbol"]
    if args.humo:
        filas = [correr(brazo, 1, escenario, arbol)
                 for brazo in BRAZOS for escenario in ("s2-surprise-trap", "s13-twin-fleet")]
        guardar(filas, SALIDAS / "humo.jsonl")
        usd = round(sum(f["usd"] or 0 for f in filas), 4)
        f_filas = [f for f in filas if f["brazo"] == "F"]
        montado = all(f["montado"] for f in f_filas)
        ley1 = all(f["llamadas_arbol"] is not None and f["llamadas_arbol"] <= MAX_LLAMADAS_ARBOL
                   for f in f_filas)
        (SALIDAS / "humo.json").write_text(json.dumps(
            {"arbol": arbol, "usd": usd, "corridas": len(filas), "montado": montado, "ley1": ley1},
            ensure_ascii=False), encoding="utf-8")
        print(f"[exp110] humo: {len(filas)} corridas, US${usd} (techo US${UMBRE_HUMO}) · "
              f"montaje {'ok' if montado else 'FALTA'} · Ley 1 {'ok' if ley1 else 'VIOLADA'}")
        for f in filas:
            print(f"[exp110]   {f['brazo']} {f['escenario']}: ca={f['correct_action']} "
                  f"tokens={f['tokens']} deleg={f['delegaciones_total']} "
                  f"arbol={f['llamadas_arbol']} err={f['error'] or '-'}")
        return 0 if (usd <= UMBRE_HUMO and montado and ley1) else 1
    if args.tanda:
        registro = SALIDAS / "humo.json"
        if not registro.is_file():
            raise SystemExit("[exp110] falta el humo: corré --humo antes de la tanda")
        humo = json.loads(registro.read_text(encoding="utf-8"))
        if humo.get("arbol") != arbol or humo.get("usd", 9) > UMBRE_HUMO or not humo.get("montado") \
                or not humo.get("ley1"):
            raise SystemExit(f"[exp110] humo inválido para este árbol ({humo}); no arranca la tanda")
        for brazo in BRAZOS:
            filas = []
            for _, seed, escenario in [c for c in corridas_tanda() if c[0] == brazo]:
                fila_ = correr(brazo, seed, escenario, arbol)
                filas.append(fila_)
                print(f"[exp110] {brazo} s{seed} {escenario}: ca={fila_['correct_action']} "
                      f"tokens={fila_['tokens']} deleg={fila_['delegaciones_total']} "
                      f"arbol={fila_['llamadas_arbol']} err={fila_['error'] or '-'}", flush=True)
            guardar(filas, SALIDAS / f"{brazo}.jsonl")
            print(f"[exp110] {brazo}: {len(filas)} corridas → {SALIDAS / f'{brazo}.jsonl'}")
        return 0
    parser.error("nada para hacer: --humo o --tanda (o --plan/--comparar)")


def criterios(base, asim):
    """Los cuatro criterios del pre-registro. PURA salvo nada (solo filas)."""
    anchas = {e: {"A": [f for f in base if f["escenario"] == e],
                  "F": [f for f in asim if f["escenario"] == e]} for e in ANCHOS}
    control = {e: {"A": [f for f in base if f["escenario"] == e],
                   "F": [f for f in asim if f["escenario"] == e]} for e in CONTROL}
    con_delegacion = {e: sum(1 for f in anchas[e]["F"] if f["delegaciones_total"] > 0) for e in ANCHOS}
    c1 = sum(1 for e in ANCHOS if con_delegacion[e] >= 2) >= 3
    a_ancha = [f for e in ANCHOS for f in anchas[e]["A"]]
    f_ancha = [f for e in ANCHOS for f in anchas[e]["F"]]
    a_control = [f for e in CONTROL for f in control[e]["A"]]
    f_control = [f for e in CONTROL for f in control[e]["F"]]
    c2 = (_media(f_ancha, "correct_action") is not None and _media(a_ancha, "correct_action") is not None
          and _media(f_ancha, "correct_action") >= _media(a_ancha, "correct_action") - MARGEN_CALIDAD
          and _media(f_control, "correct_action") is not None
          and _media(a_control, "correct_action") is not None
          and _media(f_control, "correct_action") >= _media(a_control, "correct_action") - MARGEN_CALIDAD)
    tokens_a = _media(a_ancha, "tokens")
    tokens_f = _media(f_ancha, "tokens")
    c3 = tokens_a is not None and tokens_f is not None and tokens_f <= TOPE_COSTO * tokens_a
    c4 = (all(f["montado"] and f["llamadas_arbol"] is not None
              and f["llamadas_arbol"] <= MAX_LLAMADAS_ARBOL for f in asim)
          and all(f["tokens"] is not None for f in base + asim))
    return {
        "1_adopcion": {"pasa": c1, "seeds_con_delegacion": con_delegacion,
                       "por_tool": {t: sum(f["delegaciones"].get(t, 0) for f in f_ancha) for t in ESPECIALISTAS}},
        "2_calidad": {"pasa": c2,
                      "ancha": {"A": _media(a_ancha, "correct_action"),
                                "F": _media(f_ancha, "correct_action")},
                      "control": {"A": _media(a_control, "correct_action"),
                                  "F": _media(f_control, "correct_action")},
                      "por_escenario": {e: {"A": _media(anchas[e]["A"], "correct_action"),
                                            "F": _media(anchas[e]["F"], "correct_action")} for e in ANCHOS}},
        "3_costo": {"pasa": c3, "tokens_A": tokens_a, "tokens_F": tokens_f,
                    "ratio": None if not tokens_a else tokens_f / tokens_a},
        "4_ley1": {"pasa": c4, "max_llamadas": MAX_LLAMADAS_ARBOL,
                   "peor": max((f["llamadas_arbol"] or 0) for f in asim),
                   "sin_montaje": sum(1 for f in asim if not f["montado"]),
                   "sin_tokens": sum(1 for f in base + asim if f["tokens"] is None)},
        "pasa": c1 and c2 and c3 and c4,
    }


def resumen(base, asim):
    v = criterios(base, asim)
    marca = {True: "✅", False: "❌"}
    c1, c2, c3, c4 = v["1_adopcion"], v["2_calidad"], v["3_costo"], v["4_ley1"]
    lineas = ["# exp/110 — la asimetría medida (A/B)", "",
              f"Criterio pre-registrado: `{SPEC}`.", "",
              f"**Veredicto: {'PASA' if v['pasa'] else 'NO PASA'}**", "",
              "| criterio | resultado | detalle |", "|---|---|---|",
              f"| 1 adopción | {marca[c1['pasa']]} | seeds con delegación por escenario: "
              f"{c1['seeds_con_delegacion']} · por tool: {c1['por_tool']} |",
              f"| 2 calidad no inferior | {marca[c2['pasa']]} | ancha A {c2['ancha']['A']} · F "
              f"{c2['ancha']['F']} (margen −0,5) · control A {c2['control']['A']} · F {c2['control']['F']} |",
              f"| 3 costo ≤1,25× | {marca[c3['pasa']]} | tokens medios ancha A {c3['tokens_A']} · F "
              f"{c3['tokens_F']} · ratio {c3['ratio']} |",
              f"| 4 Ley 1 ≤{c4['max_llamadas']} | {marca[c4['pasa']]} | peor corrida F "
              f"{c4['peor']} llamadas · sin montaje {c4['sin_montaje']} · sin tokens {c4['sin_tokens']} |",
              "", "## Calidad por escenario", "", "| escenario | A | F |", "|---|---|---|"]
    lineas += [f"| {e} | {c2['por_escenario'][e]['A']} | {c2['por_escenario'][e]['F']} |" for e in ANCHOS]
    lineas += ["", "## Forma del árbol (montaje F)", "",
               f"- delegaciones totales: {sum(c1['por_tool'].values())} · por tool: {c1['por_tool']}",
               "- D por escenario: " + ", ".join(
                   f"{e}: {_media([f for f in asim if f['escenario'] == e], 'd')}" for e in ANCHOS),
               f"- fallas totales: {sum(f['fallas'] for f in asim)}"]
    return "\n".join(lineas) + "\n"


if __name__ == "__main__":
    sys.exit(main())
