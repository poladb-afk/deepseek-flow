"""Bench: supervisor reactivo vs agente PLANO con tool-calling nativo
(banco/specs/bench_supervisor.md).

La pregunta sin respuesta medida: ¿el supervisor actual (Laya elige
herramienta + mayoría 2-de-3 en la duda + DeepSeek redacta args = hasta 3
llamadas remotas por paso) le gana a un agente DeepSeek plano con
tool-calling nativo sobre las MISMAS herramientas (1 llamada por paso: elige
herramienta Y args juntos)? Este bench GATEA el gasto "Choose a escala
(~2.400 casos)": si el plano empata, el despacho se simplifica y los
vetos/self-healing (que son código) se quedan; si el supervisor gana, se
escala.

Standalone (como bench_juez.py). Las DOS vías corren las MISMAS 6 tareas de
`banco/supervisor_tareas.jsonl`, cada una verificable por CÓDIGO PURO con
grading DINÁMICO (la verdad se calcula al momento, sin constantes que
deriven). Tres métricas por tarea y total: llamadas remotas (contador que
envuelve call_llm/call_llm_agent), tiempo de reloj y calidad (la
verificación determinista 1/0).

- **Supervisor**: `supervisor.supervisar(tarea, salida=tmp)` tal cual es
  (nada del supervisor se toca). El informe final es el texto a gradear.
- **Agente plano** (nuevo, acá): un bucle mínimo con el MISMO action space
  que el supervisor (`supervisor._TODAS` + `supervisor.REGISTRO`,
  anti-recursión incluida) vía `call_llm_agent` con tool-calling nativo.
  MISMO presupuesto de pasos que el supervisor (5 ejecuciones de tools máx:
  a la última ronda se retiran las tools y debe responder).

Contención: un crash de una vía en una tarea NO tira el bench (esa celda
queda "error" con el motivo, patrón exp/20).

Baseline (patrón de evals.py/bench_juez.py): sin `--actualizar-baseline`
compara contra el guardado y reporta el delta, pero NO lo pisa; con la flag
lo guarda. Salida: markdown `salidas/evals/bench_supervisor_FECHA.md` + el
JSONL crudo al lado.

Uso: python3 banco/bench_supervisor.py [--solo supervisor|plano] [--tareas n]
"""
import argparse
import json
import re
import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import supervisor
from utils.formato import pct
from utils.git import sha_o_motivo

RAIZ = Path(__file__).resolve().parent.parent
TAREAS = RAIZ / "banco" / "supervisor_tareas.jsonl"
BASELINE = RAIZ / "salidas" / "evals" / "bench_supervisor.json"
DIR_SALIDA = RAIZ / "salidas" / "evals"

MAX_RONDAS_PLANO = 8  # tope del agente plano: a esta ronda se retiran las tools
MAX_TOOLS = 5         # MISMO presupuesto de pasos que el supervisor (MAX_PASOS)
# Nombre exacto del informe que escribe el supervisor (bench_juez.FAIL_RE lo lee).
INFORME_SUPERVISOR = "salidas/supervisor.md"


# AGENTE PLANO (bucle mínimo con tool-calling nativo)

SYSTEM_PLANO = (
    "Resolvé la tarea con las herramientas disponibles. Tenés hasta {n} "
    "rondas de herramientas; cuando ya tengas la respuesta, o si te quedás "
    "sin presupuesto, respondé con el resultado final en texto, sin llamar "
    "más herramientas."
)


def _as_dict(obj):
    """La tool call como dict canónico del historial (lo que come
    `run_tool_call`). Acepta el objeto del SDK (con atributos) o un dict ya
    armado (tests)."""
    if isinstance(obj, dict):
        return obj
    fn = obj.function
    argumentos = getattr(fn, "arguments", None)
    if isinstance(argumentos, str):
        argumentos = json.loads(argumentos or "{}")
    return {
        "id": getattr(obj, "id", None) or "call",
        "type": "function",
        "function": {"name": fn.name, "arguments": json.dumps(argumentos or {}, ensure_ascii=False)},
    }


def _contenido(msg):
    return getattr(msg, "content", None) or ""


def agente_plano(tarea, llm=None, impls=None, run=None, max_rondas=MAX_RONDAS_PLANO, max_tools=MAX_TOOLS):
    """Bucle mínimo del agente plano: DeepSeek elige herramienta Y args
    juntos en cada ronda (1 llamada por ronda) hasta `max_rondas`. A la última
    ronda se retiran las tools para forzar la respuesta. Las tools se ejecutan
    por `fs_tools.run_tool_call` para heredar los hooks (denylist y
    post-hooks). El action space incluye `supervisor._TODAS` + las IMPLs
    cacheadas de `supervisor.REGISTRO` (anti-recursión heredada).

    Devuelve {"texto", "rondas", "tools_ejecutadas"}. `llm`, `impls` y `run`
    son inyectables para los tests (fakes sin LLM ni ejecución real)."""
    if llm is None:
        from utils.call_llm import call_llm_agent as llm

    if impls is None:
        impls = {n: supervisor.REGISTRO[n] for n in (supervisor.REGISTRO or {}) if n in supervisor.REGISTRO}

    if run is None:
        from utils import fs_tools

        run = fs_tools.run_tool_call

    mensajes = [
        {"role": "system", "content": SYSTEM_PLANO.format(n=max_tools)},
        {"role": "user", "content": tarea},
    ]
    texto = ""
    rondas = 0
    ejecutadas = 0
    for ronda in range(max_rondas):
        ultima = ronda == max_rondas - 1
        tools = None if ultima else supervisor._TODAS
        msg = llm(mensajes, tools=tools)
        rondas = ronda + 1
        texto = _contenido(msg)
        # A la última ronda se RETIRAN las tools: aunque el modelo devuelva
        # tool_calls, no hay presupuesto para ejecutarlas — se toma su texto
        # como respuesta final (forzar la respuesta, no colgar el bucle).
        if ultima:
            break
        llamadas = getattr(msg, "tool_calls", None) or []
        if not llamadas:
            break
        mensajes.append({
            "role": "assistant",
            "content": getattr(msg, "content", None),
            "tool_calls": [getattr(t, "model_dump_dict", None) and None or _as_dict(t) for t in llamadas],
        })
        for t in llamadas:
            tc = _as_dict(t)
            resultado = run(tc, impls)["content"]
            mensajes.append({"role": "tool", "tool_call_id": tc["id"], "content": resultado})
            ejecutadas += 1
    return {"texto": texto, "rondas": rondas, "tools_ejecutadas": ejecutadas}


# MÉTRICAS: contador de llamadas remotas (envuelve call_llm / call_llm_agent)

def contador(llm_modulo):
    """Envuelve `call_llm` y `call_llm_agent` de `llm_modulo` con un contador.
    Devuelve (estado, restaurar): `estado["llamadas"]` acumula cada invocación
    (a ambas). `restaurar()` devuelve el módulo a sus funciones originales.

    Los wrappers NO cambian el contrato (mismos args y mismo retorno) y son
    `*args, **kwargs`: sirven para contar y para inyectar un fake — el
    fake llama al contador igual. El contador es estado puro, testeable."""
    estado = {"llamadas": 0}
    originales = {}

    def envolver(nombre):
        if not hasattr(llm_modulo, nombre):
            return  # el módulo no importa ese nombre (supervisor solo tiene call_llm)
        # El original tal cual se resuelve por atributo (una función de módulo
        # o un método ya ligado). Se guarda junto a si vivía en el `__dict__`
        # del objeto: un módulo sí, una instancia con el método en la clase no.
        original = getattr(llm_modulo, nombre)
        originales[nombre] = (original, nombre in getattr(llm_modulo, "__dict__", {}))

        def wrapper(*args, **kwargs):
            estado["llamadas"] += 1
            return original(*args, **kwargs)

        setattr(llm_modulo, nombre, wrapper)

    for nombre in ("call_llm", "call_llm_agent"):
        envolver(nombre)

    def restaurar():
        # Devuelve el atributo a su ORIGEN: si estaba en el `__dict__`, se
        # repone ese mismo objeto (identidad estable, como un módulo); si no
        # (método de clase), se borra el wrapper y vuelve a resolverse por la
        # clase — nunca se deja un wrapper pegado.
        for nombre, (original, era_dict) in originales.items():
            if era_dict:
                setattr(llm_modulo, nombre, original)
            else:
                delattr(llm_modulo, nombre)

    return estado, restaurar


# VERIFICACIONES (grading dinámico, código puro)

def _contiene_numero(texto, numero):
    return bool(re.search(rf"(?<!\d){re.escape(str(numero))}(?!\d)", texto or ""))


def _verificar_contar_utils(texto):
    """El texto contiene str(len(list(Path('utils').glob('*.py')))) — la
    verdad se calcula AHORA, no es una constante."""
    n = len(list((RAIZ / "utils").glob("*.py")))
    return _contiene_numero(texto, n)


def _verificar_constante_max_pasos(texto):
    return "5" in (texto or "")


def _verificar_firma_veredicto(texto):
    """Contiene 'met' y al menos uno de {uncertain, not met} — el contrato
    observable de utils/laya.veredicto (vuelve 'met'/'not met'/'uncertain')."""
    low = (texto or "").lower()
    return "met" in low and ("uncertain" in low or "not met" in low)


def _buscar_db_trazas():
    """La trazas.db del proyecto (o la del cargador): la primera que exista."""
    for ruta in (RAIZ / "trazas.db", RAIZ / "salidas" / "trazas.db"):
        if ruta.is_file():
            return ruta
    return None


def _verificar_tablas_trazas(texto):
    """El texto contiene el conteo REAL de tablas de la trazas.db (contado
    ahora con sqlite3). Si el archivo no existe → None (tarea indeterminada)."""
    db = _buscar_db_trazas()
    if db is None:
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            n = con.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        return None
    return _contiene_numero(texto, n)


def _lineas_marcadores():
    """Las LÍNEAS (1-indexadas) donde banco/banco.py define el dict MARCADORES
    (regex `^\\s*MARCADORES` sobre el archivo real). Lista vacía si no está."""
    archivo = RAIZ / "banco" / "banco.py"
    if not archivo.is_file():
        return []
    return [
        i
        for i, linea in enumerate(
            archivo.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        )
        if re.match(r"^\s*MARCADORES", linea)
    ]


def _verificar_linea_marcadores(texto):
    """El texto contiene el número de línea REAL de la definición de
    MARCADORES. Si el archivo o la definición no están → None."""
    lineas = _lineas_marcadores()
    if not lineas:
        return None
    return any(_contiene_numero(texto, n) for n in lineas)


def _verificar_conteo_routing(texto):
    """El texto contiene len(open(salidas/routing.jsonl).readlines()) contado
    ahora. Archivo inexistente → None (tarea saltable con motivo)."""
    archivo = RAIZ / "salidas" / "routing.jsonl"
    if not archivo.is_file():
        return None
    n = len(archivo.read_text(encoding="utf-8", errors="replace").splitlines())
    return _contiene_numero(texto, n)


VERIFICACIONES = {
    "contar-utils": _verificar_contar_utils,
    "constante-max-pasos": _verificar_constante_max_pasos,
    "firma-veredicto": _verificar_firma_veredicto,
    "tablas-trazas": _verificar_tablas_trazas,
    "linea-marcadores": _verificar_linea_marcadores,
    "conteo-routing": _verificar_conteo_routing,
}


def verificar(id_tarea, texto):
    """True/False: la verificación pura de la tarea. None si la tarea es
    indeterminada AHORA (archivo ausente) — el bench la salta con motivo.
    KeyError si el id no tiene verificación (nunca un silencio)."""
    return VERIFICACIONES[id_tarea](texto)


# TAREAS

def cargar_tareas(ruta=TAREAS):
    """Tareas de `ruta` validadas: cada línea un JSON con `id` y `tarea`, y
    cada id con su verificación en `VERIFICACIONES`. Un archivo roto, un caso
    incompleto o un id sin verificación es SystemExit con mensaje CLARO."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise SystemExit(f"ERROR: no existe el archivo de tareas: {ruta}")
    tareas = []
    for i, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
        if not linea.strip():
            continue
        try:
            tarea = json.loads(linea)
        except json.JSONDecodeError as e:
            raise SystemExit(f"ERROR: JSON inválido en {ruta}:{i} ({e.msg})") from e
        if not isinstance(tarea, dict):
            raise SystemExit(f"ERROR: la tarea de {ruta}:{i} no es un objeto JSON")
        faltan = [c for c in ("id", "tarea") if not tarea.get(c)]
        if faltan:
            raise SystemExit(f"ERROR: a la tarea de {ruta}:{i} le falta {' y '.join(faltan)}")
        if tarea["id"] not in VERIFICACIONES:
            raise SystemExit(f"ERROR: la tarea {tarea['id']!r} no tiene verificación en VERIFICACIONES")
        tareas.append(tarea)
    if not tareas:
        raise SystemExit(f"ERROR: {ruta} no tiene tareas")
    return tareas


# CORRIDA (contención por tarea)

def _correr_supervisor(tarea):
    """Camino de PRODUCCIÓN: supervisor.supervisar tal cual. Devuelve el
    informe final (el archivo que escribe, leído del disco)."""
    informe = supervisor.supervisar(tarea, salida=INFORME_SUPERVISOR)
    return Path(informe).read_text(encoding="utf-8")


def contar_exploraciones(informe):
    """Cuántas veces corrió `explorar` en una corrida, leído de la sección
    "Pasos" del informe (una línea por llamada). Es la prueba de que la pieza
    CORRIÓ: un brazo con EXPLORAR=1 y 0 exploraciones no midió el explorador."""
    return len(re.findall(r"^- \d+ explorar\(", informe or "", re.M))


def _celda(id_tarea, via, texto, seg, llamadas):
    """Arma la fila de una celda ya ejecutada: gradúa con código puro (o la
    salta si la verificación devuelve None)."""
    ok = verificar(id_tarea, texto)
    return {
        "id": id_tarea,
        "via": via,
        "ok": ok,
        "seg": round(seg, 2),
        "llamadas": llamadas,
        "exploraciones": contar_exploraciones(texto) if via == "supervisor" else 0,
        "motivo": None if ok is not None else "tarea saltada: verificación indeterminada (archivo ausente)",
        "error": False,
        "respuesta": texto,
    }


def _celda_error(id_tarea, via, error, seg, llamadas):
    """Celda contenida: la vía reventó, pero el bench sigue. Patrón exp/20."""
    return {
        "id": id_tarea,
        "via": via,
        "ok": False,
        "seg": round(seg, 2),
        "llamadas": llamadas,
        "motivo": f"error: {type(error).__name__}: {str(error)[:200]}",
        "error": True,
        "respuesta": None,
    }


def correr(tareas, vias=("supervisor", "plano"), runner_sup=None, runner_plano=None,
           llm_modulo=None, dir_tmp=None):
    """Corre cada (tarea, vía) midiendo llamadas remotas y segundos. CADA celda
    está contenida: un crash de una vía no tira el bench (esa celda queda como
    error). `runner_*` y `llm_modulo` son inyectables para los tests (fakes
    sin LLM). Devuelve filas + métricas agregadas."""
    if llm_modulo is None:
        from utils import call_llm as llm_modulo

    if runner_sup is None:
        runner_sup = _correr_supervisor
    if runner_plano is None:
        def runner_plano(t):
            return agente_plano(t)["texto"]

    filas = []
    n = len(tareas) * len(vias)
    k = 0
    for tarea in tareas:
        for via in vias:
            k += 1
            runner = runner_sup if via == "supervisor" else runner_plano
            print(f"[bench] {k}/{n} {tarea['id']} · {via}…", flush=True)
            estado, restaurar = contador(llm_modulo)
            # supervisor.py importa `call_llm` DIRECTO al tope del módulo:
            # envolver solo utils.call_llm no intercepta SUS llamadas (medido:
            # la primera corrida reportó 0 llamadas para el supervisor). Se
            # envuelve también la referencia del módulo supervisor — son
            # objetos distintos, no hay doble conteo; el total es la SUMA.
            estado_sup = None
            restaurar_sup = None
            if via == "supervisor":
                estado_sup, restaurar_sup = contador(supervisor)
            t0 = time.perf_counter()
            try:
                texto = runner(tarea["tarea"])
            except Exception as e:  # noqa: BLE001 — la celda fallida es un DATO del bench
                seg = time.perf_counter() - t0
                if restaurar_sup is not None:
                    estado["llamadas"] += estado_sup["llamadas"]
                    restaurar_sup()
                filas.append(_celda_error(tarea["id"], via, e, seg, estado["llamadas"]))
                print(f"[bench] {k}/{n} {tarea['id']} · {via} fail", flush=True)
                continue
            finally:
                restaurar()
            if restaurar_sup is not None:
                estado["llamadas"] += estado_sup["llamadas"]
                restaurar_sup()
            seg = time.perf_counter() - t0
            filas.append(_celda(id_tarea=tarea["id"], via=via, texto=texto, seg=seg,
                                llamadas=estado["llamadas"]))
            print(f"[bench] {k}/{n} {tarea['id']} · {via} ok", flush=True)

    return {"filas": filas, **agregar(filas)}


def _tasa(filas):
    """Fracción de celdas `ok=True` sobre las EVALUABLES (ok no None). 0.0 si
    no hay evaluables."""
    evaluables = [f for f in filas if f["ok"] is not None]
    return round(sum(1 for f in evaluables if f["ok"]) / len(evaluables), 4) if evaluables else 0.0


def agregar(filas):
    """Métricas agregadas por vía (calidad, llamadas, segundos y tope de
    llamadas) y el veredicto agregado del bench."""
    por_via = {}
    for via in ("supervisor", "plano"):
        sub = [f for f in filas if f["via"] == via]
        if sub:
            por_via[via] = {
                "calidad": _tasa(sub),
                "llamadas": sum(f["llamadas"] for f in sub),
                "exploraciones": sum(f.get("exploraciones", 0) for f in sub),
                "seg": round(sum(f["seg"] for f in sub), 2),
                "tope_llamadas": max(f["llamadas"] for f in sub),
                "n": len(sub),
            }
    return {"por_via": por_via, "veredicto": veredicto_plano(por_via)}


def veredicto_plano(por_via):
    """Lectura del gate: si el plano EMPATA o GANA en calidad con menos
    llamadas → el despacho se simplifica. El supervisor gana solo si su
    calidad es MAYOR."""
    sup = por_via.get("supervisor")
    plano = por_via.get("plano")
    if not sup or not plano:
        return "sin datos"
    if plano["calidad"] >= sup["calidad"]:
        return "plano empata o gana → el despacho se simplifica"
    return "supervisor gana → se escala"


# BASELINE (patrón de evals.py / bench_juez.py)

def comparar_baseline(nuevo, ruta=BASELINE):
    """Compara contra el baseline guardado si existe. Delta por vía y
    veredicto: PRIMERA CORRIDA (no había baseline), REGRESIÓN (bajó la
    calidad de alguna vía, tolerancia 1e-9) u OK. Un baseline ilegible o sin
    métricas no cuenta como referencia."""
    comparacion = {"veredicto": "PRIMERA CORRIDA", "anterior": None, "delta": {}}
    if not Path(ruta).is_file():
        return comparacion
    try:
        anterior = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return comparacion
    if not anterior.get("por_via"):
        return comparacion

    comparacion["anterior"] = anterior
    delta = {}
    regresion = False
    for via, actual in nuevo.get("por_via", {}).items():
        prev = anterior["por_via"].get(via)
        if not prev:
            continue
        d = actual["calidad"] - prev["calidad"]
        delta[via] = round(d, 4)
        if d < -1e-9:
            regresion = True
    comparacion["delta"] = delta
    comparacion["veredicto"] = "REGRESIÓN" if regresion else "OK"
    return comparacion


def guardar_baseline(bench, ruta=BASELINE, sha=None, fecha_actualizacion=None):
    """Guarda el baseline nuevo {fecha, git_sha, por_via}. Solo si el bench
    corrió: una corrida sin filas no debe pisar un baseline válido. Con
    `fecha_actualizacion` (flag explícita) se agrega `actualizado_en` para
    dejar rastro visible de que el archivo se pisó a propósito."""
    if not bench.get("filas"):
        return None
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "git_sha": sha if sha is not None else sha_o_motivo(),
        "por_via": bench["por_via"],
        "veredicto": bench["veredicto"],
    }
    if fecha_actualizacion:
        datos["actualizado_en"] = datetime.now().isoformat(timespec="seconds")
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return datos


# INFORME

def _fmt_ok(v):
    return {True: "✅", False: "🔴", None: "－"}.get(v, "—")


def informe_markdown(bench, comparacion, sha, fecha):
    L = []
    L.append(f"# Bench supervisor vs agente plano — {fecha}")
    L.append("")
    L.append(f"git sha: `{sha}`")
    L.append("")
    L.append("El supervisor de producción (`supervisor.supervisar`: hoy el loop del "
             "kernel con las leyes del ejecutor y la síntesis, H2 PR 2) contra un agente "
             "DeepSeek PLANO con tool-calling nativo sobre las MISMAS herramientas "
             "(1 llamada por ronda). "
             "Las 6 tareas de `banco/supervisor_tareas.jsonl` gradúan con CÓDIGO PURO "
             "y DINÁMICO: la verdad se calcula al momento, sin constantes que deriven.")
    L.append("")
    por_via = bench["por_via"]
    for via in ("supervisor", "plano"):
        if via not in por_via:
            continue
        m = por_via[via]
        L.append(f"- **{via}**: calidad {pct(m['calidad'])} · "
                 f"{m['llamadas']} llamadas remotas · {m['seg']:.1f}s "
                 f"(tope por tarea {m['tope_llamadas']})"
                 + (f" · `explorar` corrió {m.get('exploraciones', 0)} veces" if via == "supervisor" else ""))
    L.append("")
    L.append(f"**Veredicto:** {bench['veredicto']}")
    L.append("")
    L.append("## Detalle por tarea y vía")
    L.append("")
    L.append("| tarea | vía | ok | llamadas | seg | explorar |")
    L.append("|-------|-----|----|----------|-----|----------|")
    for f in bench["filas"]:
        ok = _fmt_ok(f["ok"])
        L.append(f"| {f['id']} | {f['via']} | {ok} | {f['llamadas']} | {f['seg']:.2f} "
                 f"| {f.get('exploraciones', 0)} |")
    L.append("")
    v = comparacion["veredicto"]
    icono = {"OK": "✅", "REGRESIÓN": "🔴", "PRIMERA CORRIDA": "🆕"}.get(v, "•")
    L.append(f"**Baseline:** {icono} {v}")
    if comparacion["anterior"]:
        a = comparacion["anterior"]
        L.append("")
        L.append(f"- Anterior: {a.get('fecha', '?')} · sha `{(a.get('git_sha') or '?')[:10]}` "
                 f"· {a.get('veredicto', '?')}")
        for via, d in comparacion["delta"].items():
            L.append(f"- Delta calidad {via}: {d:+.4f}")
    L.append("")
    fallos = [f for f in bench["filas"] if f["error"] or f["ok"] is False]
    saltadas = [f for f in bench["filas"] if f["ok"] is None]
    if fallos:
        L.append("## Fallos y errores")
        L.append("")
        for f in fallos:
            L.append(f"### {f['id']} · {f['via']}")
            L.append("")
            L.append(f"- {f['motivo']}")
            if f["respuesta"]:
                L.append("")
                L.append("<details><summary>respuesta cruda</summary>")
                L.append("")
                L.append("```")
                L.append(f["respuesta"].strip())
                L.append("```")
                L.append("</details>")
            L.append("")
    if saltadas:
        L.append("## Tareas saltadas")
        L.append("")
        for f in saltadas:
            L.append(f"- {f['id']} · {f['via']}: {f['motivo']}")
        L.append("")
    return "\n".join(L)


def escribir_jsonl(bench, fecha, dir_salida=DIR_SALIDA):
    dir_salida = Path(dir_salida)
    dir_salida.mkdir(parents=True, exist_ok=True)
    destino = dir_salida / f"bench_supervisor_{fecha}.jsonl"
    with destino.open("w", encoding="utf-8") as fh:
        for fila in bench["filas"]:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return destino


def generar(tareas=TAREAS, dir_salida=DIR_SALIDA, vias=("supervisor", "plano"),
            runner_sup=None, runner_plano=None, llm_modulo=None, sha=None,
            actualizar_baseline=False):
    """Corre el bench y escribe el informe markdown + el JSONL crudo. Sin
    `actualizar_baseline` compara contra el baseline pero NO lo pisa; con la
    flag lo guarda. Devuelve (Path_md, Path_jsonl)."""
    fecha = date.today().isoformat()
    sha = sha if sha is not None else sha_o_motivo()

    # main() ya cargó (y quizá recortó) la lista; el default y los tests
    # pueden pasar la RUTA — las dos formas entran acá.
    lista = tareas if isinstance(tareas, list) else cargar_tareas(tareas)
    bench = correr(lista, vias=vias, runner_sup=runner_sup, runner_plano=runner_plano,
                   llm_modulo=llm_modulo)
    comparacion = comparar_baseline(bench)
    if actualizar_baseline:
        guardar_baseline(bench, sha=sha, fecha_actualizacion=fecha)

    md = informe_markdown(bench, comparacion, sha, fecha)
    dir_salida = Path(dir_salida)
    dir_salida.mkdir(parents=True, exist_ok=True)
    destino = dir_salida / f"bench_supervisor_{fecha}.md"
    destino.write_text(md, encoding="utf-8")
    jsonl = escribir_jsonl(bench, fecha, dir_salida)
    return destino, jsonl


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="bench_supervisor",
        description="Bench: supervisor reactivo vs agente plano con tool-calling nativo, grading en código puro")
    parser.add_argument("--solo", choices=["supervisor", "plano"], default=None,
                        help="corre SOLO una vía (default: las dos)")
    parser.add_argument("--tareas", type=int, default=None,
                        help="máximo de tareas a correr (default: todas)")
    parser.add_argument("--actualizar-baseline", action="store_true",
                        help="guarda el baseline; sin esta flag se compara y NO se pisa")
    args = parser.parse_args(argv)

    tareas = cargar_tareas()
    if args.tareas is not None:
        tareas = tareas[: args.tareas]
    vias = (args.solo,) if args.solo else ("supervisor", "plano")

    destino, jsonl = generar(tareas=tareas, vias=vias,
                             actualizar_baseline=args.actualizar_baseline)
    print(f"✓ bench supervisor → {destino}")
    print(f"  JSONL crudo → {jsonl}")


if __name__ == "__main__":
    main()
