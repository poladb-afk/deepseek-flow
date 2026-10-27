"""H3-B — ¿el explorador paga cuando el contexto pesa? (pre-registro: banco/specs/h3b_swarm.md)

RESUELTO (X79): no ganó y el explorador se borró. Se conserva como registro
reproducible; re-correrlo hoy compara el chat con el supervisor SIN
sub-agente (el setting EXPLORAR ya no existe).

Dos brazos sobre las auditorías amplias de fable (s17–s20): el chat de
siempre y el supervisor con `EXPLORAR=1`. Mide calidad (`bench_fable.puntuar`),
costo (tokens) y adopción (llamadas a `explorar`), y aplica el criterio
pre-registrado sin retocarlo.

Uso:
    python3 banco/probes/h3b_swarm.py                       # 4 escenarios × seeds 1,2,3 × 2 brazos
    python3 banco/probes/h3b_swarm.py --seeds 1 --escenarios s19-real-audit-2
    python3 banco/probes/h3b_swarm.py --resumen
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import bench_fable as bf  # noqa: E402

from banco.banco import escribir_scope  # noqa: E402

EXP = "h3b-swarm"
ESCENARIOS = ("s17-scale-audit", "s18-real-audit", "s19-real-audit-2", "s20-real-audit-3")
BRAZOS = ("chat", "supervisor")
RE_TOKENS = re.compile(r"\[tokens\] sesión: (\d+) llamadas — ([\d.]+) prompt \+ ([\d.]+) completion")
RE_EXPLORAR = re.compile(r"^- \d+ explorar\(", re.M)

# El supervisor corre en un proceso propio (EXPLORAR se lee al importar) y
# devuelve, en una línea JSON, la ruta del informe y el uso de la sesión.
DRIVER = (
    "import json, sys\n"
    "import supervisor\n"
    "from utils.call_llm import uso_de_sesion\n"
    "ruta = supervisor.supervisar(sys.argv[1], sys.argv[2])\n"
    "print('H3B ' + json.dumps({'informe': ruta, 'uso': uso_de_sesion()}))\n"
)


def tokens_del_log(log):
    """(llamadas, tokens) de la línea `[tokens] sesión` del chat, o None."""
    m = RE_TOKENS.search(log or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2).replace(".", "")) + int(m.group(3).replace(".", ""))


def exploraciones(informe):
    return len(RE_EXPLORAR.findall(informe or ""))


def correr_chat(escenario, seed):
    r = bf.correr_uno(EXP, escenario, "A", seed, forzar=True, salir=True)
    uso = tokens_del_log(r.pop("log"))
    return {"brazo": "chat", "escenario": escenario, "seed": seed,
            "calidad": r["correct_action"], "checks": r["checks"],
            "llamadas": uso[0] if uso else None, "tokens": uso[1] if uso else None,
            "exploraciones": 0, "seg": r["seg"], "error": r["error"] or (None if uso else "sin línea [tokens]")}


def correr_supervisor(escenario, seed):
    pristine = bf.SALIDAS / "pristine" / EXP / escenario
    if not pristine.is_dir():
        bf.copiar_sin_ground_truth(bf.fuente_fixture(escenario), pristine)
    run = bf.SALIDAS / "runs" / EXP / "supervisor" / f"s{seed}" / escenario
    bf.copiar_sin_ground_truth(pristine, run)
    salidas = run.parent / f"{escenario}-salida"
    shutil.rmtree(salidas, ignore_errors=True)
    salidas.mkdir(parents=True)
    rel = run.relative_to(RAIZ).as_posix()
    # el MISMO scope que el chat en bench_fable (escrituras en la copia, mismos prefijos)
    scope = escribir_scope(salidas / "scope.json", [str(run)],
                           [f"cd {rel}", f"cd {run}", f"python3 {rel}", f"python3 {run}"],
                           20, salidas / "hitl.jsonl")
    env = {**os.environ, "EXPLORAR": "1", "MEMORIA": "0", "HITL_SCOPE": str(scope),
           "AGENT_ALLOWED_DIRS": f"{run}:{salidas}", "PATH": bf._python_shim(), "PYTHONUNBUFFERED": "1",
           "THREADS_DIR": str(salidas / "threads"), "HUMANO_RESPUESTA": bf.RESPUESTA_HUMANO_OFFLINE}
    tarea = bf.TAREAS[escenario](rel) + " " + bf.OFFLINE
    timeout = int(bf.ESCENARIOS[escenario]["timeout"]) + 120
    inicio, error, datos = time.time(), None, {}
    try:
        p = subprocess.run([sys.executable, "-c", DRIVER, tarea, str(salidas / "informe.md")],
                           cwd=RAIZ, env=env, capture_output=True, text=True, timeout=timeout)
        (salidas / "transcript.log").write_text(p.stdout + p.stderr, encoding="utf-8")
        linea = next((ln for ln in p.stdout.splitlines() if ln.startswith("H3B ")), None)
        datos = json.loads(linea[4:]) if linea else {}
        if not datos:
            error = f"supervisor exit {p.returncode}: {p.stderr[-300:]}"
    except subprocess.TimeoutExpired:
        error = "timeout del supervisor"
    informe = Path(datos["informe"]).read_text(encoding="utf-8") if datos.get("informe") else ""
    puntaje = bf.puntuar(escenario, pristine, run, informe)
    uso = datos.get("uso") or {}
    return {"brazo": "supervisor", "escenario": escenario, "seed": seed,
            "calidad": puntaje["correct_action"], "checks": puntaje["checks"],
            "llamadas": uso.get("llamadas"),
            "tokens": (uso["prompt"] + uso["completion"]) if uso else None,
            "exploraciones": exploraciones(informe), "seg": round(time.time() - inicio, 1), "error": error}


def _media(valores):
    valores = [v for v in valores if v is not None]
    return sum(valores) / len(valores) if valores else None


def veredicto(resultados):
    """El criterio de banco/specs/h3b_swarm.md, sin retoques. PURA."""
    por_brazo = {b: [r for r in resultados if r["brazo"] == b] for b in BRAZOS}
    medidas = {}
    for brazo, filas in por_brazo.items():
        calidad, tokens = _media(r["calidad"] for r in filas), _media(r["tokens"] for r in filas)
        medidas[brazo] = {"n": len(filas), "calidad": calidad, "tokens": tokens,
                          "calidad_por_mtoken": (calidad / tokens * 1e6) if calidad is not None and tokens else None}
    escenarios = sorted({r["escenario"] for r in por_brazo["supervisor"]})
    adopcion = {e: sum(r["exploraciones"] for r in por_brazo["supervisor"] if r["escenario"] == e)
                for e in escenarios}
    chat, sup = medidas["chat"], medidas["supervisor"]
    completo = bool(chat["n"] and sup["n"] and None not in (chat["calidad"], sup["calidad"], chat["tokens"], sup["tokens"]))
    condiciones = {
        "adopcion": bool(adopcion) and all(n > 0 for n in adopcion.values()),
        "calidad": completo and sup["calidad"] > chat["calidad"],
        "calidad_por_token": completo and sup["calidad_por_mtoken"] > chat["calidad_por_mtoken"],
    }
    gana = completo and all(condiciones.values())
    return {"medidas": medidas, "adopcion": adopcion, "condiciones": condiciones,
            "completo": completo, "gana": gana,
            "decision": ("el explorador se queda" if gana else
                         "el explorador no paga: se borra (explorador.py, `explorar`, EXPLORAR)")
            if completo else "faltan datos: no hay veredicto"}


def _fmt(x, d=2):
    return "—" if x is None else f"{x:.{d}f}"


def resumen(resultados):
    v = veredicto(resultados)
    L = ["# H3-B — ¿el explorador paga cuando el contexto pesa?", "",
         "Criterio pre-registrado: banco/specs/h3b_swarm.md.", "",
         "| brazo | n | calidad media (0–2) | tokens medios | calidad / Mtoken |", "|---|---|---|---|---|"]
    for brazo in BRAZOS:
        m = v["medidas"][brazo]
        L.append(f"| {brazo} | {m['n']} | {_fmt(m['calidad'])} | {_fmt(m['tokens'], 0)} | {_fmt(m['calidad_por_mtoken'])} |")
    L += ["", "**Adopción** (llamadas a `explorar` por escenario, sumando seeds): "
          + (", ".join(f"{e}={n}" for e, n in v["adopcion"].items()) or "—"), ""]
    L += [f"- {c}: {'✅' if ok else '❌'}" for c, ok in v["condiciones"].items()]
    L += ["", f"**Veredicto:** {'GANA' if v['gana'] else 'NO GANA'} → {v['decision']}", "",
          "| brazo | escenario | seed | calidad | tokens | explorar | seg | error |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(resultados, key=lambda r: (r["escenario"], r["seed"], r["brazo"])):
        L.append(f"| {r['brazo']} | {r['escenario']} | {r['seed']} | {r['calidad']} | {r['tokens'] or '—'} "
                 f"| {r['exploraciones']} | {r['seg']} | {r['error'] or '—'} |")
    return "\n".join(L) + "\n"


def _ruta():
    return bf.SALIDAS / "resultados" / f"{EXP}.jsonl"


def cargar():
    ruta = _ruta()
    return [json.loads(ln) for ln in ruta.read_text(encoding="utf-8").splitlines() if ln.strip()] if ruta.is_file() else []


def guardar(fila):
    ruta = _ruta()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    clave = (fila["brazo"], fila["escenario"], fila["seed"])
    filas = [r for r in cargar() if (r["brazo"], r["escenario"], r["seed"]) != clave] + [fila]
    ruta.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in filas), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="h3b_swarm", description="H3-B: chat vs supervisor+explorar en fable s17–s20")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--escenarios", default=",".join(ESCENARIOS))
    parser.add_argument("--brazos", default=",".join(BRAZOS))
    parser.add_argument("--resumen", action="store_true", help="solo escribe el resumen de lo ya corrido")
    args = parser.parse_args(argv)
    if not args.resumen:
        correr = {"chat": correr_chat, "supervisor": correr_supervisor}
        for seed in (int(s) for s in args.seeds.split(",") if s.strip()):
            for escenario in (e.strip() for e in args.escenarios.split(",") if e.strip()):
                for brazo in (b.strip() for b in args.brazos.split(",") if b.strip()):
                    fila = correr[brazo](escenario, seed)
                    guardar(fila)
                    print(f"[h3b] {brazo} s{seed} {escenario}: calidad={fila['calidad']} tokens={fila['tokens']} "
                          f"explorar={fila['exploraciones']} err={fila['error'] or '-'}", flush=True)
    texto = resumen(cargar())
    destino = bf.SALIDAS / "resultados" / f"{EXP}-resumen.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"[h3b] resumen → {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
