"""Tablero de retrabajo — datos locales, sin red ni LLM (auditoría F4/F5).

Lee .runs (ok/error, códigos cortos de error, decisiones HITL compactas), el
último gate y git; escribe tablero.md/tablero.json. Es una HERRAMIENTA de
diagnóstico, no una palanca del gate: no bloquea nada y no se corre en CI.

Uso:
    python3 tablero.py [--runs .runs] [--salida salidas/tablero] [--gate RUTA]

Nunca lanza por datos faltantes: un .runs vacío, un gate inexistente o git
sin permisos se reportan como "sin datos", no rompen la medición.
"""
import argparse
import collections
import json
import re
import subprocess
from pathlib import Path

from utils.rutas import DIR_RUNS

BASE = Path(__file__).resolve().parent
SALIDA_DEFAULT = Path("salidas/tablero")


def leer_eventos(path):
    eventos = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            eventos.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return eventos


def recolectar(runs):
    archivos = sorted(Path(runs).glob("*.jsonl"))
    vacias = legibles = 0
    tool = collections.Counter()
    tool_err = collections.Counter()
    codigos = collections.Counter()
    hitl = collections.Counter()
    hitl_nivel = collections.Counter()
    runs_con_error = 0
    cortes = timeouts = 0
    retry_ok = retry_total = prob_rechazo = 0
    dias = collections.defaultdict(lambda: {"traces": 0, "eventos": 0, "errores": 0})

    for f in archivos:
        eventos = leer_eventos(f)
        if not eventos:
            vacias += 1
            continue
        legibles += 1
        dia = f.stem[:8]
        dias[dia]["traces"] += 1
        errores_traza = 0
        for i, e in enumerate(eventos):
            nodo = str(e.get("nodo"))
            accion = str(e.get("accion"))
            if nodo.startswith("hitl_") and accion in ("aprobado", "rechazado"):
                hitl[accion] += 1
                hitl_nivel[str(e.get("nivel")) + ":" + nodo[5:]] += 1
                continue
            if accion in ("ok", "error"):
                tool[nodo] += 1
                dias[dia]["eventos"] += 1
                if accion == "error":
                    tool_err[nodo] += 1
                    dias[dia]["errores"] += 1
                    errores_traza += 1
                    if e.get("codigo"):
                        codigos[str(e["codigo"])] += 1
                    if float(e.get("seg") or 0) >= 100:
                        timeouts += 1
                    retry_total += 1
                    for e2 in eventos[i + 1:]:
                        if (str(e2.get("accion")) == "ok"
                                and str(e2.get("nodo")) == nodo):
                            retry_ok += 1
                            break
                elif nodo == "run_command" and float(e.get("seg") or 0) < 0.5:
                    prob_rechazo += 1
            elif nodo == "corte_no_progreso":
                cortes += 1
        if errores_traza:
            runs_con_error += 1

    total_tools = sum(tool.values())
    total_err = sum(tool_err.values())
    por_tool = sorted(
        ({"tool": n, "llamadas": tool[n], "errores": tool_err[n],
          "tasa": round(100 * tool_err[n] / tool[n], 1)} for n in tool if tool_err[n]),
        key=lambda x: -x["errores"],
    )
    tabla_dias = [
        {"dia": dia, "traces": d["traces"], "eventos": d["eventos"],
         "errores": d["errores"],
         "tasa": round(100 * d["errores"] / max(1, d["eventos"]), 2)}
        for dia, d in sorted(dias.items())
    ]
    return {
        "trazas": {"total": len(archivos), "legibles": legibles, "vacias": vacias},
        "tools": {"eventos": total_tools, "errores": total_err,
                  "tasa": round(100 * total_err / max(1, total_tools), 2),
                  "runs_con_error": runs_con_error, "top_errores": por_tool[:10]},
        "retrabajo": {"retries": retry_total, "retries_ok": retry_ok,
                      "autocorreccion": round(100 * retry_ok / max(1, retry_total), 1),
                      "timeouts": timeouts, "cortes_no_progreso": cortes,
                      "rechazos_probables_heuristicos": prob_rechazo},
        "causas": dict(codigos.most_common(10)),
        "hitl": {"aprobados": hitl.get("aprobado", 0),
                 "rechazados": hitl.get("rechazado", 0),
                 "por_nivel_tipo": dict(hitl_nivel.most_common(10))},
        "dias": tabla_dias,
    }


def _gate_tests(ruta):
    if not ruta or not Path(ruta).is_file():
        return None
    texto = Path(ruta).read_text(encoding="utf-8", errors="replace")
    golpe = re.search(r"(\d+) passed", texto)
    return int(golpe.group(1)) if golpe else None


def _git_commits():
    try:
        out = subprocess.run(["git", "log", "--format=%cd", "--date=short"],
                             cwd=BASE, capture_output=True, text=True).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    return dict(sorted(collections.Counter(out.split()).items()))


def _md(data):
    t = data["tools"]
    r = data["retrabajo"]
    tests = data["gate"]["tests"]
    lineas = [
        "# Tablero de retrabajo",
        "",
        f"Datos: {data['trazas']['total']} trazas · "
        f"{tests if tests is not None else '?'} tests · "
        f"{data['revision']['commits_totales']} commits.",
        "",
        "## 1. Salud del loop",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Trazas totales / legibles / vacías | {data['trazas']['total']} / "
        f"{data['trazas']['legibles']} / {data['trazas']['vacias']} |",
        f"| Eventos de tool | {t['eventos']} |",
        f"| Errores de tool | {t['errores']} ({t['tasa']}%) |",
        f"| Runs con >=1 error | {t['runs_con_error']} |",
        f"| Autocorrección (error -> ok misma tool) | {r['retries_ok']}/{r['retries']} "
        f"= {r['autocorreccion']}% |",
        f"| Timeouts (>=100 s) | {r['timeouts']} |",
        f"| Cortes por no-progreso | {r['cortes_no_progreso']} |",
        f"| Rechazos HITL probables (heurística) | {r['rechazos_probables_heuristicos']} |",
        "",
        "## 2. HITL registrado (formato nuevo, sin contenido)",
        "",
        f"- Aprobados: {data['hitl']['aprobados']} · Rechazados: {data['hitl']['rechazados']}",
        f"- Por nivel:tipo: {data['hitl']['por_nivel_tipo'] or '(sin datos)'}",
        "",
        "## 3. Tools con error",
        "",
        "| Tool | Llamadas | Errores | Tasa |",
        "|---|---:|---:|---:|",
    ]
    lineas += [f"| {x['tool']} | {x['llamadas']} | {x['errores']} | {x['tasa']}% |"
               for x in t["top_errores"]]
    lineas += ["", "## 4. Causas registradas (código corto, sin contenido)", "",
               f"{data['causas'] or '(sin datos: trazas viejas sin código)'}", "",
               "## 5. Tendencia por día", "",
               "| Día | Trazas | Eventos | Errores | Tasa |",
               "|---|---:|---:|---:|---:|"]
    lineas += [f"| {d['dia']} | {d['traces']} | {d['eventos']} | {d['errores']} | {d['tasa']}% |"
               for d in data["dias"]]
    lineas += ["", "## 6. Gaps de instrumentación", "",
               "- La traza no guarda el texto del error: el código agrupa causas, no las desarrolla.",
               "- La heurística de rechazo HITL mezcla ejecuciones auto rápidas con rechazos reales;",
               "  el número confiable es el HITL registrado (§2).",
               "- No hay métrica de defectos escapados ni de capacidad de revisión.",
               ""]
    return "\n".join(lineas)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tablero de retrabajo del harness (datos locales).")
    parser.add_argument("--runs", default=str(DIR_RUNS), help="carpeta de trazas (default: .runs)")
    parser.add_argument("--salida", default=str(SALIDA_DEFAULT), help="directorio de salida")
    parser.add_argument("--gate", default=None, help="log del gate para leer la cantidad de tests")
    args = parser.parse_args(argv)

    data = recolectar(args.runs)
    data["gate"] = {"tests": _gate_tests(args.gate)}
    commits = _git_commits()
    data["revision"] = {"por_dia": commits,
                        "commits_totales": sum(commits.values())}

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "tablero.json").write_text(
        json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    (salida / "tablero.md").write_text(_md(data), encoding="utf-8")
    print(f"tablero -> {salida / 'tablero.md'}")
    print(f"  trazas {data['trazas']['total']} ({data['trazas']['vacias']} vacias) · "
          f"errores {data['tools']['errores']} ({data['tools']['tasa']}%) · "
          f"autocorreccion {data['retrabajo']['autocorreccion']}% · "
          f"HITL +{data['hitl']['aprobados']}/-{data['hitl']['rechazados']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
