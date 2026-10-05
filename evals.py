"""Evals: el harness juzgándose a sí mismo con la evidencia de disco.

Mesa 1 del menú de desarrollo (12-factor #8: "own your evals"). Pieza 100%
código y determinista donde se puede — sin LLM en el linter ni en los costos
—, y con el camino EXACTO de producción donde no (el bench corre el mismo
LayaRouter: contrato importado de nodes, compuerta con los mismos umbrales).
Tres secciones, un solo informe markdown:

1. BENCH DEL ROUTER — los 30 casos del test de bmo por el camino de
   producción (utils.laya.agente + PREGUNTA_ROUTER importado de nodes, no
   copiado: lección de la sonda). Reporta acierto con compuerta, acierto
   crudo y ECE (10 bins). Guarda un baseline (salidas/evals/bench_router.json)
   con score, ece, fecha y el git sha del código, y lo compara con el anterior:
   delta por métrica + veredicto OK/REGRESIÓN/PRIMERA CORRIDA. Si laya no
   está, degrada con mensaje y el resto del informe se escribe igual.

2. LINTER DE TRAZAS — invariantes estructurales del wiring sobre los
   .runs/*.jsonl reales. No juzga calidad: verifica que el grafo se haya
   recorrido como el grafo manda. Cuatro invariantes (a-d), violaciones por
   archivo y ranking de los peores.

3. COSTO POR SESIÓN — suma de seg por nodo y cantidad de eventos de tools por
   traza; tabla de las 5 sesiones más caras con su nodo dominante.

Uso:
    python3 main.py evals [--dir .runs] [--salida salidas/evals]
"""
import argparse
import json
import subprocess
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

# El test de 30 casos del fine-tune router_flow (bmo/train/kaggle-router).
# Fuera del repo a propósito: es la evidencia de entrenamiento, no un artefacto
# del harness. Su ausencia degrada el bench, nunca el resto del informe.
TEST_ROUTER = Path("/home/roquedb/Documentos/00_IA/bmo/train/tasks/router_flow_test.jsonl")
BASELINE = Path("salidas/evals/bench_router.json")
DIR_RUNS = Path(".runs")
DIR_SALIDA = Path("salidas/evals")

# Umbral del invariante (d): un ExecuteTools más largo que esto sin eventos de
# tools propios es el "ciego viejo" de la auditoría (una ronda inatribuible).
UMBRAL_CEGUERA_SEG = 120.0


def _git_sha():
    """sha corto del código actual (subprocess, como pide el menú). Vacío si
    git no está o el repo no está inicializado: el informe no depende de él."""
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                           text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception as e:  # noqa: BLE001 (git es best-effort, no dependencia)
        return f"(git no disponible: {type(e).__name__})"


# ---------------------------------------------------------------------------
# 1) BENCH DEL ROUTER
# ---------------------------------------------------------------------------

def _decision(eleccion, conf, veredicto):
    """La compuerta EXACTA de producción (nodes.LayaRouter.post): 'directo'
    solo si eligió directo Y el veredicto es 'met'; cualquier otra cosa
    (uncertain, not met, herramientas) cae al lado SEGURO = herramientas."""
    return "directo" if (eleccion == "directo" and veredicto(conf) == "met") else "herramientas"


def ece(confianzas, aciertos, bins=10):
    """Expected Calibration Error: promedio ponderado de |accuracy - confidence|
    por bin. `confianzas[i]` es la conf del caso i, `aciertos[i]` un 0/1 de si
    acertó (crudo). Un modelo perfectamente calibrado da 0."""
    if not confianzas:
        return 0.0
    n = len(confianzas)
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        # el último bin incluye el 1.0 (hi = 1.0000 no es estricto arriba)
        idx = [i for i, c in enumerate(confianzas)
               if (lo < c <= hi) or (b == 0 and c <= hi)]
        if not idx:
            continue
        acc = sum(aciertos[i] for i in idx) / len(idx)
        conf = sum(confianzas[i] for i in idx) / len(idx)
        total += (len(idx) / n) * abs(acc - conf)
    return total


def _casos_router():
    if not TEST_ROUTER.is_file():
        return None, f"no existe el test: {TEST_ROUTER}"
    casos = [json.loads(l) for l in TEST_ROUTER.read_text(encoding="utf-8").splitlines() if l.strip()]
    return casos, None


def _placeholder_bench(motivo):
    return {"estado": "no disponible", "motivo": motivo, "score": None,
            "score_crudo": None, "ece": None, "n": 0, "filas": []}


def correr_bench(agente=None):
    """Corre el test por el camino de producción. `agente` es un objeto con
    system_one(estado, preguntas, lang) — en producción utils.laya.agente()
    (carga el checkpoint de LAYA_MODEL); en tests, un fake fiteado.

    Devuelve (resultado, motivo_error). resultado incluye score (con compuerta),
    score_crudo, ece y el detalle por caso; `filas` es la evidencia del informe.
    """
    from nodes import PREGUNTA_ROUTER  # el contrato, IMPORTADO no copiado
    from utils.laya import _confianza, veredicto

    casos, err = _casos_router()
    if err:
        return _placeholder_bench(err), err

    if agente is None:
        try:
            from utils.laya import agente as agente_real

            agente = agente_real()
        except Exception as e:  # noqa: BLE001 (sin laya: degradar, no romper)
            motivo = f"laya no disponible: {type(e).__name__}: {e}"
            return _placeholder_bench(motivo), motivo

    filas, ok, crudo_ok, confs, aciertos = [], 0, 0, [], []
    for caso in casos:
        estado = {"pregunta": caso["fields"]["pregunta"]}
        r = agente.system_one(estado, PREGUNTA_ROUTER, lang="es")
        resp = r["answers"]["necesita_herramientas"]
        eleccion = resp.get("choice", resp.get("answer"))
        conf = _confianza(resp)
        esperado = caso["answers"]["necesita_herramientas"]
        decision = _decision(eleccion, conf, veredicto)
        ok += decision == esperado
        acierto_crudo = int(eleccion == esperado)
        crudo_ok += acierto_crudo
        # el ECE se mide sobre la decisión CRUDA (la confianza calibra la
        # elección del modelo, no la compuerta posterior)
        confs.append(float(conf))
        aciertos.append(acierto_crudo)
        filas.append({
            "id": caso["id"], "esperado": esperado, "crudo": eleccion,
            "conf": round(float(conf), 4), "decision": decision,
            "ok": decision == esperado,
        })

    n = len(casos)
    return {
        "estado": "ok",
        "n": n,
        "score": round(ok / n, 4) if n else 0.0,
        "score_crudo": round(crudo_ok / n, 4) if n else 0.0,
        "ece": round(ece(confs, aciertos), 4),
        "filas": filas,
    }, None


def comparar_baseline(nuevo, ruta=BASELINE):
    """Compara contra el baseline guardado si existe. Delta por métrica y
    veredicto:
      - PRIMERA CORRIDA: no había baseline.
      - REGRESIÓN: el score bajó y/o el ECE subió (con tolerancia 1e-9).
      - OK: score igual/mejor y ECE igual/mejor.
    Un baseline sin score (corrida degradada) no cuenta como referencia."""
    comparacion = {"veredicto": "PRIMERA CORRIDA", "anterior": None, "delta": {}}
    if not ruta.is_file():
        return comparacion
    try:
        anterior = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return comparacion
    if anterior.get("score") is None:
        return comparacion

    comparacion["anterior"] = anterior
    delta_score = nuevo["score"] - anterior["score"]
    ece_ant = anterior.get("ece")
    delta_ece = (nuevo["ece"] - ece_ant) if ece_ant is not None else None
    comparacion["delta"] = {"score": round(delta_score, 4),
                            "ece": round(delta_ece, 4) if delta_ece is not None else None}
    regresion = delta_score < -1e-9 or (delta_ece is not None and delta_ece > 1e-9)
    comparacion["veredicto"] = "REGRESIÓN" if regresion else "OK"
    return comparacion


def guardar_baseline(bench, ruta=BASELINE, sha=None):
    """Guarda el baseline nuevo (score, ece, fecha, git sha). Solo si el bench
    corrió: una corrida degradada no debe pisar un baseline válido."""
    if bench.get("score") is None:
        return None
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = {
        "score": bench["score"],
        "score_crudo": bench["score_crudo"],
        "ece": bench["ece"],
        "n": bench["n"],
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "git_sha": sha if sha is not None else _git_sha(),
    }
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return datos


# ---------------------------------------------------------------------------
# 2) LINTER DE TRAZAS
# ---------------------------------------------------------------------------

# Conjunto canónico (nodo, accion) del sistema — MANTENIMIENTO: crece cuando
# se agrega un nodo con una acción nueva. Armado de los flows reales (flow.py,
# informe.py, juez.py, juez_lote.py, auditoria.py, research.py, supervisor.py,
# debate.py, effective_n.py, rag.py) + los eventos de tools (nombre de tool →
# ok/error) que emite utils.tracing.evento_tool. El linter NO importa los
# flows: importarlos dispara discover() de módulos y side effects; esta lista
# explícita es la fuente, con este comentario como contrato de mantenimiento.
ACCIONES_CANONICAS = {
    # chat (nodes.py)
    ("GetQuestion", "continue"), ("GetQuestion", "exit"),
    ("LayaRouter", "directo"), ("LayaRouter", "herramientas"),
    ("AgentStep", "tool"), ("AgentStep", "answer"),
    ("DirectAnswer", "tool"), ("DirectAnswer", "answer"),
    ("ExecuteTools", "default"),
    ("ExitChat", "None"),
    # informe
    ("ScanFiles", "None"), ("AnalizeFile", "None"), ("WriteReport", "None"),
    # juez
    ("Draft", "None"), ("Judge", "entregar"), ("Entregar", "None"),
    # juez_lote
    ("CorrerJuez", "None"),
    # auditoria
    ("CarpetaScan", "None"), ("Seccion", "None"), ("ReduceGlobal", "None"),
    # research
    ("Planner", "None"), ("Researcher", "None"),
    ("Synthesizer", "research"), ("Synthesizer", "finalize"),
    ("Fin", "None"),
    # supervisor
    ("ElegirSiguiente", "ejecutar"), ("ElegirSiguiente", "sintetizar"),
    ("EjecutarPaso", "elegir"), ("EjecutarPaso", "sintetizar"),
    ("Sintetizar", "None"),
    # debate
    ("Proponente", "continue"), ("Proponente", "end"),
    ("Critico", "continue"), ("Critico", "end"),
    ("FinAgente", "None"), ("JuezDebate", "None"),
    # effective_n
    ("HashFile", "None"),
    # rag
    ("ChunkDocs", "None"), ("EmbedChunks", "None"), ("SaveIndex", "None"),
}

# Nodos que NO son flujos, son tools: sus eventos los emite tracing.evento_tool
# con accion ok/error. Vienen de modules/*.py (IMPLEMENTACIONES) + CORE_TOOLS.
# MANTENIMIENTO: agregar el nombre de la tool acá al crear una nueva.
TOOLS_CONOCIDAS = {
    # CORE (utils/fs_tools.py)
    "list_files", "read_file", "search_files", "write_file", "edit_file",
    "run_command",
    # módulos
    "run_informe", "run_auditoria", "rag_search", "rag_index", "run_effective_n",
    "answer_verified", "mcp_tools", "mcp_call", "search_web", "deep_research",
    "run_supervisor", "sql", "db_schema", "memory_search", "memory_save",
    # tools que los flujos exponen como herramientas del chat (modules/*)
    "debate", "juez_lote",
    # alias históricos vistos en trazas viejas (una acción 'bash' error, nunca
    # llegó a ser tool CORE): se reconocen para no contarlos como desconocidos
    "bash",
}


def _accion_valida(nodo, accion):
    if (nodo, accion) in ACCIONES_CANONICAS:
        return True
    # evento de tool individual
    if nodo in TOOLS_CONOCIDAS and accion in ("ok", "error"):
        return True
    return False


def linter_traza(eventos, umbral_seg=UMBRAL_CEGUERA_SEG):
    """Recorre los eventos de UNA traza y devuelve la lista de violaciones.

    Invariantes:
      (a) cada AgentStep tool debe tener un ExecuteTools antes del próximo
          AgentStep (si se pidió tools, se ejecutaron).
      (b) cada turno arranca en el router: entre GetQuestion continue y la
          respuesta (AgentStep answer / DirectAnswer) debe aparecer un
          LayaRouter... salvo flujos de un solo-shot que no son el chat
          (informe/auditoria/juez), donde GetQuestion no existe. El invariante
          SOLO aplica si el turno llegó a un AgentStep/DirectAnswer por el chat.
      (c) todo (nodo, accion) pertenece al conjunto canónico.
      (d) ningún ExecuteTools con seg > umbral sin eventos de tools propios
          entre el AgentStep que lo pidió y el ExecuteTools (ciego viejo).
    """
    viol = []

    # (a) AgentStep tool → ExecuteTools antes del próximo AgentStep
    for i, e in enumerate(eventos):
        if e["nodo"] == "AgentStep" and e["accion"] == "tool":
            j, encontrado = i + 1, False
            while j < len(eventos) and eventos[j]["nodo"] != "AgentStep":
                if eventos[j]["nodo"] == "ExecuteTools":
                    encontrado = True
                    break
                j += 1
            if not encontrado:
                viol.append(("a", i, "AgentStep tool sin ExecuteTools antes del próximo AgentStep"))

    # (b) turno del chat arranca en el router
    # solo aplicamos si en la traza hay LayaRouter en algún lado (chat con
    # router activo); un chat con USE_LAYA_ROUTER=0 no tiene router y el
    # invariante no puede exigirlo — se detecta y se reporta aparte.
    hay_router_en_traza = any(e["nodo"] == "LayaRouter" for e in eventos)
    for i, e in enumerate(eventos):
        if e["nodo"] == "GetQuestion" and e["accion"] == "continue":
            j, hay_router, respuesta, es_chat = i + 1, False, False, False
            while j < len(eventos):
                n = eventos[j]
                if n["nodo"] == "GetQuestion":
                    break
                if n["nodo"] == "LayaRouter":
                    hay_router = True
                if n["nodo"] == "AgentStep":
                    es_chat = True
                    if n["accion"] == "answer":
                        respuesta = True
                        break
                if n["nodo"] == "DirectAnswer":
                    es_chat = True
                    respuesta = True
                    break
                j += 1
            # solo exigimos router si esta traza es del chat con router activo
            if es_chat and respuesta and not hay_router and hay_router_en_traza:
                viol.append(("b", i, "turno del chat sin LayaRouter (arranca en AgentStep/DirectAnswer)"))

    # (c) pares (nodo, accion) canónicos
    for i, e in enumerate(eventos):
        if not _accion_valida(e["nodo"], e["accion"]):
            viol.append(("c", i, f"acción desconocida: {e['nodo']}/{e['accion']}"))

    # (d) ExecuteTools largo sin eventos de tools propios
    for i, e in enumerate(eventos):
        if e["nodo"] == "ExecuteTools" and e.get("seg", 0) > umbral_seg:
            # buscar hacia atrás el AgentStep que lo pidió y contar tools
            # propias entre ese AgentStep y este ExecuteTools
            j, tools = i - 1, []
            while j >= 0 and eventos[j]["nodo"] != "GetQuestion":
                n = eventos[j]
                if n["nodo"] == "AgentStep":
                    break
                if n["nodo"] in TOOLS_CONOCIDAS:
                    tools.append(n)
                j -= 1
            if not tools:
                viol.append(("d", i, f"ExecuteTools de {e['seg']:.1f}s sin eventos de tools propios"))

    return viol


def _leer_eventos(archivo):
    """Eventos de un .jsonl; [] si el archivo es ilegible o una línea es JSON
    inválido. Trazas y costos comparten este parseo (una traza corrupta es un
    artefacto a saltear, nunca una excepción que tumbe el informe)."""
    eventos = []
    try:
        for l in Path(archivo).read_text(encoding="utf-8").splitlines():
            l = l.strip()
            if l:
                eventos.append(json.loads(l))
    except (json.JSONDecodeError, OSError):
        return []
    return eventos


def linter_runs(directorio=DIR_RUNS):
    """Corre el linter sobre todos los .jsonl de `directorio`. Devuelve un
    resumen con total de trazas, violaciones por invariante y archivos peores.
    Una traza con JSONL corrupto se reporta como violación de lectura (no
    rompe el linter entero: es un artefacto, no una dependencia)."""
    directorio = Path(directorio)
    por_invariante = Counter()
    por_archivo = {}
    problemas_lectura = []
    total = 0
    archivos = sorted(directorio.glob("*.jsonl"))
    for archivo in archivos:
        total += 1
        eventos = _leer_eventos(archivo)
        if not eventos and archivo.stat().st_size > 0:
            # tenía contenido y no se pudo parsear: traza corrupta (no una
            # traza legítimamente vacía)
            problemas_lectura.append((archivo.name, "JSONL inválido"))
            continue
        viol = linter_traza(eventos)
        if viol:
            por_archivo[archivo.name] = viol
            for inv, _, _ in viol:
                por_invariante[inv] += 1
    peores = sorted(por_archivo.items(), key=lambda kv: len(kv[1]), reverse=True)
    return {
        "total": total,
        "por_invariante": dict(por_invariante),
        "por_archivo": por_archivo,
        "peores": peores[:5],
        "problemas_lectura": problemas_lectura,
    }


# ---------------------------------------------------------------------------
# 3) COSTO POR SESIÓN
# ---------------------------------------------------------------------------

def costo_traza(eventos):
    """Seg por nodo, cantidad de eventos de tool y nodo dominante de una traza."""
    seg_nodo = defaultdict(float)
    tools = 0
    for e in eventos:
        seg_nodo[e["nodo"]] += float(e.get("seg", 0.0) or 0.0)
        if e["nodo"] in TOOLS_CONOCIDAS:
            tools += 1
    total = sum(seg_nodo.values())
    dominante = max(seg_nodo.items(), key=lambda kv: kv[1])[0] if seg_nodo else "-"
    return {"total": round(total, 3), "por_nodo": dict(seg_nodo),
            "tools": tools, "dominante": dominante}


def costos_runs(directorio=DIR_RUNS):
    """Costo por sesión de todas las trazas, ordenadas de más cara a más barata.
    La fecha sale del nombre del archivo (YYYYMMDD_HHMMSS.jsonl)."""
    directorio = Path(directorio)
    sesiones = []
    for archivo in sorted(directorio.glob("*.jsonl")):
        eventos = _leer_eventos(archivo)
        if not eventos:
            continue
        info = costo_traza(eventos)
        info["archivo"] = archivo.name
        info["fecha"] = _fecha_de(archivo.stem)
        sesiones.append(info)
    sesiones.sort(key=lambda s: s["total"], reverse=True)
    return sesiones


def _fecha_de(stem):
    """'20261005_113102' → '2026-10-05 11:31:02' (o el stem tal cual)."""
    try:
        dt = datetime.strptime(stem, "%Y%m%d_%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return stem


# ---------------------------------------------------------------------------
# INFORME
# ---------------------------------------------------------------------------

def _fmt_pct(x):
    return f"{x * 100:.1f}%" if x is not None else "—"


def informe_markdown(bench, comparacion, linter, costos, sha, fecha):
    L = []
    L.append(f"# Evals del harness — {fecha}")
    L.append("")
    L.append(f"git sha: `{sha}`")
    L.append("")
    L.append("Informe del harness juzgándose a sí mismo con la evidencia de "
             "disco (mesa 1, replay-evals). Tres secciones: bench del router, "
             "linter de trazas, costo por sesión.")
    L.append("")

    # --- 1) bench
    L.append("## 1) Bench del router")
    L.append("")
    if bench.get("estado") != "ok":
        L.append(f"⚠️  **No disponible:** {bench.get('motivo', 'sin datos')}")
        L.append("")
    else:
        L.append(f"- Casos: **{bench['n']}**")
        L.append(f"- Acierto con compuerta (producción): **{_fmt_pct(bench['score'])}**")
        L.append(f"- Acierto crudo (sin compuerta): {_fmt_pct(bench['score_crudo'])}")
        L.append(f"- ECE (10 bins): {bench['ece']:.4f}")
        L.append("")
        v = comparacion["veredicto"]
        icono = {"OK": "✅", "REGRESIÓN": "🔴", "PRIMERA CORRIDA": "🆕"}.get(v, "•")
        L.append(f"**Baseline:** {icono} {v}")
        if comparacion["anterior"]:
            a = comparacion["anterior"]
            d = comparacion["delta"]
            L.append("")
            L.append(f"- Anterior: score {_fmt_pct(a.get('score'))} · ECE "
                     f"{a.get('ece')} · {a.get('fecha', '?')} · sha `{(a.get('git_sha') or '?')[:10]}`")
            ds = d.get("score")
            de = d.get("ece")
            L.append(f"- Delta score: {ds:+.4f}" if ds is not None else "- Delta score: —")
            L.append(f"- Delta ECE: {de:+.4f}" if de is not None else "- Delta ECE: —")
        L.append("")
        fallos = [f for f in bench["filas"] if not f["ok"]]
        if fallos:
            L.append("### Casos fallados (con compuerta)")
            L.append("")
            L.append("| id | esperado | crudo | conf | decisión |")
            L.append("|----|----------|-------|------|----------|")
            for f in fallos:
                L.append(f"| {f['id']} | {f['esperado']} | {f['crudo']} | "
                         f"{f['conf']:.2f} | {f['decision']} |")
            L.append("")

    # --- 2) linter
    L.append("## 2) Linter de trazas")
    L.append("")
    L.append(f"- Trazas analizadas: **{linter['total']}**")
    nombres = {"a": "AgentStep tool sin ExecuteTools",
               "b": "turno sin LayaRouter",
               "c": "acción desconocida",
               "d": "ExecuteTools largo sin tools"}
    L.append("- Violaciones por invariante:")
    for k in ("a", "b", "c", "d"):
        L.append(f"  - ({k}) {nombres[k]}: **{linter['por_invariante'].get(k, 0)}**")
    if linter["problemas_lectura"]:
        L.append(f"- Trazas ilegibles: {len(linter['problemas_lectura'])}")
    L.append("")
    if linter["peores"]:
        L.append("### Archivos con más violaciones")
        L.append("")
        L.append("| archivo | violaciones | invariantes |")
        L.append("|---------|-------------|-------------|")
        for nombre, viol in linter["peores"]:
            invs = Counter(v[0] for v in viol)
            detalle = ", ".join(f"({k})×{n}" for k, n in sorted(invs.items()))
            L.append(f"| {nombre} | {len(viol)} | {detalle} |")
        L.append("")

    # --- 3) costo
    L.append("## 3) Costo por sesión")
    L.append("")
    L.append(f"Sesiones con eventos: **{len(costos)}**")
    L.append("")
    if costos:
        L.append("### Las 5 sesiones más caras")
        L.append("")
        L.append("| # | fecha | total (s) | tools | nodo dominante | archivo |")
        L.append("|---|-------|-----------|-------|----------------|---------|")
        for i, s in enumerate(costos[:5], 1):
            dom = s["por_nodo"].get(s["dominante"], 0)
            L.append(f"| {i} | {s['fecha']} | {s['total']:.1f} | {s['tools']} | "
                     f"{s['dominante']} ({dom:.1f}s) | {s['archivo']} |")
        L.append("")

    return "\n".join(L)


def generar(dir_runs=DIR_RUNS, dir_salida=DIR_SALIDA, agente=None, sha=None):
    """Corre las tres secciones y escribe UN informe markdown. Devuelve su Path.
    `agente` (opcional) permite inyectar un fake en tests sin tocar utils.laya."""
    fecha = date.today().isoformat()
    sha = sha if sha is not None else _git_sha()

    bench, _ = correr_bench(agente=agente)
    comparacion = comparar_baseline(bench)
    if bench.get("score") is not None:
        guardar_baseline(bench, sha=sha)

    linter = linter_runs(dir_runs)
    costos = costos_runs(dir_runs)

    md = informe_markdown(bench, comparacion, linter, costos, sha, fecha)
    dir_salida = Path(dir_salida)
    dir_salida.mkdir(parents=True, exist_ok=True)
    destino = dir_salida / f"evals_{fecha}.md"
    destino.write_text(md, encoding="utf-8")
    return destino


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="evals", description="Evals del harness: bench del router, linter de trazas, costo por sesión")
    parser.add_argument("--dir", default=str(DIR_RUNS), help="carpeta de trazas .jsonl (default: %(default)s)")
    parser.add_argument("--salida", default=str(DIR_SALIDA), help="carpeta de salida (default: %(default)s)")
    args = parser.parse_args(argv)

    if not Path(args.dir).is_dir():
        raise SystemExit(f"ERROR: no existe la carpeta de trazas: {args.dir}")

    destino = generar(dir_runs=args.dir, dir_salida=args.salida)
    print(f"✓ informe de evals → {destino}")


if __name__ == "__main__":
    main()