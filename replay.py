"""Replay de trazas .runs contra el CÓDIGO ACTUAL (Mesa 1, 12-factor #8).

La pregunta de la mesa, pendiente desde el origen: cuando el código cambia,
¿el harness de HOY todavía ejecuta las caminatas que ejecutó en producción?
Los tests de unidades no la responden (revisan piezas, no conducta); este
replay la responde con la evidencia de disco: cada traza `.runs/*.jsonl`
guarda la caminata real (nodo/acción/duración por evento), y acá se valida
contra los grafos VIVOS del código actual — no contra una lista congelada.

--------------------------------------------------------------------------
LÍMITE HONESTO (lo que este replay NO puede ver)
--------------------------------------------------------------------------
La traza guarda la CAMINATA, no el contenido: ni preguntas, ni argumentos,
ni resultados (documentado en minar_errores.py). Este replay detecta
regresión de comportamiento ESTRUCTURAL: una acción que ya no es emisible,
una arista del chat que ya no existe, una tool del action space que se
renombró o se borró, una compuerta del router que hoy decidiría distinto
sobre el mismo tráfico. La regresión SEMÁNTICA (misma caminata, peor
respuesta) es invisible acá — para eso están bench_juez y el banco, que sí
tienen contenido. Es instrumento de SEÑAL, no gate (el matiz del consejo
en la primera corrida de evals).

Niveles, de más general a más específico:

  A) EMISIBILIDAD — cada (nodo, accion) de cada traza histórica tiene que
     ser emisible por el código de HOY: la clase existe en algún grafo
     vivo (con recursión dentro de los Flow/BatchFlow anidados) y la
     acción sigue cableada (o es terminal/"default"). Es la generalización
     del guard de calles muertas (exp/39) a caminatas REALES en vez de
     declaradas: detecta renombres y aristas removidas.
  B) ADYACENCIA DEL CHAT — los runs de nodos del CHAT dentro de una traza
     tienen que seguir siendo aristas del chat actual (unión de las
     variantes ±router). Solo el chat: es el flujo del producto y sus
     nodos corren en secuencia estricta. Los flujos que el chat despacha
     por tools (supervisor, debate, juez...) dejan sus eventos EN EL MISMO
     archivo — corridas de otros grafos, no caminatas del chat — y los
     concurrentes intercalan corutinas: juzgarlos por adyacencia sería un
     falso positivo (medido en la primera corrida: 246 falsos).
  C) REGISTRO DE TOOLS — cada evento de tool individual (evento_tool:
     nombre + ok/error) tiene que corresponder a una herramienta del
     action space VIVO (nodos.TOOLS + MODULE_IMPLS importados). Una tool
     que corrió en producción y ya no existe queda flaggeada (si se quitó
     a propósito, el informe lo muestra y el baseline se actualiza).
  D) POLÍTICA DEL ROUTER SOBRE TRÁFICO REAL — cada decisión registrada en
     salidas/routing.jsonl (exp/35) con su p(directo) se re-evalúa con la
     compuerta de HOY (umbral/q de utils.laya_routing.config_router):
     si hoy bloquearía un directo que se aprobó, o dejaría pasar uno que
     se bloqueó, es drift de política medido sobre tráfico real.

Determinista a propósito: SIN LLM, sin red, sin modelo. Baseline con el
patrón de evals.py (comparar sin pisar; --actualizar-baseline guarda).

Uso:
    python3 main.py replay [--dir .runs] [--salida salidas/evals] [--actualizar-baseline]
"""
import argparse
import json
import subprocess
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from utils.rutas import DIR_RUNS

DIR_SALIDA = Path("salidas/evals")
BASELINE = Path("salidas/evals/replay_baseline.json")
ROUTING_LOG = Path("salidas/routing.jsonl")

# Eventos que NO son ni nodo ni tool: marcas de incidente y alias históricos
# vistos en trazas viejas (la misma tolerancia que TOOLS_CONOCIDAS de evals).
NO_NODOS_TOLERADOS = {
    "corte_no_progreso": "marca de incidente (nodes.ExecuteTools.prep)",
    "bash": "alias histórica de run_command en trazas viejas",
}

# Los nodos del CHAT: el nivel B juzga los RUNS de estos nodos dentro de
# cualquier traza. Los flujos internos que el chat despacha por tools
# (supervisor, debate, juez...) dejan SUS eventos en el mismo archivo — son
# corridas de OTROS grafos, no caminatas del chat.
NODOS_CHAT = {"GetQuestion", "LayaRouter", "DirectAnswer", "AgentStep",
              "ExecuteTools", "ExitChat"}


# ---------------------------------------------------------------------------
# 1) GRAFOS VIVOS: clases, acciones cableadas y aristas del chat
# ---------------------------------------------------------------------------

def _nodos_alcanzables(start):
    """Los nodos alcanzables desde `start` (lo que el framework ejecuta).

    Un nodo Flow/BatchFlow anidado (auditoría, effective_n multi) tiene su
    pipeline en `start_node`, NO en successors: sin la recursión, las clases
    del flujo interno (CarpetaScan, Seccion...) quedarían invisibles para el
    replay — el propio guard de calles muertas tiene ese punto ciego."""
    vistos, orden, pendientes = set(), [], [start]
    while pendientes:
        nodo = pendientes.pop()
        if id(nodo) in vistos:
            continue
        vistos.add(id(nodo))
        orden.append(nodo)
        pendientes.extend(nodo.successors.values())
        interno = getattr(nodo, "start_node", None)
        if interno is not None and id(interno) not in vistos:
            pendientes.append(interno)
    return orden


def _grafo_debate():
    """El grafo inline de debate.py, armado sin correr nada: debatir() lo
    construye adentro de la función, así que se replica cableando los nodos
    igual que el fuente (Proponente/Critico se auto-apuntan). Devuelve las
    RAÍCES: P y C arrancan corutinas independientes, ninguno alcanza al
    otro."""
    from debate import Critico, FinAgente, JuezDebate, Proponente

    p, c, fin = Proponente(), Critico(), FinAgente()
    p - "continue" >> p
    p - "end" >> fin
    c - "continue" >> c
    c - "end" >> fin
    # el juez del debate corre DESPUÉS, en su propio Flow (debatir lo arma
    # aparte): raíz adicional, terminal sin aristas
    return [p, c, JuezDebate()]


def _grafo_rag():
    """El grafo inline de rag.py (indexar lo construye adentro)."""
    from rag import ChunkDocs, EmbedChunks, SaveIndex

    chunk, embed_, save = ChunkDocs(), EmbedChunks(), SaveIndex()
    chunk >> embed_ >> save
    return [chunk]


def _grafos_vivos():
    """(clases, aristas_chat): las clases VIVAS con sus acciones cableadas
    {nombre: set(acciones)} y las aristas del chat {(de, accion, a)} — unión
    de las variantes ±router del chat real."""
    import os

    from utils.viz import FLOWS

    clases = {}
    chat_nodos = []

    def registrar(start):
        for nodo in _nodos_alcanzables(start):
            nombre = type(nodo).__name__
            clases.setdefault(nombre, set()).update(nodo.successors)

    for nombre, ctor in FLOWS.items():
        flujo = ctor()
        registrar(flujo.start_node)
        if nombre == "chat":
            chat_nodos.append(flujo.start_node)

    # variante de degradación (USE_LAYA_ROUTER=0): fue producción y sigue
    # siéndolo cuando el checkpoint no está — sus aristas también cuentan
    from flow import create_agent_flow

    previo = os.environ.get("USE_LAYA_ROUTER")
    os.environ["USE_LAYA_ROUTER"] = "0"
    try:
        sin_router = create_agent_flow()
    finally:
        if previo is None:
            os.environ.pop("USE_LAYA_ROUTER", None)
        else:
            os.environ["USE_LAYA_ROUTER"] = previo
    registrar(sin_router.start_node)
    chat_nodos.append(sin_router.start_node)

    # los flujos inline (debate, rag), contra su propio fuente como el guard
    for raiz in _grafo_debate():
        registrar(raiz)
    for raiz in _grafo_rag():
        registrar(raiz)

    aristas_chat = set()
    for start in chat_nodos:
        for nodo in _nodos_alcanzables(start):
            for accion, siguiente in nodo.successors.items():
                aristas_chat.add((type(nodo).__name__, accion, type(siguiente).__name__))
    # exp/50: PreFetch es un pasaje TRANSPARENTE entre GetQuestion y el resto.
    # Las caminatas históricas (pre-exp/50) saltaban directo de GetQuestion a
    # LayaRouter/AgentStep y siguen siendo válidas: se agregan las aristas
    # transitivas (A -accion-> PreFetch -accion-> X implica A -accion-> X),
    # para que el nivel B no reporte como rotas caminatas que solo cambiaron
    # de forma, no de fondo.
    aristas_chat |= {
        (a, accion, c)
        for (a, accion, b) in aristas_chat
        if b == "PreFetch"
        for (b2, accion2, c) in aristas_chat
        if b2 == "PreFetch" and accion2 == accion and c != "PreFetch"
    }
    return clases, aristas_chat


def _herramientas_vivas():
    """Los nombres del action space VIVO: TOOLS (esquemas) + IMPL (implementaciones)
    importados de nodes — el registro real del que el chat despacha."""
    from nodes import MODULE_IMPLS, TOOLS

    return {t["function"]["name"] for t in TOOLS} | set(MODULE_IMPLS)


# ---------------------------------------------------------------------------
# 2) NIVELES — funciones PURAS sobre listas de eventos
# ---------------------------------------------------------------------------

def _es_error_trazado(accion):
    """El wrapper de tracing registra las excepciones como 'error:Tipo' —
    emisibles por cualquier nodo (no son una acción del post)."""
    return str(accion).startswith("error:")


def nivel_a(eventos, clases):
    """(nodo, accion) no emisibles por el código actual. Una acción es
    emisible si está cableada en la clase viva; 'None' (fin de flujo) lo es
    si la clase es terminal o tiene arista default."""
    violaciones = []
    for e in eventos:
        nodo, accion = e.get("nodo"), str(e.get("accion"))
        if nodo in NO_NODOS_TOLERADOS or _es_error_trazado(accion):
            continue
        aristas = clases.get(nodo)
        if aristas is None:
            continue  # ni clase: la clasifica el nivel C (tools) o es desconocida
        if accion == "None":
            ok = not aristas or "default" in aristas
        else:
            ok = accion in aristas
        if not ok:
            violaciones.append((nodo, accion))
    return violaciones


def nivel_a_desconocidos(eventos, clases, herramientas):
    """Eventos cuyo nodo no es clase viva NI tool viva NI tolerado: no hay
    forma de que el código actual los produzca. Los eventos tool-shaped
    (accion ok/error) los juzga el nivel C: acá solo los huérfanos de grafo."""
    desconocidos = []
    for e in eventos:
        nodo, accion = e.get("nodo"), str(e.get("accion"))
        if nodo in clases or nodo in herramientas or nodo in NO_NODOS_TOLERADOS:
            continue
        if _es_error_trazado(accion) or accion in ("ok", "error"):
            continue
        desconocidos.append((nodo, accion))
    return desconocidos


def nivel_b_chat(eventos, clases, aristas_chat):
    """Los RUNS de nodos del CHAT dentro de una traza tienen que seguir
    siendo aristas del chat actual (unión ±router). Solo el chat: los flujos
    que el chat despacha por tools dejan sus propios eventos intercalados en
    el mismo archivo (son corridas de OTROS grafos) y los concurrentes
    intercalan corutinas — juzgarlos por adyacencia sería falso positivo.
    Los eventos de tools y los errores (el flujo aborta) se saltean."""
    if not any(e.get("nodo") in NODOS_CHAT for e in eventos):
        return []
    nodos = [e for e in eventos
             if e.get("nodo") in NODOS_CHAT and not _es_error_trazado(e.get("accion"))]
    rotas = []
    for e1, e2 in zip(nodos, nodos[1:], strict=False):
        accion = str(e1["accion"])
        clave = "default" if accion == "None" else accion
        if (e1["nodo"], clave, e2["nodo"]) not in aristas_chat:
            rotas.append((e1["nodo"], accion, e2["nodo"]))
    return rotas


def nivel_c_tools(eventos, clases, herramientas):
    """Eventos de tools cuyo nombre ya no vive en el action space."""
    fantasma = []
    for e in eventos:
        nodo, accion = e.get("nodo"), str(e.get("accion"))
        if nodo in clases or nodo in NO_NODOS_TOLERADOS:
            continue
        if accion not in ("ok", "error"):
            continue  # no es evento de tool: nivel A / desconocidos lo trata
        if nodo not in herramientas:
            fantasma.append((nodo, accion))
    return fantasma


def nivel_d_router(lineas, config):
    """Re-evalúa las decisiones registradas del router con la compuerta de
    HOY. `lineas` son los dicts de routing.jsonl; `config` un RouterConfig
    de utils.laya_routing (puro: la política, no la inferencia).

    Dos direcciones, ambas drift sobre tráfico real:
    - APRETÓ: propuesta 'directo' (pasó la compuerta de entonces) que hoy
      no pasaría.
    - AFLOJÓ: propuesta 'herramientas' bloqueada por umbral (la causa
      empieza con 'p(directo)=', el formato versionado de decide) que hoy
      SÍ pasaría.
    La capa del voto posterior no está en el registro: se re-evalúa la
    compuerta, no el ensamble completo."""
    piso = (1.0 - config.q) if config.q is not None else config.umbral
    divergencias = []
    for ev in lineas:
        p = ev.get("p_directo")
        if p is None:
            continue
        propuesta = ev.get("propuesta")
        if propuesta == "directo" and p < piso:
            divergencias.append(("apretó", ev.get("causa"), p))
        elif (
            propuesta == "herramientas"
            and str(ev.get("causa", "")).startswith("p(directo)=")
            and p >= piso
        ):
            divergencias.append(("aflojó", ev.get("causa"), p))
    return divergencias


# ---------------------------------------------------------------------------
# 3) CORRIDA sobre .runs + routing.jsonl
# ---------------------------------------------------------------------------

def _leer_eventos(archivo):
    """El mismo parseo tolerante de evals (importado, no copiado)."""
    from evals import _leer_eventos as _leer

    return _leer(archivo)


def _leer_jsonl(ruta):
    ruta = Path(ruta)
    if not ruta.is_file():
        return []
    lineas = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            try:
                lineas.append(json.loads(linea))
            except json.JSONDecodeError:
                continue  # un renglón roto es un artefacto, no una excepción
    return lineas


def replay_runs(dir_runs=DIR_RUNS, routing_log=ROUTING_LOG, config=None):
    """Corre los cuatro niveles sobre todas las trazas. Devuelve el informe
    crudo (dict) que consume el markdown. `config` (RouterConfig) permite
    inyectar la política en tests; en producción la de config_router()."""
    clases, aristas_chat = _grafos_vivos()
    herramientas = _herramientas_vivas()

    dir_runs = Path(dir_runs)
    archivos = sorted(dir_runs.glob("*.jsonl")) if dir_runs.is_dir() else []
    por_nivel = {"a": [], "a_desconocidos": [], "b": [], "c": [], "d": []}
    ejemplos = {"a": {}, "a_desconocidos": {}, "b": {}, "c": {}}
    total_eventos = 0
    trazas_chat = 0

    for archivo in archivos:
        eventos = _leer_eventos(archivo)
        if not eventos:
            continue
        total_eventos += len(eventos)
        es_chat = any(e.get("nodo") == "GetQuestion" for e in eventos)
        trazas_chat += int(es_chat)

        viol_a = nivel_a(eventos, clases)
        viol_unk = nivel_a_desconocidos(eventos, clases, herramientas)
        viol_b = nivel_b_chat(eventos, clases, aristas_chat)
        viol_c = nivel_c_tools(eventos, clases, herramientas)
        for nivel, viols in (("a", viol_a), ("a_desconocidos", viol_unk),
                             ("b", viol_b), ("c", viol_c)):
            por_nivel[nivel].extend((archivo.name, *v) for v in viols)
            for v in viols:
                ejemplos[nivel].setdefault(v, []).append(archivo.name)

    if config is None:
        from utils.laya_routing import config_router

        config = config_router()
    lineas_routing = _leer_jsonl(routing_log)
    por_nivel["d"] = [(tipo, causa, p) for tipo, causa, p in nivel_d_router(lineas_routing, config)]

    return {
        "trazas": len(archivos),
        "eventos": total_eventos,
        "trazas_chat": trazas_chat,
        "grafos": {
            "clases": len(clases),
            "herramientas": len(herramientas),
            "aristas_chat": len(aristas_chat),
        },
        "violaciones": {
            "a": len(por_nivel["a"]),
            "a_desconocidos": len(por_nivel["a_desconocidos"]),
            "b": len(por_nivel["b"]),
            "c": len(por_nivel["c"]),
            "d": len(por_nivel["d"]),
        },
        "detalle": por_nivel,
        "ejemplos": {k: {str(clave): sorted(set(v))[:3] for clave, v in d.items()}
                     for k, d in ejemplos.items()},
        "routing": {"eventos": len(lineas_routing), "log": str(routing_log)},
        "politica_hoy": {"modo": config.modo, "umbral": config.umbral, "q": config.q},
    }


# ---------------------------------------------------------------------------
# 4) BASELINE (patrón evals.py: comparar sin pisar)
# ---------------------------------------------------------------------------

def comparar_baseline(informe, ruta=BASELINE):
    """Veredicto OK/REGRESIÓN/PRIMERA CORRIDA sobre el TOTAL de violaciones
    por nivel. La señal no es gate: un REGRESIÓN dice 'mirá esto', no
    bloquea nada."""
    comparacion = {"veredicto": "PRIMERA CORRIDA", "anterior": None, "delta": {}}
    if not Path(ruta).is_file():
        return comparacion
    try:
        anterior = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return comparacion
    if "violaciones" not in anterior:
        return comparacion
    comparacion["anterior"] = anterior
    delta = {}
    peor = False
    for nivel, valor in informe["violaciones"].items():
        antes = anterior["violaciones"].get(nivel, 0)
        delta[nivel] = valor - antes
        if valor > antes:
            peor = True
    comparacion["delta"] = delta
    comparacion["veredicto"] = "REGRESIÓN" if peor else "OK"
    return comparacion


def guardar_baseline(informe, ruta=BASELINE, sha=None):
    """Guarda el baseline {fecha, git_sha, violaciones}. Nunca pisa desde
    una corrida sin trazas."""
    if not informe.get("trazas"):
        return None
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "git_sha": sha if sha is not None else _git_sha(),
        "violaciones": informe["violaciones"],
        "trazas": informe["trazas"],
        "eventos": informe["eventos"],
    }
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return datos


# ---------------------------------------------------------------------------
# 5) INFORME
# ---------------------------------------------------------------------------

def _git_sha():
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001 (git es best-effort, no dependencia)
        return ""


_NIVEL_NOMBRE = {
    "a": "acciones no emisibles por el código actual",
    "a_desconocidos": "nodos desconocidos (ni clase ni tool viva)",
    "b": "adyacencia rota del chat",
    "c": "tools fuera del action space vivo",
    "d": "divergencias de política del router",
}


def informe_markdown(informe, comparacion, sha, fecha):
    L = []
    L.append(f"# Replay de trazas — {fecha}")
    L.append("")
    L.append(f"git sha: `{sha}`")
    L.append("")
    L.append("## Límite honesto")
    L.append("")
    L.append("La traza guarda la CAMINATA (nodo/acción/duración), no el contenido: sin preguntas, "
             "args ni resultados. Este replay valida comportamiento **estructural** contra el "
             "código actual — la regresión **semántica** (misma caminata, peor respuesta) la "
             "atrapan los benches con contenido (bench_juez, banco). Instrumento de señal, no gate.")
    L.append("")
    L.append("## Resumen")
    L.append("")
    L.append(f"- Trazas: **{informe['trazas']}** ({informe['trazas_chat']} del chat) · "
             f"{informe['eventos']} eventos")
    L.append(f"- Grafos vivos: {informe['grafos']['clases']} clases · "
             f"{informe['grafos']['herramientas']} herramientas · "
             f"{informe['grafos']['aristas_chat']} aristas del chat")
    L.append(f"- Decisiones de routing re-evaluadas: {informe['routing']['eventos']} "
             f"(política de hoy: modo {informe['politica_hoy']['modo']}, "
             f"umbral {informe['politica_hoy']['umbral']}, q {informe['politica_hoy']['q']})")
    L.append("")
    L.append("| nivel | qué detecta | violaciones |")
    L.append("|---|---|---|")
    for nivel in ("a", "a_desconocidos", "b", "c", "d"):
        L.append(f"| {nivel} | {_NIVEL_NOMBRE[nivel]} | **{informe['violaciones'][nivel]}** |")
    L.append("")
    v = comparacion["veredicto"]
    icono = {"OK": "✅", "REGRESIÓN": "🔴", "PRIMERA CORRIDA": "🆕"}.get(v, "•")
    L.append(f"**Baseline:** {icono} {v}")
    if comparacion.get("delta"):
        L.append("")
        L.append("- " + " · ".join(f"{k}: {d:+d}" for k, d in comparacion["delta"].items()))
    L.append("")

    secciones = {
        "a": ("### Nivel A — acciones no emisibles", ("nodo", "accion")),
        "a_desconocidos": ("### Nivel A′ — nodos desconocidos", ("nodo", "accion")),
        "b": ("### Nivel B — adyacencia rota del chat", ("desde", "accion", "hacia")),
        "c": ("### Nivel C — tools fuera del action space", ("tool", "resultado")),
        "d": ("### Nivel D — divergencias de política del router", ("dirección", "causa registrada", "p(directo)")),
    }
    for nivel, (titulo, columnas) in secciones.items():
        detalle = informe["detalle"][nivel]
        if not detalle:
            continue
        L.append(titulo)
        L.append("")
        conteo = Counter(tuple(d) if nivel == "d" else tuple(d[1:]) for d in detalle)
        L.append("| " + " | ".join(columnas) + " | veces | ejemplo |")
        L.append("|" + "---|" * (len(columnas) + 2))
        for firma, n in conteo.most_common(20):
            ejemplos = informe["ejemplos"].get(nivel, {}).get(str(firma), [])
            L.append("| " + " | ".join(str(x) for x in firma) + f" | {n} | {', '.join(ejemplos[:2])} |")
        L.append("")
    if not any(informe["detalle"][n] for n in secciones):
        L.append("Sin violaciones: las caminatas de producción siguen siendo ejecutables "
                 "por el código actual.")
        L.append("")
    return "\n".join(L)


def generar(dir_runs=DIR_RUNS, dir_salida=DIR_SALIDA, routing_log=ROUTING_LOG,
            config=None, sha=None, actualizar_baseline=False):
    """Corre el replay y escribe UN informe markdown. Devuelve su Path."""
    fecha = date.today().isoformat()
    sha = sha if sha is not None else _git_sha()
    informe = replay_runs(dir_runs, routing_log=routing_log, config=config)
    comparacion = comparar_baseline(informe)
    if actualizar_baseline:
        guardar_baseline(informe, sha=sha)
    md = informe_markdown(informe, comparacion, sha, fecha)
    dir_salida = Path(dir_salida)
    dir_salida.mkdir(parents=True, exist_ok=True)
    destino = dir_salida / f"replay_{fecha}.md"
    destino.write_text(md, encoding="utf-8")
    return destino


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="replay",
        description="Replay de trazas .runs contra el código actual (regresión de comportamiento)",
    )
    parser.add_argument("--dir", default=str(DIR_RUNS), help="carpeta de trazas (default: %(default)s)")
    parser.add_argument("--routing", default=str(ROUTING_LOG),
                        help="jsonl de decisiones del router (default: %(default)s)")
    parser.add_argument("--salida", default=str(DIR_SALIDA), help="carpeta de salida (default: %(default)s)")
    parser.add_argument("--actualizar-baseline", action="store_true",
                        help="guarda el baseline; sin esta flag se compara y NO se pisa")
    args = parser.parse_args(argv)

    destino = generar(dir_runs=args.dir, dir_salida=args.salida, routing_log=args.routing,
                      actualizar_baseline=args.actualizar_baseline)
    print(f"✓ informe de replay → {destino}")
    return destino


if __name__ == "__main__":
    main()
