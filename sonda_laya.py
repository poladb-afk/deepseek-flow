"""Sonda de evidencia de los checkpoints de Laya: ECE propio, confiabilidad
por bucket, curva de compuerta, latencia local y RSS pico.

Motivación (exp/7): las afirmaciones sobre calibración, acierto crudo y
"ahorro" de los checkpoints venían heredadas de notas, no medidas con
nuestra propia vara. Esta sonda convierte esas afirmaciones en números:
corre el test etiquetado de UN checkpoint y escribe md+json en salidas/evals/.

Es determinista a propósito: SIN LLM, SIN red, SIN DeepSeek. Solo carga el
checkpoint local (en CPU), infiere cada caso del test y agrega métricas.

LEY DE RAM: exactamente UN checkpoint por proceso. Se carga, se mide, se
escribe y el proceso TERMINA. No hay modo multi-checkpoint ni servidor:
cargar dos de estos en el mismo proceso revienta la memoria (medido).

Uso:
    python3 sonda_laya.py router        # .modelos/router_flow-1k + test router (30)
    python3 sonda_laya.py voto          # .modelos/router_voto + test voto (30)
    python3 sonda_laya.py supervisor    # .modelos/supervisor_dispatch-1k + test (24)
    python3 sonda_laya.py base          # .modelos/laya-multilingual + test router (referencia)
"""
import argparse
import json
import os
import resource
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RAIZ = Path(__file__).resolve().parent
TAREAS = Path("/home/roquedb/Documentos/00_IA/bmo/train/tasks")
SALIDA = RAIZ / "salidas" / "evals"

# Los contratos EXISTENTES se importan, no se copian: una copia local derivaría
# del contrato del fine-tune sin que ningún test lo note (mismo criterio que
# sonda_router.py). Los tests son los mismos que leen evals.py y las sondas.
from nodes import PREGUNTA_ROUTER, PREGUNTA_VOTO  # noqa: E402
from supervisor import PREGUNTA_DESPACHO  # noqa: E402

# El mapeo nombre → (checkpoint, test, pregunta, arma el estado por caso).
# El estado de cada familia es el contrato del fine-tune correspondiente:
#   router/voto → {"pregunta": fields["pregunta"]}
#   supervisor → {"tarea": fields["tarea"], "hechos": fields.get("hechos", "")}
# (hechos puede ser string multilínea o venir vacío: el .get con default "" cubre
# el caso vacío; probado contra los tres .jsonl, un caso por línea).
ESPECIFICACIONES = {
    "router": {
        "checkpoint": ".modelos/router_flow-1k",
        "test": TAREAS / "router_flow_test.jsonl",
        "pregunta": "necesita_herramientas",
        "contrato": PREGUNTA_ROUTER,
        "estado": lambda f: {"pregunta": f["pregunta"]},
    },
    "voto": {
        "checkpoint": ".modelos/router_voto",
        "test": TAREAS / "router_voto_test.jsonl",
        "pregunta": "confirma_herramientas",
        "contrato": PREGUNTA_VOTO,
        "estado": lambda f: {"pregunta": f["pregunta"]},
    },
    "supervisor": {
        "checkpoint": ".modelos/supervisor_dispatch-1k",
        "test": TAREAS / "supervisor_dispatch_test.jsonl",
        "pregunta": "elegir_proxima",
        "contrato": PREGUNTA_DESPACHO,
        "estado": lambda f: {"tarea": f["tarea"], "hechos": f.get("hechos", "")},
    },
    "base": {
        "checkpoint": ".modelos/laya-multilingual",
        "test": TAREAS / "router_flow_test.jsonl",
        "pregunta": "necesita_herramientas",
        "contrato": PREGUNTA_ROUTER,
        "estado": lambda f: {"pregunta": f["pregunta"]},
    },
}

# Los bordes de la tabla de confiabilidad: 5 buckets sobre [0.5, 1].
BORDES = [0.5, 0.7, 0.85, 0.95]


# ---------------------------------------------------------------------------
# Métricas — funciones PURAS sobre una lista de casos. Puras para poder
# testearlas sin cargar el modelo (un checkpoint son GB y minutos): la
# aritmética de calibración se verifica sola, el modelo se mide aparte.

def tabla_confiabilidad(casos, bordes=BORDES):
    """Acierto y conteo por bucket de answer_confidence.

    `bordes` son los cortes inferiores de cada bucket, p. ej. [0.5, 0.7, 0.85, 0.95]
    da los buckets [0.5,0.7) [0.7,0.85) [0.85,0.95) [0.95,1.0] y un último
    [1.0,∞) que recoge el 1.0 exacto. Devuelve una lista de dicts con
    lo/hi/conf_media/acierto/n/conf_observada (la confianza media del bucket
    es la que se compara contra el acierto para leer la calibración).
    """
    filas = []
    for i, lo in enumerate(bordes):
        hi = bordes[i + 1] if i + 1 < len(bordes) else None
        # El último bucket arranca en el último borde y es abierto hacia arriba,
        # para que conf==1.0 entre (con un tope cerrado se caería del histograma).
        dentro = [c for c in casos if c["conf"] >= lo and (hi is None or c["conf"] < hi)]
        n = len(dentro)
        filas.append({
            "lo": lo,
            "hi": hi,
            "conf_media": (sum(c["conf"] for c in dentro) / n) if n else None,
            "acierto": (sum(c["correcto"] for c in dentro) / n) if n else None,
            "n": n,
        })
    return filas


def curva_compuerta(casos, umbrales=None):
    """Por umbral t: cobertura = fracción con conf >= t (los que la compuerta
    decidiría locales), precisión = acierto crudo entre esos casos, y ahorro
    = cobertura (1 llamada externa evitada por caso local).

    Es la curva que justifica la compuerta: subir t compra precisión a costa
    de cobertura. El umbral de producción (LAY A_UNSURE_*) es un punto de la
    curva."""
    if umbrales is None:
        umbrales = [round(0.5 + 0.05 * i, 2) for i in range(10)]  # 0.50 .. 0.95
    filas = []
    for t in umbrales:
        locales = [c for c in casos if c["conf"] >= t]
        n = len(locales)
        filas.append({
            "umbral": t,
            "cobertura": n / len(casos) if casos else 0.0,
            "precision": (sum(c["correcto"] for c in locales) / n) if n else None,
            "ahorro": n / len(casos) if casos else 0.0,
            "n_locales": n,
        })
    return filas


def ece_local(casos, bins=10):
    """ECE con bins iguales en [0,1] sobre answer_confidence.

    Esperado de acierto por bin = media de correcto (0/1); observado = media
    de conf. ECE = suma ponderada por n_bin/n de |esperado - observado|.
    Es la implementación de respaldo, usada cuando laya.ece_score no está:
    la salida documenta cuál se usó para que el número sea trazable.
    """
    if not casos:
        return None
    total = len(casos)
    ece_val = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        # El último bin cierra el borde derecho para incluir conf == 1.0.
        dentro = [c for c in casos if c["conf"] >= lo and (c["conf"] < hi or (b == bins - 1 and c["conf"] <= hi))]
        if not dentro:
            continue
        esperado = sum(c["correcto"] for c in dentro) / len(dentro)
        observado = sum(c["conf"] for c in dentro) / len(dentro)
        ece_val += (len(dentro) / total) * abs(esperado - observado)
    return ece_val


def ece(casos):
    """ECE sobre answer_confidence, con laya.ece_score si su firma lo permite.

    Devuelve (valor, fuente) con fuente en {"laya.ece_score", "local:10bins"}
    para poder documentar cuál se usó. La firma de laya.ece_score no está fijada
    por contrato, así que se prueba a llamarla con los pares (conf, correcto) y
    si no encaja se cae a la implementación local — nunca se rompe por esto.
    """
    if not casos:
        return None, "local:10bins"
    try:
        import laya  # import perezoso: solo existe si el checkpoint se pudo cargar

        ece_score = getattr(laya, "ece_score", None)
        if callable(ece_score):
            try:
                valor = ece_score([c["conf"] for c in casos], [c["correcto"] for c in casos])
                return float(valor), "laya.ece_score"
            except TypeError:
                pass  # otra firma: no adivinamos, usamos la nuestra
    except Exception:
        pass
    return ece_local(casos), "local:10bins"


# ---------------------------------------------------------------------------
# Medición

def percentil(valores, p):
    """Percentil por interpolación lineal (método igual al de numpy en su
    default): no dependemos de numpy para esto, la sonda corre pelada."""
    if not valores:
        return None
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]
    pos = p / 100 * (len(ordenados) - 1)
    i = int(pos)
    frac = pos - i
    if i + 1 >= len(ordenados):
        return ordenados[i]
    return ordenados[i] * (1 - frac) + ordenados[i + 1] * frac


def cargar_casos(test):
    return [json.loads(linea) for linea in test.read_text(encoding="utf-8").splitlines() if linea.strip()]


def correr(nombre, spec):
    """Carga UN checkpoint, corre el test caso por caso y devuelve el informe.

    La carga se mide APARTE de la inferencia: el tiempo de carga en frío es
    costo fijo por proceso, la latencia por caso es el costo variable que
    decide si Laya ahorra una llamada remota. Mezclarlas escondería las dos.
    """
    from utils.laya import agente

    casos = cargar_casos(spec["test"])
    if not casos:
        raise SystemExit(f"test vacío: {spec['test']}")

    # Un setting PROPIO por corrida: utils.laya cachea agentes por setting y
    # hereda HF_HUB_OFFLINE antes de importar, el caché de errores y el RLock.
    # Al setear env var + nombre de setting nos aseguramos de no pisar ni
    # reusar el agente de LAYA_MODEL (router del chat) o del supervisor.
    os.environ["SONDA_LAYA_CKPT"] = str(RAIZ / spec["checkpoint"])
    t0 = time.perf_counter()
    a = agente("SONDA_LAYA_CKPT")
    carga_ms = (time.perf_counter() - t0) * 1000

    filas, errores = [], []
    for caso in casos:
        estado = spec["estado"](caso["fields"])
        t1 = time.perf_counter()
        r = a.system_one(estado, spec["contrato"], lang="es")
        latencia_ms = (time.perf_counter() - t1) * 1000
        resp = r["answers"][spec["pregunta"]]
        eleccion = resp.get("choice", resp.get("answer"))
        conf = resp["answer_confidence"] if resp.get("answer_confidence") is not None else resp.get("confidence", 0.0)
        esperado = caso["answers"][spec["pregunta"]]
        correcto = eleccion == esperado
        filas.append({
            "id": caso["id"],
            "esperado": esperado,
            "obtenido": eleccion,
            "conf": conf,
            "correcto": correcto,
            "latencia_ms": latencia_ms,
        })
        if not correcto:
            errores.append({"id": caso["id"], "esperado": esperado, "obtenido": eleccion, "conf": conf})

    latencias = [f["latencia_ms"] for f in filas]
    score = sum(f["correcto"] for f in filas) / len(filas)
    ece_val, ece_fuente = ece(filas)
    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KB en Linux

    # git sha corto para anclar el número a un commit exacto (patrón bench_router.json).
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=RAIZ, capture_output=True, text=True, timeout=10,
        ).stdout.strip() or None
    except Exception:
        sha = None

    return {
        "nombre": nombre,
        "checkpoint": spec["checkpoint"],
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "git_sha": sha,
        "n": len(filas),
        "score": score,
        "ece": ece_val,
        "ece_fuente": ece_fuente,
        "latencia_p50_ms": percentil(latencias, 50),
        "latencia_p95_ms": percentil(latencias, 95),
        "carga_ms": carga_ms,
        "rss_max_kb": rss_kb,
        "tabla_confiabilidad": tabla_confiabilidad(filas),
        "curva_compuerta": curva_compuerta(filas),
        "fallos": errores,
        "casos": filas,
    }


def escribir_md(informe):
    """Informe legible: resumen, confiabilidad, curva y fallos con su confianza
    exacta (para poder discutir cada error, no solo el agregado)."""
    o = []
    o.append(f"# Evidencia Laya — `{informe['nombre']}`\n")
    o.append(f"Checkpoint: `{informe['checkpoint']}` · fecha {informe['fecha']} · git `{informe['git_sha']}`\n")
    o.append("## Resumen\n")
    o.append(f"- Casos: {informe['n']}")
    o.append(f"- Acierto crudo: {informe['score']:.4f} ({round(informe['score'] * informe['n'])}/{informe['n']})")
    fuente = informe["ece_fuente"]
    valor_ece = "n/d" if informe["ece"] is None else f"{informe['ece']:.4f}"
    o.append(f"- ECE: {valor_ece} (fuente: {fuente})")
    o.append(f"- Latencia inferencia: p50 {informe['latencia_p50_ms']:.1f} ms · p95 {informe['latencia_p95_ms']:.1f} ms")
    o.append(f"- Carga en frío: {informe['carga_ms'] / 1000:.1f} s")
    o.append(f"- RSS pico: {informe['rss_max_kb'] / 1024:.0f} MiB ({informe['rss_max_kb']} KB)\n")

    o.append("## Tabla de confiabilidad\n")
    o.append("| bucket | n | conf. media | acierto | gap |")
    o.append("|---|---|---|---|---|")
    for f in informe["tabla_confiabilidad"]:
        hi = "1.0+" if f["hi"] is None else f"{f['hi']:.2f}"
        if f["n"]:
            o.append(f"| [{f['lo']:.2f}, {hi}) | {f['n']} | {f['conf_media']:.3f} | "
                     f"{f['acierto']:.3f} | {f['acierto'] - f['conf_media']:+.3f} |")
        else:
            o.append(f"| [{f['lo']:.2f}, {hi}) | 0 | — | — | — |")

    o.append("\n## Curva de compuerta\n")
    o.append("| umbral | cobertura | precisión | ahorro | n locales |")
    o.append("|---|---|---|---|---|")
    for f in informe["curva_compuerta"]:
        prec = "—" if f["precision"] is None else f"{f['precision']:.3f}"
        o.append(f"| {f['umbral']:.2f} | {f['cobertura']:.3f} | {prec} | {f['ahorro']:.3f} | {f['n_locales']} |")

    o.append(f"\n## Fallos ({len(informe['fallos'])})\n")
    if informe["fallos"]:
        o.append("| caso | esperado | obtenido | conf |")
        o.append("|---|---|---|---|")
        for e in informe["fallos"]:
            o.append(f"| {e['id']} | {e['esperado']} | {e['obtenido']} | {e['conf']:.3f} |")
    else:
        o.append("Ninguno.")
    return "\n".join(o) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evidencia de UN checkpoint de Laya (ECE, compuerta, RAM).")
    parser.add_argument("nombre", choices=sorted(ESPECIFICACIONES), help="checkpoint a medir (uno por proceso)")
    parser.add_argument("--salida", default=None, help="directorio de salida (default: salidas/evals)")
    args = parser.parse_args(argv)

    spec = ESPECIFICACIONES[args.nombre]
    informe = correr(args.nombre, spec)

    destino = Path(args.salida) if args.salida else SALIDA
    destino.mkdir(parents=True, exist_ok=True)
    md_path = destino / f"laya_evidencia_{args.nombre}.md"
    json_path = destino / f"laya_evidencia_{args.nombre}.json"
    md_path.write_text(escribir_md(informe), encoding="utf-8")
    json_path.write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"=== {args.nombre} · {informe['checkpoint']} ===")
    print(f"  acierto crudo: {informe['score']:.4f} ({round(informe['score'] * informe['n'])}/{informe['n']})")
    print(f"  ECE: {'n/d' if informe['ece'] is None else f'{informe['ece']:.4f}'} ({informe['ece_fuente']})")
    print(f"  p50/p95: {informe['latencia_p50_ms']:.1f}/{informe['latencia_p95_ms']:.1f} ms · "
          f"carga {informe['carga_ms'] / 1000:.1f} s · RSS {informe['rss_max_kb'] / 1024:.0f} MiB")
    print(f"  fallos: {len(informe['fallos'])}")
    print(f"  → {md_path}")
    print(f"  → {json_path}")


if __name__ == "__main__":
    main()
