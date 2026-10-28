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
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

# El test de 30 casos del fine-tune router_flow (bmo/train/kaggle-router).
# Fuera del repo a propósito: es la evidencia de entrenamiento, no un artefacto
# del harness. Su ausencia degrada el bench, nunca el resto del informe.
from utils.formato import pct
from utils.git import sha_o_motivo
from utils.rutas import DIR_RUNS, DIR_SALIDA, tasks_dir
from utils.trazas import leer_eventos

TEST_ROUTER = tasks_dir() / "router_flow_test.jsonl"  # BMO_TASKS_DIR lo mueve
# Baseline del bench del router. El v1 (2026-10-06: score 0.9667 / crudo 0.90 /
# ECE 0.0658) se midió con la compuerta CRUDA, antes de que el bench
# reprodujera la política de producción (conformal + modo + regla temporal): no
# es comparable con el bench v2, así que queda como ancla histórica y el v2
# escribe su propio archivo. La primera corrida v2 dirá "PRIMERA CORRIDA".
BASELINE = Path("salidas/evals/bench_router_v2.json")
BASELINE_HISTORICO = Path("salidas/evals/bench_router.json")

# Umbral del invariante (d): un ExecuteTools más largo que esto sin eventos de
# tools propios es el "ciego viejo" de la auditoría (una ronda inatribuible).
UMBRAL_CEGUERA_SEG = 120.0


# 1) BENCH DEL ROUTER

def _decision(eleccion, conf, veredicto):
    """La compuerta CRUDA del bench: 'directo' solo si el modelo eligió directo
    Y el veredicto es 'met'; cualquier otra cosa cae al lado SEGURO.

    NO es la compuerta de producción (ese docstring era falso, A10/H10): la
    política real suma el umbral conformal, el modo y la regla temporal. Se
    conserva porque es la serie histórica del bench (baseline v1)."""
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
    casos = [json.loads(linea) for linea in TEST_ROUTER.read_text(encoding="utf-8").splitlines() if linea.strip()]
    return casos, None


def _placeholder_bench(motivo):
    return {"estado": "no disponible", "motivo": motivo, "score": None,
            "score_crudo": None, "score_compuerta": None, "score_aplicada": None,
            "ece": None, "n": 0, "n_regla": 0, "modo": None, "filas": []}


def correr_bench(agente=None):
    """Corre el test por el camino de PRODUCCIÓN (A10/H10).

    Desde el 2026-10-15 el bench aplica la MISMA política que el chat: mismo
    truncamiento del estado (1000 chars, como LayaRouter.prep), misma regla
    temporal ANTES del modelo cuando el modo es enforce (exp/46), y el mismo
    decide + ruta_aplicada de utils.laya_routing (umbral conformal incluido).
    `agente` es un objeto con system_one(estado, preguntas, lang): en
    producción utils.laya.agente(); en tests, un fake fiteado.

    Tres números, porque miden cosas distintas:
      - `score`: la PROPUESTA de la política, independiente del modo. Es la
        métrica comparable entre corridas y la que ancla el baseline v2.
      - `score_aplicada`: lo que el grafo EJECUTA hoy con el modo configurado
        (en off/shadow todo cae a herramientas: no sirve como serie).
      - `score_crudo`: la ELECCIÓN cruda del modelo, sin compuerta (baseline v1:
        0.90) y `score_compuerta`: elección + veredicto con umbral fijo (v1:
        0.9667). Juntos reproducen la serie histórica del 2026-10-06.

    El voto 2-de-2 NO se mide acá: exige el checkpoint del voto y convertiría
    la corrida en dos modelos (se mide en banco/probes/calibrar_voto.py).
    Devuelve (resultado, motivo_error); `filas` es la evidencia del informe.
    """
    from nodes import PREGUNTA_ROUTER  # el contrato, IMPORTADO no copiado
    from utils.laya import _confianza, veredicto
    from utils.laya_routing import config_router, decide, regla_temporal, ruta_aplicada

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

    config = config_router()
    filas = []
    ok = aplicada_ok = crudo_ok = compuerta_ok = n_crudo = n_regla = 0
    confs, aciertos = [], []
    for caso in casos:
        estado = {"pregunta": caso["fields"]["pregunta"][:1000]}  # corte de producción
        esperado = caso["answers"]["necesita_herramientas"]

        if config.modo == "enforce" and regla_temporal(estado["pregunta"]):
            # producción corta acá SIN gastar a Laya: la regla dura manda
            n_regla += 1
            acierto = esperado == "herramientas"
            ok += acierto
            aplicada_ok += acierto
            filas.append({"id": caso["id"], "esperado": esperado, "crudo": None,
                          "compuerta": None, "conf": None,
                          "propuesta": "herramientas", "aplicada": "herramientas",
                          "causa": "regla:temporal", "ok": acierto})
            continue

        r = agente.system_one(estado, PREGUNTA_ROUTER, lang="es")
        resp = r["answers"]["necesita_herramientas"]
        eleccion = resp.get("choice", resp.get("answer"))
        conf = _confianza(resp)
        propuesta, causa, _p = decide(resp, config)
        aplicada = ruta_aplicada(propuesta, config)
        compuerta = _decision(eleccion, conf, veredicto) if conf is not None else "herramientas"

        n_crudo += 1
        # la serie histórica del v1 son DOS métricas distintas: la elección
        # pelada del modelo y esa elección pasada por la compuerta de umbral fijo
        crudo_ok += eleccion == esperado
        compuerta_ok += compuerta == esperado
        if conf is not None:
            # el ECE se mide sobre la decisión CRUDA (la confianza calibra la
            # elección del modelo, no la compuerta posterior)
            confs.append(float(conf))
            aciertos.append(int(eleccion == esperado))
        ok += propuesta == esperado
        aplicada_ok += aplicada == esperado
        filas.append({
            "id": caso["id"], "esperado": esperado, "crudo": eleccion,
            "compuerta": compuerta,
            "conf": round(float(conf), 4) if conf is not None else None,
            "propuesta": propuesta, "aplicada": aplicada, "causa": causa,
            "ok": propuesta == esperado,
        })

    n = len(casos)
    return {
        "estado": "ok",
        "n": n,
        "n_regla": n_regla,
        "modo": config.modo,
        "umbral": config.umbral,
        "q": config.q,
        "score": round(ok / n, 4) if n else 0.0,
        "score_aplicada": round(aplicada_ok / n, 4) if n else 0.0,
        "score_crudo": round(crudo_ok / n_crudo, 4) if n_crudo else 0.0,
        "score_compuerta": round(compuerta_ok / n_crudo, 4) if n_crudo else 0.0,
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
    if nuevo.get("score") is None:
        # bench degradado (sin Laya o sin test): nada que comparar — antes
        # reventaba con TypeError None - float si había baseline numérico
        comparacion["veredicto"] = "SIN BENCH"
        return comparacion
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
        "score_aplicada": bench.get("score_aplicada"),
        "score_crudo": bench["score_crudo"],
        "score_compuerta": bench.get("score_compuerta"),
        "ece": bench["ece"],
        "n": bench["n"],
        "modo": bench.get("modo"),
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "git_sha": sha if sha is not None else sha_o_motivo(),
    }
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return datos


# 2) LINTER DE TRAZAS

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
    # exp/50 y F6: nunca entraron acá — toda traza real del chat desde
    # entonces daba dos violaciones (c) falsas (descubierto en X95)
    ("PreFetch", "continue"), ("VerificarCitas", "default"),
    # marca de incidente del corte por no-progreso (nodes.py la emite con
    # evento_tool): no es una tool, pero viaja en la traza y el linter la
    # tiene que reconocer para no contarla como acción desconocida
    ("corte_no_progreso", "ok"),
    ("LayaRouter", "directo"), ("LayaRouter", "herramientas"),
    # X95: la compacción antes de cada llamada al modelo; sale por la ruta
    ("Contexto", "directo"), ("Contexto", "herramientas"),
    # X96: el presupuesto se acabó (arista de Contexto), la ronda se cuenta y
    # la última llamada va sin tools
    ("Contexto", "cierre"), ("Observar", "default"),
    ("Cierre", "answer"), ("Cierre", "tool"),
    ("AgentStep", "tool"), ("AgentStep", "answer"),
    ("DirectAnswer", "tool"), ("DirectAnswer", "answer"),
    ("ExecuteTools", "default"),
    ("ExitChat", "None"),
    # informe
    ("ScanFiles", "None"), ("AnalizeFile", "None"), ("WriteReport", "None"),
    # juez
    ("Draft", "None"), ("Judge", "retry"), ("Judge", "entregar"), ("Entregar", "None"),
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
    "debate", "juez_lote", "ver_imagen", "ver_pdf", "agentes_remotos", "a2a_tarea",
    # alias históricos vistos en trazas viejas (una acción 'bash' error, nunca
    # llegó a ser tool CORE): se reconocen para no contarlos como desconocidos
    "bash",
}


def _accion_valida(nodo, accion):
    if (nodo, accion) in ACCIONES_CANONICAS:
        return True
    # evento de tool individual
    return nodo in TOOLS_CONOCIDAS and accion in ("ok", "error")


def _violaciones_a(eventos):
    """(a) AgentStep tool debe tener un ExecuteTools antes del próximo AgentStep."""
    viol = []
    for i, e in enumerate(eventos):
        if e["nodo"] != "AgentStep" or e["accion"] != "tool":
            continue
        if not _hay_execute_tools_antes_del_proximo_agentstep(eventos, i):
            viol.append(("a", i, "AgentStep tool sin ExecuteTools antes del próximo AgentStep"))
    return viol


def _hay_execute_tools_antes_del_proximo_agentstep(eventos, inicio):
    for e in eventos[inicio + 1:]:
        if e["nodo"] == "AgentStep":
            return False
        if e["nodo"] == "ExecuteTools":
            return True
    return False


def _turno_del_chat(eventos, inicio):
    """(hay_router, llegó_a_respuesta, es_chat) desde un GetQuestion continue."""
    hay_router = respuesta = es_chat = False
    for e in eventos[inicio + 1:]:
        if e["nodo"] == "GetQuestion":
            break
        if e["nodo"] == "LayaRouter":
            hay_router = True
        elif e["nodo"] == "AgentStep":
            es_chat = True
            if e["accion"] == "answer":
                respuesta = True
                break
        elif e["nodo"] in ("DirectAnswer", "Cierre"):
            # X96: Cierre es la respuesta de un turno que agotó el presupuesto
            es_chat = respuesta = True
            break
    return hay_router, respuesta, es_chat


def _violaciones_b(eventos):
    """(b) el turno del chat arranca en el router (si la traza es del chat)."""
    hay_router_en_traza = any(e["nodo"] == "LayaRouter" for e in eventos)
    if not hay_router_en_traza:
        return []
    viol = []
    for i, e in enumerate(eventos):
        if e["nodo"] != "GetQuestion" or e["accion"] != "continue":
            continue
        hay_router, respuesta, es_chat = _turno_del_chat(eventos, i)
        if es_chat and respuesta and not hay_router:
            viol.append(("b", i, "turno del chat sin LayaRouter (arranca en AgentStep/DirectAnswer)"))
    return viol


def _violaciones_c(eventos):
    """(c) todo (nodo, accion) pertenece al conjunto canónico."""
    return [
        ("c", i, f"acción desconocida: {e['nodo']}/{e['accion']}")
        for i, e in enumerate(eventos)
        if not _accion_valida(e["nodo"], e["accion"])
    ]


def _hay_tools_propias_antes(eventos, inicio):
    """Tools propias entre el AgentStep que pidió y el ExecuteTools (i)."""
    for e in reversed(eventos[:inicio]):
        if e["nodo"] in ("AgentStep", "GetQuestion"):
            return False
        if e["nodo"] in TOOLS_CONOCIDAS:
            return True
    return False


def _violaciones_d(eventos, umbral_seg):
    """(d) ExecuteTools largo sin eventos de tools propias (ciego viejo)."""
    viol = []
    for i, e in enumerate(eventos):
        if e["nodo"] != "ExecuteTools" or e.get("seg", 0) <= umbral_seg:
            continue
        if not _hay_tools_propias_antes(eventos, i):
            viol.append(("d", i, f"ExecuteTools de {e['seg']:.1f}s sin eventos de tools propios"))
    return viol


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
    return (
        _violaciones_a(eventos)
        + _violaciones_b(eventos)
        + _violaciones_c(eventos)
        + _violaciones_d(eventos, umbral_seg)
    )

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
        eventos = leer_eventos(archivo)
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


# 3) COSTO POR SESIÓN

def costo_traza(eventos):
    """Seg por nodo y por tool, sin contar dos veces lo anidado.

    Los eventos de nodo son INCLUSIVOS (envuelven la corrida completa del nodo)
    y cada tool emite el suyo DENTRO de ExecuteTools: sumar ambos daba 20 s
    para 10 s de pared (medido, R16). Acá un evento contenido en la ventana de
    otro se cuenta como anidado y no suma a "total" (la pared estimada); se
    conservan "total_inclusivo" —la suma cruda, comparable con lo histórico— y
    "anidados", para que la diferencia quede visible en vez de silenciosa."""
    seg_nodo = defaultdict(float)
    tools = 0
    spans = []  # (inicio, fin, nodo, seg)
    for e in eventos:
        seg = float(e.get("seg", 0.0) or 0.0)
        nodo = e["nodo"]
        seg_nodo[nodo] += seg
        if nodo in TOOLS_CONOCIDAS:
            tools += 1
        inicio = float(e.get("ts", 0.0) or 0.0)
        spans.append((inicio, inicio + seg, nodo, seg))

    def _contiene(j, i):
        """¿El span j envuelve al i? Ventanas idénticas: el nodo de flujo es el
        contenedor y la tool la anidada (el orden real de la ejecución)."""
        ai, bi, nodoi, segi = spans[i]
        aj, bj, nodoj, segj = spans[j]
        if i == j or not (aj - 1e-3 <= ai and bi <= bj + 1e-3):
            return False
        if segj > segi:
            return True
        return segj == segi and nodoj not in TOOLS_CONOCIDAS and nodoi in TOOLS_CONOCIDAS

    total, anidados = 0.0, 0
    for i in range(len(spans)):
        if any(_contiene(j, i) for j in range(len(spans))):
            anidados += 1
            continue
        total += spans[i][3]

    inclusivo = sum(seg_nodo.values())
    dominante = max(seg_nodo.items(), key=lambda kv: kv[1])[0] if seg_nodo else "-"
    return {"total": round(total, 3), "total_inclusivo": round(inclusivo, 3),
            "anidados": anidados, "por_nodo": dict(seg_nodo),
            "tools": tools, "dominante": dominante}


def tokens_traza(eventos):
    """Tokens de UNA traza: suma los eventos llm (exp/89). Las trazas
    previas a exp/89 no tienen eventos: 0 y se declara, no se estima."""
    prompt = sum(int(e.get("prompt_tokens", 0)) for e in eventos
                 if e.get("nodo") == "llm")
    completion = sum(int(e.get("completion_tokens", 0)) for e in eventos
                     if e.get("nodo") == "llm")
    llamadas = sum(1 for e in eventos if e.get("nodo") == "llm")
    return {"llamadas": llamadas, "prompt": prompt, "completion": completion}


def costos_runs(directorio=DIR_RUNS):
    """Costo por sesión de todas las trazas, ordenadas de más cara a más barata.
    La fecha sale del nombre del archivo (YYYYMMDD_HHMMSS.jsonl)."""
    directorio = Path(directorio)
    sesiones = []
    for archivo in sorted(directorio.glob("*.jsonl")):
        eventos = leer_eventos(archivo)
        if not eventos:
            continue
        info = costo_traza(eventos)
        info["tokens"] = tokens_traza(eventos)
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


# INFORME

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

# 1) bench
    L.append("## 1) Bench del router")
    L.append("")
    if bench.get("estado") != "ok":
        L.append(f"⚠️  **No disponible:** {bench.get('motivo', 'sin datos')}")
        L.append("")
    else:
        L.append(f"- Casos: **{bench['n']}** · modo `{bench.get('modo') or '?'}` · "
                 f"regla temporal aplicada en {bench.get('n_regla', 0)}")
        L.append(f"- Acierto de la POLÍTICA (lo que decide, sin el modo): "
                 f"**{pct(bench['score'])}**")
        L.append(f"- Acierto APLICADO (lo que el grafo ejecuta con ese modo): "
                 f"{pct(bench.get('score_aplicada'))}")
        L.append(f"- Acierto crudo del modelo (sin compuerta, v1: 90.0%): "
                 f"{pct(bench['score_crudo'])}")
        L.append(f"- Acierto con compuerta de umbral fijo (v1: 96.7%): "
                 f"{pct(bench.get('score_compuerta'))}")
        L.append(f"- ECE (10 bins): {bench['ece']:.4f}")
        L.append("")
        v = comparacion["veredicto"]
        icono = {"OK": "✅", "REGRESIÓN": "🔴", "PRIMERA CORRIDA": "🆕"}.get(v, "•")
        L.append(f"**Baseline:** {icono} {v}")
        if comparacion["anterior"]:
            a = comparacion["anterior"]
            d = comparacion["delta"]
            L.append("")
            L.append(f"- Anterior: score {pct(a.get('score'))} · ECE "
                     f"{a.get('ece')} · {a.get('fecha', '?')} · sha `{(a.get('git_sha') or '?')[:10]}`")
            ds = d.get("score")
            de = d.get("ece")
            L.append(f"- Delta score: {ds:+.4f}" if ds is not None else "- Delta score: —")
            L.append(f"- Delta ECE: {de:+.4f}" if de is not None else "- Delta ECE: —")
        L.append("")
        fallos = [f for f in bench["filas"] if not f["ok"]]
        if fallos:
            L.append("### Casos fallados (política)")
            L.append("")
            L.append("| id | esperado | crudo | compuerta | conf | propuesta | aplicada |")
            L.append("|----|----------|-------|-----------|------|-----------|----------|")
            for f in fallos:
                conf = f"{f['conf']:.2f}" if f.get("conf") is not None else "—"
                L.append(f"| {f['id']} | {f['esperado']} | {f.get('crudo')} | "
                         f"{f.get('compuerta')} | {conf} | {f.get('propuesta')} | "
                         f"{f.get('aplicada')} |")
            L.append("")

# 2) linter
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

# 3) costo
    L.append("## 3) Costo por sesión")
    L.append("")
    L.append(f"Sesiones con eventos: **{len(costos)}**")
    L.append("")
    if costos:
        L.append("### Las 5 sesiones más caras")
        L.append("")
        L.append("| # | fecha | total (s) | tokens (p+c) | tools | nodo dominante | archivo |")
        L.append("|---|-------|-----------|--------------|-------|----------------|---------|")
        for i, s in enumerate(costos[:5], 1):
            dom = s["por_nodo"].get(s["dominante"], 0)
            tok = s.get("tokens", {})
            tokens = f"{tok.get('prompt', 0):,}+{tok.get('completion', 0):,}".replace(",", ".")
            L.append(f"| {i} | {s['fecha']} | {s['total']:.1f} | {tokens} | {s['tools']} | "
                     f"{s['dominante']} ({dom:.1f}s) | {s['archivo']} |")
        L.append("")

    return "\n".join(L)


def generar(dir_runs=DIR_RUNS, dir_salida=DIR_SALIDA, agente=None, sha=None,
            actualizar_baseline=True):
    """Corre las tres secciones y escribe UN informe markdown. Devuelve su Path.
    `agente` (opcional) permite inyectar un fake en tests sin tocar utils.laya.
    `actualizar_baseline=False` (tool del chat): compara pero NO pisa el
    baseline — el ancla de medición no se sobrescribe desde una conversación."""
    fecha = date.today().isoformat()
    sha = sha if sha is not None else sha_o_motivo()

    bench, _ = correr_bench(agente=agente)
    comparacion = comparar_baseline(bench)
    if actualizar_baseline and bench.get("score") is not None:
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
