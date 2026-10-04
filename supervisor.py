"""Supervisor: descompone una tarea y la despacha como sub-agentes.

Planificar (YAML + assert) → EjecutarPasos (BatchNode; cada paso corre una
pieza con su PROPIO shared — el aislamiento que el grafo no da, lo da el
que cada pieza construya su estado) → Sintetizar (informe final).
El registro de piezas es EL MISMO action space del chat (MODULE_IMPLS +
herramientas base): el supervisor es el bucle de tools del chat, pero
planificado de una vez en vez de decido paso a paso.

Leyes: MAX_PASOS=5 (L8). Los errores de un paso son datos para la
síntesis, no crash del lote.

Uso: python3 main.py supervisor "tarea" [--salida supervisor.md]
"""
import argparse
from pathlib import Path

from pocketflow import BatchNode, Flow, Node

from modules import discover
from utils import fs_tools
from utils.call_llm import call_llm
from utils.estructura import extraer_yaml
from utils.fs_tools import TOOLS as BASE_TOOLS

MAX_PASOS = 5

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


def catalogo():
    lineas = []
    for t in _TODAS:
        f = t["function"]
        args = f.get("parameters", {}).get("properties", {})
        firma = ", ".join(f"{n}{'?' if n not in f.get('parameters', {}).get('required', []) else ''}" for n in args)
        lineas.append(f"- {f['name']}({firma}): {f['description']}")
    return "\n".join(lineas)


class Planificar(Node):
    def prep(self, shared):
        return shared["tarea"]

    def exec(self, tarea):
        prompt = f"""Tarea del usuario: {tarea}

Herramientas disponibles (nombre: descripción):
{catalogo()}

Descompón la tarea en hasta {MAX_PASOS} pasos. Cada paso usa UNA
herramienta con sus argumentos. Solo planifica pasos que la herramienta
pueda hacer con argumentos estáticos (si un paso depende del resultado
de otro, deja que la síntesis final lo razone en vez de planificarlo).

Responde SOLO yaml:
```yaml
pasos:
  - herramienta: nombre
    args:
      parametro: valor
    proposito: una línea
```"""
        plan = extraer_yaml(call_llm(prompt))
        pasos = plan["pasos"]
        assert isinstance(pasos, list) and pasos, "plan vacío"
        assert len(pasos) <= MAX_PASOS, f"máximo {MAX_PASOS} pasos"
        for p in pasos:
            assert p["herramienta"] in REGISTRO, f"herramienta desconocida: {p['herramienta']}"
            assert isinstance(p.get("args", {}), dict), "args debe ser dict"
        return pasos

    def post(self, shared, prep_res, exec_res):
        shared["plan"] = exec_res
        print(f"\n📋 plan ({len(exec_res)} pasos):")
        for i, p in enumerate(exec_res, 1):
            print(f"  {i}. {p['herramienta']} — {p.get('proposito', '')}")


class EjecutarPasos(BatchNode):
    def prep(self, shared):
        return shared["plan"]

    def exec(self, paso):
        fn = REGISTRO[paso["herramienta"]]
        print(f"\n▶ paso {paso['herramienta']}({paso.get('args', {})})")
        try:
            resultado = str(fn(**paso.get("args", {})))
        except Exception as e:
            resultado = f"ERROR ({type(e).__name__}): {e}"
        return {
            "herramienta": paso["herramienta"],
            "proposito": paso.get("proposito", ""),
            "resultado": resultado[:4000],
        }

    def post(self, shared, prep_res, exec_res_list):
        shared["resultados"] = exec_res_list


class Sintetizar(Node):
    def prep(self, shared):
        return shared["tarea"], shared.get("resultados", [])

    def exec(self, inputs):
        tarea, resultados = inputs
        material = "\n\n".join(
            f"### {r['herramienta']} — {r['proposito']}\n{r['resultado']}" for r in resultados
        ) or "(sin pasos ejecutados)"
        return call_llm(
            f"Tarea original: {tarea}\n\nResultados de los pasos ejecutados:\n{material}\n\n"
            "Escribe en español el cierre: ¿se cumplió la tarea?, qué se encontró, "
            "qué pasos fallaron y qué quedaría pendiente. Máximo 15 líneas."
        )

    def post(self, shared, prep_res, exec_res):
        salida = Path(shared["salida"])
        salida.write_text(f"# Supervisor — {shared['tarea']}\n\n{exec_res}\n", encoding="utf-8")
        shared["informe"] = str(salida.resolve())
        print(f"\n✅ síntesis escrita: {shared['informe']}\n\n{exec_res}")


def create_supervisor_flow():
    planificar = Planificar(max_retries=3, wait=5)
    ejecutar = EjecutarPasos(max_retries=3, wait=5)
    sintetizar = Sintetizar(max_retries=3, wait=5)
    planificar >> ejecutar >> sintetizar
    return Flow(start=planificar)


def supervisar(tarea, salida="supervisor.md"):
    shared = {"tarea": tarea, "salida": salida}
    create_supervisor_flow().run(shared)
    return shared["informe"]


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="supervisor", description="Descompone una tarea y la ejecuta con sub-agentes"
    )
    parser.add_argument("tarea")
    parser.add_argument("--salida", default="supervisor.md")
    args = parser.parse_args(argv)
    supervisar(args.tarea, args.salida)


if __name__ == "__main__":
    main()
