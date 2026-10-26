"""Supervisor v3 (H2 PR 2): una instancia del kernel con las leyes del ejecutor.

El bench de 2026-10-13 midió que el valor del supervisor no estaba en el
Choose (Laya + mayoría) sino en las LEYES de código: vetos, caché,
presupuesto, fallo-como-feedback, anti-recursión. v2 ya despachaba con UNA
llamada que elige herramienta y args; v3 deja de tener loop propio: el loop
es el del kernel (`utils/kernel.loop`) y lo que queda acá es lo que lo hace
supervisor.

    loop del kernel ──▶ Auditar ──▶ Sintetizar

- **Las leyes envuelven cada Tool** (`con_leyes`): veto por fallos, caché de
  la llamada idéntica, veto de repetición. Las guardas siguen PURAS
  (`guarda_vetada`, `guarda_repetida`) y el estado de ley vive en el shared
  del supervisor, no en globals. Un lock serializa la consulta y el registro
  (las lecturas del kernel pueden correr en paralelo).
- **Un saldo para todo el árbol** (`Ledger(MAX_PASOS)`): con `EXPLORAR=1` la
  tool `explorar` es el sub-agente del kernel y gasta del MISMO saldo que el
  supervisor. El kernel no la ofrece si no queda saldo para ella y su loop.
- **Auditar**: arma la sección "Pasos" y la telemetría de rondas secas (exp/96,
  sin corte) desde el registro de llamadas.
- **Sintetizar**: igual que siempre (informe + sección "Pasos").

Anti-recursión (L1): run_supervisor no está en el catálogo. El contrato del
fine-tune supervisor_dispatch vive en sonda_supervisor.py.

Uso: python3 main.py supervisor "tarea" [--salida supervisor.md]
"""
import argparse
import json
import threading
from pathlib import Path

from pocketflow import Flow, Node

import explorador
from modules import discover
from utils import fs_tools
from utils.call_llm import _setting, call_llm, call_llm_agent
from utils.convergencia import seco
from utils.fs_tools import TOOLS as BASE_TOOLS
from utils.fs_tools import escribir_salida
from utils.kernel import Ctx, Ledger, Tool, loop
from utils.kernel import semilla as semilla_agente

MAX_PASOS = 5
HECHO_LARGO = 160
MAX_FALLOS_POR_HERRAMIENTA = 2  # L8: dos errores y la herramienta se veta
# exp/97: la tool `explorar` (sub-agente de sólo lectura, contexto fresco).
# Se lee al importar (mismo criterio que MAX_TOOL_ROUNDS): cambiarla exige
# reiniciar el proceso.
EXPLORAR = _setting("EXPLORAR", "0").strip().lower() in ("1", "true", "si", "sí", "yes")

MODULE_TOOLS, MODULE_IMPLS = discover()
# Ley anti-recursión (L1 de bmo): el supervisor no se despacha a sí mismo.
_MODULE_IMPLS = {k: v for k, v in MODULE_IMPLS.items() if k != "run_supervisor"}
_TODAS = [t for t in BASE_TOOLS + MODULE_TOOLS if t["function"]["name"] != "run_supervisor"]
if EXPLORAR:  # off por default: sin el setting el catálogo queda byte-idéntico
    _TODAS = _TODAS + [explorador.TOOL_EXPLORAR]

REGISTRO = {
    "list_files": fs_tools.list_files,
    "read_file": fs_tools.read_file,
    "search_files": fs_tools.search_files,
    **_MODULE_IMPLS,
}
if EXPLORAR:
    REGISTRO[explorador.NOMBRE_TOOL] = explorador.explorar

# Herramientas sin argumentos: repetirlas en una corrida es quemar presupuesto
# (patología medida: db_schema corrió 4 veces en una tarea real de 5 pasos).
SIN_ARGS = {t["function"]["name"] for t in _TODAS if not t["function"].get("parameters", {}).get("properties")}
# Lo que se puede correr en paralelo: lo que solo lee. El resto (escrituras,
# comandos, tools de módulos sin declarar) va en orden, en un solo hilo.
LECTURA = {"list_files", "read_file", "search_files", explorador.NOMBRE_TOOL}

TEXTO_VETO = (
    f"ERROR: herramienta vetada en esta corrida (falló {MAX_FALLOS_POR_HERRAMIENTA} veces) "
    "— elegí otra o cerrá"
)


# Leyes como guardas PURAS (§2): sin LLM, sin estado compartido, testeables.

def clave_de(args):
    """La firma canónica de los args de una llamada: json con claves
    ordenadas — la herramienta la aporta la tupla (herramienta, clave)."""
    return json.dumps(args or {}, sort_keys=True, ensure_ascii=False)


def guarda_vetada(herramienta, fallos):
    """Ley L8: una herramienta que falló dos veces en esta corrida no vuelve
    a correr. Devuelve None si puede correr, o el TEXTO de resultado que
    vuelve al modelo como feedback (no se ejecuta)."""
    if fallos.get(herramienta, 0) >= MAX_FALLOS_POR_HERRAMIENTA:
        return TEXTO_VETO
    return None


def guarda_repetida(firma, previas, exitosas, sin_args):
    """El caché y el veto de repetición. Devuelve None si la llamada corre;
    si es idéntica (misma firma (herramienta, clave)) a una exitosa previa,
    devuelve ("cached", resultado); si es sin-args ya exitosa o la misma
    firma ya vista dos veces, devuelve ("veto", TEXTO_VETO).

    `sin_args` es el conjunto de herramientas sin parámetros; `exitosas` la
    lista de herramientas que ya corrieron bien; `previas` el registro
    {(h, clave): {"n", "resultado"}}."""
    herramienta, _clave = firma
    registro = previas.get(firma)
    if registro and registro.get("resultado") is not None:
        return "cached", registro["resultado"]
    if herramienta in sin_args and herramienta in exitosas:
        return "veto", TEXTO_VETO
    if registro and registro.get("n", 0) >= 2:
        return "veto", TEXTO_VETO
    return None


def hecho_de(n, herramienta, args, resultado):
    breve = ", ".join(f"{k}={str(v)[:40]}" for k, v in (args or {}).items())
    una_linea = " ".join(str(resultado).split())
    return f"{n} {herramienta}({breve}) -> {una_linea[:HECHO_LARGO]}"


def catalogo():
    """El catálogo en prosa (lo usa la sonda del despacho jubilado)."""
    lineas = []
    for t in _TODAS:
        f = t["function"]
        args = f.get("parameters", {}).get("properties", {})
        firma = ", ".join(f"{n}{'?' if n not in f.get('parameters', {}).get('required', []) else ''}" for n in args)
        lineas.append(f"- {f['name']}({firma}): {f['description']}")
    return "\n".join(lineas)


def system_prompt(tarea):
    """System prompt del sub-agente: corto y tarea-primero (estilo casa). La
    tarea del usuario, el objetivo, el presupuesto, el CWD y los directorios
    permitidos. El catálogo son los schemas (nada de menú en prosa)."""
    from utils.fs_tools import allowed_roots

    roots = "\n".join(f"- {r}" for r in allowed_roots())
    cwd = Path.cwd()
    return (
        "Sos un sub-agente que resuelve UNA tarea con las tools disponibles.\n\n"
        f"Tarea: {tarea}\n\n"
        f"Resolvela con las tools disponibles; tenés un presupuesto de {MAX_PASOS} rondas "
        "(a la última se retiran las tools y tenés que cerrar con tu respuesta).\n\n"
        f"Trabajás en {cwd} y sus subdirectorios.\n"
        f"Directorio(s) permitido(s):\n{roots}\n\n"
        "Cuando la tarea esté cubierta o bloqueada, respondé con el resultado final en "
        "texto, sin llamar más herramientas."
    )


def _args_de(llamada):
    try:
        args = json.loads(llamada["function"].get("arguments") or "{}")
    except (TypeError, ValueError):
        args = {}
    return args if isinstance(args, dict) else {}


def _despachar(llamada, ctx):
    """Una tool del catálogo por run_tool_call (hooks, denylist, contención);
    `explorar` es el sub-agente del kernel y gasta del saldo del árbol."""
    if llamada["function"]["name"] == explorador.NOMBRE_TOOL:
        return explorador.AGENTE.correr(llamada, ctx)
    return fs_tools.run_tool_call(llamada, REGISTRO)["content"]


def _decidir(nombre, firma, ley):
    """(texto, repetida) si una ley frena la llamada; (None, None) si corre."""
    texto = guarda_vetada(nombre, ley["fallos"])
    if texto is not None:
        return texto, None
    veredicto = guarda_repetida(firma, ley["previas"], ley["exitosas"], SIN_ARGS)
    if veredicto is None:
        return None, None
    modo, valor = veredicto
    if modo == "cached":
        print("  [L8] llamada idéntica a una previa: se reutiliza el resultado")
        return valor, True
    return valor, None


def _registrar(nombre, firma, texto, ley):
    """Los contadores DESPUÉS de ejecutar: un error suma al veto; un éxito
    limpia el contador y deja el resultado para el caché."""
    if texto.startswith("ERROR"):
        ley["fallos"][nombre] = ley["fallos"].get(nombre, 0) + 1
        print(f"  ✗ paso erróneo ({ley['fallos'][nombre]}/{MAX_FALLOS_POR_HERRAMIENTA} de {nombre})")
        return
    ley["fallos"][nombre] = 0  # el éxito limpia el contador
    ley["exitosas"].append(nombre)
    registro = ley["previas"].setdefault(firma, {"n": 0, "resultado": None})
    registro["n"] += 1
    registro["resultado"] = texto
    print(f"  → {texto[:120]}")


def con_leyes(esquema, ley):
    """La Tool del kernel para una tool del catálogo, con las leyes alrededor:
    las guardas deciden ANTES de despachar y los contadores se actualizan
    DESPUÉS. Cada llamada (corrida, cacheada o vetada) queda en `ley["llamadas"]`
    para la auditoría. El lock hace atómicas la consulta y el registro."""
    nombre = esquema["function"]["name"]

    def correr(llamada, ctx):
        args = _args_de(llamada)
        firma = (nombre, clave_de(args))
        with ley["lock"]:
            texto, repetida = _decidir(nombre, firma, ley)
            ronda = MAX_PASOS - ctx.ledger.rondas
        corrio = texto is None
        if corrio:
            texto = _despachar(llamada, ctx)
        else:
            print(f"  [L8] {nombre}: {texto[:120]}")
        with ley["lock"]:
            if corrio:
                _registrar(nombre, firma, texto, ley)
            ley["llamadas"].append({"ronda": ronda, "herramienta": nombre, "args": args,
                                    "resultado": texto, "repetida": repetida})
        return texto

    efecto = "lectura" if nombre in LECTURA else "escritura"
    return Tool(nombre, esquema, correr, efecto, agente=nombre == explorador.NOMBRE_TOOL)


def semilla(tarea, salida, llm=None):
    """El shared del supervisor: el del kernel (contexto fresco, saldo del
    árbol) + las tools con sus leyes + lo que necesita la síntesis."""
    ley = {"fallos": {}, "exitosas": [], "previas": {}, "llamadas": [], "lock": threading.Lock()}
    ctx = Ctx(llm or (lambda m, t: call_llm_agent(m, tools=t)), Ledger(MAX_PASOS))
    tools = [con_leyes(t, ley) for t in _TODAS]
    s = semilla_agente(system_prompt(tarea), tarea, tools, ctx)
    s.update({"tarea": tarea, "salida": salida, "ley": ley})
    return s


class Auditar(Node):
    """De las llamadas registradas: los hechos de la sección "Pasos", los
    resultados para la síntesis y la telemetría de rondas secas (exp/96:
    la TANDA de una ronda contra la de la anterior, SIN corte)."""

    def prep(self, s):
        return [dict(c) for c in s["ley"]["llamadas"]]

    def exec(self, llamadas):
        hechos, resultados, tandas = [], [], {}
        for n, c in enumerate(llamadas, 1):
            hecho = hecho_de(n, c["herramienta"], c["args"], c["resultado"])
            hechos.append(hecho)
            resultados.append({"herramienta": c["herramienta"], "args": c["args"],
                               "resultado": c["resultado"][:4000], "n": n, "repetida": c["repetida"]})
            tandas.setdefault(c["ronda"], []).append(hecho)
        orden = ["\n".join(tandas[r]) for r in sorted(tandas)]
        secadas = [seco(a, b) for a, b in zip(orden, orden[1:], strict=False)]
        return hechos, resultados, secadas

    def post(self, s, _, auditoria):
        s["hechos"], s["resultados"], s["secadas"] = auditoria
        s["rondas"] = MAX_PASOS - s["ctx"].ledger.rondas
        for n, es_seca in enumerate(s["secadas"], 2):
            print(f"  [supervisor] ronda {n}: seca: {'sí' if es_seca else 'no'}")


class Sintetizar(Node):
    def prep(self, shared):
        return shared["tarea"], shared.get("resultados", []), shared.get("hechos", [])

    def exec(self, inputs):
        tarea, resultados, hechos = inputs
        material = "\n\n".join(
            f"### {r['herramienta']}({r['args']})\n{r['resultado']}" for r in resultados
        ) or "(sin pasos ejecutados)"
        return call_llm(
            f"Tarea original: {tarea}\n\nResultados de los pasos ejecutados:\n{material}\n\n"
            "Escribe en español el cierre: ¿se cumplió la tarea?, qué se encontró, "
            "qué pasos fallaron y qué quedaría pendiente. Máximo 15 líneas."
        )

    def post(self, shared, prep_res, exec_res):
        pasos = "\n".join(f"- {h}" for h in shared.get("hechos", [])) or "(ninguno)"
        destino, err = escribir_salida(
            shared["salida"],
            f"# Supervisor — {shared['tarea']}\n\n{exec_res}\n\n"
            f"## Pasos (la auditoría de la corrida)\n\n{pasos}\n",
        )
        if err:
            raise ValueError(f"ERROR: {err}")
        shared["informe"] = str(destino)
        print(f"\n✅ síntesis escrita: {shared['informe']}\n\n{exec_res}")


def create_supervisor_flow():
    """El loop del kernel es un Node más del flujo (agente = Flow = Node)."""
    agente = loop()
    auditar = Auditar()
    sintetizar = Sintetizar(max_retries=3, wait=5)
    agente >> auditar >> sintetizar
    return Flow(start=agente)


def supervisar(tarea, salida="salidas/supervisor.md"):
    shared = semilla(tarea, salida)
    create_supervisor_flow().run(shared)
    return shared["informe"]


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="supervisor", description="Supervisor v3: el loop del kernel con las leyes del ejecutor"
    )
    parser.add_argument("tarea")
    parser.add_argument("--salida", default="salidas/supervisor.md")
    args = parser.parse_args(argv)
    supervisar(args.tarea, args.salida)


if __name__ == "__main__":
    main()
