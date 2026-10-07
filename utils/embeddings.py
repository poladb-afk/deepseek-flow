"""Embeddings locales con fastembed (ONNX, CPU, sin API key).

El primer uso descarga el modelo (una vez). Si ningún candidato carga
(p. ej. sin red), rag.py degrada a búsqueda léxica BM25: mismo flujo,
otro scorer."""
CANDIDATOS = [
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "intfloat/multilingual-e5-large",
]

_modelo = None
_nombre_modelo = None


def get_modelo():
    global _modelo, _nombre_modelo
    if _modelo is not None:
        return _modelo
    from fastembed import TextEmbedding

    errores = []
    for nombre in CANDIDATOS:
        try:
            _modelo = TextEmbedding(model_name=nombre)
            _nombre_modelo = nombre
            print(f"[embeddings] modelo local: {nombre}")
            return _modelo
        except Exception as e:  # candidato no disponible: probar el siguiente
            errores.append(f"{nombre}: {type(e).__name__}: {e}")
    raise RuntimeError("ningún embedder local disponible: " + "; ".join(errores))


def embed(textos, consulta=False):
    modelo = get_modelo()  # primero carga: setea _nombre_modelo
    # la familia e5 exige prefijos query:/passage:; paraphrase no los usa
    prefijo = ""
    if _nombre_modelo and "e5" in _nombre_modelo:
        prefijo = "query: " if consulta else "passage: "
    return [list(v) for v in modelo.embed([prefijo + t for t in textos])]
