"""Evals: el harness juzgándose a sí mismo con la evidencia de disco.

Mesa 1 del menú de desarrollo (12-factor #8: "own your evals"). Pieza 100%
código y determinista: sin LLM ni modelo. Dos secciones, un solo informe
markdown (el bench del router se fue con el router, fase 3b, X106):

1. LINTER DE TRAZAS — invariantes estructurales del wiring sobre los
   .runs/*.jsonl reales. No juzga calidad: verifica que el grafo se haya
   recorrido como el grafo manda. Tres invariantes (a, c, d), violaciones por
   archivo y ranking de los peores.

2. COSTO POR SESIÓN — suma de seg por nodo y cantidad de eventos de tools por
   traza; tabla de las 5 sesiones más caras con su nodo dominante.

Uso:
    python3 main.py evals [--dir .runs] [--salida salidas/evals]
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from utils.git import sha_o_motivo
from utils.rutas import DIR_RUNS, DIR_SALIDA
from utils.tracing import es_bookkeeping
from utils.trazas import leer_eventos

# Umbral del invariante (d): un ExecuteTools más largo que esto sin eventos de
# tools propios es el "ciego viejo" de la auditoría (una ronda inatribuible).
UMBRAL_CEGUERA_SEG = 120.0


# 1) LINTER DE TRAZAS

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
    # X106: la entrada del skill (antes vivía en el router)
    ("Skills", "continue"),
    # X95: la compacción antes de cada llamada al modelo
    ("Contexto", "herramientas"),
    # X96: el presupuesto se acabó (arista de Contexto), la ronda se cuenta y
    # la última llamada va sin tools
    ("Contexto", "cierre"), ("Observar", "default"),
    ("Cierre", "answer"), ("Cierre", "tool"),
    ("AgentStep", "tool"), ("AgentStep", "answer"),
    ("ExecuteTools", "default"),
    ("ExitChat", "None"),
    # HISTÓRICAS: el router y la ruta directa (borrados en X106) siguen en las
    # trazas viejas de .runs; el linter juzga el cableado de cada traza, no si
    # el nodo sobrevivió (eso es del replay, nivel A′)
    ("LayaRouter", "directo"), ("LayaRouter", "herramientas"),
    ("Contexto", "directo"), ("DirectAnswer", "tool"), ("DirectAnswer", "answer"),
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
    if (nodo, accion) in ACCIONES_CANONICAS or es_bookkeeping(nodo, accion):
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

    Invariantes (la (b), "cada turno arranca en el router", se fue con el
    router en X106; la letra no se reusa para no confundir informes viejos):
      (a) cada AgentStep tool debe tener un ExecuteTools antes del próximo
          AgentStep (si se pidió tools, se ejecutaron).
      (c) todo (nodo, accion) pertenece al conjunto canónico.
      (d) ningún ExecuteTools con seg > umbral sin eventos de tools propios
          entre el AgentStep que lo pidió y el ExecuteTools (ciego viejo).
    """
    return (
        _violaciones_a(eventos)
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


# 2) COSTO POR SESIÓN

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

def informe_markdown(linter, costos, sha, fecha):
    L = []
    L.append(f"# Evals del harness — {fecha}")
    L.append("")
    L.append(f"git sha: `{sha}`")
    L.append("")
    L.append("Informe del harness juzgándose a sí mismo con la evidencia de "
             "disco (mesa 1, replay-evals). Dos secciones: linter de trazas y "
             "costo por sesión.")
    L.append("")

# 1) linter
    L.append("## 1) Linter de trazas")
    L.append("")
    L.append(f"- Trazas analizadas: **{linter['total']}**")
    nombres = {"a": "AgentStep tool sin ExecuteTools",
               "c": "acción desconocida",
               "d": "ExecuteTools largo sin tools"}
    L.append("- Violaciones por invariante:")
    for k in ("a", "c", "d"):
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

# 2) costo
    L.append("## 2) Costo por sesión")
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


def generar(dir_runs=DIR_RUNS, dir_salida=DIR_SALIDA, sha=None):
    """Corre las dos secciones y escribe UN informe markdown. Devuelve su Path."""
    fecha = date.today().isoformat()
    sha = sha if sha is not None else sha_o_motivo()
    linter = linter_runs(dir_runs)
    costos = costos_runs(dir_runs)
    md = informe_markdown(linter, costos, sha, fecha)
    dir_salida = Path(dir_salida)
    dir_salida.mkdir(parents=True, exist_ok=True)
    destino = dir_salida / f"evals_{fecha}.md"
    destino.write_text(md, encoding="utf-8")
    return destino


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="evals", description="Evals del harness: linter de trazas y costo por sesión")
    parser.add_argument("--dir", default=str(DIR_RUNS), help="carpeta de trazas .jsonl (default: %(default)s)")
    parser.add_argument("--salida", default=str(DIR_SALIDA), help="carpeta de salida (default: %(default)s)")
    args = parser.parse_args(argv)

    if not Path(args.dir).is_dir():
        raise SystemExit(f"ERROR: no existe la carpeta de trazas: {args.dir}")

    destino = generar(dir_runs=args.dir, dir_salida=args.salida)
    print(f"✓ informe de evals → {destino}")


if __name__ == "__main__":
    main()
