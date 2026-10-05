"""Supervisor: bucle reactivo — Laya elige la siguiente herramienta, el
código ejecuta y observa, y la elección siguiente ve lo ya hecho.

ElegirSiguiente (Laya local con la task supervisor_dispatch; uncertain o
sin laya → DeepSeek con el catálogo) → EjecutarPaso (args por DeepSeek
para la herramienta elegida + ejecución + hecho registrado) → repetir
hasta `finish` o MAX_PASOS → Sintetizar (informe final).

Antes era una tanda: un plan completo de una vez y los pasos dependientes
quedaban fuera ("que la síntesis lo razone"). Ahora el paso N+1 decide
con el resultado del paso N — el Choose de bmo, con el if en local.

Leyes: MAX_PASOS=5 (L8); anti-recursión — run_supervisor no está entre
las opciones ni en el catálogo del fallback (L1). Los errores de un paso
son datos (hechos) para la siguiente elección y la síntesis, no crash.

El contrato con el fine-tune: PREGUNTA_DESPACHO y el estado
{"tarea", "hechos"} replican la task supervisor_dispatch de bmo byte a
byte (tests/test_smoke.py lo vigila). Si el action space cambia, la
lista aquí congelada NO cambia sola: las tools nuevas llegan por el
fallback de DeepSeek, nunca por Laya.

Uso: python3 main.py supervisor "tarea" [--salida supervisor.md]
"""
import argparse
import json
from pathlib import Path

from pocketflow import Flow, Node

from modules import discover
from utils import fs_tools
from utils.call_llm import call_llm
from utils.estructura import extraer_yaml
from utils.fs_tools import TOOLS as BASE_TOOLS

MAX_PASOS = 5
HECHOS_MAX_LINEAS = 15
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


def vetadas(fallos):
    """Las herramientas con dos errores: ni Laya ni DeepSeek pueden volver a
    elegirlas en esta corrida (ley L8 — el reintento tiene presupuesto)."""
    return {h for h, n in fallos.items() if n >= MAX_FALLOS_POR_HERRAMIENTA}


# Herramientas sin argumentos: repetirlas en una corrida es quemar presupuesto
# (patología medida: db_schema corrió 4 veces en una tarea real de 5 pasos).
SIN_ARGS = {t["function"]["name"] for t in _TODAS if not t["function"].get("parameters", {}).get("properties")}


def repetidas(exitosas):
    """Las herramientas sin-args que ya corrieron bien: idéntica repetición."""
    return {h for h in exitosas if h in SIN_ARGS}

# Congelada: task supervisor_dispatch (bmo/train/tasks/supervisor_dispatch.yaml).
# Las 18 opciones en este orden exacto; entrenamiento y producción leen igual.
PREGUNTA_DESPACHO = {
    "elegir_proxima": {
        "type": "choice",
        "instructions": "Which tool runs the next step of this task, given what already ran?",
        "criteria": {
            "list_files": "see which files a folder holds",
            "read_file": "read the exact content of one file",
            "search_files": "find files by name or contained text",
            "write_file": "create or replace a file (needs approval)",
            "run_informe": "summarize one folder of traces",
            "run_auditoria": "compare several folders of traces",
            "answer_verified": "answer with citations checked against files",
            "rag_search": "semantic search over the local index",
            "rag_index": "(re)index a folder for semantic search",
            "debate": "run a proponent-vs-critic debate",
            "mcp_tools": "list the tools of external MCP servers",
            "mcp_call": "call a tool on an external MCP server",
            "search_web": "quick web search: titles, URLs, snippets",
            "deep_research": "multi-round web research with a report",
            "sql": "one SELECT query over the traces db",
            "db_schema": "schema of the traces database",
            "run_effective_n": "exact dedup of trace datasets",
            "finish": "done or blocked: synthesize now",
        },
    }
}
OPCIONES = list(PREGUNTA_DESPACHO["elegir_proxima"]["criteria"])


def catalogo():
    lineas = []
    for t in _TODAS:
        f = t["function"]
        args = f.get("parameters", {}).get("properties", {})
        firma = ", ".join(f"{n}{'?' if n not in f.get('parameters', {}).get('required', []) else ''}" for n in args)
        lineas.append(f"- {f['name']}({firma}): {f['description']}")
    return "\n".join(lineas)


def esquema_de(nombre):
    for t in _TODAS:
        if t["function"]["name"] == nombre:
            return json.dumps(t["function"].get("parameters", {}), ensure_ascii=False)
    return "{}"


def hecho_de(n, herramienta, args, resultado):
    breve = ", ".join(f"{k}={str(v)[:40]}" for k, v in (args or {}).items())
    una_linea = " ".join(str(resultado).split())
    return f"{n} {herramienta}({breve}) -> {una_linea[:HECHO_LARGO]}"


class ElegirSiguiente(Node):
    """El Choose: Laya decide local (ms, costo 0); la compuerta manda —
    solo 'met' despacha con la elección de Laya, cualquier duda cae al
    lado seguro (DeepSeek con el catálogo completo). El umbral del
    supervisor es MÁS exigente que el del router (0.9 vs 0.7): el costo
    de un despacho erróneo (un paso quemado de MAX_PASOS) pesa más que
    lo que ahorra (una mini-llamada de elección)."""

    def prep(self, shared):
        return shared["tarea"], shared.get("hechos", []), shared.get("fallos", {}), shared.get("exitosas", [])

    def exec(self, inputs):
        tarea, hechos, fallos, exitosas = inputs
        fuera = vetadas(fallos) | repetidas(exitosas)
        eleccion, origen = None, None
        from utils.call_llm import _setting
        from utils.laya import disponible, preguntar, veredicto

        alto = _setting("LAYA_UNSURE_HIGH_SUPERVISOR", "0.9")
        if disponible("LAYA_MODEL_SUPERVISOR"):
            estado = {"tarea": tarea, "hechos": "\n".join(hechos[-HECHOS_MAX_LINEAS:])}
            resp, conf = preguntar(estado, PREGUNTA_DESPACHO, setting="LAYA_MODEL_SUPERVISOR")["elegir_proxima"]
            if resp in REGISTRO or resp == "finish":
                if resp in fuera:
                    print(f"  [laya] {resp} está vetada (dos fallos) → elige DeepSeek")
                elif veredicto(conf, alto=alto) == "met":
                    eleccion, origen = resp, f"laya (conf {conf:.2f})"
                else:
                    print(f"  [laya] {resp} conf {conf:.2f} < {alto} → duda: elige DeepSeek")
            else:
                print(f"  [laya] opción fuera de contrato: {resp!r} → elige DeepSeek")
        else:
            print("  [laya] no disponible → elige DeepSeek")
        if eleccion is None:
            veto_txt = (
                f"\nPROHIBIDO elegir (ya fallaron {MAX_FALLOS_POR_HERRAMIENTA} veces): "
                + ", ".join(sorted(fuera)) + ".\n" if fuera else ""
            )
            plan = extraer_yaml(call_llm(
                f"Tarea del usuario: {tarea}\n\n"
                f"Ya ejecutado:\n" + ("\n".join(hechos) or "(nada)") + "\n\n"
                f"Herramientas disponibles (nombre: descripción):\n{catalogo()}\n"
                f"{veto_txt}"
                f"finish: la tarea está cubierta o bloqueada; sintetizar ya.\n\n"
                "Elige UNA herramienta para el siguiente paso (o finish). "
                "El siguiente paso sigue de lo que FALTA, no de lo ya hecho.\n\n"
                "Responde SOLO yaml:\n```yaml\nherramienta: nombre\n```"
            ))
            eleccion = plan["herramienta"]
            if eleccion in fuera:  # desobedeció el veto: cerrar, no chocar otra vez
                print(f"  [L8] {eleccion} vetada y elegida igual → finish")
                eleccion = "finish"
            assert eleccion in REGISTRO or eleccion == "finish", f"herramienta desconocida: {eleccion}"
            origen = "deepseek"
        return eleccion, origen

    def post(self, shared, prep_res, exec_res):
        eleccion, origen = exec_res
        shared["eleccion"] = eleccion
        print(f"\n▶ [{origen}] {eleccion}")
        return "sintetizar" if eleccion == "finish" else "ejecutar"


class EjecutarPaso(Node):
    """Args por DeepSeek (Laya elige, no redacta) + ejecución + el hecho
    que verá la elección siguiente. El error de un paso es un hecho más;
    reintentar una herramienta que falló recibe el error como feedback
    explícito, y a los {MAX_FALLOS_POR_HERRAMIENTA} fallos se veta."""

    def prep(self, shared):
        return (
            shared["tarea"],
            shared.get("hechos", []),
            shared["eleccion"],
            len(shared.get("hechos", [])) + 1,
            shared.get("fallos", {}).get(shared["eleccion"], 0),
        )

    def exec(self, inputs):
        tarea, hechos, herramienta, n, fallos_previos = inputs
        feedback = ""
        if fallos_previos:
            previos = [h for h in hechos if f" {herramienta}(" in h and "ERROR" in h][-1:]
            feedback = (
                f"\nATENCIÓN: esta herramienta ya falló ({fallos_previos} vez/veces). "
                f"Último intento y su error: {previos[0] if previos else '(ver hechos)'}. "
                "Corrige los argumentos — no repitas el mismo error. Los nombres válidos "
                "(columnas, rutas, parámetros) ya aparecen en los pasos ejecutados de arriba: "
                "cópialos EXACTOS de ahí, no los inventes.\n"
            )
        plan = extraer_yaml(call_llm(
            f"Tarea del usuario: {tarea}\n\n"
            f"Ya ejecutado:\n" + ("\n".join(hechos) or "(nada)") + "\n\n"
            f"Herramienta decidida: {herramienta}\nEsquema de args: {esquema_de(herramienta)}\n"
            f"{feedback}\n"
            "Genera SOLO los argumentos para esa herramienta en este paso "
            "(args vacíos si no necesita): \n"
            "Responde SOLO yaml:\n```yaml\nargs:\n  parametro: valor\n```"
        ))
        args = plan.get("args", {}) or {}
        assert isinstance(args, dict), "args debe ser dict"
        try:
            resultado = str(REGISTRO[herramienta](**args))
        except Exception as e:  # noqa: BLE001  (el error es un hecho, no un crash)
            resultado = f"ERROR ({type(e).__name__}): {e}"
        return {"herramienta": herramienta, "args": args, "resultado": resultado[:4000], "n": n}

    def post(self, shared, prep_res, exec_res):
        shared.setdefault("hechos", []).append(
            hecho_de(exec_res["n"], exec_res["herramienta"], exec_res["args"], exec_res["resultado"])
        )
        shared.setdefault("resultados", []).append(exec_res)
        fallos = shared.setdefault("fallos", {})
        if exec_res["resultado"].startswith("ERROR"):
            fallos[exec_res["herramienta"]] = fallos.get(exec_res["herramienta"], 0) + 1
            print(f"  ✗ paso erróneo ({fallos[exec_res['herramienta']]}/{MAX_FALLOS_POR_HERRAMIENTA} de "
                  f"{exec_res['herramienta']})")
        else:
            fallos[exec_res["herramienta"]] = 0  # el éxito limpia el contador
            shared.setdefault("exitosas", []).append(exec_res["herramienta"])
            print(f"  → {exec_res['resultado'][:120]}")
        if len(shared["hechos"]) >= MAX_PASOS:
            print(f"  [L8] tope de {MAX_PASOS} pasos → síntesis")
            return "sintetizar"
        return "elegir"


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
        salida = Path(shared["salida"])
        pasos = "\n".join(f"- {h}" for h in shared.get("hechos", [])) or "(ninguno)"
        salida.write_text(
            f"# Supervisor — {shared['tarea']}\n\n{exec_res}\n\n"
            f"## Pasos (la auditoría de la corrida)\n\n{pasos}\n",
            encoding="utf-8",
        )
        shared["informe"] = str(salida.resolve())
        print(f"\n✅ síntesis escrita: {shared['informe']}\n\n{exec_res}")


def create_supervisor_flow():
    elegir = ElegirSiguiente(max_retries=3, wait=5)
    ejecutar = EjecutarPaso(max_retries=3, wait=5)
    sintetizar = Sintetizar(max_retries=3, wait=5)
    elegir - "ejecutar" >> ejecutar
    elegir - "sintetizar" >> sintetizar
    ejecutar - "elegir" >> elegir
    ejecutar - "sintetizar" >> sintetizar
    return Flow(start=elegir)


def supervisar(tarea, salida="supervisor.md"):
    shared = {"tarea": tarea, "salida": salida}
    create_supervisor_flow().run(shared)
    return shared["informe"]


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="supervisor", description="Bucle reactivo: Laya elige la herramienta de cada paso"
    )
    parser.add_argument("tarea")
    parser.add_argument("--salida", default="supervisor.md")
    args = parser.parse_args(argv)
    supervisar(args.tarea, args.salida)


if __name__ == "__main__":
    main()
