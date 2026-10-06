"""Effective N de un dataset de trazas .jsonl: deduplicación exacta, en código.

El informe map-reduce (informe.py) cuenta registros por archivo; aquí se
responde la pregunta previa al re-entrenamiento: cuántos de esos registros
son **distintos de verdad**. La huella de contenido es sha1 del par
(fields, answers.next) canónicamente serializado — ignora id/created/model,
que cambian entre volcados del mismo caso.

Pieza 100% código (como carga_trazas.py): determinista, verificable, sin
LLM. Map-Reduce de PocketFlow solo como forma: HashFile es el mapa y el
reduce cruza pares y escribe el markdown.

Modo multi-carpeta (BatchFlow, patrón esencial de PocketFlow): el MISMO
flujo por carpeta (create_effective_n_flow) se fanea sobre la lista de
carpetas — cada corrida queda intacta, con su propio informe y resumen. Es
SECUENCIAL a propósito: la carga es CPU puro (leer y hashear .jsonl), donde
el paralelismo no aporta, y el orden en que se apilan las secciones del
informe conjunto es una virtud (determinista, reproducible). Con una sola
carpeta el resultado es idéntico al de siempre (compatibilidad hacia atrás).

Uso:
    python3 main.py effective_n [carpeta ...] [--glob '*.jsonl'] [--salida effective_n.md]
"""
import argparse
import hashlib
import json
from collections import Counter
from copy import copy
from datetime import date
from pathlib import Path

from pocketflow import BatchFlow, BatchNode, Flow, Node

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
        # la carpeta y el glob llegan por params (el BatchFlow multi-carpeta
        # inyecta un job por carpeta); shared queda para los resultados.
        # `glob` cae a shared para el flujo de una carpeta suelto.
        return self.params["folder"], self.params.get("glob") or shared.get("glob", "*.jsonl")

    def exec(self, inputs):
        return collect_files(*inputs)

    def post(self, shared, prep_res, exec_res):
        shared["files"] = exec_res
        print(f"Encontrados {len(exec_res)} archivos ({prep_res[1]} en {prep_res[0]})")


class HashFile(BatchNode):
    """Mapa: por archivo, las huellas de sus registros (CPU puro, secuencial)."""

    def prep(self, shared):
        return shared["files"]

    def _run(self, shared):
        # En el BatchFlow multi-carpeta, HashFile hereda los params del job
        # (folder/glob/salida) del nodo anterior; aquí sobran (la lista de
        # archivos va por shared), así que se descartan.
        self.params = {}
        return super()._run(shared)

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
        # Contrato de shared["analisis"] (auditoría de consistencia 2026-10-05):
        # acá es una LISTA de esquemas de HUELLAS de contenido
        # [{"file", "n", "huellas", "dist", "md5"}]. informe.py usa la MISMA
        # clave con el esquema del LLM (resúmenes). Colisión semántica
        # consciente: el flujo es independiente, no se unifica el vocabulario.
        shared["analisis"] = exec_res_list
        for a in exec_res_list:
            print(f"  ✓ {a['file'].name}: {a['n']} registros, {len(set(a['huellas']))} únicos")


class WriteReport(Node):
    """Reduce: cruces por pares, Effective N del conjunto, contradicciones."""

    def prep(self, shared):
        # el nodo hereda el job por params: `folder` (BatchFlow) o, en el
        # flujo de una carpeta, también está en shared.
        return self.params.get("folder") or shared["folder"], shared.get("analisis", [])

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
        # total==0 (archivos vacíos o solo-rotos): evitar la división por cero
        pct_dup = f"{(1 - efectivo / total):.1%}" if total else "—"

        return {"total": total, "efectivo": efectivo, "markdown": f"""# Effective N — {date.today().isoformat()}

Carpeta: `{folder}` · {len(analisis)} archivos · {total} registros válidos

Huella de contenido: sha1 de `({', '.join(CAMPOS)}, answers.next)` —
ignora `id`/`created`/`model`. El Effective N es el número de registros con
huella distinta en el CONJUNTO (no por archivo).

## Resumen

- Registros: {total} → **Effective N: {efectivo}** ({total - efectivo} duplicados, {pct_dup})
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
        # El flujo de una carpeta corre con salida en shared; el job del
        # BatchFlow multi-carpeta trae salida=None (no escribe a disco: el
        # informe conjunto lo escribe el batch). El resultado va SIEMPRE a
        # shared y a shared["informes"] (acumulador del batch).
        shared.update(exec_res)  # total, efectivo, markdown
        salida = shared.get("salida") or self.params.get("salida")
        if salida:
            path = Path(salida)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(exec_res["markdown"], encoding="utf-8")
            shared["informe"] = str(path.resolve())
        shared["resumen"] = (
            f"{exec_res['total']} registros → Effective N {exec_res['efectivo']} "
            f"({exec_res['total'] - exec_res['efectivo']} duplicados)"
        )
        if shared.get("informes") is not None:
            # id estable para el informe conjunto: la carpeta (por params en
            # el BatchFlow, del shared en el flujo de una carpeta). Se copia
            # un dict NUEVO por corrida: el shared es el MISMO en todas las
            # ramas, así que sin copia el acumulador guardaría N veces el
            # último resultado.
            folder = self.params.get("folder") or shared.get("folder")
            shared["informes"].append({
                **shared,
                **exec_res,
                "folder": str(Path(folder).resolve()) if folder is not None else None,
            })
        if salida:
            print(f"Informe escrito: {salida}")
        else:
            print(f"Carpeta procesada: {self.params.get('folder', shared.get('folder'))}")


def create_effective_n_flow():
    """Flujo de UNA carpeta: ScanFiles → HashFile → WriteReport.

    La carpeta/glob/salida viajan en los params del flujo (el BatchFlow
    multi-carpeta inyecta un job por corrida). Si el llamador no fijó params,
    se derivan de shared: así el flujo sigue corriéndose con
    shared = {folder, glob, salida} como siempre (compatibilidad).

    Detalle de PocketFlow: `Flow._orch` fija en cada nodo `params or
    {**self.params}` — los params del FLUJO pisan los del start_node. Por eso
    el job vive en self.params y los nodos lo leen de ahí."""
    scan = ScanFiles()
    mapa = HashFile()
    reduce_ = WriteReport()
    scan >> mapa >> reduce_
    flow = Flow(start=scan)

    def _run(shared):
        if not flow.params:
            flow.set_params({
                "folder": shared.get("folder"),
                "glob": shared.get("glob", "*.jsonl"),
                "salida": shared.get("salida"),
            })
        return Flow._run(flow, shared)

    flow._run = _run
    return flow


class EffectiveNMulti(BatchFlow):
    """Un flujo effective_n POR CARPETA, sobre la MISMA pieza
    (create_effective_n_flow). SECUENCIAL a propósito: CPU puro (leer y
    hashear .jsonl), donde el paralelismo no aporta y el orden en que se
    apilan las secciones del informe conjunto es una virtud (determinista,
    reproducible).

    prep devuelve un job por carpeta; BatchFlow corre el pipeline para cada
    uno. La salida se decide en post: con una sola carpeta, escribe donde el
    flujo de una sola carpeta lo haría (comportamiento EXACTO de siempre);
    con varias, arma un informe por sección + resumen conjunto."""

    def __init__(self, carpetas, glob, salida):
        super().__init__(start=create_effective_n_flow())
        self.carpetas = list(carpetas)
        self.glob = glob
        self.salida = salida

    def prep(self, shared):
        # jobs del batch — SOLO el payload. El flujo de una carpeta se usa
        # como start: anidarlo como rama dispara su derivación de params (y
        # en el batch el shared no tiene folder), así que _run lo reemplaza
        # por un nodo que corre el MISMO pipeline con los params del flujo.
        return [{"folder": str(c)} for c in self.carpetas]

    def post(self, shared, prep_res, exec_res):
        informes = shared["informes"]
        if len(self.carpetas) == 1:
            # compatibilidad hacia atrás: el flujo de UNA carpeta no cambia
            # (shared["informe"]/["resumen"]/["folder"] con los de esa carpeta)
            shared.update(informes[0])
            return
        path = Path(self.salida)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(informe_conjunto(informes), encoding="utf-8")
        shared["informe"] = str(path.resolve())
        shared["resumen"] = resumen_conjunto(informes)
        print(f"Informe conjunto escrito: {path.resolve()}")

    def _run(self, shared):
        """Inicializa la cola de jobs y reenvía el batch: cada rama deja su
        parte en shared["informes"]; el informe conjunto (o único) lo escribe
        post(). El flujo interno NO escribe a disco (salida=None).

        Detalle de PocketFlow: BatchFlow llama `_orch(shared, {**params,
        **bp})`, pero la rama (el nodo del batch) es un FLUJO anidado — y el
        `_orch` de ese flujo interno NO recibe el job. Por eso el job se toma
        de una cola propia, en orden, y se aplica a la corrida del pipeline.
        La copia del flujo es SUPERFICIAL (como la de _orch): los successors
        siguen apuntando al pipeline original."""
        shared["informes"] = []
        self._jobs = list(self.prep(shared))
        flujo = self.start_node
        self._flujo = flujo
        nodo = copy(flujo)

        def _run_plano(shared, batch=self):
            # El `_orch` del batch NO pasa el job a este nodo (sí a los
            # demás), así que el job sale de la cola, en orden.
            job = batch._jobs.pop(0) if batch._jobs else {}
            batch._flujo.params = {**job, "glob": batch.glob, "salida": None}
            return batch._flujo._orch(shared)

        nodo._run = _run_plano
        self.start_node = nodo
        return super()._run(shared)


def resumen_conjunto(informes):
    """Total del lote. La deduplicación es POR CARPETA (cada corrida es
    independiente): el Effective N conjunto suma los de cada carpeta y no
    detecta coincidencias entre carpetas — eso queda como propiedad de los
    solapes por pares cuando se corren juntas. El total de registros sí es
    la suma real de todas las carpetas."""
    total = sum(i["total"] for i in informes)
    efectivo = sum(i["efectivo"] for i in informes)
    return (
        f"{len(informes)} carpetas · {total} registros → Effective N {efectivo} "
        f"({total - efectivo} duplicados)"
    )


def informe_conjunto(informes):
    """Markdown del lote: resumen conjunto + una sección por carpeta (su
    informe completo, con el H1 degradado a H2)."""
    partes = [f"""# Effective N — lote de {len(informes)} carpetas — {date.today().isoformat()}

{resumen_conjunto(informes)}
"""]
    for i in informes:
        folder = Path(i["folder"]).resolve()
        partes.append(f"## Carpeta `{folder}`\n")
        for linea in i["markdown"].splitlines():
            if linea.startswith("# "):
                linea = "#" + linea
            partes.append(linea)
        partes.append("")
    return "\n".join(partes)


def resolver_carpetas(args):
    """Carpetas del lote: todas las posicionales (o DEFAULT_FOLDER)."""
    raw = args.carpeta or [DEFAULT_FOLDER]
    carpetas, errores = [], []
    for c in raw:
        folder, err = _resolve(c)
        if err:
            errores.append(f"{c}: {err}")
        elif not folder.is_dir():
            errores.append(f"{c}: no es una carpeta: {folder}")
        else:
            carpetas.append(folder)
    if errores:
        raise SystemExit("ERROR:\n" + "\n".join(errores))
    return carpetas


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="effective_n",
        description="Deduplicación exacta por contenido de trazas .jsonl (código puro)",
    )
    parser.add_argument("carpeta", nargs="*", default=None,
                        help=f"carpetas a analizar, una o varias (default: {DEFAULT_FOLDER})")
    parser.add_argument("--glob", default="*.jsonl", help="patrón de archivos (default: %(default)s)")
    parser.add_argument("--salida", default="salidas/effective_n.md", help="archivo de salida (default: %(default)s)")
    args = parser.parse_args(argv)

    carpetas = resolver_carpetas(args)

    if len(carpetas) == 1:
        # ruta EXACTA de siempre (mismo flujo, mismo post, mismo print)
        shared = {"folder": str(carpetas[0]), "glob": args.glob, "salida": args.salida}
        create_effective_n_flow().run(shared)
        return

    # con una sola carpeta el BatchFlow no cambia nada; con varias fanea el
    # flujo por carpeta (SECUENCIAL: CPU puro, orden determinista).
    shared = {"informes": []}
    EffectiveNMulti(carpetas, args.glob, args.salida).run(shared)


if __name__ == "__main__":
    main()
