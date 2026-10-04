"""RAG: indexación offline + recuperación semántica (patrón RAG del cookbook).

Offline (un Flow): ChunkDocs → EmbedChunks → SaveIndex — trocea los
archivos de texto de una carpera, los vectoriza con embeddings locales
(fastembed) y guarda el índice en rag_index/. Online: buscar(consulta)
incrusta la consulta y devuelve los k fragmentos más cercanos por coseno.
Si no hay embedder disponible, el índice degrada a BM25 léxico: el flujo
no cambia, solo el scorer.

Uso:
    python3 main.py index [carpeta] [--glob '*']
"""
import argparse
import fnmatch
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

import numpy as np
from pocketflow import BatchNode, Flow, Node

from utils.fs_tools import SKIP_DIRS, _resolve

INDICE_DIR = Path(__file__).resolve().parent / "rag_index"
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150
MAX_ARCHIVO = 2 * 1024 * 1024
EMBED_BATCH = 64
K_DEFAULT = 4


def _es_texto(path):
    try:
        with open(path, "rb") as f:
            return b"\x00" not in f.read(4096)
    except OSError:
        return False


def archivos_de(carpeta, patron):
    archivos = []
    for dirpath, dirnames, filenames in os.walk(carpeta):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and "rag_index" not in d]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if not fnmatch.fnmatch(fname, patron):
                continue
            try:
                if fpath.stat().st_size > MAX_ARCHIVO:
                    continue
            except OSError:
                continue
            if _es_texto(fpath):
                archivos.append(fpath)
    return sorted(archivos)


def _chunkear(texto):
    paso = CHUNK_CHARS - CHUNK_OVERLAP
    chunks = []
    for i in range(0, len(texto), paso):
        chunk = texto[i : i + CHUNK_CHARS].strip()
        if chunk:
            chunks.append(chunk)
        if i + CHUNK_CHARS >= len(texto):
            break
    return chunks


class ChunkDocs(BatchNode):
    def prep(self, shared):
        return archivos_de(shared["folder"], shared["glob"])

    def exec(self, filepath):
        try:
            texto = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        return [{"path": str(filepath), "texto": c} for c in _chunkear(texto)]

    def post(self, shared, prep_res, exec_res_list):
        shared["chunks"] = [c for lista in exec_res_list for c in lista]
        print(f"{len(exec_res_list)} archivos → {len(shared['chunks'])} fragmentos")


class EmbedChunks(BatchNode):
    def prep(self, shared):
        chunks = shared.get("chunks", [])
        return [chunks[i : i + EMBED_BATCH] for i in range(0, len(chunks), EMBED_BATCH)]

    def exec(self, batch):
        # el modo viaja en params (config de la tarea, no dato): lo setea indexar()
        if self.params.get("modo", "semantico") != "semantico" or not batch:
            return {"chunks": batch, "vectores": []}
        from utils.embeddings import embed

        vectores = embed([c["texto"] for c in batch])
        return {"chunks": batch, "vectores": vectores}

    def post(self, shared, prep_res, exec_res_list):
        shared["indexados"] = exec_res_list


class SaveIndex(Node):
    def prep(self, shared):
        return shared.get("indexados", []), shared.get("modo", "semantico")

    def exec(self, inputs):
        partes, modo = inputs
        chunks = [c for p in partes for c in p["chunks"]]
        vectores_todos = [v for p in partes for v in p["vectores"]]
        INDICE_DIR.mkdir(exist_ok=True)
        if vectores_todos:
            np.save(INDICE_DIR / "vectores.npy", np.array(vectores_todos, dtype=np.float32))
        with open(INDICE_DIR / "chunks.json", "w", encoding="utf-8") as f:
            json.dump({"modo": modo, "chunks": chunks}, f, ensure_ascii=False)
        return modo, len(chunks), bool(vectores_todos)

    def post(self, shared, prep_res, exec_res):
        modo, n, con_vectores = exec_res
        shared["indice"] = str(INDICE_DIR)
        print(f"Índice ({modo}) listo: {n} fragmentos" + (", con vectores" if con_vectores else ""))


def indexar(carpeta, glob="*"):
    folder, err = _resolve(carpeta)
    if err:
        raise ValueError(f"ERROR: {err}")
    if not folder.is_dir():
        raise ValueError(f"ERROR: no es una carpeta: {folder}")

    modo = "semantico"
    try:
        from utils.embeddings import get_modelo

        get_modelo()
    except (RuntimeError, ImportError):
        modo = "lexico"
        print("[rag] sin embedder local: índice léxico (BM25)")

    shared = {"folder": str(folder), "glob": glob, "modo": modo}
    chunk = ChunkDocs()
    embed_ = EmbedChunks()
    save = SaveIndex()
    chunk >> embed_ >> save
    flow = Flow(start=chunk)
    flow.set_params({"modo": modo})  # params: config de la tarea, visible en exec()
    flow.run(shared)
    return shared["indice"]


_indice_cache = None


def _cargar():
    global _indice_cache
    if _indice_cache is not None:
        return _indice_cache
    chunks_file = INDICE_DIR / "chunks.json"
    if not chunks_file.is_file():
        raise RuntimeError("no hay índice: corre `python3 main.py index [carpeta]` o la herramienta rag_index")
    data = json.loads(chunks_file.read_text(encoding="utf-8"))
    vectores = None
    if data["modo"] == "semantico":
        vectores = np.load(INDICE_DIR / "vectores.npy")
    _indice_cache = (data["modo"], vectores, data["chunks"])
    return _indice_cache


_TOKEN_RE = re.compile(r"[a-záéíóúñü0-9]+")

def _tokenizar(texto):
    return _TOKEN_RE.findall(texto.lower())


def _bm25(consulta, chunks, k):
    docs = [_tokenizar(c["texto"]) for c in chunks]
    n = len(docs) or 1
    avgdl = sum(len(d) for d in docs) / n or 1.0
    df = Counter()
    for d in docs:
        df.update(set(d))
    q = _tokenizar(consulta)
    k1, b = 1.5, 0.75
    scores = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for t in set(q):
            if t not in df:
                continue
            idf = math.log((n - df[t] + 0.5) / (df[t] + 0.5) + 1.0)
            s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avgdl))
        scores.append(s)
    ranking = sorted(range(len(chunks)), key=lambda i: -scores[i])[:k]
    return [(i, scores[i]) for i in ranking]


def buscar(consulta, k=K_DEFAULT):
    modo, vectores, chunks = _cargar()
    if not chunks:
        return "El índice está vacío: reindexa con rag_index."
    if modo == "semantico":
        from utils.embeddings import embed

        q = np.array(embed([consulta], consulta=True)[0], dtype=np.float32)
        qn = q / max(float(np.linalg.norm(q)), 1e-12)
        normas = np.linalg.norm(vectores, axis=1, keepdims=True)
        vn = vectores / np.maximum(normas, 1e-12)
        sims = vn @ qn
        ranking = sorted(range(len(chunks)), key=lambda i: -sims[i])[:k]
        pares = [(i, float(sims[i])) for i in ranking]
    else:
        pares = _bm25(consulta, chunks, k)

    salida = [f"{len(chunks)} fragmentos indexados (modo {modo}); top {len(pares)}:"]
    for i, score in pares:
        c = chunks[i]
        salida.append(f"\n--- {c['path']} (score {score:.3f}) ---\n{c['texto'][:600]}")
    return "\n".join(salida)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="index", description="Indexa una carpeta para búsqueda semántica (RAG offline)"
    )
    parser.add_argument("carpeta", nargs="?", default=str(Path(__file__).resolve().parent),
                        help="carpeta a indexar (default: este proyecto)")
    parser.add_argument("--glob", default="*", help="patrón de archivos (default: todos)")
    args = parser.parse_args(argv)
    try:
        indexar(args.carpeta, args.glob)
    except ValueError as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
