"""Informe map-reduce sobre trazas de decisiones (.jsonl).

Patrón Map-Reduce del cookbook de PocketFlow:
- ScanFiles reúne los archivos de la carpeta (contención a raíces permitidas).
- AnalizeFile (BatchNode) es el mapa: por archivo, estadísticas exactas en
  código + interpretación breve de DeepSeek.
- WriteReport es el reduce: tabla exacta en código, síntesis en DeepSeek,
  y escribe el markdown final.

Principio heredado de bmo: los datos exactos los cuenta el código; el LLM
solo interpreta.

Uso:
    python3 main.py informe [carpeta] [--glob '*.jsonl'] [--salida informe.md]
"""
import argparse
import asyncio
import fnmatch
import json
import os
from collections import Counter
from datetime import date
from pathlib import Path

from pocketflow import AsyncFlow, AsyncParallelBatchNode, Node

from utils.call_llm import _entero, _setting, call_llm, call_llm_async
from utils.fs_tools import SKIP_DIRS, _resolve

MAX_FILES = 30
SAMPLE_TASKS = 2
TASK_CHARS = 300
DEFAULT_FOLDER = _setting("INFORME_CARPETA", ".")  # portable; local: INFORME_CARPETA en .env
# Semáforo anti-429: acota cuántas llamadas a DeepSeek se solapan en el mapa
MAPA_CONCURRENCIA = _entero("MAPA_CONCURRENCIA", 8)
_SEMAFORO = asyncio.Semaphore(MAPA_CONCURRENCIA)


def collect_files(folder, pattern):
    files = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fnmatch.fnmatch(fname, pattern):
                files.append(Path(dirpath) / fname)
    return sorted(files)[:MAX_FILES]


def stats_de(filepath):
    """Hechos exactos: cuenta registros y decisiones por módulo."""
    total, errores = 0, 0
    modulos, ejemplos = Counter(), []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                errores += 1
                continue
            nxt = rec.get("answers", {}).get("next")
            if nxt:
                modulos[nxt] += 1
            if len(ejemplos) < SAMPLE_TASKS:
                task = rec.get("fields", {}).get("task")
                if task:
                    ejemplos.append(str(task)[:TASK_CHARS])
    return {"total": total, "errores": errores, "modulos": dict(modulos), "ejemplos": ejemplos}


def tabla_markdown(analisis):
    """Filas de tabla (exactas, en código) a partir del análisis por archivo."""
    filas = []
    for a in analisis:
        dist = ", ".join(f"{m}: {n}" for m, n in sorted(a["modulos"].items(), key=lambda x: -x[1]))
        filas.append(f"| `{a['file']}` | {a['total']} | {a['errores']} | {dist or '—'} |")
    return "\n".join(filas)


async def interpretar(filepath, stats):
    ejemplos = "\n".join(f"- {e}" for e in stats["ejemplos"]) or "(sin ejemplos)"
    dist = ", ".join(f"{m}: {n}" for m, n in sorted(stats["modulos"].items(), key=lambda x: -x[1])) or "(sin decisiones)"
    prompt = f"""Archivo de trazas de decisiones: {filepath}
Registros: {stats['total']} (líneas con JSON roto: {stats['errores']})
Decisiones por módulo: {dist}
Tareas de ejemplo:
{ejemplos}

Escribe en español, máximo 5 líneas, sin título markdown: qué contiene este
archivo y algo notable (distribución, sesgo, anomalía, calidad de las tareas)."""
    return await call_llm_async(prompt)


class ScanFiles(Node):
    def prep(self, shared):
        return shared["folder"], shared["glob"]

    def exec(self, inputs):
        folder, pattern = inputs
        return collect_files(folder, pattern)

    def post(self, shared, prep_res, exec_res):
        shared["files"] = exec_res
        print(f"Encontrados {len(exec_res)} archivos ({prep_res[1]} en {prep_res[0]})")


class AnalizeFile(AsyncParallelBatchNode):
    # Contrato de shared["analisis"] (auditoría de consistencia 2026-10-05):
    # acá es una LISTA de esquemas del LLM [{"file", "total", ..., "resumen"}].
    # effective_n.py reusa la MISMA clave con otra forma (huellas de contenido).
    # Colisión semántica consciente y sancionada: el vocabulario de shared NO
    # se unifica (los flujos comparten la clave pero nunca se ejecutan juntos).
    async def prep_async(self, shared):
        return shared["files"]

    async def exec_async(self, filepath):
        async with _SEMAFORO:
            stats = stats_de(filepath)
            print(f"  ✓ {filepath.name}: {stats['total']} registros")
            return {"file": filepath, **stats, "resumen": await interpretar(filepath, stats)}

    async def post_async(self, shared, prep_res, exec_res_list):
        shared["analisis"] = exec_res_list


class WriteReport(Node):
    def prep(self, shared):
        return shared["folder"], shared.get("analisis", [])

    def exec(self, inputs):
        folder, analisis = inputs
        if not analisis:
            return f"# Informe de trazas\n\nNo se encontraron archivos en `{folder}`.\n"

        tabla = tabla_markdown(analisis)
        resumenes = "\n\n".join(f"### {a['file']}\n\n{a['resumen']}" for a in analisis)
        total_reg = sum(a["total"] for a in analisis)
        globales = Counter()
        for a in analisis:
            globales.update(a["modulos"])
        glob_txt = ", ".join(f"{m}: {n}" for m, n in globales.most_common())

        sintesis = call_llm(f"""Estos son los resultados de analizar {len(analisis)} archivos de trazas
({total_reg} registros en total; decisiones globales: {glob_txt}).

Tabla por archivo (archivo | registros | líneas rotas | decisiones por módulo):
{tabla}

Resúmenes por archivo:
{resumenes}

Escribe en español la sección final de un informe (sin título): patrones
globales, diferencias entre archivos o rounds, y hasta 3 recomendaciones.
Máximo 12 líneas.""")

        return f"""# Informe de trazas — {date.today().isoformat()}

Carpeta: `{folder}` · {len(analisis)} archivos · {total_reg} registros

## Tabla por archivo

| Archivo | Registros | Líneas rotas | Decisiones por módulo |
|---|---|---|---|
{tabla}

## Lectura por archivo

{resumenes}

## Síntesis

{sintesis}
"""

    def post(self, shared, prep_res, exec_res):
        path = Path(shared["salida"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(exec_res, encoding="utf-8")
        shared["informe"] = str(path.resolve())
        print(f"Informe escrito: {path.resolve()}")


def create_informe_flow():
    # ScanFiles y WriteReport quedan síncronos: AsyncFlow ejecuta los Node
    # normales tal cual y solo espera a los AsyncNode.
    scan = ScanFiles()
    mapa = AnalizeFile(max_retries=3, wait=5)
    reduce_ = WriteReport(max_retries=3, wait=5)
    scan >> mapa >> reduce_
    return AsyncFlow(start=scan)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="informe",
        description="Informe map-reduce de trazas .jsonl (patrón Map-Reduce de PocketFlow)",
    )
    parser.add_argument("carpeta", nargs="?", default=DEFAULT_FOLDER, help=f"carpeta a analizar (default: {DEFAULT_FOLDER})")
    parser.add_argument("--glob", default="*.jsonl", help="patrón de archivos (default: %(default)s)")
    parser.add_argument("--salida", default="salidas/informe.md", help="archivo de salida (default: %(default)s)")
    args = parser.parse_args(argv)

    folder, err = _resolve(args.carpeta)
    if err:
        raise SystemExit(f"ERROR: {err}")
    if not folder.is_dir():
        raise SystemExit(f"ERROR: no es una carpeta: {folder}")

    shared = {"folder": str(folder), "glob": args.glob, "salida": args.salida}
    asyncio.run(create_informe_flow().run_async(shared))


if __name__ == "__main__":
    main()
