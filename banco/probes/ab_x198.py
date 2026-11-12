"""A/B X198 (criterios 9–10): el catálogo y las tools mínimas del CORE.

Pre-registro: `banco/specs/x198_catalogo.md` (D5=A, D6=A). Reutiliza el
instrumento de X204 (`banco/probes/ab_x204.py`: mismos helpers de entorno,
traza y seguridad; mismo método de corrida y grading con
`banco/bench_supervisor.py`), adaptado a dos brazos **commiteados**:

- base: `git archive 54bfd54` (X197b, 30 tools en el request).
- catalogo: `git archive faac7a7` (X198, 5 tools: 3 del CORE + `catalogo` +
  `usar`; el modelo llega a `run_supervisor` por `usar`).

36 corridas (6 tareas × 3 seeds × 2 brazos), una a la vez, humo primero,
tope US$0,30. El brazo catálogo tiene que dar 18/18 y adoptar `run_supervisor`
en las 18 (medido: evento `usar` en la traza + el supervisor corrió); las
llamadas se declaran contra la base con la tolerancia de +2 por corrida
(el pre-registro dice "por tarea": se declara la lectura).

Desvío declarado ANTES de correr (el mismo de X204): `trazas.db` y
`salidas/routing.jsonl` se copian idénticos a los dos brazos para que las dos
tareas de artefactos sean evaluables; denominador 18 por brazo, simétrico.

Uso:
    python3 banco/probes/ab_x198.py --preparar
    python3 banco/probes/ab_x198.py --humo
    python3 banco/probes/ab_x198.py --tanda
    python3 banco/probes/ab_x198.py --evaluar
"""
import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "banco"))
sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import ab_x204 as previo  # noqa: E402  (helpers compartidos del A/B de X204)
import bench_fable as bf  # noqa: E402
import bench_supervisor as bs  # noqa: E402
import yaml  # noqa: E402
from s6 import tope_del_log, uso_del_log  # noqa: E402

EXP = "x198_ab"
BASE_SHA = "54bfd54"
BRAZO_SHA = "faac7a7"
SALIDAS = RAIZ / "salidas" / EXP
ARMS = SALIDAS / "arms"
BRAZOS = ("base", "catalogo")
SEEDS = (1, 2, 3)
RONDAS = 8
TIMEOUT = 420
TOPE_HUMO = 0.05
TOPE_TOTAL = 0.30
TOLERANCIA_LLAMADAS = 2
RECURSOS = (("trazas.db", "trazas.db"), ("salidas/routing.jsonl", "salidas/routing.jsonl"))


def _tareas():
    ruta = RAIZ / "banco" / "supervisor_tareas.jsonl"
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()
            if linea.strip()]


def _copiar_recurso(brazo):
    for origen, destino in RECURSOS:
        ruta = ARMS / brazo / destino
        ruta.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RAIZ / origen, ruta)


def preparar(forzar=False):
    """Los dos brazos, desde los commits: base 54bfd54, catalogo faac7a7."""
    if ARMS.is_dir() and not forzar:
        print(f"[ab_x198] brazos ya preparados en {ARMS}")
        return
    if ARMS.is_dir():
        shutil.rmtree(ARMS)
    for brazo, sha in (("base", BASE_SHA), ("catalogo", BRAZO_SHA)):
        tar = subprocess.run(["git", "archive", "--format=tar", sha],
                             cwd=RAIZ, capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(tar)) as archivo:
            archivo.extractall(ARMS / brazo)
        _copiar_recurso(brazo)
        print(f"[ab_x198] {brazo} = {sha}")
    print(f"[ab_x198] brazos listos: base={BASE_SHA} · catalogo={BRAZO_SHA} "
          f"· recursos copiados (trazas.db, salidas/routing.jsonl)")


def _escenario(run, tarea):
    return {
        "id": f"x198-{tarea['id']}",
        "descripcion": f"A/B X198 {tarea['id']}",
        "env": {
            "AGENT_ALLOWED_DIRS": str(run),
            "MEMORIA": "0",
            "MAX_TOOL_ROUNDS": str(RONDAS),
            "SKILLS": "0",
            "TRACE": "1",
            "HUMANO_RESPUESTA": bf.RESPUESTA_HUMANO_OFFLINE,
            "PATH": bf._python_shim(),
        },
        "permitir": [str(run)],
        "permitir_comandos": [f"cd {run}"],
        "turnos": [
            {"id": "tarea", "linea": f"usá run_supervisor para: {tarea['tarea']} {bf.OFFLINE}",
             "hitl": "s", "timeout": TIMEOUT, "max_hitl": 20},
            {"id": "salir", "linea": "salir", "timeout": 60},
        ],
    }


def _cambios(brazo, run):
    """Lo que el agente tocó, fuera de `salidas/` y de las cachés."""
    def huellas(base):
        return {
            p.relative_to(base).as_posix(): hash(p.read_bytes())
            for p in sorted(base.rglob("*"))
            if p.is_file()
            and not p.relative_to(base).as_posix().startswith(("salidas/", ".runs/", "__pycache__/",
                                                               ".pytest_cache/", ".ruff_cache/"))
            and "__pycache__/" not in p.relative_to(base).as_posix()
            and not p.name.endswith(".pyc")
            and p.name != "GROUND-TRUTH.md"
        }
    a, b = huellas(ARMS / brazo), huellas(run)
    return {
        "modificados": sorted(k for k in a.keys() & b.keys() if a[k] != b[k]),
        "nuevos": sorted(b.keys() - a.keys()),
        "borrados": sorted(a.keys() - b.keys()),
    }


def _adopcion(log, trazas):
    """(adopción, `usar`s, `catalogo`s, supervisor corrió).

    En el brazo catálogo la única vía a `run_supervisor` es `usar`; el
    supervisor corrió si dejó sus nodos en la traza (`Auditar`/`Sintetizar`) o
    su línea de síntesis en el log. En la base, el chat lo llamaba directo."""
    usos = sum(1 for e in trazas if e.get("nodo") == "usar")
    catalogos = sum(1 for e in trazas if e.get("nodo") == "catalogo")
    directo = sum(1 for e in trazas if e.get("nodo") == "run_supervisor")
    supervisor = ("síntesis escrita" in log
                  or any(e.get("nodo") == "Auditar" for e in trazas)
                  or any(e.get("nodo") == "Sintetizar" for e in trazas))
    return (supervisor and (usos >= 1 or directo >= 1), usos, catalogos, supervisor)


def _ruta_resultados():
    return SALIDAS / "resultados.jsonl"


def _cargar():
    ruta = _ruta_resultados()
    if not ruta.is_file():
        return []
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()
            if linea.strip()]


def _guardar(fila):
    previas = [r for r in _cargar()
               if (r["brazo"], r["tarea"], r["seed"]) != (fila["brazo"], fila["tarea"], fila["seed"])]
    previas.append(fila)
    _ruta_resultados().parent.mkdir(parents=True, exist_ok=True)
    _ruta_resultados().write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in previas), encoding="utf-8")


def correr_uno(brazo, tarea, seed, forzar=False):
    if not forzar and any(r["brazo"] == brazo and r["tarea"] == tarea["id"] and r["seed"] == seed
                          for r in _cargar()):
        print(f"[ab_x198] ya corrido: {brazo} {tarea['id']} s{seed}")
        return None
    run = SALIDAS / "runs" / f"{brazo}-s{seed}-{tarea['id']}"
    if run.exists():
        shutil.rmtree(run)
    bf.copiar_sin_ground_truth(ARMS / brazo, run)
    yaml_corrida = SALIDAS / "yaml" / f"{brazo}-s{seed}-{tarea['id']}.yaml"
    yaml_corrida.parent.mkdir(parents=True, exist_ok=True)
    yaml_corrida.write_text(yaml.safe_dump(_escenario(run, tarea), allow_unicode=True,
                                           sort_keys=False), encoding="utf-8")
    banco_dir = SALIDAS / "banco" / f"{brazo}-s{seed}-{tarea['id']}"
    if banco_dir.exists():
        shutil.rmtree(banco_dir)
    inicio = time.time()
    error = None
    try:
        corrida = subprocess.run(
            [sys.executable, str(run / "banco" / "banco.py"), str(yaml_corrida),
             "--dir", str(banco_dir)],
            cwd=run, env=previo._entorno(), capture_output=True, text=True,
            timeout=TIMEOUT + 300)
        if corrida.returncode not in (0, 1):
            error = f"banco exit {corrida.returncode}: {corrida.stderr[-300:]}"
    except subprocess.TimeoutExpired:
        error = "timeout del banco"
    seg = round(time.time() - inicio, 1)
    log = bf._texto_de(banco_dir, "*.log")
    eventos = bf._eventos_de(banco_dir)
    reporte = bf.reporte_del_log(log)
    trazas = previo._trazas(run)
    llamadas_arbol = sum(1 for e in trazas if e.get("nodo") == "llm")
    adopcion, usos, catalogos, supervisor = _adopcion(log, trazas)
    denegados = len(previo.RE_DENEGADO.findall(log))
    # HITL_AUTO aprueba lecturas sin pasar por la decisión del scope:
    # se cuentan del transcript (todas read-only y dentro de la copia).
    comandos_auto = len(re.findall(r"── run_command \[auto: solo-lectura\]", log))
    uso = uso_del_log(log)
    # Grading con el bench: la verdad de cada tarea se calcula sobre el brazo.
    bs.RAIZ = ARMS / brazo
    ok = bs.verificar(tarea["id"], reporte)
    cambios = _cambios(brazo, run)
    artefacto = SALIDAS / "artefactos" / brazo / f"{tarea['id']}-s{seed}"
    artefacto.mkdir(parents=True, exist_ok=True)
    (artefacto / "reporte.txt").write_text(reporte, encoding="utf-8")
    (artefacto / "log.txt").write_text(log, encoding="utf-8")
    (artefacto / "eventos.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in eventos), encoding="utf-8")
    (artefacto / "trazas.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in trazas), encoding="utf-8")
    shutil.copyfile(yaml_corrida, artefacto / "escenario.yaml")
    fila = {
        "exp": EXP, "brazo": brazo, "tarea": tarea["id"], "seed": seed,
        "ok": ok, "error": error, "seg": seg,
        "uso": uso, "tope": tope_del_log(log), "rondas": len(re.findall(r"⚙ ronda", log)),
        "llamadas_arbol": llamadas_arbol, "adopcion": adopcion,
        "usos": usos, "catalogos": catalogos, "supervisor": supervisor,
        "denegados_anidados": denegados,
        "hitl": sum(1 for e in eventos if e.get("tipo") == "hitl"),
        "comandos_auto": comandos_auto,
        "acciones": previo._acciones(eventos, run), "cambios": cambios,
        "reporte_ruta": str((artefacto / "reporte.txt").relative_to(RAIZ)),
    }
    _guardar(fila)
    shutil.rmtree(run)
    print(f"[ab_x198] {brazo} {tarea['id']} s{seed}: ok={ok} usd={uso['usd']} "
          f"llamadas={llamadas_arbol} usar={usos} catalogo={catalogos} "
          f"adopcion={adopcion} supervisor={supervisor} seg={seg} err={error or '-'}",
          flush=True)
    return fila


def _gasto(filas):
    return sum(f["uso"]["usd"] or 0 for f in filas)


def humo():
    tarea = next(t for t in _tareas() if t["id"] == "constante-max-pasos")
    for brazo in BRAZOS:
        correr_uno(brazo, tarea, 1)
    filas = [f for f in _cargar() if f["tarea"] == tarea["id"] and f["seed"] == 1]
    total = _gasto(filas)
    print(f"[ab_x198] humo: {len(filas)} corridas · US${total:.4f} · "
          f"proyección 36 corridas US${total / 2 * 36:.4f}")
    if total > TOPE_HUMO:
        print(f"[ab_x198] PARADA: el humo pasó US${TOPE_HUMO:.2f}; no se corre la tanda")
        return 1
    return 0


def tanda():
    acumulado = _gasto(_cargar())
    for seed in SEEDS:
        for tarea in _tareas():
            for brazo in BRAZOS:
                if acumulado >= TOPE_TOTAL:
                    print(f"[ab_x198] PARADA: gasto acumulado ≥ US${TOPE_TOTAL:.2f}")
                    return 1
                fila = correr_uno(brazo, tarea, seed)
                if fila is not None:
                    acumulado += fila["uso"]["usd"] or 0
    evaluar()
    return 0


def _por_brazo(filas, brazo):
    sub = [f for f in filas if f["brazo"] == brazo]
    evaluables = [f for f in sub if f["ok"] is not None]
    usd = [f["uso"]["usd"] for f in sub if f["uso"]["usd"] is not None]
    return {
        "corridas": len(sub), "evaluables": len(evaluables),
        "saltadas": len(sub) - len(evaluables),
        "aciertos": sum(1 for f in evaluables if f["ok"] is True),
        "adopcion": sum(1 for f in sub if f["adopcion"]),
        "usos": sum(f["usos"] for f in sub),
        "catalogos": sum(f["catalogos"] for f in sub),
        "usd_total": round(sum(usd), 4) if usd else None,
        "usd_media": round(sum(usd) / len(usd), 4) if usd else None,
        "llamadas": sum(f["llamadas_arbol"] for f in sub),
        "llamadas_max": max((f["llamadas_arbol"] for f in sub), default=0),
        "escrituras_fuera": sum(f["acciones"]["escrituras_fuera"] for f in sub),
        "comandos_fuera": sum(f["acciones"]["comandos_fuera"] for f in sub),
        "fuera_de_alcance": sum(f["acciones"]["fuera_de_alcance"] for f in sub),
        "errores": sum(1 for f in sub if f["error"]),
    }


def _deltas_llamadas(filas):
    """Delta de llamadas (catalogo − base) por corrida y por tarea (3 seeds)."""
    pares = {}
    for f in filas:
        pares.setdefault((f["tarea"], f["seed"]), {})[f["brazo"]] = f
    por_corrida = []
    for (tarea, seed), v in sorted(pares.items()):
        if "base" in v and "catalogo" in v:
            por_corrida.append((tarea, seed,
                                v["catalogo"]["llamadas_arbol"] - v["base"]["llamadas_arbol"]))
    por_tarea = {}
    for tarea, _, d in por_corrida:
        por_tarea.setdefault(tarea, []).append(d)
    return por_corrida, {k: sum(v) for k, v in por_tarea.items()}


def evaluar():
    filas = _cargar()
    if not filas:
        print("[ab_x198] no hay resultados")
        return 1
    resumen = {brazo: _por_brazo(filas, brazo) for brazo in BRAZOS}
    base, arm = resumen["base"], resumen["catalogo"]
    deltas, deltas_tarea = _deltas_llamadas(filas)
    peor = max((d for _, _, d in deltas), default=0)
    criterios = {
        "9_calidad": (arm["aciertos"] == arm["evaluables"] == 18
                      and base["aciertos"] == base["evaluables"] == 18,
                      f"catalogo {arm['aciertos']}/{arm['evaluables']} vs base "
                      f"{base['aciertos']}/{base['evaluables']}"),
        "9_adopcion": (arm["adopcion"] == 18 and arm["usos"] >= 18,
                       f"supervisor vía usar en {arm['adopcion']}/18 "
                       f"({arm['usos']} usar, {arm['catalogos']} catalogo)"),
        "9_seguridad": (arm["escrituras_fuera"] == 0 and arm["comandos_fuera"] == 0
                        and base["escrituras_fuera"] == 0 and base["comandos_fuera"] == 0,
                        f"escrituras fuera {arm['escrituras_fuera']}/{base['escrituras_fuera']} · "
                        f"comandos fuera {arm['comandos_fuera']}/{base['comandos_fuera']} "
                        f"(catalogo/base); hooks: cubiertos por el test estructural"),
        "9_llamadas": (peor <= TOLERANCIA_LLAMADAS,
                       f"máx delta por corrida +{peor} (tolerancia +{TOLERANCIA_LLAMADAS}); "
                       f"por tarea: {deltas_tarea}"),
        "10_presupuesto": (arm["usd_total"] is not None and base["usd_total"] is not None
                           and arm["usd_total"] + base["usd_total"] <= TOPE_TOTAL,
                           f"gasto total US${round((arm['usd_total'] or 0) + (base['usd_total'] or 0), 4)} "
                           f"≤ US${TOPE_TOTAL:.2f}"),
    }
    veredicto = "PASA" if all(v[0] for v in criterios.values()) else "NO PASA"
    lineas = [f"# A/B X198 — {veredicto}", "",
              f"base = `{BASE_SHA}` · catalogo = `{BRAZO_SHA}` · {len(filas)} corridas "
              f"({base['corridas']} + {arm['corridas']})", "",
              "| criterio | | detalle |", "|---|---|---|"]
    for nombre, (pasa, detalle) in criterios.items():
        lineas.append(f"| {nombre} | {'✅' if pasa else '🔴'} | {detalle} |")
    lineas += ["", "## Por brazo", "",
               "| brazo | aciertos/evaluables | adopción | usar | catálogo | US$ total | "
               "US$ media | llamadas | máx |",
               "|---|---|---|---|---|---|---|---|---|"]
    for brazo in BRAZOS:
        m = resumen[brazo]
        lineas.append(f"| {brazo} | {m['aciertos']}/{m['evaluables']} | {m['adopcion']} | "
                      f"{m['usos']} | {m['catalogos']} | {m['usd_total']} | {m['usd_media']} | "
                      f"{m['llamadas']} | {m['llamadas_max']} |")
    lineas += ["", "## Llamadas por corrida (catalogo − base)", "",
               "| tarea | seed | delta |", "|---|---|---|"]
    for tarea, seed, d in deltas:
        lineas.append(f"| {tarea} | {seed} | {d:+d} |")
    lineas += ["", "## Corridas", "",
               "| brazo | tarea | seed | ok | US$ | llamadas | usar | catálogo | adopción |",
               "|---|---|---|---|---|---|---|---|---|"]
    for f in sorted(filas, key=lambda f: (f["brazo"], f["tarea"], f["seed"])):
        lineas.append(f"| {f['brazo']} | {f['tarea']} | {f['seed']} | "
                      f"{'✅' if f['ok'] is True else ('🔴' if f['ok'] is False else '－')} | "
                      f"{f['uso']['usd']} | {f['llamadas_arbol']} | {f['usos']} | "
                      f"{f['catalogos']} | {f['adopcion']} |")
    destino = SALIDAS / "veredicto.md"
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    print(f"\n[ab_x198] veredicto → {destino}")
    return 0 if veredicto == "PASA" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ab_x198", description="A/B X198 (criterios 9–10)")
    parser.add_argument("--preparar", action="store_true", help="arma los dos brazos desde los commits")
    parser.add_argument("--forzar-armado", action="store_true", help="reasienta los brazos")
    parser.add_argument("--humo", action="store_true")
    parser.add_argument("--tanda", action="store_true")
    parser.add_argument("--evaluar", action="store_true")
    args = parser.parse_args(argv)
    if args.preparar or args.forzar_armado:
        preparar(forzar=args.forzar_armado)
        return 0
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
