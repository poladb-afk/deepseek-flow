"""exp/45 — el veredicto del router con datos propios (criterio PRE-REGISTRADO).

**Criterio pre-registrado** (roadmap, fijado el 2026-10-13 ANTES de juntar
estos datos, para que no se elija después de ver el resultado): con ≥100
decisiones etiquetadas por la flywheel (exp/43), si la **base rate de
"directo"** es <10% → apagar el router (no hay ahorro que justifique el
riesgo); si no → elegir **alpha de la curva conformal propia** y pasar a
enforce con calibración ambiental.

Código puro: sin LLM, sin red, determinista. La etiqueta ambiental mide lo que
DeepSeek HIZO en shadow (límite declarado en etiquetar_ambiental.py).

Uso:
    python3 banco/probes/veredicto_router.py [--calibracion RUTA] [--alphas 0.02,0.05,0.10]
"""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

from utils.conformal import cobertura_loo, conjunto, cuantil_conformal, puntaje  # noqa: E402

UMBRAL_APAGAR = 0.10  # pre-registrado
ALPHAS = (0.02, 0.05, 0.10, 0.15, 0.20, 0.30)


def leer_filas(ruta):
    """Las filas de calibración ambiental ({conf, correcto, laya, etiqueta, ts})."""
    return [json.loads(linea) for linea in Path(ruta).read_text(encoding="utf-8").splitlines() if linea.strip()]


def composicion(filas, excluir_dia=None):
    """n, base rate de la etiqueta "directo", recall de Laya y mezcla por día."""
    seleccion = [f for f in filas if excluir_dia is None or _dia(f) != excluir_dia]
    n = len(seleccion)
    directo = sum(1 for f in seleccion if f["etiqueta"] == "directo")
    propuestas = [f for f in seleccion if f["laya"] == "directo"]
    aciertos = sum(1 for f in propuestas if f["correcto"])
    por_dia = {}
    for f in seleccion:
        dia = _dia(f)
        por_dia.setdefault(dia, {"n": 0, "directo": 0})
        por_dia[dia]["n"] += 1
        por_dia[dia]["directo"] += 1 if f["etiqueta"] == "directo" else 0
    return {
        "n": n,
        "directo": directo,
        "base_rate": directo / n if n else 0.0,
        "propuestas_directo": len(propuestas),
        "propuestas_directo_ok": aciertos,
        "recall": len(propuestas) / directo if directo else None,
        "precision_directo": aciertos / len(propuestas) if propuestas else None,
        "por_dia": dict(sorted(por_dia.items())),
    }


def _dia(fila):
    ts = fila.get("ts")
    return datetime.fromtimestamp(ts).date().isoformat() if isinstance(ts, (int, float)) and ts > 0 else "sin-ts"


def decidir(base_rate, umbral=UMBRAL_APAGAR):
    """La regla pre-registrada: base rate < umbral → APAGAR; si no → SEGUIR."""
    return "APAGAR" if base_rate < umbral else "SEGUIR"


def curva(filas, alphas=ALPHAS):
    """Curva conformal LOO: cobertura global y, por separado, los `directo`.

    La decisión del router solo cambia el mundo cuando aplica `directo`; por eso
    la precisión que importa es la de los directos aceptados (un falso directo
    responde sin leer lo que hacía falta).
    """
    casos = [{"conf": float(f["conf"]), "correcto": bool(f["correcto"])} for f in filas]
    n = len(casos)
    filas_curva = []
    for alpha in alphas:
        q = cuantil_conformal([puntaje(c["conf"], c["correcto"]) for c in casos], alpha)
        m = cobertura_loo(casos, alpha)
        directo_aceptado = directo_ok = 0
        for i, fila in enumerate(filas):
            otros = [puntaje(casos[j]["conf"], casos[j]["correcto"]) for j in range(n) if j != i]
            q_caso = cuantil_conformal(otros, alpha)
            if len(conjunto(casos[i]["conf"], q_caso)) != 1 or fila["laya"] != "directo":
                continue
            directo_aceptado += 1
            directo_ok += 1 if fila["correcto"] else 0
        filas_curva.append({
            "alpha": alpha,
            "q": None if q == float("inf") else round(q, 3),
            "umbral": None if q == float("inf") else round(1.0 - q, 3),
            "cobertura": round(m["cobertura"], 3),
            "precision_global": None if m["precision"] is None else round(m["precision"], 3),
            "directo_aceptado": directo_aceptado,
            "directo_ok": directo_ok,
            "directo_precision": (directo_ok / directo_aceptado) if directo_aceptado else None,
        })
    return filas_curva


def elegir_alpha(filas_curva, precision_min=1.0):
    """El alpha más útil que mantiene precision_min en los `directo` aceptados.

    "Más útil" = más directos servidos localmente (más turnos ahorrados). Si
    ninguno cumple la precisión, None: se queda con la compuerta fija.
    """
    candidatos = [
        f for f in filas_curva
        if f["directo_aceptado"] > 0 and f["directo_precision"] is not None
        and f["directo_precision"] >= precision_min
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda f: (f["directo_aceptado"], f["cobertura"]))


def _ruta_visible(ruta):
    """La ruta relativa al repo si está adentro (portable, regla X9)."""
    try:
        return Path(ruta).resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return str(ruta)


def informe(calibracion, filas):
    """El markdown del veredicto (determinista)."""
    comp = composicion(filas)
    comp_sin_hoy = composicion(filas, excluir_dia=date.today().isoformat())
    verdicto = decidir(comp["base_rate"])
    tabla = curva(filas)
    elegido = elegir_alpha(tabla, precision_min=1.0)
    lineas = [
        "# exp/45 — veredicto del router con datos propios",
        "",
        f"**Calibración:** `{calibracion}` · pares etiquetados: **{comp['n']}** "
        f"(el pre-registro pide ≥100).",
        "",
        "## Criterio pre-registrado",
        f"base rate de `directo` < {UMBRAL_APAGAR:.0%} → **APAGAR**; si no → alpha propio + enforce.",
        "",
        "## Base rate",
        f"- **directo: {comp['directo']}/{comp['n']} = {comp['base_rate']:.1%}** → **{verdicto}**",
        f"- Laya propuso directo {comp['propuestas_directo']} veces "
        f"({comp['precision_directo']:.0%} de precisión) → recall {comp['recall']:.0%} de los directo reales."
        if comp["recall"] is not None else "- Laya propuso directo 0 veces.",
        f"- Sensibilidad (sin el tráfico sintético de hoy): "
        f"{comp_sin_hoy['directo']}/{comp_sin_hoy['n']} = {comp_sin_hoy['base_rate']:.1%} → "
        f"{decidir(comp_sin_hoy['base_rate'])}.",
        "",
        "## Mezcla por día",
        "| día | pares | directo |",
        "|---|---|---|",
    ]
    for dia, d in comp["por_dia"].items():
        lineas.append(f"| {dia} | {d['n']} | {d['directo']} |")
    lineas += [
        "",
        "## Curva conformal propia (LOO)",
        "| alpha | q | umbral | cobertura | precision global | directo servidos | directo OK | precision directo |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for f in tabla:
        lineas.append(
            f"| {f['alpha']:.2f} | {f['q']} | {f['umbral']} | {f['cobertura']} | "
            f"{f['precision_global']} | {f['directo_aceptado']} | {f['directo_ok']} | {f['directo_precision']} |"
        )
    lineas += ["", "## Veredicto"]
    if verdicto == "APAGAR":
        lineas.append("**APAGAR el router** (pre-registrado): la base rate es <10% y no hay ahorro que justifique el riesgo.")
    elif elegido is None:
        lineas.append("**SEGUIR, pero sin enforce**: ningún alpha del propio set sirve directo con precisión 1,0; "
                      "se queda la compuerta fija y se junta más calibración.")
    else:
        ahorro = elegido["directo_aceptado"] / comp["n"]
        lineas += [
            f"**SEGUIR + enforce** con `LAYA_ALPHA={elegido['alpha']:.2f}` (calibración ambiental propia): "
            f"sirve {elegido['directo_aceptado']}/{comp['n']} turnos directo ({ahorro:.1%}) con precisión "
            f"{elegido['directo_precision']:.0%} en esos directos.",
            "",
            "```",
            "LAYA_MODO=enforce",
            f"LAYA_CALIBRACION_ROUTER={_ruta_visible(calibracion)}",
            f"LAYA_ALPHA={elegido['alpha']:.2f}",
            "```",
            "",
            f"Límites: n={comp['n']}, etiqueta ambiental (lo que DeepSeek hizo, no lo que la pregunta "
            "necesitaba), recall del router "
            f"{comp['recall']:.0%}; el ahorro efectivo es chico y hay que vigilar falsos directo.",
        ]
    return "\n".join(lineas) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="veredicto_router", description="exp/45: veredicto del router")
    parser.add_argument("--calibracion", default=None,
                        help="JSONL de etiqueta ambiental (default: el más reciente en banco/)")
    parser.add_argument("--salida", default=None,
                        help="markdown de salida (default: salidas/evals/veredicto_router_FECHA.md)")
    args = parser.parse_args(argv)
    if args.calibracion is None:
        candidatos = sorted(RAIZ.glob("banco/calibracion_ambiental_*.jsonl"))
        if not candidatos:
            raise SystemExit("no hay calibración ambiental en banco/; corré etiquetar_ambiental.py")
        args.calibracion = candidatos[-1]
    filas = leer_filas(args.calibracion)
    texto = informe(args.calibracion, filas)
    destino = Path(args.salida or (RAIZ / "salidas" / "evals" /
                                   f"veredicto_router_{date.today().isoformat()}.md"))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"artefacto: {destino.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
