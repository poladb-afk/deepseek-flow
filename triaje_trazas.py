"""Triaje DETERMINISTA de trazas (.runs/*.jsonl): ¿qué vale la pena auditar?

La auditoría nocturna sobre TODAS las trazas cuesta N llamadas LLM que crece
sin techo (176 hoy). Este triaje NO usa modelo: cruza dos señales baratas y ya
presentes en disco — el linter de invariantes estructurales (evals.linter_traza)
y los outliers de duración total — para elegir el subconjunto que amerita una
lectura profunda. Sobre las trazas reales marca 37/176 (21%): el ahorro del 79%
no necesita modelo.

Tercera decisión por EVIDENCIA del harness (las otras: router y supervisor):
donde la evidencia alcanza sin Laya, se decide sin Laya.

--------------------------------------------------------------------------
LÍMITE HONESTO (lo que el triaje NO puede ver)
--------------------------------------------------------------------------
El triaje ve lo ESTRUCTURAL: invariantes del wiring (linter) y duración
(outliers). NO ve lo SEMÁNTICO: una decisión mala del agente que no rompe
ninguna invariante (p. ej. eligió la tool equivocada, o respondió de más) es
invisible acá — no viola nada y no tarda. Esa lectura SÍ requiere LLM.

Por eso el triaje es un FILTRO, no un reemplazo: dice dónde mirar primero para
gastar menos llamadas, pero la auditoría completa (sobre todas las trazas)
sigue disponible para cuando haga falta profundidad. Decir "auditamos todo con
esto" sería mentir sobre la cobertura.

Determinista a propósito: SIN LLM, SIN red, SIN torch — JSON puro. El mismo
parseo tolerante de evals.py (`_leer_eventos`): una traza corrupta es un
artefacto a saltear, nunca una excepción.

Uso:
    python3 triaje_trazas.py [--carpeta .runs] [--umbral 120.0] [--salida salidas/evals]
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Reuso EXACTO del parseo y del linter de evals.py: misma vara para todas las
# trazas del proyecto. Se importa (no se copia): una copia local derivaría sin
# que ningún test lo note, y acá la única defensa contra mientes-la-tabla es que
# los números y las violaciones salgan del mismo linter que el resto del harness.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evals import _leer_eventos, linter_traza  # noqa: E402

RAIZ = Path(__file__).resolve().parent
DIR_RUNS = Path(".runs")
DIR_SALIDA = Path("salidas/evals")

# Umbral de duración total (suma de seg de toda la traza) para marcar un outlier.
# 120 s = 2 minutos: una sesión que tardó más que eso concentra el costo y es
# candidata a lectura aunque no tenga violaciones. Alineado con el umbral de
# ceguera de evals.py (UMBRAL_CEGUERA_SEG = 120.0) por coherencia de escala.
UMBRAL_SEG_DEFAULT = 120.0


# ---------------------------------------------------------------------------
# 1) FUNCIÓN PURA (importable y testeable sobre listas sintéticas)
# ---------------------------------------------------------------------------

def seleccionar(evaluaciones, umbral_seg=UMBRAL_SEG_DEFAULT):
    """({nombre: [(nodo, accion, seg), ...]}) → dict {nombre: motivo} de las
    trazas a auditar.

    Una traza entra si cumple AL MENOS una condición:
      - flaggeada por el linter (linter_traza de evals devuelve violaciones), o
      - outlier de duración: suma de seg > umbral_seg.

    Devuelve un dict {nombre: motivo} donde motivo ∈ {"violaciones", "duración",
    "ambos"}, no un set: el MOTIVO es la evidencia que el informe necesita para
    priorizar (ambos > violaciones > duración). El conjunto de claves es lo que
    la spec pide como "set de nombres a auditar" — el dict es ese set + por qué.

    Pura y determinista: no toca disco ni red, recibe el dict ya armado.
    """
    seleccionadas = {}
    for nombre, eventos in evaluaciones.items():
        eventos = eventos or []
        violaciones = linter_traza(list(eventos))
        total_seg = sum(float(e.get("seg", 0.0) or 0.0) for e in eventos)
        tiene_viol = bool(violaciones)
        es_larga = total_seg > umbral_seg
        if tiene_viol and es_larga:
            seleccionadas[nombre] = "ambos"
        elif tiene_viol:
            seleccionadas[nombre] = "violaciones"
        elif es_larga:
            seleccionadas[nombre] = "duración"
    return seleccionadas


def _duracion(eventos):
    """Suma de seg de la traza (0.0 si no hay eventos)."""
    return sum(float(e.get("seg", 0.0) or 0.0) for e in eventos or [])


# ---------------------------------------------------------------------------
# 2) LECTURA DE LA CARPETA (mismo parseo tolerante que el resto del harness)
# ---------------------------------------------------------------------------

def evaluar_runs(directorio=DIR_RUNS, umbral_seg=UMBRAL_SEG_DEFAULT):
    """Lee todos los .runs/*.jsonl, arma el dict de evaluaciones y aplica
    `seleccionar`. Devuelve el informe crudo (dict) que consume `escribir_md`.

    Trazas ilegibles (con contenido pero JSON inválido) y vacías se cuentan
    aparte; el triaje NUNCA se cae por una traza rota."""
    directorio = Path(directorio)
    evaluaciones = {}          # nombre → lista de eventos (solo trazas legibles)
    vacias = []                # tenía contenido 0 bytes: legítimamente vacía
    ilegibles = []             # tenía contenido y no se pudo parsear: rota
    duraciones = {}            # nombre → suma de seg

    for archivo in sorted(directorio.glob("*.jsonl")):
        eventos = _leer_eventos(archivo)
        if not eventos:
            if archivo.stat().st_size > 0:
                ilegibles.append(archivo.name)
            else:
                vacias.append(archivo.name)
            continue
        evaluaciones[archivo.name] = eventos
        duraciones[archivo.name] = _duracion(eventos)

    motivo = seleccionar(evaluaciones, umbral_seg=umbral_seg)

    # Detalle de cada seleccionada, para la tabla del informe.
    detalle = {}
    for nombre, mot in motivo.items():
        eventos = evaluaciones[nombre]
        viol = linter_traza(list(eventos))
        detalle[nombre] = {
            "motivo": mot,
            "violaciones": len(viol),
            "duracion_seg": round(duraciones[nombre], 3),
        }

    total = len(evaluaciones) + len(vacias) + len(ilegibles)
    return {
        "total": total,
        "legibles": len(evaluaciones),
        "vacias": len(vacias),
        "ilegibles": ilegibles,
        "seleccionadas": detalle,
        "n_seleccionadas": len(detalle),
        "umbral_seg": umbral_seg,
        "ahorro_pct": _ahorro(len(detalle), len(evaluaciones)),
    }


def _ahorro(n_sel, n_legibles):
    """% de trazas que NO se auditan (ahorro de llamadas LLM). None si no hay
    trazas legibles (no se puede ahorrar sobre la nada)."""
    if not n_legibles:
        return None
    return (1 - n_sel / n_legibles) * 100.0


# ---------------------------------------------------------------------------
# 3) SALIDAS (informe md, patrón minar_errores / laya_evidencia_*)
# ---------------------------------------------------------------------------

def _fmt_pct(x):
    return f"{x:.1f}%" if x is not None else "—"


# Orden de severidad del motivo: ambos (0) primero, violaciones (1), duración (2).
_ORDEN_MOTIVO = {"ambos": 0, "violaciones": 1, "duración": 2}


def _clave_orden(item):
    """Ordena las seleccionadas por severidad: motivo (ambos → violaciones →
    duración) y, dentro de cada motivo, duración desc (lo más caro primero)."""
    nombre, info = item
    return (_ORDEN_MOTIVO.get(info["motivo"], 99), -info["duracion_seg"], nombre)


def escribir_md(informe, sha, fecha):
    """Informe markdown: el límite honesto ARRIBA (primero lo que el triaje NO
    ve), después el ahorro destacado y la tabla de seleccionadas por severidad."""
    o = []
    o.append("# Triaje de trazas — qué vale la pena auditar\n")
    o.append(f"Fecha {fecha} · git `{sha or '?'}` · "
             f"carpeta `.runs/` · umbral de duración {informe['umbral_seg']:.0f}s\n")

    o.append("## Límite honesto\n")
    o.append("Este triaje ve lo **estructural**: invariantes del wiring (linter "
             "de `evals.py`) y duración (outliers). **NO** ve lo **semántico**: "
             "una decisión mala del agente que no rompe ninguna invariante "
             "(eligió la tool equivocada, respondió de más) es invisible acá — "
             "no viola nada y no tarda.\n")
    o.append("Es un **filtro**, no un reemplazo: dice dónde mirar primero para "
             "gastar menos llamadas LLM. **La auditoría completa sigue "
             "disponible** para cuando haga falta profundidad; decir \"auditamos "
             "todo con esto\" sería mentir sobre la cobertura.\n")

    o.append("## Resumen\n")
    o.append(f"> **Ahorro de la auditoría nocturna: {_fmt_pct(informe['ahorro_pct'])}** "
             f"({informe['n_seleccionadas']}/{informe['legibles']} trazas se auditan; "
             f"el resto se saltea sin gastar una sola llamada LLM).\n")
    o.append("| métrica | valor |")
    o.append("|---|---|")
    o.append(f"| trazas totales | {informe['total']} |")
    o.append(f"| legibles | {informe['legibles']} |")
    o.append(f"| vacías | {informe['vacias']} |")
    if informe["ilegibles"]:
        o.append(f"| ilegibles (salteadas) | {len(informe['ilegibles'])} |")
    o.append(f"| seleccionadas para auditar | {informe['n_seleccionadas']} |")
    o.append("")

    o.append("## Seleccionadas (por severidad)\n")
    o.append("Orden: **ambos** → **violaciones** → **duración** (dentro de cada "
             "motivo, la más larga primero). El motivo es la evidencia que "
             "prioriza la lectura.\n")
    o.append("| traza | motivo | violaciones | duración (s) |")
    o.append("|---|---|---|---|")
    for nombre, info in sorted(informe["seleccionadas"].items(), key=_clave_orden):
        o.append(f"| {nombre} | {info['motivo']} | {info['violaciones']} | "
                 f"{info['duracion_seg']:.1f} |")
    if not informe["seleccionadas"]:
        o.append("| — | — | — | — |")
    o.append("")

    if informe["ilegibles"]:
        o.append("## Trazas ilegibles (no auditables)\n")
        for nombre in informe["ilegibles"]:
            o.append(f"- {nombre}")
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
        description="Triaje determinista de trazas: linter + outliers de duración.")
    parser.add_argument("--carpeta", default=str(DIR_RUNS),
                        help="carpeta de trazas (default: .runs)")
    parser.add_argument("--umbral", type=float, default=UMBRAL_SEG_DEFAULT,
                        help=f"umbral de duración total en segundos "
                             f"(default: {UMBRAL_SEG_DEFAULT:.0f})")
    parser.add_argument("--salida", default=str(DIR_SALIDA),
                        help="directorio de salida (default: salidas/evals)")
    args = parser.parse_args(argv)

    informe = evaluar_runs(args.carpeta, umbral_seg=args.umbral)
    sha = _git_sha()
    fecha = datetime.now().isoformat(timespec="seconds")

    destino = Path(args.salida)
    destino.mkdir(parents=True, exist_ok=True)
    md_path = destino / f"triaje_trazas_{datetime.now().date().isoformat()}.md"
    md_path.write_text(escribir_md(informe, sha, fecha), encoding="utf-8")

    print(f"=== triaje de trazas · {fecha} · git {sha or '?'} ===")
    print(f"  trazas: {informe['total']} · legibles: {informe['legibles']} · "
          f"vacías: {informe['vacias']}"
          + (f" · ilegibles: {len(informe['ilegibles'])}" if informe["ilegibles"] else ""))
    print(f"  seleccionadas: {informe['n_seleccionadas']}/{informe['legibles']} "
          f"(ahorro {_fmt_pct(informe['ahorro_pct'])})")
    print(f"  → {md_path}")


if __name__ == "__main__":
    main()
