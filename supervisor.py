"""Supervisor v2: un paso = UNA llamada que elige herramienta Y args juntos.

El bench (2026-10-13, salidas/evals/bench_supervisor_2026-10-13.md) midió que
el supervisor reactivo gastaba 65 llamadas remotas / 358 s donde un agente
plano con tool-calling nativo resolvía LO MISMO (6/6 ambos) en 14 / 26 s. El
valor del supervisor nunca estuvo en el Choose (Laya + mayoría 2-de-3): está
en las LEYES de código — vetos, caché, presupuesto, fallo-como-feedback,
anti-recursión. Esta versión aplica ese veredicto: cada ronda es UNA llamada
a call_llm_agent(messages, tools) que elige la herramienta y redacta sus args
juntos, con las leyes intactas como guardas PURAS del ejecutor.

Flujo (Flow de la casa):

    UnPaso ──tool────▶ Ejecutar ──default──▶ UnPaso
    UnPaso ──answer──▶ Sintetizar
    UnPaso ──sintetizar──▶ Sintetizar

- **UnPaso**: arma messages + tools (retiradas al llegar a MAX_PASOS rondas:
  la ley del chat — el modelo debe cerrar), llama un paso y decide: con
  tool_calls → "tool"; sin ellas → "sintetizar" (el contenido es el cierre
  parcial que Sintetizar puede reusar). El historial viaja COMPLETO entre
  pasos (los resultados reales, no hechos recortados).
- **Ejecutar**: por cada tool_call corre las guardas de ley ANTES de
  despachar y luego fs_tools.run_tool_call (el único camino con hooks); el
  resultado —o el texto de la guarda— vuelve como mensaje role=tool (el canal
  fallo-como-feedback de siempre). Arma el hecho de auditoría para la
  sección "Pasos".
- **Sintetizar**: igual que siempre (informe + sección "Pasos").

Leyes (guards del §2, puras y testeables sin LLM): MAX_PASOS=5 (L8);
anti-recursión — run_supervisor no está en _TODAS (L1); MAX_FALLOS_POR_
HERRAMIENTA=2 veta una herramienta que falló dos veces; caché de llamadas
idénticas exitosas; sin-args ya exitosa o misma firma dos veces → veto.

El contrato del fine-tune supervisor_dispatch (PREGUNTA_DESPACHO y
elegir_con_deepseek) se mudó a sonda_supervisor.py: la sonda mide el
checkpoint jubilado como evidencia histórica.

Uso: python3 main.py supervisor "tarea" [--salida supervisor.md]
"""
import argparse
import json
from pathlib import Path

from pocketflow import Flow, Node

from modules import discover
from utils import fs_tools
from utils.call_llm import call_llm, call_llm_agent
from utils.fs_tools import TOOLS as BASE_TOOLS
from utils.fs_tools import escribir_salida

MAX_PASOS = 5
HECHO_LARGO = 160
MAX_FALLOS_POR_HERRAMIENTA = 2  # L8: dos errores y la herramienta se veta

MODULE_TOOLS, MODULE_IMPLS = discover()
# Ley anti-recursión (L1 de bmo): el supervisor no se despacha a sí mismo.
_MODULE_IMPLS = {k: v for k, v in MODULE_IMPLS.items() if k != "run_supervisor"}
_TODAS = [t for t in BASE_TOOLS + MODULE_TOOLS if t["function"]["name"] != "run_supervisor"]

REGISTRO = {
    "list_files": fs_tools.list_files,
    "read_file": fs_tools.read_file,
    "search_files": fs_tools.search_files,
    **_MODULE_IMPLS,
}

# Herramientas sin argumentos: repetirlas en una corrida es quemar presupuesto
# (patología medida: db_schema corrió 4 veces en una tarea real de 5 pasos).
SIN_ARGS = {t["function"]["name"] for t in _TODAS if not t["function"].get("parameters", {}).get("properties")}

TEXTO_VETO = (
    f"ERROR: herramienta vetada en esta corrida (falló {MAX_FALLOS_POR_HERRAMIENTA} veces) "
    "— elegí otra o cerrá"
)


# Leyes como guardas PURAS (§2): sin LLM, sin estado compartido, testeables.
# La semántica es la de siempre — los contadores se actualizan DESPUÉS de
# ejecutar (éxito limpia fallos, registro en previas/exitosas).

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
    """El catálogo en prosa: solo para el system prompt corto. Los schemas
    son la fuente de verdad de las tools; esto es la vista legible."""
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


def semilla(tarea, salida):
    """El `shared` semilla del supervisor. El historial (messages) viaja
    completo entre pasos — el modelo ve los resultados reales."""
    return {
        "tarea": tarea,
        "salida": salida,
        "messages": [
            {"role": "system", "content": system_prompt(tarea)},
            {"role": "user", "content": tarea},
        ],
        "rondas": 0,
        "fallos": {},
        "exitosas": [],
        "previas": {},
        "hechos": [],
        "resultados": [],
    }


def _historiar(msg):
    """El mensaje del asistente en forma canónica para el historial: solo
    role/content/tool_calls (el reasoning_content del modo thinking no
    viaja)."""
    m = {"role": "assistant", "content": getattr(msg, "content", None)}
    if getattr(msg, "tool_calls", None):
        m["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]
    return m


def _as_dict(tc):
    """La tool call como dict canónico del historial (lo que come
    run_tool_call). Acepta el objeto del SDK o un dict ya armado."""
    if isinstance(tc, dict):
        return tc
    return {
        "id": tc.id,
        "type": "function",
        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
    }


class UnPaso(Node):
    """La llamada del paso: el modelo elige herramienta Y args juntos. Con
    tool_calls → "tool"; sin ellas → "sintetizar" (el contenido es el cierre
    parcial que Sintetizar reusa). Al llegar a MAX_PASOS rondas se retiran
    las tools (la ley del chat: el modelo debe cerrar)."""

    def prep(self, shared):
        rondas = shared.get("rondas", 0)
        tools = None if rondas >= MAX_PASOS else _TODAS
        return shared["messages"], tools

    def exec(self, inputs):
        messages, tools = inputs
        return call_llm_agent(messages, tools=tools)

    def post(self, shared, prep_res, exec_res):
        shared["messages"].append(_historiar(exec_res))
        if getattr(exec_res, "tool_calls", None):
            shared["_paso_tool_calls"] = [_as_dict(tc) for tc in exec_res.tool_calls]
            return "tool"
        shared["_cierre_parcial"] = getattr(exec_res, "content", None)
        return "sintetizar"


def _args_de(tc):
    try:
        args = json.loads(tc["function"].get("arguments") or "{}")
    except (TypeError, ValueError):
        args = {}
    return args if isinstance(args, dict) else {}


class Ejecutar(Node):
    """Por cada tool_call: las guardas de ley ANTES de despachar (§2) y luego
    run_tool_call (el único camino con hooks). El resultado —o el texto de la
    guarda— vuelve como mensaje role=tool: el canal fallo-como-feedback. El
    hecho de auditoría se arma con hecho_de para la sección "Pasos".

    Contadores se actualizan DESPUÉS de ejecutar (éxito limpia fallos,
    registro en previas/exitosas) — la semántica de siempre."""

    def prep(self, shared):
        """Snapshot de la ronda: las tool_calls elegidas por UnPaso + una
        copia de los contadores de ley (exec() NO toca shared; post() sí)."""
        return {
            "tool_calls": shared.get("_paso_tool_calls") or [],
            "fallos": dict(shared.get("fallos", {})),
            "exitosas": list(shared.get("exitosas", [])),
            "previas": {k: dict(v) for k, v in shared.get("previas", {}).items()},
            "base": len(shared.get("hechos", [])),
        }

    def exec(self, snap):
        """Una entrada por tool_call: guarda vetada/repetida (pura) y, si
        pasa, run_tool_call. NO actualiza los contadores (eso es post, y así
        la ley se prueba pura)."""
        salidas = []
        # estado VIVO de la ronda: el snapshot de prep no ve lo que pasa
        # DENTRO de la tanda, y los modelos sí emiten llamadas duplicadas en
        # una misma ronda — el caché tiene que alcanzarlas.
        vivas = {k: dict(v) for k, v in snap["previas"].items()}
        exitosas_vivas = list(snap["exitosas"])
        for i, tc in enumerate(snap["tool_calls"]):
            nombre = tc["function"]["name"]
            args = _args_de(tc)
            firma = (nombre, clave_de(args))
            n = snap["base"] + i + 1
            texto = guarda_vetada(nombre, snap["fallos"])
            repetida = None
            if texto is None:
                veredicto = guarda_repetida(firma, vivas, exitosas_vivas, SIN_ARGS)
                if veredicto is not None:
                    modo, valor = veredicto
                    if modo == "cached":
                        print("  [L8] llamada idéntica a una previa: se reutiliza el resultado")
                        repetida, texto = True, valor
                    else:
                        texto = valor
            if texto is not None:
                print(f"  [L8] {nombre}: {texto}")
                ejecuto = False
            else:
                texto = fs_tools.run_tool_call(tc, REGISTRO)["content"]
                ejecuto = True
                if not texto.startswith("ERROR"):
                    vivas[firma] = {"n": vivas.get(firma, {}).get("n", 0) + 1,
                                    "resultado": texto}
                    if nombre not in exitosas_vivas:
                        exitosas_vivas.append(nombre)
            salidas.append({
                "tool_call": tc, "herramienta": nombre, "args": args,
                "firma": firma, "n": n, "resultado": texto,
                "repetida": repetida, "ejecuto": ejecuto,
            })
        return salidas

    def post(self, shared, prep_res, exec_res):
        fallos = shared.setdefault("fallos", {})
        exitosas = shared.setdefault("exitosas", [])
        previas = shared.setdefault("previas", {})
        hechos, resultados = [], []
        for r in exec_res:
            shared["messages"].append(
                {"role": "tool", "tool_call_id": r["tool_call"]["id"], "content": r["resultado"]}
            )
            hechos.append(hecho_de(r["n"], r["herramienta"], r["args"], r["resultado"]))
            resultados.append({"herramienta": r["herramienta"], "args": r["args"],
                               "resultado": r["resultado"][:4000], "n": r["n"], "repetida": r["repetida"]})
            if not r["ejecuto"]:
                continue
            # Contadores DESPUÉS de ejecutar.
            if r["resultado"].startswith("ERROR"):
                fallos[r["herramienta"]] = fallos.get(r["herramienta"], 0) + 1
                print(f"  ✗ paso erróneo ({fallos[r['herramienta']]}/"
                      f"{MAX_FALLOS_POR_HERRAMIENTA} de {r['herramienta']})")
            else:
                fallos[r["herramienta"]] = 0  # el éxito limpia el contador
                exitosas.append(r["herramienta"])
                registro = previas.setdefault(r["firma"], {"n": 0, "resultado": None})
                registro["n"] += 1  # el intento cuenta aunque haya sido cacheado
                if not r["repetida"]:
                    registro["resultado"] = r["resultado"]
                print(f"  → {r['resultado'][:120]}")
        shared.setdefault("hechos", []).extend(hechos)
        shared.setdefault("resultados", []).extend(resultados)
        shared["rondas"] = shared.get("rondas", 0) + 1
        shared.pop("_paso_tool_calls", None)
        return "default"


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
    un_paso = UnPaso(max_retries=3, wait=5)
    ejecutar = Ejecutar(max_retries=3, wait=5)
    sintetizar = Sintetizar(max_retries=3, wait=5)
    un_paso - "tool" >> ejecutar
    un_paso - "sintetizar" >> sintetizar
    ejecutar - "default" >> un_paso
    return Flow(start=un_paso)


def supervisar(tarea, salida="salidas/supervisor.md"):
    shared = semilla(tarea, salida)
    create_supervisor_flow().run(shared)
    return shared["informe"]


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="supervisor", description="Supervisor v2: un paso = una llamada que elige herramienta y args"
    )
    parser.add_argument("tarea")
    parser.add_argument("--salida", default="salidas/supervisor.md")
    args = parser.parse_args(argv)
    supervisar(args.tarea, args.salida)


if __name__ == "__main__":
    main()
