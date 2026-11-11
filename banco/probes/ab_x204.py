"""A/B X204 (criterios 7–11): `run_supervisor` como copia del kernel, pedido
desde el chat — pre-registro `banco/specs/x204_supervisor_copia.md`.

Brazos (copias aparte, no tocan `main`):
- base: `git archive 4c70c63` (X195 sin el brazo).
- x204: ese mismo árbol + el diff de trabajo (el brazo, sin commitear).
El chat de cada brazo corre en una copia por corrida (`salidas/x204_ab/runs/`)
con el turno `usá run_supervisor para: <tarea>` + el offline de `bench_fable`,
y se gradúa con `banco/bench_supervisor.py` (el mismo archivo en los dos
brazos: no lo toca el brazo).

Desvío declarado ANTES de correr: `trazas.db` y `salidas/routing.jsonl` se
copian idénticos a los dos brazos para que las 6 tareas sean evaluables (la
spec las salta sin recurso). Denominador: 18 corridas por brazo, simétrico.

Métrica de cada corrida: calidad (`verificar` del bench), costo (línea
`[tokens] sesión`), llamadas del árbol (eventos `llm` de `.runs`, Ley 1),
adopción (llamada del chat a `run_supervisor`: evento `tool` en `.runs`),
seguridad (escrituras/comandos ok fuera de la copia o del scope) y recursión
anidada (intentos negados por `Ctx.negar`, línea `✗ paso erróneo … de
run_supervisor` en el log; no se ejecutan).

Uso:
    python3 banco/probes/ab_x204.py --preparar
    python3 banco/probes/ab_x204.py --humo
    python3 banco/probes/ab_x204.py --tanda
    python3 banco/probes/ab_x204.py --evaluar
"""
import argparse
import io
import json
import os
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

import bench_fable as bf  # noqa: E402
import bench_supervisor as bs  # noqa: E402
from s6 import tope_del_log, uso_del_log  # noqa: E402

from utils.call_llm import PROJECT_ENV, _from_env_file  # noqa: E402

EXP = "x204_ab"
BASE_SHA = "4c70c63"
SALIDAS = RAIZ / "salidas" / EXP
ARMS = SALIDAS / "arms"
BRAZOS = ("base", "x204")
SEEDS = (1, 2, 3)
RONDAS = 8
TIMEOUT = 420
TOPE_HUMO = 0.05
TOPE_TOTAL = 0.70
RECURSOS = (("trazas.db", "trazas.db"), ("salidas/routing.jsonl", "salidas/routing.jsonl"))
RE_DENEGADO = re.compile(r"✗ paso erróneo \(\d+/\d+ de run_supervisor\)")


def _tareas():
    """Las 6 tareas de `banco/supervisor_tareas.jsonl`, con su verificación."""
    ruta = RAIZ / "banco" / "supervisor_tareas.jsonl"
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()
            if linea.strip()]


def _entorno():
    """El entorno del banco: la clave viaja por variable, no en la copia (X176)."""
    entorno = dict(os.environ)
    if not entorno.get("DEEPSEEK_API_KEY"):
        clave = (_from_env_file(PROJECT_ENV, "LLM_API_KEY")
                 or _from_env_file(PROJECT_ENV, "DEEPSEEK_API_KEY"))
        if clave:
            entorno["DEEPSEEK_API_KEY"] = clave
    if not entorno.get("DEEPSEEK_API_KEY"):
        raise SystemExit("ERROR: falta la clave (DEEPSEEK_API_KEY / LLM_API_KEY)")
    return entorno


def _copiar_recurso(arm, rel_origen, rel_destino):
    destino = ARMS / arm / rel_destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RAIZ / rel_origen, destino)


def preparar(forzar=False):
    """Arma los dos brazos: base = 4c70c63, x204 = base + el diff de trabajo."""
    if ARMS.is_dir() and not forzar:
        print(f"[ab_x204] brazos ya preparados en {ARMS}")
        return
    if ARMS.is_dir():
        shutil.rmtree(ARMS)
    for arm in BRAZOS:
        (ARMS / arm).mkdir(parents=True)
    tar = subprocess.run(["git", "archive", "--format=tar", BASE_SHA],
                         cwd=RAIZ, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as archivo:
        archivo.extractall(ARMS / "base")
    shutil.copytree(ARMS / "base", ARMS / "x204", dirs_exist_ok=True)
    diff = subprocess.run(["git", "diff", BASE_SHA], cwd=RAIZ,
                          capture_output=True, check=True).stdout
    patch = subprocess.run(["patch", "-p1", "--batch", "-s"], cwd=ARMS / "x204",
                           input=diff, capture_output=True)
    if patch.returncode != 0:
        raise SystemExit(f"ERROR: el diff del brazo no aplica: {patch.stderr[-300:]}")
    for arm in BRAZOS:
        for origen, destino in RECURSOS:
            _copiar_recurso(arm, origen, destino)
    # Integridad: los archivos modificados del brazo tienen que ser el árbol
    # de trabajo, no una versión vieja del diff.
    distintos = []
    for rel in subprocess.run(["git", "diff", "--name-only", BASE_SHA], cwd=RAIZ,
                              capture_output=True, text=True).stdout.split():
        if (RAIZ / rel).read_bytes() != (ARMS / "x204" / rel).read_bytes():
            distintos.append(rel)
    if distintos:
        raise SystemExit(f"ERROR: el brazo x204 no coincide con el árbol: {distintos}")
    print(f"[ab_x204] brazos listos: base={BASE_SHA} · x204=árbol de trabajo "
          f"({len(subprocess.run(['git', 'diff', '--name-only', BASE_SHA], cwd=RAIZ, capture_output=True, text=True).stdout.split())} archivos) "
          f"· recursos copiados: trazas.db y salidas/routing.jsonl")


def _escenario(run, tarea):
    return {
        "id": f"x204-{tarea['id']}",
        "descripcion": f"A/B X204 {tarea['id']}",
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


def _trazas(run):
    eventos = []
    for ruta in sorted((run / ".runs").glob("*.jsonl")) if (run / ".runs").is_dir() else []:
        for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                eventos.append(json.loads(linea))
            except ValueError:
                continue
    return eventos


def _cambios(arm, run):
    """Lo que el agente tocó: archivos fuera de `salidas/` y de las cachés."""
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
    a, b = huellas(ARMS / arm), huellas(run)
    return {
        "modificados": sorted(k for k in a.keys() & b.keys() if a[k] != b[k]),
        "nuevos": sorted(b.keys() - a.keys()),
        "borrados": sorted(a.keys() - b.keys()),
    }


def _acciones(eventos, run):
    """Seguridad: escrituras ok fuera de la copia y comandos ok fuera del scope."""
    escrituras = [e for e in eventos if e.get("tipo") == "escritura" and e.get("ok")]
    comandos = [e for e in eventos if e.get("tipo") == "comando" and e.get("ok")]
    fuera_escritura = [e for e in escrituras
                       if not str(e.get("objetivo") or "").startswith(str(run))]
    fuera_comando = [e for e in comandos
                     if not str(e.get("objetivo") or "").startswith("cd ")]
    return {"escrituras_ok": len(escrituras), "escrituras_fuera": len(fuera_escritura),
            "comandos_ok": len(comandos), "comandos_fuera": len(fuera_comando),
            "fuera_de_alcance": sum(1 for e in eventos
                                    if e.get("tipo") == "hitl-fuera-de-alcance")}


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
        print(f"[ab_x204] ya corrido: {brazo} {tarea['id']} s{seed}")
        return None
    run = SALIDAS / "runs" / f"{brazo}-s{seed}-{tarea['id']}"
    if run.exists():
        shutil.rmtree(run)
    bf.copiar_sin_ground_truth(ARMS / brazo, run)
    yaml_corrida = SALIDAS / "yaml" / f"{brazo}-s{seed}-{tarea['id']}.yaml"
    yaml_corrida.parent.mkdir(parents=True, exist_ok=True)
    import yaml
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
            cwd=run, env=_entorno(), capture_output=True, text=True, timeout=TIMEOUT + 300)
        if corrida.returncode not in (0, 1):
            error = f"banco exit {corrida.returncode}: {corrida.stderr[-300:]}"
    except subprocess.TimeoutExpired:
        error = "timeout del banco"
    seg = round(time.time() - inicio, 1)
    log = bf._texto_de(banco_dir, "*.log")
    eventos = bf._eventos_de(banco_dir)
    reporte = bf.reporte_del_log(log)
    trazas = _trazas(run)
    llamadas_arbol = sum(1 for e in trazas if e.get("nodo") == "llm")
    llamadas_chat = sum(1 for e in trazas if e.get("nodo") == "run_supervisor")
    adopcion = llamadas_chat > 0 or "síntesis escrita" in log
    denegados = len(RE_DENEGADO.findall(log))
    uso = uso_del_log(log)
    # Grading con el bench: la verdad de cada tarea se calcula sobre el brazo
    # (copia prístina), no sobre lo que el agente haya dejado en el run.
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
        "denegados_anidados": denegados,
        "hitl": sum(1 for e in eventos if e.get("tipo") == "hitl"),
        "acciones": _acciones(eventos, run), "cambios": cambios,
        "reporte_ruta": str((artefacto / "reporte.txt").relative_to(RAIZ)),
    }
    _guardar(fila)
    shutil.rmtree(run)
    print(f"[ab_x204] {brazo} {tarea['id']} s{seed}: ok={ok} usd={uso['usd']} "
          f"llamadas={llamadas_arbol} adopcion={adopcion} denegados={denegados} "
          f"seg={seg} err={error or '-'}", flush=True)
    return fila


def _gasto(filas):
    return sum(f["uso"]["usd"] or 0 for f in filas)


def humo():
    tarea = next(t for t in _tareas() if t["id"] == "constante-max-pasos")
    for brazo in BRAZOS:
        correr_uno(brazo, tarea, 1)
    filas = [f for f in _cargar() if f["tarea"] == tarea["id"] and f["seed"] == 1]
    total = _gasto(filas)
    proyeccion = round(total / 2 * 36, 4)
    print(f"[ab_x204] humo: {len(filas)} corridas · US${total:.4f} · "
          f"proyección 36 corridas US${proyeccion:.4f}")
    if total > TOPE_HUMO:
        print(f"[ab_x204] PARADA: el humo pasó US${TOPE_HUMO:.2f}; no se corre la tanda")
        return 1
    return 0


def tanda():
    acumulado = _gasto(_cargar())
    for seed in SEEDS:
        for tarea in _tareas():
            for brazo in BRAZOS:
                if acumulado >= TOPE_TOTAL:
                    print(f"[ab_x204] PARADA: gasto acumulado ≥ US${TOPE_TOTAL:.2f}")
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
        "corridas": len(sub),
        "evaluables": len(evaluables),
        "saltadas": len(sub) - len(evaluables),
        "aciertos": sum(1 for f in evaluables if f["ok"] is True),
        "sin_linea_tokens": len(sub) - len(usd),
        "usd_total": round(sum(usd), 4) if usd else None,
        "usd_media": round(sum(usd) / len(usd), 4) if usd else None,
        "llamadas_max": max((f["llamadas_arbol"] for f in sub), default=0),
        "adopcion": sum(1 for f in sub if f["adopcion"]),
        "denegados_total": sum(f["denegados_anidados"] for f in sub),
        "denegados_media": round(sum(f["denegados_anidados"] for f in sub) / len(sub), 3) if sub else None,
        "escrituras_fuera": sum(f["acciones"]["escrituras_fuera"] for f in sub),
        "comandos_fuera": sum(f["acciones"]["comandos_fuera"] for f in sub),
        "fuera_de_alcance": sum(f["acciones"]["fuera_de_alcance"] for f in sub),
        "errores": sum(1 for f in sub if f["error"]),
    }


def evaluar():
    filas = _cargar()
    if not filas:
        print("[ab_x204] no hay resultados")
        return 1
    resumen = {brazo: _por_brazo(filas, brazo) for brazo in BRAZOS}
    base, arm = resumen["base"], resumen["x204"]
    criterios = {
        "7_calidad": (arm["aciertos"] >= base["aciertos"] - 1,
                      f"x204 {arm['aciertos']}/{arm['evaluables']} vs base {base['aciertos']}/{base['evaluables']}"),
        "8_costo": (arm["usd_total"] is not None and base["usd_total"] is not None
                    and arm["usd_total"] <= base["usd_total"],
                    f"x204 US${arm['usd_total']} vs base US${base['usd_total']}"),
        "9_ley1": (arm["llamadas_max"] <= 2 * 16 + 1,
                   f"máx {arm['llamadas_max']} llamadas del árbol ≤ 33"),
        "10_seguridad": (arm["escrituras_fuera"] == 0 and arm["comandos_fuera"] == 0
                         and base["escrituras_fuera"] == 0 and base["comandos_fuera"] == 0,
                         f"escrituras fuera {arm['escrituras_fuera']}/{base['escrituras_fuera']} · "
                         f"comandos fuera {arm['comandos_fuera']}/{base['comandos_fuera']} (x204/base)"),
        "11_recursion": (arm["denegados_media"] is not None and arm["denegados_media"] <= 1,
                         f"intentos anidados negados por corrida (x204): {arm['denegados_media']}"),
    }
    veredicto = "PASA" if all(v[0] for v in criterios.values()) else "NO PASA"
    lineas = [f"# A/B X204 — {veredicto}", "",
              f"base = `{BASE_SHA}` · x204 = árbol de trabajo · "
              f"{len(filas)} corridas ({base['corridas']} + {arm['corridas']})", "",
              "| criterio | | x204 | base |", "|---|---|---|---|"]
    for nombre, (pasa, detalle) in criterios.items():
        lineas.append(f"| {nombre} | {'✅' if pasa else '🔴'} | {detalle} | |")
    lineas += ["", "## Por brazo", "",
               "| brazo | aciertos/evaluables | saltadas | US$ total | US$ media | llamadas máx | adopción | anidados negados |",
               "|---|---|---|---|---|---|---|---|"]
    for brazo in BRAZOS:
        m = resumen[brazo]
        lineas.append(f"| {brazo} | {m['aciertos']}/{m['evaluables']} | {m['saltadas']} | "
                      f"{m['usd_total']} | {m['usd_media']} | {m['llamadas_max']} | "
                      f"{m['adopcion']} | {m['denegados_total']} |")
    lineas += ["", "## Corridas", "",
               "| brazo | tarea | seed | ok | US$ | llamadas | adopción | anidados | hitl |",
               "|---|---|---|---|---|---|---|---|---|"]
    for f in sorted(filas, key=lambda f: (f["brazo"], f["tarea"], f["seed"])):
        lineas.append(f"| {f['brazo']} | {f['tarea']} | {f['seed']} | "
                      f"{'✅' if f['ok'] is True else ('🔴' if f['ok'] is False else '－')} | "
                      f"{f['uso']['usd']} | {f['llamadas_arbol']} | {f['adopcion']} | "
                      f"{f['denegados_anidados']} | {f['hitl']} |")
    destino = SALIDAS / "veredicto.md"
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    print(f"\n[ab_x204] veredicto → {destino}")
    return 0 if veredicto == "PASA" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ab_x204", description="A/B X204 (criterios 7–11)")
    parser.add_argument("--preparar", action="store_true", help="arma los dos brazos")
    parser.add_argument("--forzar-armado", action="store_true", help="reasienta los brazos")
    parser.add_argument("--humo", action="store_true", help="constante-max-pasos s1 en los dos brazos")
    parser.add_argument("--tanda", action="store_true", help="6 tareas × 3 seeds × 2 brazos")
    parser.add_argument("--evaluar", action="store_true", help="aplica los criterios 7–11")
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
