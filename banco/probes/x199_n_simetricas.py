"""X199 — N simétricas + verificador contra 1 agente con el presupuesto
igualado (F6). Pre-registro: `banco/specs/x199_n_simetricas.md` (D1–D8 = A).

Reusa el instrumento de la aceptación v1 (`banco/probes/aceptacion_v1.py`):
los `pristine` de T1/T2 sobre `git archive 73b05fe` (T2 con el bloque de X179
invertido), los prompts y el scope, el `correct_action` determinista
(`_puntuar_auditoria` / `_puntuar_rerun` + el test oculto) y `bench_fable` para
correr el chat. Lo nuevo:

- Brazo **N** (D1/D3): 3 copias simétricas × 8 rondas, independientes, sobre
  copias propias del repo; después, verificador.
- Brazo **base**: 1 agente × 24 rondas sobre las mismas 6 celdas.
- Verificador (D4): `fable_judge.verificar_trabajo` sobre cada copia (trabajo =
  la copia, pristine = el árbol pre-tarea, reporte = el mensaje final); se
  queda el primer VERIFIED, si no el de VERIFIED WITH CAVEATS con menos
  caveats, si no el primero. No ve el test oculto ni el `correct_action`.
- Independencia (D5): fallas por celda contra el modelo independiente con la
  tasa marginal por copia (bootstrap sobre las 6 celdas).

Costo (D3): el de las copias es de la línea `[tokens] sesión` de cada corrida;
el del verificador, del delta de `desglose_de_sesion()` del proceso de la
sonda (sus dos etapas LLM corren in-process) y se imputa al brazo N.

Uso:
    python3 banco/probes/x199_n_simetricas.py --humo
    python3 banco/probes/x199_n_simetricas.py --tanda
    python3 banco/probes/x199_n_simetricas.py --evaluar
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "banco"))
sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import aceptacion_v1 as av  # noqa: E402
import bench_fable as bf  # noqa: E402
import yaml  # noqa: E402
from s6 import tope_del_log, uso_del_log  # noqa: E402

import fable_judge  # noqa: E402
from utils import conductor  # noqa: E402
from utils.call_llm import _setting, desglose_de_sesion, uso_de_sesion  # noqa: E402
from utils.costos import costo_desglose, delta_desglose, precios  # noqa: E402

EXP = "x199"
SALIDAS = RAIZ / "salidas" / EXP
TAREAS = ("auditar-cobertura", "arreglar-rerun")
SEEDS = (1, 2, 3)
COPIAS = 3
RONDAS_COPIA = 8
RONDAS_BASE = 24
TOPE_TOTAL = 0.50
TIMEOUT = 1500
RANGO_VEREDICTO = {"VERIFIED": 0, "VERIFIED WITH CAVEATS": 1, "REFUTED": 2}


def _escenario(tarea, run, rondas):
    esc = av._escenario(tarea, run)
    esc["id"] = f"x199-{tarea}"
    esc["descripcion"] = f"X199 {tarea} (rondas {rondas})"
    esc["env"]["MAX_TOOL_ROUNDS"] = str(rondas)
    esc["env"]["PREFETCH"] = "0"
    esc["turnos"][0]["timeout"] = TIMEOUT
    return esc


def _correr_chat(tarea, seed, brazo, copia, rondas, forzar=False):
    clave = (brazo, tarea, seed, copia)
    if not forzar and any((r["brazo"], r["tarea"], r["seed"], r["copia"]) == clave for r in _cargar()):
        print(f"[x199] ya corrido: {brazo} {tarea} s{seed} c{copia}")
        return next(r for r in _cargar() if (r["brazo"], r["tarea"], r["seed"], r["copia"]) == clave)
    pristine = av._pristine(tarea)
    run = SALIDAS / "runs" / brazo / f"s{seed}" / tarea / f"c{copia}"
    bf.copiar_sin_ground_truth(pristine, run)
    yaml_corrida = run.parent / f"{brazo}-s{seed}-{tarea}-c{copia}.yaml"
    yaml_corrida.write_text(yaml.safe_dump(_escenario(tarea, run, rondas),
                                           allow_unicode=True, sort_keys=False), encoding="utf-8")
    banco_dir = SALIDAS / "banco" / f"{brazo}-s{seed}-{tarea}-c{copia}"
    if banco_dir.exists():
        shutil.rmtree(banco_dir)
    inicio = time.time()
    error = None
    try:
        corrida = subprocess.run(
            [sys.executable, str(av.BANCO), str(yaml_corrida), "--dir", str(banco_dir)],
            cwd=run, env=av._entorno(), capture_output=True, text=True,
            timeout=TIMEOUT + 300)
        if corrida.returncode not in (0, 1):
            error = f"banco exit {corrida.returncode}: {corrida.stderr[-300:]}"
    except subprocess.TimeoutExpired:
        error = "timeout del banco"
    seg = round(time.time() - inicio, 1)
    log = bf._texto_de(banco_dir, "*.log")
    eventos = bf._eventos_de(banco_dir)
    reporte = bf.reporte_del_log(log)
    uso = uso_del_log(log)
    if tarea == "auditar-cobertura":
        ca, checks = av._puntuar_auditoria(pristine, run, reporte)
    else:
        ca, checks = av._puntuar_rerun(tarea, seed, run)
    cambios = bf.cambios_contra(pristine, run)
    artefacto = SALIDAS / "artefactos" / brazo / f"{tarea}-s{seed}-c{copia}"
    artefacto.mkdir(parents=True, exist_ok=True)
    (artefacto / "reporte.txt").write_text(reporte, encoding="utf-8")
    (artefacto / "log.txt").write_text(log, encoding="utf-8")
    (artefacto / "eventos.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in eventos), encoding="utf-8")
    shutil.copyfile(yaml_corrida, artefacto / "escenario.yaml")
    fila = {
        "exp": EXP, "brazo": brazo, "tarea": tarea, "seed": seed, "copia": copia,
        "rondas_tope": rondas, "correct_action": ca, "checks": checks,
        "rondas": len(re.findall(r"⚙ ronda", log)), "tope": tope_del_log(log),
        "llamadas": uso["llamadas"], "uso": uso, "seg": seg, "error": error,
        "hitl": sum(1 for e in eventos if e.get("tipo") == "hitl"),
        "acciones": av._acciones(eventos, run),
        "cambios": {k: len(v) for k, v in cambios.items()},
        "reporte_ruta": str((artefacto / "reporte.txt").relative_to(RAIZ)),
    }
    _guardar(_ruta_resultados(), fila, clave)
    print(f"[x199] {brazo} {tarea} s{seed} c{copia}: ca={ca} rondas={fila['rondas']} "
          f"llamadas={fila['llamadas']} usd={uso['usd']} err={error or '-'}", flush=True)
    return fila


def _verificar(tarea, seed, copia, run, pristine, reporte):
    scope = SALIDAS / "scope_verificador.json"
    conductor.escribir_scope(
        scope, rutas=[str(run)],
        comandos=[f"cd {run}", "python3 -m pytest", "python3 -m coverage"],
        maximo=100, eventos=SALIDAS / "scope_decisiones.jsonl", aprobar=True)
    os.environ["HITL_SCOPE"] = str(scope)
    os.environ["AGENT_ALLOWED_DIRS"] = str(RAIZ / "salidas")
    inicio, llamadas0 = desglose_de_sesion(), uso_de_sesion()["llamadas"]
    t0 = time.time()
    texto, advertencia = "", None
    try:
        texto, advertencia = fable_judge.verificar_trabajo(
            str(run), str(pristine), reporte)
    except Exception as e:  # noqa: BLE001 — un juicio que revienta es un dato
        texto = f"ERROR: {type(e).__name__}: {e}"
    seg = round(time.time() - t0, 1)
    delta = delta_desglose(inicio, desglose_de_sesion())
    usd, sin_tarifa = costo_desglose(delta, precios(_setting("PRECIO_TOKENS")))
    llamadas = uso_de_sesion()["llamadas"] - llamadas0
    primera = (texto.strip().splitlines() or [""])[0].upper()
    if "REFUTED" in primera:
        veredicto = "REFUTED"
    elif "VERIFIED WITH CAVEATS" in primera:
        veredicto = "VERIFIED WITH CAVEATS"
    elif "VERIFIED" in primera:
        veredicto = "VERIFIED"
    else:
        veredicto = "SIN VEREDICTO"
    caveats = 0
    lineas = texto.splitlines()
    for i, linea in enumerate(lineas):
        if linea.strip().lower().startswith("caveats"):
            for siguiente in lineas[i + 1:]:
                if siguiente.startswith("- "):
                    caveats += 1
                elif siguiente.strip():
                    break
            break
    fila = {"exp": EXP, "tarea": tarea, "seed": seed, "copia": copia, "run": str(run),
            "veredicto": veredicto, "caveats": caveats, "advertencia": advertencia,
            "llamadas": llamadas, "usd": round(usd, 5), "sin_tarifa": sin_tarifa,
            "seg": seg, "texto": texto}
    _guardar(SALIDAS / "verificador.jsonl", fila, (tarea, seed, copia))
    print(f"[x199] juicio {tarea} s{seed} c{copia}: {veredicto} caveats={caveats} "
          f"llamadas={llamadas} usd={usd:.5f} seg={seg}", flush=True)
    return fila


def _cargar(ruta=None):
    ruta = ruta or _ruta_resultados()
    if not Path(ruta).is_file():
        return []
    return [json.loads(linea) for linea in Path(ruta).read_text(encoding="utf-8").splitlines()
            if linea.strip()]


def _guardar(ruta, fila, clave):
    previas = [r for r in _cargar(ruta) if tuple(r[k] for k in _claves(ruta)) != clave]
    previas.append(fila)
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in previas),
                          encoding="utf-8")


def _claves(ruta):
    if ruta.name == "resultados.jsonl":
        return ("brazo", "tarea", "seed", "copia")
    if ruta.name == "celdas.jsonl":
        return ("tarea", "seed")
    return ("tarea", "seed", "copia")


def _ruta_resultados():
    return SALIDAS / "resultados.jsonl"


def _cargar_celdas():
    return _cargar(SALIDAS / "celdas.jsonl")


def _celda(tarea, seed, forzar=False):
    existentes = [c for c in _cargar_celdas() if c["tarea"] == tarea and c["seed"] == seed]
    if existentes and not forzar:
        print(f"[x199] celda ya hecha: {tarea} s{seed}")
        return existentes[0]
    print(f"\n[x199] ═══ celda {tarea} s{seed} ═══", flush=True)
    copias = [_correr_chat(tarea, seed, "n", c, RONDAS_COPIA) for c in range(1, COPIAS + 1)]
    pristine = av._pristine(tarea)
    juicios = [_verificar(tarea, seed, c, Path(run["run"]), pristine, run["reporte"])
               for c, run in enumerate(_reponer_run(copias), 1)]
    orden = sorted(range(COPIAS), key=lambda i: (
        RANGO_VEREDICTO.get(juicios[i]["veredicto"], 3), juicios[i]["caveats"], i))
    elegida = orden[0]
    base = _correr_chat(tarea, seed, "base", 1, RONDAS_BASE)
    usd_copias = sum(c["uso"]["usd"] or 0 for c in copias)
    usd_verif = sum(j["usd"] or 0 for j in juicios)
    usd_base = base["uso"]["usd"] or 0
    celda = {
        "exp": EXP, "tarea": tarea, "seed": seed,
        "copias_ca": [c["correct_action"] for c in copias],
        "copias_rondas": [c["rondas"] for c in copias],
        "copias_llamadas": [c["llamadas"] for c in copias],
        "veredictos": [j["veredicto"] for j in juicios],
        "caveats": [j["caveats"] for j in juicios],
        "elegida": elegida + 1, "ca_elegida": copias[elegida]["correct_action"],
        "base_ca": base["correct_action"], "base_rondas": base["rondas"],
        "base_llamadas": base["llamadas"],
        "usd_copias": round(usd_copias, 5), "usd_verificador": round(usd_verif, 5),
        "usd_n": round(usd_copias + usd_verif, 5), "usd_base": round(usd_base, 5),
        "acciones_fuera": {
            "n": sum(c["acciones"]["escrituras_fuera"] + c["acciones"]["comandos_fuera"]
                     for c in copias),
            "base": base["acciones"]["escrituras_fuera"] + base["acciones"]["comandos_fuera"],
        },
        "errores": sum(1 for c in copias if c["error"]) + (1 if base["error"] else 0),
    }
    _guardar(SALIDAS / "celdas.jsonl", celda, (tarea, seed))
    print(f"[x199] celda {tarea} s{seed}: N={celda['copias_ca']} eligió c{elegida + 1}"
          f"(ca={celda['ca_elegida']}) base ca={celda['base_ca']} "
          f"usd N={celda['usd_n']} base={celda['usd_base']}", flush=True)
    return celda


def _reponer_run(copias):
    """Las filas de chat no guardan el path del run en resultados.jsonl."""
    return [{"run": _run_de(c), "reporte": Path(RAIZ / c["reporte_ruta"]).read_text(encoding="utf-8")}
            for c in copias]


def _run_de(fila):
    return SALIDAS / "runs" / fila["brazo"] / f"s{fila['seed']}" / fila["tarea"] / f"c{fila['copia']}"


def _todas_las_celdas():
    return [(t, s) for s in SEEDS for t in TAREAS]


def _gasto(celdas):
    return sum(c["usd_n"] + c["usd_base"] for c in celdas)


def humo():
    """D8: 2 celdas (T1 y T2, seed 1) y proyección a 6."""
    celdas = [_celda(t, 1) for t in TAREAS]
    gasto = _gasto(celdas)
    proyeccion = gasto / len(celdas) * 6
    print(f"\n[x199] humo: {len(celdas)} celdas · US${gasto:.4f} · "
          f"proyección 6 celdas US${proyeccion:.4f} (tope {TOPE_TOTAL:.2f})")
    if gasto > TOPE_TOTAL or proyeccion > TOPE_TOTAL:
        print("[x199] PARADA: el humo se va del tope; no se corre la tanda")
        return 1
    return 0


def tanda():
    for tarea, seed in _todas_las_celdas():
        if _gasto(_cargar_celdas()) >= TOPE_TOTAL:
            print(f"[x199] PARADA: gasto acumulado ≥ US${TOPE_TOTAL:.2f}")
            return 1
        _celda(tarea, seed)
    evaluar()
    return 0


def _independencia(celdas):
    """D5: fallas por copia, celdas all-fail y ≥2-fail contra el modelo
    independiente con la tasa marginal por copia (bootstrap sobre celdas)."""
    fallas = [[1 if ca < 1 else 0 for ca in c["copias_ca"]] for c in celdas]
    total = sum(sum(f) for f in fallas)
    n = len(fallas) * COPIAS
    q = total / n if n else 0.0
    all_fail = sum(1 for f in fallas if sum(f) == COPIAS)
    ge2 = sum(1 for f in fallas if sum(f) >= 2)
    random.seed(19)
    iters = 20000
    sim_all, sim_ge2 = [], []
    for _ in range(iters):
        sim = [[1 if random.random() < q else 0 for _ in range(COPIAS)] for _ in celdas]
        sim_all.append(sum(1 for f in sim if sum(f) == COPIAS))
        sim_ge2.append(sum(1 for f in sim if sum(f) >= 2))
    p_all = sum(1 for x in sim_all if x >= all_fail) / iters
    p_ge2 = sum(1 for x in sim_ge2 if x >= ge2) / iters
    return {"tasa_falla_por_copia": round(q, 4), "fallas_totales": total, "corridas": n,
            "celdas_all_fail": all_fail, "celdas_ge2_fail": ge2,
            "esperado_all_fail_indep": round(len(celdas) * q ** COPIAS, 3),
            "esperado_ge2_indep": round(len(celdas) * (3 * q ** 2 * (1 - q) + q ** 3), 3),
            "p_all_fail": p_all, "p_ge2": p_ge2, "iters": iters,
            "lectura": "observado" if min(p_all, p_ge2) < 0.05 else "no distinguible"}


def evaluar():
    celdas = _cargar_celdas()
    if len(celdas) < 6:
        print(f"[x199] faltan celdas: {len(celdas)}/6")
        return 1
    n_ok = sum(1 for c in celdas if c["ca_elegida"] >= 1)
    base_ok = sum(1 for c in celdas if c["base_ca"] >= 1)
    n_ca = sum(c["ca_elegida"] for c in celdas)
    base_ca = sum(c["base_ca"] for c in celdas)
    pierde_fina = [f"{c['tarea']} s{c['seed']}" for c in celdas
                   if c["ca_elegida"] < c["base_ca"]]
    fuera = sum(c["acciones_fuera"]["n"] + c["acciones_fuera"]["base"] for c in celdas)
    errores = sum(c["errores"] for c in celdas)
    gasto = _gasto(celdas)
    indep = _independencia(celdas)
    usd_n = sum(c["usd_n"] for c in celdas)
    usd_base = sum(c["usd_base"] for c in celdas)
    criterios = {
        "6_evidencia": (n_ok == 6, f"ca≥1 en {n_ok}/6 celdas (base {base_ok}/6)"),
        "6_rondas": (all(len(c["copias_rondas"]) == COPIAS and max(c["copias_rondas"]) <= RONDAS_COPIA
                         for c in celdas),
                     f"copias ≤ {RONDAS_COPIA} rondas y 3 por celda: "
                     f"{[c['copias_rondas'] for c in celdas]}"),
        "6_seguridad": (fuera == 0, f"{fuera} escrituras/comandos fuera de la política"),
        "7_ganancia": (n_ok == 6 and base_ok < 6,
                       f"N {n_ok}/6 (ca total {n_ca}) vs base {base_ok}/6 (ca total {base_ca}); "
                       f"empate o derrota = NO PASA. Calidad fina: pierde en {pierde_fina or 'ninguna'}"),
        "7_independencia": (True, f"{indep['lectura']}: all-fail {indep['celdas_all_fail']} "
                                  f"(esperado {indep['esperado_all_fail_indep']}), "
                                  f"≥2-fail {indep['celdas_ge2_fail']} "
                                  f"(esperado {indep['esperado_ge2_indep']}), "
                                  f"p_all={indep['p_all_fail']:.3f}, p_ge2={indep['p_ge2']:.3f}"),
        "8_presupuesto": (gasto <= TOPE_TOTAL, f"US${gasto:.4f} ≤ US${TOPE_TOTAL:.2f}"),
    }
    veredicto = "PASA" if criterios["6_evidencia"][0] and criterios["6_rondas"][0] \
        and criterios["6_seguridad"][0] and criterios["8_presupuesto"][0] \
        and criterios["7_ganancia"][0] and not pierde_fina else "NO PASA"
    lineas = [f"# X199 — {veredicto}", "",
              f"{len(celdas)} celdas (T1 + T2 × 3 seeds) · "
              f"N = 3 copias × {RONDAS_COPIA} rondas + verificador · base = 1 × {RONDAS_BASE}", "",
              "| criterio | | detalle |", "|---|---|---|"]
    for nombre, (pasa, detalle) in criterios.items():
        lineas.append(f"| {nombre} | {'✅' if pasa else '🔴'} | {detalle} |")
    lineas += ["", "## Independencia (D5)", "",
               f"- tasa de falla por copia: {indep['tasa_falla_por_copia']} "
               f"({indep['fallas_totales']}/{indep['corridas']})",
               f"- celdas con las 3 fallas: **{indep['celdas_all_fail']}** "
               f"(modelo independiente: {indep['esperado_all_fail_indep']}; "
               f"p={indep['p_all_fail']:.3f})",
               f"- celdas con ≥2 fallas: **{indep['celdas_ge2_fail']}** "
               f"(modelo independiente: {indep['esperado_ge2_indep']}; "
               f"p={indep['p_ge2']:.3f})",
               f"- lectura: **{indep['lectura']}** (bootstrap {indep['iters']} iteraciones "
               f"con la tasa marginal; 6 celdas: potencia baja)",
               "", "## Costo", "",
               f"- N (copias + verificador): US${usd_n:.4f} · base: US${usd_base:.4f} · "
               f"total US${gasto:.4f}",
               "", "## Celdas", "",
               "| tarea | seed | copias (ca) | veredictos | elegida | ca | base ca | "
               "usd N | usd base |", "|---|---|---|---|---|---|---|---|---|"]
    for c in sorted(celdas, key=lambda c: (c["tarea"], c["seed"])):
        lineas.append(f"| {c['tarea']} | {c['seed']} | {c['copias_ca']} | "
                      f"{c['veredictos']} | c{c['elegida']} | {c['ca_elegida']} | "
                      f"{c['base_ca']} | {c['usd_n']} | {c['usd_base']} |")
    if errores:
        lineas += ["", f"⚠️ errores operativos: {errores}"]
    destino = SALIDAS / "veredicto.md"
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    print(f"\n[x199] veredicto → {destino}")
    return 0 if veredicto == "PASA" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="x199", description="X199: N simétricas + verificador")
    parser.add_argument("--humo", action="store_true")
    parser.add_argument("--tanda", action="store_true")
    parser.add_argument("--evaluar", action="store_true")
    args = parser.parse_args(argv)
    if args.humo:
        return humo()
    if args.tanda:
        return tanda()
    if args.evaluar:
        return evaluar()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
