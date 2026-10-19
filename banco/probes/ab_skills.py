"""exp/56 — A/B del efecto de la skill `revision` (pre-registrado).

**Pregunta:** ¿cambia la skill la REVISIÓN de un archivo con 3 issues
plantados (global muerta + parámetro sin usar; `except` amplio mudo; docstring
que miente), medido con señales DETERMINISTAS (sin juez LLM)?

**Criterio PRE-REGISTRADO (fijado antes de correr; está en `CRITERIO` y en
el artefacto):** con n=3 por brazo, la skill sirve si:
1. detección media de los 3 issues ≥ control + 1;
2. proporción de citas archivo:línea VÁLIDAS contra el disco (utils/citas) en
   el brazo skill ≥ control;
3. citas inválidas (archivo/línea inexistente, fuera de raíces) = 0 en skill;
4. no infla el ruido: palabras del brazo skill ≤ 1,4× control.
Si falla, se documenta el NEGATIVO (la skill queda como mecanismo, se declara
sin efecto medido) — no se retoca el criterio después.

**Método:** escenarios `exp56-skill-revision-off/on` (mismo prompt; único
cambio `SKILLS=0|1`, `CITAS_VERIFICAR=0`). La respuesta final del turno se
extrae del transcript del banco; detección por palabras clave del issue
(declaradas abajo); citas verificadas con la MISMA función del producto
(`utils.citas.verificar_citas`). Límite declarado: los issues son plantados y
las keywords son una aproximación; mide comportamiento, no calidad absoluta.
**exp/56b (mismo criterio, sin techo):** `PREFETCH=0` (el modelo debe leer por
tools) y fixture `revision_target_dificil.py` con issues SUTILES (off-by-one,
mutación de estado global entre llamadas, denominador mal calculado). Se
pre-registró ANTES de correr que se aplica el mismo criterio de 4 puntos; si
tampoco hay lift, el valor medido de la skill es bajar ruido (exp/56) y se
documenta el negativo.

Uso: python3 banco/probes/ab_skills.py [--exp 56|56b] [--runs 3]
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from utils.citas import verificar_citas  # noqa: E402

EXPERIMENTOS = {
    "56": {
        "escenarios": {
            "off": "banco/escenarios/exp56-skill-revision-off.yaml",
            "on": "banco/escenarios/exp56-skill-revision-on.yaml",
        },
        "prefijo": "exp56-skill-revision",
        "issues": {},  # se completa abajo
    },
    "56b": {
        "escenarios": {
            "off": "banco/escenarios/exp56b-skill-revision-off.yaml",
            "on": "banco/escenarios/exp56b-skill-revision-on.yaml",
        },
        "prefijo": "exp56b-skill-revision",
        "issues": {},
    },
}
ESCENARIOS = EXPERIMENTOS["56"]["escenarios"]
# Issues plantados en el fixture y las palabras que cuentan como haberlos visto.
ISSUES_56 = {
    "global_muerta_param_sin_usar": (
        "cache", "sin usar", "sin uso", "nunca se usa", "no se usa", "vestigial",
        "muerta", "muerto", "unused", "dead", "parámetro sin", "parametro sin",
    ),
    "except_amplio_mudo": (
        "except", "amplio", "silenci", "mudo", "traga", "enmascara", "oculta",
        "error masking", "se come",
    ),
    "docstring_miente_unidad": (
        "docstring", "0-100", "0–100", "fracción", "fraccion", "miente",
        "contradice", "unidad", "porcentaje", "no coincide",
    ),
}

# exp/56b: issues SUTILES (el control puede no verlos; la detección tiene margen).
ISSUES_56B = {
    "off_by_one": (
        "off-by-one", "off by one", "saltea el último", "saltea el ultimo",
        "omite el último", "omite el ultimo", "no procesa el último",
        "se come el último", "se come el ultimo", "queda afuera el último",
        "ultimo elemento", "último elemento",
    ),
    "muta_estado_global": (
        "muta", "mutación", "mutacion", "estado global", "variable global",
        "lista global", "global compartida", "entre llamadas", "no es idempotente",
        "efecto secundario", "side effect", "se acumula",
    ),
    "denominador_original": (
        "denominador", "divide por len(valores)", "longitud original",
        "incluye los inválidos", "incluye los invalidos", "cuenta los inválidos",
        "cuenta los invalidos", "len(valores) en vez", "promedio mal calculado",
        "sesga el promedio", "lista original",
    ),
}
EXPERIMENTOS["56"]["issues"] = ISSUES_56
EXPERIMENTOS["56b"]["issues"] = ISSUES_56B

CRITERIO = (
    "con n=3 por brazo: (1) detección media skill >= control + 1; "
    "(2) citas válidas skill >= control; (3) citas inválidas skill = 0; "
    "(4) palabras skill <= 1.4x control"
)


def extraer_respuesta_final(log):
    """El ÚLTIMO mensaje del asistente de la sesión (el cierre del turno de
    revisión; el transcript del banco no ecoa la pregunta, así que se ancla en
    el último bloque `DeepSeek:` y termina en el próximo `Tú:`)."""
    lineas = log.splitlines()
    ultimo = next((i for i in range(len(lineas) - 1, -1, -1)
                   if lineas[i].startswith("DeepSeek:")), None)
    if ultimo is None:
        return ""
    fin = next((i for i in range(ultimo + 1, len(lineas))
                if lineas[i].startswith("Tú:")), len(lineas))
    texto = [lineas[ultimo][len("DeepSeek: "):], *lineas[ultimo + 1:fin]]
    return "\n".join(texto).strip()


def detectar_issues(texto, issues=None):
    """{issue: bool} por palabras clave declaradas (lowercase)."""
    issues = issues or ISSUES_56
    bajo = (texto or "").lower()
    return {nombre: any(clave in bajo for clave in claves)
            for nombre, claves in issues.items()}


def medir_respuesta(texto, verificar=None, issues=None):
    """Métricas deterministas de una respuesta de revisión."""
    verificar = verificar or verificar_citas
    issues = issues or ISSUES_56
    citas = verificar(texto or "")
    detectados = detectar_issues(texto, issues)
    return {
        "palabras": len((texto or "").split()),
        "issues": detectados,
        "issues_detectados": sum(detectados.values()),
        "citas_total": citas["total"],
        "citas_ok": citas["ok"],
        "citas_invalidas": len(citas["mal"]),
    }


def resumen(filas):
    """Agregado por brazo de las filas válidas."""
    salida = {}
    for brazo in ("off", "on"):
        validas = [f for f in filas if f["brazo"] == brazo and f["valida"]]
        if not validas:
            salida[brazo] = {"filas": 0}
            continue
        citas_total = sum(f["citas_total"] for f in validas)
        salida[brazo] = {
            "filas": len(validas),
            "issues_media": round(statistics.mean(f["issues_detectados"] for f in validas), 2),
            "citas_ok_ratio": round(sum(f["citas_ok"] for f in validas) / citas_total, 3)
            if citas_total else 0.0,
            "citas_invalidas": sum(f["citas_invalidas"] for f in validas),
            "palabras_media": round(statistics.mean(f["palabras"] for f in validas), 1),
            "seg_media": round(statistics.mean(f["seg"] for f in validas), 1),
            "rondas_media": round(statistics.mean(f["rondas"] for f in validas), 1),
        }
    return salida


def veredicto(resumenes):
    """Aplica el criterio pre-registrado; devuelve (cumple, fallas)."""
    off, on = resumenes.get("off", {}), resumenes.get("on", {})
    if not off.get("filas") or not on.get("filas"):
        return False, ["sin filas válidas en un brazo"]
    fallas = []
    if on["issues_media"] < off["issues_media"] + 1:
        fallas.append(f"(1) detección {on['issues_media']} < control {off['issues_media']} + 1")
    if on["citas_ok_ratio"] < off["citas_ok_ratio"]:
        fallas.append(f"(2) citas válidas {on['citas_ok_ratio']} < control {off['citas_ok_ratio']}")
    if on["citas_invalidas"] != 0:
        fallas.append(f"(3) {on['citas_invalidas']} citas inválidas en skill")
    if off.get("palabras_media") and on["palabras_media"] > 1.4 * off["palabras_media"]:
        fallas.append(f"(4) ruido: {on['palabras_media']} palabras > 1.4x {off['palabras_media']}")
    return not fallas, fallas


def _eventos_del_turno(log_path):
    """seg y rondas del turno `revision` desde el JSONL hermano del banco."""
    ruta = Path(log_path).with_suffix(".jsonl")
    seg, rondas = 0.0, 0
    try:
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            evento = json.loads(linea)
            if (evento.get("tipo") == "turno-fin"
                    and (evento.get("detalle") or {}).get("id") == "revision"):
                detalle = evento["detalle"]
                seg = detalle.get("seg", 0.0)
                rondas = (detalle.get("marcadores") or {}).get("ronda", 0)
    except (OSError, json.JSONDecodeError):
        pass
    return seg, rondas


def correr_sesion(brazo, experimento="56"):
    config = EXPERIMENTOS[experimento]
    inicio = time.perf_counter()
    proceso = subprocess.run([sys.executable, "banco/banco.py",
                              config["escenarios"][brazo]],
                             cwd=RAIZ, capture_output=True, text=True, timeout=1200)
    segundos = round(time.perf_counter() - inicio, 1)
    logs = sorted((RAIZ / "salidas" / "banco").glob(f"{config['prefijo']}-{brazo}_*.log"),
                  key=lambda ruta: ruta.stat().st_mtime)
    if not logs:
        return {"brazo": brazo, "ok": False, "valida": False,
                "motivo": "sin transcript", "seg": segundos}
    log_path = logs[-1]
    log = log_path.read_text(encoding="utf-8")
    activo = "[skill] revision" in log
    esperado = brazo == "on"
    texto = extraer_respuesta_final(log)
    fila = {"brazo": brazo, "ok": proceso.returncode == 0, "valida": activo == esperado,
            "motivo": "" if activo == esperado else f"marcador de skill inesperado ({activo})",
            "traza": log_path.name, "seg": segundos}
    fila.update(medir_respuesta(texto, issues=EXPERIMENTOS[experimento]["issues"]))
    seg_turno, rondas = _eventos_del_turno(str(log_path))
    fila["seg"] = seg_turno or segundos
    fila["rondas"] = rondas
    return fila


def main_probe(argv=None):
    parser = argparse.ArgumentParser(description="exp/56: A/B de la skill revision")
    parser.add_argument("--exp", choices=tuple(EXPERIMENTOS), default="56",
                        help="experimento (default 56)")
    parser.add_argument("--runs", type=int, default=3, help="corridas por brazo (default 3)")
    args = parser.parse_args(argv)

    filas = []
    for turno in range(args.runs):
        for brazo in ("off", "on"):
            print(f"  · {brazo}/r{turno + 1}…", flush=True)
            fila = correr_sesion(brazo, args.exp)
            fila["run"] = turno + 1
            filas.append(fila)
            print(f"    ok={fila.get('ok')} valida={fila.get('valida')} "
                  f"issues={fila.get('issues_detectados')} citas="
                  f"{fila.get('citas_ok')}/{fila.get('citas_total')} "
                  f"palabras={fila.get('palabras')} seg={fila.get('seg')}", flush=True)

    resumenes = resumen(filas)
    cumple, fallas = veredicto(resumenes)
    print(f"\n== exp/{args.exp} A/B skill `revision` (n={args.runs} por brazo) ==")
    for brazo, datos in resumenes.items():
        print(f"  {brazo:3}: {datos}")
    print(f"  criterio: {CRITERIO}")
    print("  veredicto:", "✅ CUMPLE" if cumple else "❌ NO CUMPLE", fallas if fallas else "")

    destino = RAIZ / "salidas" / "evals"
    destino.mkdir(parents=True, exist_ok=True)
    salida = destino / f"ab_skills{args.exp}_{datetime.now():%Y%m%d_%H%M%S}.json"
    salida.write_text(json.dumps({
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "experimento": args.exp,
        "runs": args.runs,
        "criterio": CRITERIO,
        "resumen": resumenes,
        "veredicto": "CUMPLE" if cumple else "NO CUMPLE",
        "fallas": fallas,
        "filas": filas,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"artefacto: {salida.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main_probe())
