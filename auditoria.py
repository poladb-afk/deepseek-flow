"""Auditoría multi-carpeta — BatchFlow + flujo anidado (Flow como Node).

Por cada carpeta corre el MISMO flujo interno: CarpetaScan → AnalizeFile
(el mapa paralelo de informe.py, REUTILIZADO) → Seccion. El BatchFlow
aporta params["carpeta"] — params vs shared: el identificador de la tarea
viaja en params, los datos en shared. Al terminar todas las carpetas, el
BatchFlow se enchufa como nodo en un Flow exterior con un reduce global
después: composición literal de Flows.

Nota: las iteraciones del BatchFlow son secuenciales a propósito — todas
comparten el mismo `shared` (shared["files"], shared["analisis"] se
sobrescriben por carpeta). La versión paralela (AsyncParallelBatchFlow)
exigiría un shared por iteración.

Uso:
    python3 main.py auditoria carpeta1 carpeta2 [--glob '*.jsonl'] [--salida auditoria.md]
"""
import argparse
import asyncio
from datetime import date
from pathlib import Path

from pocketflow import AsyncBatchFlow, AsyncFlow, Node

from informe import AnalizeFile, collect_files, tabla_markdown
from utils.call_llm import call_llm
from utils.fs_tools import _resolve


class CarpetaScan(Node):
    def prep(self, shared):
        return self.params["carpeta"], shared.get("glob", "*.jsonl")

    def exec(self, inputs):
        return collect_files(*inputs)

    def post(self, shared, prep_res, exec_res):
        shared["files"] = exec_res
        print(f"[{prep_res[0]}] {len(exec_res)} archivos")


class Seccion(Node):
    def prep(self, shared):
        return self.params["carpeta"], shared.get("analisis", [])

    def exec(self, inputs):
        carpeta, analisis = inputs
        if not analisis:
            return f"## {carpeta}\n\n(sin archivos para el patrón)"
        resumenes = "\n\n".join(f"#### {a['file'].name}\n\n{a['resumen']}" for a in analisis)
        sintesis = call_llm(
            f"Análisis de los archivos de la carpeta {carpeta}:\n{resumenes}\n\n"
            "Escribe en español, máximo 4 líneas sin título: qué caracteriza a esta carpeta."
        )
        return (
            f"## {carpeta}\n\n{sintesis}\n\n"
            "| Archivo | Registros | Líneas rotas | Decisiones por módulo |\n|---|---|---|---|\n"
            f"{tabla_markdown(analisis)}\n\n### Lecturas\n\n{resumenes}"
        )

    def post(self, shared, prep_res, exec_res):
        shared.setdefault("secciones", {})[prep_res[0]] = exec_res


def inner_flow():
    scan = CarpetaScan()
    mapa = AnalizeFile(max_retries=3, wait=5)  # reutilizado de informe.py
    seccion = Seccion(max_retries=3, wait=5)
    scan >> mapa >> seccion
    return AsyncFlow(start=scan)  # async porque AnalizeFile lo es


class AuditorCarpetas(AsyncBatchFlow):
    async def prep_async(self, shared):
        return [{"carpeta": c} for c in shared["carpetas"]]


class ReduceGlobal(Node):
    def prep(self, shared):
        return shared.get("secciones", {})

    def exec(self, secciones):
        if not secciones:
            return "# Auditoría de carpetas\n\nNo se encontraron carpetas válidas.\n"
        cuerpo = "\n\n".join(secciones[c] for c in sorted(secciones))
        resumen_secciones = "\n".join(f"## {c}\n{s[:400]}" for c, s in sorted(secciones.items()))
        sintesis = call_llm(
            f"Auditoría de {len(secciones)} carpetas:\n{resumen_secciones}\n\n"
            "Escribe en español la sección final de un informe (sin título, máx 8 líneas): "
            "diferencias entre carpetas y hasta 3 recomendaciones."
        )
        return (
            f"# Auditoría de carpetas — {date.today().isoformat()}\n\n"
            f"{len(secciones)} carpetas\n\n{cuerpo}\n\n## Síntesis global\n\n{sintesis}\n"
        )

    def post(self, shared, prep_res, exec_res):
        salida = Path(shared["salida"])
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_text(exec_res, encoding="utf-8")
        shared["auditoria"] = str(salida.resolve())
        print(f"Auditoría escrita: {salida.resolve()}")


def create_auditoria_flow():
    audit = AuditorCarpetas(start=inner_flow())
    reduce_ = ReduceGlobal(max_retries=3, wait=5)
    audit >> reduce_  # el BatchFlow como nodo dentro de un Flow exterior
    return AsyncFlow(start=audit)


def auditar(carpetas, glob="*.jsonl", salida="auditoria.md"):
    validas = []
    for c in carpetas:
        folder, err = _resolve(c)
        if err or not folder.is_dir():
            raise ValueError(f"carpeta inválida: {c} ({err or 'no es un directorio'})")
        validas.append(str(folder))
    shared = {"carpetas": validas, "glob": glob, "salida": salida}
    asyncio.run(create_auditoria_flow().run_async(shared))
    return shared["auditoria"]


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="auditoria",
        description="Auditoría multi-carpeta: BatchFlow + flujo anidado (patrón Map-Reduce compuesto)",
    )
    parser.add_argument("carpetas", nargs="+", help="carpetas a auditar")
    parser.add_argument("--glob", default="*.jsonl", help="patrón de archivos (default: %(default)s)")
    parser.add_argument("--salida", default="salidas/auditoria.md", help="archivo de salida (default: %(default)s)")
    args = parser.parse_args(argv)
    auditar(args.carpetas, args.glob, args.salida)


if __name__ == "__main__":
    main()
