"""Effective N de un dataset de trazas .jsonl: deduplicación exacta, en código.

El informe map-reduce (informe.py) cuenta registros por archivo; aquí se
responde la pregunta previa al re-entrenamiento: cuántos de esos registros
son **distintos de verdad**. La huella de contenido es sha1 del par
(fields, answers.next) canónicamente serializado — ignora id/created/model,
que cambian entre volcados del mismo caso.

Pieza 100% código (como carga_trazas.py): determinista, verificable, sin
LLM. Map-Reduce de PocketFlow solo como forma: HashFile es el mapa y el
reduce cruza pares y escribe el markdown.

Uso:
    python3 main.py effective_n [carpeta] [--glob '*.jsonl'] [--salida effective_n.md]
"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

from pocketflow import BatchNode, Flow, Node

from informe import DEFAULT_FOLDER, collect_files
from utils.fs_tools import _resolve

MAX_EJEMPLOS = 5  # contradicciones mostradas en el informe

# Campos de `fields` que forman el contenido de una decisión Choose
CAMPOS = ("task", "observation", "criteria", "steps")


def huella(rec, con_next=True):
    """sha1 del contenido: fields (CAMPOS) [+ answers.next]. El orden de
    `steps` conserva el del estado — es parte del contenido."""
    obj = [rec.get("fields", {}).get(c) for c in CAMPOS]
    if con_next:
        obj.append(rec.get("answers", {}).get("next"))
    return hashlib.sha1(json.dumps(obj, ensure_ascii=False).encode()).hexdigest()


def md5_de(path):
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            digest.update(bloque)
    return digest.hexdigest()


class ScanFiles(Node):
    def prep(self, shared):
        return shared["folder"], shared["glob"]

    def exec(self, inputs):
        return collect_files(*inputs)

    def post(self, shared, prep_res, exec_res):
        shared["files"] = exec_res
        print(f"Encontrados {len(exec_res)} archivos ({prep_res[1]} en {prep_res[0]})")


class HashFile(BatchNode):
    """Mapa: por archivo, las huellas de sus registros (CPU puro, secuencial)."""

    def prep(self, shared):
        return shared["files"]

    def exec(self, filepath):
        n, rotos, con_steps, con_obs = 0, 0, 0, 0
        huellas, etiquetas, dist = [], {}, Counter()
        with open(filepath, encoding="utf-8") as f:
            for linea in f:
                if not linea.strip():
                    continue
                n += 1
                try:
                    rec = json.loads(linea)
                except json.JSONDecodeError:
                    rotos += 1
                    continue
                campos = rec.get("fields", {})
                if campos.get("steps"):
                    con_steps += 1
                if campos.get("observation"):
                    con_obs += 1
                nxt = rec.get("answers", {}).get("next")
                if nxt:
                    dist[nxt] += 1
                huellas.append(huella(rec))
                # misma huella sin next → etiquetas que recibió (contradicciones)
                etiquetas.setdefault(huella(rec, con_next=False), set()).add(nxt)
        return {
            "file": filepath,
            "n": n,
            "rotos": rotos,
            "con_steps": con_steps,
            "con_obs": con_obs,
            "huellas": huellas,
            "etiquetas": etiquetas,
            "dist": dict(dist),
            "md5": md5_de(filepath),
        }

    def post(self, shared, prep_res, exec_res_list):
        shared["analisis"] = exec_res_list
        for a in exec_res_list:
            print(f"  ✓ {a['file'].name}: {a['n']} registros, {len(set(a['huellas']))} únicos")


class WriteReport(Node):
    """Reduce: cruces por pares, Effective N del conjunto, contradicciones."""

    def prep(self, shared):
        return shared["folder"], shared.get("analisis", [])

    def exec(self, inputs):
        folder, analisis = inputs
        if not analisis:
            return {
                "markdown": f"# Effective N\n\nNo se encontraron archivos en `{folder}`.\n",
                "total": 0,
                "efectivo": 0,
            }

        # identificador: ruta relativa a la carpeta (los rounds repiten nombre)
        def rel(a):
            try:
                return str(a["file"].relative_to(folder))
            except ValueError:
                return a["file"].name

        # archivos duplicados enteros (mismo md5)
        por_md5 = {}
        for a in analisis:
            por_md5.setdefault(a["md5"], []).append(rel(a))
        dup_archivos = [v for v in por_md5.values() if len(v) > 1]

        # solape por pares sobre el contenido (con next)
        sets = {rel(a): set(a["huellas"]) for a in analisis}
        nombres = list(sets)
        solapes = []
        for i, x in enumerate(nombres):
            for y in nombres[i + 1:]:
                inter = len(sets[x] & sets[y])
                if inter:
                    solapes.append((x, y, inter, len(sets[x] | sets[y])))

        # Effective N del conjunto + contradicciones de etiqueta
        todas = []
        for a in analisis:
            todas.extend(a["huellas"])
        total = len(todas)
        efectivo = len(set(todas))
        contradicciones = [
            (rel(a), nexts)
            for a in analisis
            for nexts in a["etiquetas"].values()
            if len(nexts) > 1
        ]

        tabla = "\n".join(
            f"| `{rel(a)}` | {a['n']} | {a['n'] - a['rotos'] - len(set(a['huellas']))} "
            f"| {len(set(a['huellas']))} | {a['con_steps']} | {a['con_obs']} |"
            for a in analisis
        )
        filas_solape = "\n".join(
            f"| `{x}` | `{y}` | {inter} | {inter / union:.0%} |" for x, y, inter, union in solapes
        ) or "| — | — | 0 | — |"
        ejemplos_contra = "\n".join(
            f"- `{f}`: etiquetas en conflicto {sorted(n)}" for f, n in contradicciones[:MAX_EJEMPLOS]
        ) or "ninguna"
        bloque_dup = "\n".join("- " + " ≡ ".join(f"`{n}`" for n in g) for g in dup_archivos) or "ninguno"

        return {"total": total, "efectivo": efectivo, "markdown": f"""# Effective N — {date.today().isoformat()}

Carpeta: `{folder}` · {len(analisis)} archivos · {total} registros válidos

Huella de contenido: sha1 de `({', '.join(CAMPOS)}, answers.next)` —
ignora `id`/`created`/`model`. El Effective N es el número de registros con
huella distinta en el CONJUNTO (no por archivo).

## Resumen

- Registros: {total} → **Effective N: {efectivo}** ({total - efectivo} duplicados, {1 - efectivo / total:.1%})
- Archivos duplicados enteros (md5):
{bloque_dup}
- Contradicciones de etiqueta (mismo contenido, distinto next): {ejemplos_contra}

## Tabla por archivo

| Archivo | Registros | Dup internos | Únicos | Con steps | Con observation |
|---|---|---|---|---|---|
{tabla}

(La huella ignora `id`/`created`: dos volcados del mismo caso con ids
distintos cuentan como duplicado igual.)

## Solape entre archivos (por contenido, con etiqueta)

| Archivo A | Archivo B | En común | % del union |
|---|---|---|---|
{filas_solape}

## Lectura para re-entrenar

- El Effective N ({efectivo} de {total}) es el tope de casos distintos que
  cualquier mezcla de estos archivos puede aportar.
- Los solapes altos marcan rounds acumulativos: el archivo más nuevo ya
  contiene al viejo; sumar ambos no suma datos.
- `Con steps` bajo con `Con observation` alto indica un volcado cuyo
  esquema de estado no es el de producción (el Choose real lleva `steps`).
"""}

    def post(self, shared, prep_res, exec_res):
        path = Path(shared["salida"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(exec_res["markdown"], encoding="utf-8")
        shared["informe"] = str(path.resolve())
        shared["resumen"] = (
            f"{exec_res['total']} registros → Effective N {exec_res['efectivo']} "
            f"({exec_res['total'] - exec_res['efectivo']} duplicados)"
        )
        print(f"Informe escrito: {path.resolve()}")


def create_effective_n_flow():
    scan = ScanFiles()
    mapa = HashFile()
    reduce_ = WriteReport()
    scan >> mapa >> reduce_
    return Flow(start=scan)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="effective_n",
        description="Deduplicación exacta por contenido de trazas .jsonl (código puro)",
    )
    parser.add_argument("carpeta", nargs="?", default=DEFAULT_FOLDER, help=f"carpeta a analizar (default: {DEFAULT_FOLDER})")
    parser.add_argument("--glob", default="*.jsonl", help="patrón de archivos (default: %(default)s)")
    parser.add_argument("--salida", default="salidas/effective_n.md", help="archivo de salida (default: %(default)s)")
    args = parser.parse_args(argv)

    folder, err = _resolve(args.carpeta)
    if err:
        raise SystemExit(f"ERROR: {err}")
    if not folder.is_dir():
        raise SystemExit(f"ERROR: no es una carpeta: {folder}")

    shared = {"folder": str(folder), "glob": args.glob, "salida": args.salida}
    create_effective_n_flow().run(shared)


if __name__ == "__main__":
    main()
