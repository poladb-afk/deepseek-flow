"""Bench del juez: la vara que le faltaba a answer_verified (exp/20).

`answer_verified` es la herramienta insignia de calidad y no tenía bench:
cada cambio al juez se validaba a ojo. Esta pieza corre los casos de
`banco/juez_preguntas.jsonl` — etiquetas verificadas mecánicamente contra el
repo por la auditoría — por el MISMO camino de producción
(`juez.responder_con_juez`, rondas default) y los evalúa con CÓDIGO PURO: el
grading no lo hace un modelo.

Dos funciones de evaluación, puras y deterministas:
- `respuesta_ok(texto, caso)`: todos los `contiene` presentes y, si hay
  `contiene_alguno`, al menos uno presente (ambos case-insensitive).
- `cita_ok(texto, caso)`: si el caso no pide cita → None (no aplica). Si
  pide: al menos una cita en el formato de producción (`CITA_RE`, IMPORTADO
  de juez.py, no copiado) cuya ruta termine en `cita_archivo` y cuya LÍNEA
  —leída del disco por nosotros— contenga algún `cita_contiene`. Es la misma
  verificación que hace el Judge en producción, pero INDEPENDIENTE: no
  confiamos en el juez para calificar al juez.

La corrida es SECUENCIAL a propósito: es un instrumento de medición, y el
determinismo importa más que la velocidad.

Baseline (patrón de evals.py, `salidas/evals/bench_juez.json`): sin
`--actualizar-baseline` compara contra el guardado y reporta el delta, pero
NO lo pisa (la tool del chat hereda esta regla); con la flag lo guarda. El
git sha se reutiliza de evals.py.

Uso:
    python3 main.py bench_juez [--preguntas banco/juez_preguntas.jsonl] [--actualizar-baseline]
"""
import argparse
import json
import time
from datetime import date, datetime
from pathlib import Path

from evals import _git_sha
from juez import CITA_RE

PREGUNTAS = Path("banco/juez_preguntas.jsonl")
BASELINE = Path("salidas/evals/bench_juez.json")
DIR_SALIDA = Path("salidas/evals")


# ---------------------------------------------------------------------------
# EVALUACIÓN (código puro, sin LLM)
# ---------------------------------------------------------------------------

def respuesta_ok(texto, caso):
    """Todos los `contiene` presentes (case-insensitive) Y (si el caso trae
    `contiene_alguno`) al menos uno de esos presente. Función pura: no toca
    disco ni red."""
    low = (texto or "").lower()
    if not all(t.lower() in low for t in caso.get("contiene", [])):
        return False
    alguno = caso.get("contiene_alguno", [])
    return not (alguno and not any(t.lower() in low for t in alguno))


def _linea_de(ruta, numero):
    """Contenido real de la línea `numero` de `ruta`, o None si la ruta no es
    un archivo legible o la línea no existe (más allá del EOF, etc.)."""
    try:
        lineas = Path(ruta).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not (1 <= numero <= len(lineas)):
        return None
    return lineas[numero - 1]


def cita_ok(texto, caso):
    """Verificación INDEPENDIENTE de la cita esperada, con el MISMO regex de
    producción (`CITA_RE`, importado de juez.py).

    None si el caso no pide cita (`cita_archivo` ausente). Si pide: True si
    alguna cita del texto apunta a una ruta que termina en `cita_archivo` y
    cuya línea —LEÍDA DEL DISCO con ese número— contiene (case-insensitive)
    al menos un `cita_contiene`; False en cualquier otro caso (incluida una
    cita a línea inexistente)."""
    esperado = caso.get("cita_archivo")
    if not esperado:
        return None
    tokens = [t.lower() for t in caso.get("cita_contiene", [])]
    for ruta, numero in CITA_RE.findall(texto or ""):
        if not ruta.endswith(esperado):
            continue
        linea = _linea_de(ruta, int(numero))
        if linea is None:
            continue
        if not tokens or any(t in linea.lower() for t in tokens):
            return True
    return False


# ---------------------------------------------------------------------------
# CASOS Y CORRIDA
# ---------------------------------------------------------------------------

def cargar_casos(ruta=PREGUNTAS):
    """Casos de `ruta` validados: cada línea debe ser un JSON con `id` y
    `pregunta`. Un archivo roto o un caso incompleto es un SystemExit con
    mensaje CLARO (nunca un silencio que deje el bench midiendo de menos)."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise SystemExit(f"ERROR: no existe el archivo de preguntas: {ruta}")
    casos = []
    for i, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
        if not linea.strip():
            continue
        try:
            caso = json.loads(linea)
        except json.JSONDecodeError as e:
            raise SystemExit(f"ERROR: JSON inválido en {ruta}:{i} ({e.msg})") from e
        if not isinstance(caso, dict):
            raise SystemExit(f"ERROR: el caso de {ruta}:{i} no es un objeto JSON")
        faltan = [c for c in ("id", "pregunta") if not caso.get(c)]
        if faltan:
            raise SystemExit(
                f"ERROR: al caso de {ruta}:{i} le falta {' y '.join(faltan)}")
        casos.append(caso)
    if not casos:
        raise SystemExit(f"ERROR: {ruta} no tiene casos")
    return casos


def detalle_fallo(texto, caso):
    """Explicación legible de por qué falló un caso: qué token de `contiene`
    no apareció y/o qué cita no verificó contra el disco. Lista vacía si el
    caso pasó."""
    razones = []
    low = (texto or "").lower()
    faltan = [t for t in caso.get("contiene", []) if t.lower() not in low]
    if faltan:
        razones.append("faltan tokens: " + ", ".join(repr(t) for t in faltan))
    alguno = caso.get("contiene_alguno", [])
    if alguno and not any(t.lower() in low for t in alguno):
        razones.append("no apareció ninguno de: " + ", ".join(repr(t) for t in alguno))
    estado_cita = cita_ok(texto, caso)
    if estado_cita is False:
        esperado = caso.get("cita_archivo")
        tokens = caso.get("cita_contiene", [])
        citas = CITA_RE.findall(texto or "")
        if not citas:
            razones.append(f"sin citas en formato ruta:línea (se esperaba {esperado})")
        else:
            halladas = ", ".join(f"{r}:{n}" for r, n in citas)
            razones.append(
                f"ninguna cita a {esperado} con la línea que contiene "
                f"{tokens or '(cualquiera)'} (citó: {halladas})")
    return razones


def correr(casos, responder=None):
    """Corre los casos SECUENCIALMENTE, uno por caso, midiendo segundos.

    `responder` es inyectable para los tests (fake sin LLM); en producción es
    `juez.responder_con_juez` (rondas default del juez). Devuelve el dict con
    filas y métricas agregadas."""
    if responder is None:
        from juez import responder_con_juez

        responder = responder_con_juez

    filas = []
    n = len(casos)
    for i, caso in enumerate(casos, 1):
        # PROGRESO: un print ANTES de correr cada caso, para que una corrida
        # parcial sea visible en vivo y se sepa DÓNDE murió si muere.
        print(f"[bench] {i}/{n} {caso['id']}…", flush=True)
        t0 = time.perf_counter()
        try:
            texto, advertencia = responder(caso["pregunta"])
        except Exception as e:  # noqa: BLE001 — el caso fallido es un DATO del bench, no su muerte
            seg = time.perf_counter() - t0
            causa = str(e)[:200]
            filas.append({
                "id": caso["id"],
                "pregunta": caso["pregunta"],
                "trampa": bool(caso.get("trampa", False)),
                "respuesta_ok": False,
                "cita_ok": None,
                "seg": round(seg, 2),
                "razones": [f"excepción: {type(e).__name__}: {causa}"],
                "advertencia": None,
                "respuesta": None,
            })
            print(f"[bench] {i}/{n} {caso['id']} fail", flush=True)
            continue
        seg = time.perf_counter() - t0
        ok = respuesta_ok(texto, caso)
        cita = cita_ok(texto, caso)
        filas.append({
            "id": caso["id"],
            "pregunta": caso["pregunta"],
            "trampa": bool(caso.get("trampa", False)),
            "respuesta_ok": ok,
            "cita_ok": cita,
            "seg": round(seg, 2),
            "razones": detalle_fallo(texto, caso),
            "advertencia": advertencia,
            "respuesta": texto,
        })
        print(f"[bench] {i}/{n} {caso['id']} {'ok' if ok else 'fail'}", flush=True)

    n = len(filas)
    con_cita = [f for f in filas if f["cita_ok"] is not None]
    return {
        "n": n,
        "respuesta_ok": round(sum(f["respuesta_ok"] for f in filas) / n, 4) if n else 0.0,
        "cita_ok": (round(sum(f["cita_ok"] for f in con_cita) / len(con_cita), 4)
                    if con_cita else 0.0),
        "n_con_cita": len(con_cita),
        "filas": filas,
    }


# ---------------------------------------------------------------------------
# BASELINE (patrón de evals.py)
# ---------------------------------------------------------------------------

def comparar_baseline(nuevo, ruta=BASELINE):
    """Compara contra el baseline guardado si existe. Delta por métrica y
    veredicto: PRIMERA CORRIDA (no había baseline), REGRESIÓN (bajó
    respuesta_ok y/o cita_ok, tolerancia 1e-9) u OK. Un baseline ilegible o
    sin métricas no cuenta como referencia."""
    comparacion = {"veredicto": "PRIMERA CORRIDA", "anterior": None, "delta": {}}
    if not Path(ruta).is_file():
        return comparacion
    try:
        anterior = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return comparacion
    if anterior.get("respuesta_ok") is None:
        return comparacion

    comparacion["anterior"] = anterior
    delta_resp = nuevo["respuesta_ok"] - anterior["respuesta_ok"]
    cita_ant = anterior.get("cita_ok")
    delta_cita = (nuevo["cita_ok"] - cita_ant) if cita_ant is not None else None
    comparacion["delta"] = {
        "respuesta_ok": round(delta_resp, 4),
        "cita_ok": round(delta_cita, 4) if delta_cita is not None else None,
    }
    regresion = delta_resp < -1e-9 or (delta_cita is not None and delta_cita < -1e-9)
    comparacion["veredicto"] = "REGRESIÓN" if regresion else "OK"
    return comparacion


def guardar_baseline(bench, ruta=BASELINE, sha=None):
    """Guarda el baseline nuevo {fecha, git_sha, n, respuesta_ok, cita_ok,
    n_con_cita}. Solo si el bench corrió: una corrida sin casos no debe pisar
    un baseline válido."""
    if not bench.get("n"):
        return None
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "git_sha": sha if sha is not None else _git_sha(),
        "n": bench["n"],
        "respuesta_ok": bench["respuesta_ok"],
        "cita_ok": bench["cita_ok"],
        "n_con_cita": bench["n_con_cita"],
    }
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return datos


# ---------------------------------------------------------------------------
# INFORME
# ---------------------------------------------------------------------------

def _fmt_pct(x):
    return f"{x * 100:.1f}%" if x is not None else "—"


def _fmt_cita(v):
    return {True: "✅", False: "🔴", None: "—"}.get(v, "—")


def informe_markdown(bench, comparacion, sha, fecha):
    L = []
    L.append(f"# Bench del juez — {fecha}")
    L.append("")
    L.append(f"git sha: `{sha}`")
    L.append("")
    L.append("La vara del juez (exp/20): los casos de "
             "`banco/juez_preguntas.jsonl` por el MISMO camino de producción "
             "(`juez.responder_con_juez`), evaluados con código puro — el "
             "grading no lo hace un modelo. Corrida SECUENCIAL: el "
             "determinismo importa más que la velocidad.")
    L.append("")
    L.append(f"- Casos: **{bench['n']}**")
    L.append(f"- `respuesta_ok` (principal): **{_fmt_pct(bench['respuesta_ok'])}**")
    L.append(f"- `cita_ok` (sobre {bench['n_con_cita']} que aplican): "
             f"**{_fmt_pct(bench['cita_ok'])}**")
    total_seg = sum(f["seg"] for f in bench["filas"])
    L.append(f"- Tiempo total: {total_seg:.1f}s")
    L.append("")
    v = comparacion["veredicto"]
    icono = {"OK": "✅", "REGRESIÓN": "🔴", "PRIMERA CORRIDA": "🆕"}.get(v, "•")
    L.append(f"**Baseline:** {icono} {v}")
    if comparacion["anterior"]:
        a = comparacion["anterior"]
        d = comparacion["delta"]
        L.append("")
        L.append(f"- Anterior: respuesta_ok {_fmt_pct(a.get('respuesta_ok'))} · "
                 f"cita_ok {_fmt_pct(a.get('cita_ok'))} · {a.get('fecha', '?')} · "
                 f"sha `{(a.get('git_sha') or '?')[:10]}`")
        dr, dc = d.get("respuesta_ok"), d.get("cita_ok")
        L.append(f"- Delta respuesta_ok: {dr:+.4f}" if dr is not None else "- Delta respuesta_ok: —")
        L.append(f"- Delta cita_ok: {dc:+.4f}" if dc is not None else "- Delta cita_ok: —")
    L.append("")
    L.append("## Detalle por caso")
    L.append("")
    L.append("| caso | respuesta_ok | cita_ok | seg |")
    L.append("|------|--------------|---------|-----|")
    for f in bench["filas"]:
        L.append(f"| {f['id']} | {'✅' if f['respuesta_ok'] else '🔴'} | "
                 f"{_fmt_cita(f['cita_ok'])} | {f['seg']:.2f} |")
    L.append("")
    fallos = [f for f in bench["filas"] if not f["respuesta_ok"] or f["cita_ok"] is False]
    if fallos:
        L.append("## Fallos (esperado vs lo que faltó)")
        L.append("")
        for f in fallos:
            L.append(f"### {f['id']}")
            L.append("")
            if f["trampa"]:
                L.append("- (caso trampa)")
            for razon in f["razones"]:
                L.append(f"- {razon}")
            if f["advertencia"]:
                L.append(f"- ⚠️  {f['advertencia']}")
            L.append("")
            L.append("<details><summary>respuesta cruda</summary>")
            L.append("")
            L.append("```")
            L.append((f["respuesta"] or "").strip())
            L.append("```")
            L.append("")
            L.append("</details>")
            L.append("")
    return "\n".join(L)


def generar(preguntas=PREGUNTAS, dir_salida=DIR_SALIDA, responder=None, sha=None,
            actualizar_baseline=False):
    """Corre el bench y escribe UN informe markdown. Sin `actualizar_baseline`
    compara contra el baseline pero NO lo pisa (regla que la tool del chat
    hereda); con la flag lo guarda. Devuelve el Path del informe."""
    fecha = date.today().isoformat()
    sha = sha if sha is not None else _git_sha()

    casos = cargar_casos(preguntas)
    bench = correr(casos, responder=responder)
    comparacion = comparar_baseline(bench)
    if actualizar_baseline:
        guardar_baseline(bench, sha=sha)

    md = informe_markdown(bench, comparacion, sha, fecha)
    dir_salida = Path(dir_salida)
    dir_salida.mkdir(parents=True, exist_ok=True)
    destino = dir_salida / f"bench_juez_{fecha}.md"
    destino.write_text(md, encoding="utf-8")
    return destino


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="bench_juez",
        description="Bench del juez: casos verificados por el camino de producción, grading en código puro")
    parser.add_argument("--preguntas", default=str(PREGUNTAS),
                        help="archivo .jsonl de casos (default: %(default)s)")
    parser.add_argument("--salida", default=str(DIR_SALIDA),
                        help="carpeta del informe (default: %(default)s)")
    parser.add_argument("--actualizar-baseline", action="store_true",
                        help="guarda el baseline; sin esta flag se compara y NO se pisa")
    args = parser.parse_args(argv)

    destino = generar(preguntas=args.preguntas, dir_salida=args.salida,
                      actualizar_baseline=args.actualizar_baseline)
    print(f"✓ informe del bench del juez → {destino}")


if __name__ == "__main__":
    main()
