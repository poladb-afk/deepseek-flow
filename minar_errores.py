"""Minería de errores de tools en las trazas (.runs/*.jsonl): frecuencia,
firma de duración (timeouts), destino del reintento y sesiones afectadas.

Pregunta que responde (exp/9): ¿los errores de tools se AUTOCORRIGEN
(reintento con éxito) o se repeten y se abandonan? Esa tasa decide si un
triaje automático con Laya agrega valor.

Determinista a propósito: SIN LLM, SIN red, SIN torch — JSON puro. El mismo
parseo que evals.py (`_leer_eventos`): una traza corrupta es un artefacto a
saltear, nunca una excepción.

--------------------------------------------------------------------------
LÍMITE HONESTO (lo que esta evidencia NO puede decir)
--------------------------------------------------------------------------
Las trazas NO guardan el texto del error: `evento_tool` registra SOLO
nombre + ok/error + segundos. Con eso NO se puede clasificar la CAUSA
(¿falló por red? ¿por argumentos? ¿por permisos?). Lo que SÍ se mide acá es:
frecuencia, duración (un timeout de run_command firma en ~100 s) y el
DESTINO del reintento (¿se volvió a llamar? ¿con éxito?). Cualquier lectura
de causas a partir de este informe es especulación, no medición.

--------------------------------------------------------------------------
HEURÍSTICA DE RECHAZO HITL (caveat, no certeza)
--------------------------------------------------------------------------
Los rechazos HITL de run_command devuelven "RECHAZADO…", un texto que NO
empieza con "ERROR": en la traza cuentan como ok con duración casi nula. Por
eso un evento ok de run_command con seg < 0.5 es un RECHAZO PROBABLE (la
política de autocorrección de código, exp/12, lo trata como no-reintento).
Es una heurística: se reporta como categoría SEPARADA y nunca se suma a los
errores reales.

Uso:
    python3 minar_errores.py [--carpeta .runs] [--salida salidas/evals]
"""
import argparse
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Reuso EXACTO del parseo tolerante de evals.py: misma vara para todas las
# trazas del proyecto (una traza rota es artefacto a saltear, no excepción).
# Se importa (no se copia): una copia local derivaría sin que ningún test lo
# note, y acá la única defensa contra mientes-la-tabla es que los números
# salgan del mismo lector que el resto del harness.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evals import _leer_eventos  # noqa: E402

RAIZ = Path(__file__).resolve().parent
DIR_RUNS = Path(".runs")
DIR_SALIDA = Path("salidas/evals")

# Un timeout de run_command firma en ~120 s de deadline; usamos 100 s como
# umbral conservador (por debajo del deadline real, para no perderse el caso
# límite). Documentado acá porque es el número que decide qué es "timeout".
UMBRAL_TIMEOUT_SEG = 100.0

# La tool cuyo rechazo HITL imita un ok con duración casi nula.
TOOL_RECHAZO_HITL = "run_command"
UMBRAL_RECHAZO_SEG = 0.5


# ---------------------------------------------------------------------------
# 1) FUNCIONES PURAS (importables y testeables sobre listas sintéticas)
# ---------------------------------------------------------------------------

def es_timeout(ev, umbral=UMBRAL_TIMEOUT_SEG):
    """Un evento de ERROR cuya duración >= `umbral` es un timeout probable.

    Pura: no toca disco ni red. `ev` es un dict de una línea de traza
    (nodo/accion/seg). El PORQUÉ de exigir accion == "error": un ok largo
    (p.ej. read_file de un archivo grande) NO es un timeout, es trabajo."""
    return ev.get("accion") == "error" and float(ev.get("seg", 0.0) or 0.0) >= umbral


def es_rechazo_probable(ev):
    """Un ok de run_command con seg < 0.5 es PROBABLE rechazo HITL.

    Heurística (ver caveat del docstring): el rechazo devuelve "RECHAZADO…",
    que no empieza con "ERROR", así que cae como ok con duración casi nula.
    No hay certeza desde la traza: por eso NO se suma a errores, se cuenta
    aparte."""
    return (
        ev.get("accion") == "ok"
        and ev.get("nodo") == TOOL_RECHAZO_HITL
        and float(ev.get("seg", 0.0) or 0.0) < UMBRAL_RECHAZO_SEG
    )


def destino_del_reintento(eventos, ev):
    """Dado un evento de ERROR de la tool T en ts X, busca el PRÓXIMO evento
    de T en la MISMA sesión (lista ya ordenada por ts) y devuelve None (no
    hubo reintento: abandono) o {ok: bool, delta_seg: float}.

    El PRÓXIMO evento de T, sea ok o error: si volvió a llamar a T, hubo
    reintento aunque también fallara. La cantidad de reintentos se reconstruye
    llamando esta función por cada error (cada uno mira su propio "siguiente").

    `eventos` debe venir ordenado por ts (así lo entrega `_leer_eventos`, que
    lee el archivo en orden de escritura = orden temporal)."""
    tool = ev.get("nodo")
    try:
        idx = eventos.index(ev)
    except ValueError:
        return None
    for siguiente in eventos[idx + 1:]:
        if siguiente.get("nodo") == tool:
            return {
                "ok": siguiente.get("accion") == "ok",
                "delta_seg": float(siguiente.get("ts", 0.0)) - float(ev.get("ts", 0.0)),
            }
    return None


# ---------------------------------------------------------------------------
# 2) AGREGADOS (sobre todas las sesiones)
# ---------------------------------------------------------------------------

def _delta_mediano(deltas):
    """Mediana de deltas o None si no hay ninguno (evita un statistics error)."""
    return round(statistics.median(deltas), 3) if deltas else None


def minar_sesion(eventos):
    """Minería de UNA sesión (lista de eventos ordenada por ts). Devuelve los
    errores de tools, los rechazos-probables y los reintentos resueltos.

    Es pura sobre `eventos` (no abre archivos): testeable y reusada por
    `minar_runs`."""
    por_tool = defaultdict(lambda: {
        "errores": 0, "timeouts": 0, "reintentos": 0, "reintentos_ok": 0,
        "abandono": 0, "_deltas": [],
    })
    rechazos = 0
    for ev in eventos:
        if es_rechazo_probable(ev):
            rechazos += 1
        if ev.get("accion") != "error":
            continue
        tool = ev.get("nodo", "?")
        info = por_tool[tool]
        info["errores"] += 1
        if es_timeout(ev):
            info["timeouts"] += 1
        destino = destino_del_reintento(eventos, ev)
        if destino is None:
            info["abandono"] += 1
        else:
            info["reintentos"] += 1
            info["_deltas"].append(destino["delta_seg"])
            if destino["ok"]:
                info["reintentos_ok"] += 1
    for info in por_tool.values():
        info["delta_mediano_seg"] = _delta_mediano(info.pop("_deltas"))
    return {"por_tool": dict(por_tool), "rechazos_probables": rechazos}


def minar_runs(directorio=DIR_RUNS):
    """Minería de TODAS las trazas .runs/*.jsonl. Devuelve el informe crudo
    (dict) que consumen `escribir_md` / el JSON de salida.

    No corta con trazas corruptas: si `_leer_eventos` devuelve [] para un
    archivo con contenido, es una traza rota → se saltea (cuenta en
    `trazas_ilegibles`, no en errores)."""
    directorio = Path(directorio)
    por_tool = defaultdict(lambda: {
        "errores": 0, "timeouts": 0, "reintentos": 0, "reintentos_ok": 0,
        "abandono": 0, "_deltas": [],
    })
    sesiones_total = 0
    sesiones_con_error = 0
    errores_total = 0
    rechazos_total = 0
    trazas_ilegibles = []

    for archivo in sorted(directorio.glob("*.jsonl")):
        eventos = _leer_eventos(archivo)
        if not eventos:
            # tenía contenido y no se pudo parsear: traza corrupta (artefacto).
            if archivo.stat().st_size > 0:
                trazas_ilegibles.append(archivo.name)
            continue
        sesiones_total += 1
        res = minar_sesion(eventos)
        if res["por_tool"]:
            sesiones_con_error += 1
        rechazos_total += res["rechazos_probables"]
        for tool, info in res["por_tool"].items():
            agg = por_tool[tool]
            for k in ("errores", "timeouts", "reintentos", "reintentos_ok", "abandono"):
                agg[k] += info[k]
            errores_total += info["errores"]
            # reconstruyo los deltas para recalcular la mediana GLOBAL por tool
            if info["delta_mediano_seg"] is not None:
                # re-mido sobre los errores de esta sesión (barato: listas chicas)
                for ev in eventos:
                    if ev.get("accion") == "error" and ev.get("nodo") == tool:
                        d = destino_del_reintento(eventos, ev)
                        if d is not None:
                            agg["_deltas"].append(d["delta_seg"])

    for info in por_tool.values():
        info["delta_mediano_seg"] = _delta_mediano(info.pop("_deltas"))

    reintentos_ok_total = sum(i["reintentos_ok"] for i in por_tool.values())
    reintentos_total = sum(i["reintentos"] for i in por_tool.values())
    abandono_total = sum(i["abandono"] for i in por_tool.values())
    timeouts_total = sum(i["timeouts"] for i in por_tool.values())

    # LA tasa que decide todo: autocorrección = errores con reintento EXITOSO.
    tasa = (reintentos_ok_total / errores_total) if errores_total else None

    return {
        "sesiones_total": sesiones_total,
        "sesiones_con_error": sesiones_con_error,
        "errores_total": errores_total,
        "errores_por_sesion": round(errores_total / sesiones_total, 3) if sesiones_total else None,
        "timeouts_total": timeouts_total,
        "reintentos_total": reintentos_total,
        "reintentos_ok_total": reintentos_ok_total,
        "abandono_total": abandono_total,
        "rechazos_probables_total": rechazos_total,
        "tasa_autocorreccion": tasa,
        "trazas_ilegibles": trazas_ilegibles,
        "por_tool": por_tool,
    }


# ---------------------------------------------------------------------------
# 3) SALIDAS (md legible + json máquina), patrón laya_evidencia_*
# ---------------------------------------------------------------------------

def _fmt_pct(x):
    return f"{x * 100:.1f}%" if x is not None else "—"


def _fmt_seg(x):
    return f"{x:.3f}" if x is not None else "—"


def escribir_md(informe, sha, fecha):
    """Informe markdown: el límite honesto ARRIBA (primero lo que no se puede
    medir), después la tasa de autocorrección destacada y las tablas."""
    o = []
    o.append("# Minería de errores de tools en las trazas\n")
    o.append(f"Fecha {fecha} · git `{sha}` · carpeta `.runs/`\n")

    o.append("## Límite honesto\n")
    o.append("Las trazas NO guardan el texto del error: `evento_tool` registra solo "
             "**nombre + ok/error + segundos**. Desde la traza es imposible clasificar la "
             "causa (¿red? ¿argumentos? ¿permisos?). Lo que SÍ mide este informe es la "
             "**frecuencia**, la **duración** (un timeout de `run_command` firma en ~100 s) "
             "y el **destino del reintento** (¿se volvió a llamar? ¿con éxito?). "
             "Toda lectura de causas a partir de acá es especulación.\n")
    o.append("Los **rechazos HITL** de `run_command` devuelven \"RECHAZADO…\", que no empieza "
             "con \"ERROR\": en la traza cuentan como ok con duración casi nula. Se reportan "
             "como *rechazo probable* (heurística: ok de run_command con seg < 0.5), "
             "categoría **separada** que NUNCA se suma a los errores reales.\n")

    o.append("## Tasa de autocorrección (la clave)\n")
    o.append(f"> **{_fmt_pct(informe['tasa_autocorreccion'])}** de los errores fue seguido "
             f"de un reintento exitoso de la misma tool "
             f"({informe['reintentos_ok_total']}/{informe['errores_total']}).\n")
    if informe["tasa_autocorreccion"] is not None:
        if informe["tasa_autocorreccion"] >= 0.5:
            o.append("> La mayoría se autocorrige: el agente ya repara; un triaje automático "
                     "con Laya rendiría poco sobre lo que ya se resuelve solo.\n")
        else:
            o.append("> La mayoría NO se autocorrige: hay errores que se abandonan o se "
                     "repiten; un triaje automático con Laya tiene material.\n")

    o.append("## Global\n")
    o.append("| métrica | valor |")
    o.append("|---|---|")
    o.append(f"| sesiones totales | {informe['sesiones_total']} |")
    o.append(f"| sesiones con errores | {informe['sesiones_con_error']} |")
    o.append(f"| errores totales | {informe['errores_total']} |")
    o.append(f"| errores por sesión | {_fmt_seg(informe['errores_por_sesion'])} |")
    o.append(f"| timeouts (seg ≥ {UMBRAL_TIMEOUT_SEG:.0f}) | {informe['timeouts_total']} |")
    o.append(f"| reintentos (hubo próximo evento) | {informe['reintentos_total']} |")
    o.append(f"| reintentos con éxito | {informe['reintentos_ok_total']} |")
    o.append(f"| abandono (sin próximo evento) | {informe['abandono_total']} |")
    o.append(f"| rechazos-probables (heurística, aparte) | {informe['rechazos_probables_total']} |")
    if informe["trazas_ilegibles"]:
        o.append(f"| trazas ilegibles (salteadas) | {len(informe['trazas_ilegibles'])} |")
    o.append("")

    o.append("## Por tool\n")
    o.append("| tool | errores | timeouts | reintentos | reintentos ok | abandono | "
             "delta mediano (s) |")
    o.append("|---|---|---|---|---|---|---|")
    # ordenadas por errores desc: las tools problemáticas primero
    for tool, info in sorted(informe["por_tool"].items(),
                             key=lambda kv: kv[1]["errores"], reverse=True):
        o.append(f"| {tool} | {info['errores']} | {info['timeouts']} | "
                 f"{info['reintentos']} | {info['reintentos_ok']} | {info['abandono']} | "
                 f"{_fmt_seg(info['delta_mediano_seg'])} |")
    if not informe["por_tool"]:
        o.append("| — | 0 | 0 | 0 | 0 | 0 | — |")
    o.append("")
    return "\n".join(o) + "\n"


def _git_sha():
    """sha corto del código actual (best-effort: el informe no depende de git)."""
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001 (git es best-effort, no dependencia)
        return ""


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Minería de errores de tools en las trazas .runs/*.jsonl.")
    parser.add_argument("--carpeta", default=str(DIR_RUNS),
                        help="carpeta de trazas (default: .runs)")
    parser.add_argument("--salida", default=str(DIR_SALIDA),
                        help="directorio de salida (default: salidas/evals)")
    args = parser.parse_args(argv)

    informe = minar_runs(args.carpeta)
    sha = _git_sha()
    fecha = datetime.now().isoformat(timespec="seconds")

    destino = Path(args.salida)
    destino.mkdir(parents=True, exist_ok=True)
    md_path = destino / "errores_mineria.md"
    json_path = destino / "errores_mineria.json"

    md_path.write_text(escribir_md(informe, sha, fecha), encoding="utf-8")
    salida_json = {
        "fecha": fecha,
        "git_sha": sha,
        "carpeta": str(args.carpeta),
        **informe,
    }
    json_path.write_text(json.dumps(salida_json, indent=2, ensure_ascii=False),
                         encoding="utf-8")

    print(f"=== minería de errores · {fecha} · git {sha or '?'} ===")
    print(f"  sesiones: {informe['sesiones_total']} "
          f"({informe['sesiones_con_error']} con errores)")
    print(f"  errores: {informe['errores_total']} · timeouts: {informe['timeouts_total']} · "
          f"rechazos-probables: {informe['rechazos_probables_total']}")
    print(f"  tasa de autocorrección: {_fmt_pct(informe['tasa_autocorreccion'])} "
          f"({informe['reintentos_ok_total']}/{informe['errores_total']})")
    print(f"  → {md_path}")
    print(f"  → {json_path}")


if __name__ == "__main__":
    main()
