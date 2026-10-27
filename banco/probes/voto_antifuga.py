"""Anti-fuga del reentrenamiento del voto (pre-registro: banco/specs/voto_reentreno.md).

Ningún caso del bench (`banco/voto_casos.jsonl`) ni del control fuera de muestra
(`banco/voto_control.jsonl`) puede entrar al entrenamiento de `router_voto`, ni
reescrito de cerca: si entra, el gate mide memoria y no aprendizaje (la misma
familia de error que X82). Precedente: exp/13 (0 ids del test en el
entrenamiento), tras router_voto r2, donde el test entrenó dentro de los
verificados.

"Reescritura cercana" es determinista, sin LLM: misma bolsa de palabras
normalizada (minúsculas, sin tildes, palabras de 3+ letras) con Jaccard
>= UMBRAL. Atrapa paráfrasis por recorte o reorden; una paráfrasis con otras
palabras pasa (límite declarado).

Uso:
    python3 banco/probes/voto_antifuga.py RUTA_ENTRENAMIENTO.jsonl   # exit 1 si hay fuga
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PROTEGIDOS = (RAIZ / "banco" / "voto_casos.jsonl", RAIZ / "banco" / "voto_control.jsonl")
UMBRAL = 0.6


def palabras(texto):
    plano = unicodedata.normalize("NFKD", str(texto or "").lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return frozenset(p for p in re.findall(r"[a-z0-9]+", plano) if len(p) >= 3)


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def pregunta_de(fila):
    """El texto de una fila: formato de tareas Laya (`fields.pregunta`) o plano."""
    campos = fila.get("fields")
    if isinstance(campos, dict) and campos.get("pregunta"):
        return campos["pregunta"]
    return fila.get("pregunta") or ""


def leer(ruta):
    ruta = Path(ruta)
    if not ruta.is_file():
        return []
    return [json.loads(ln) for ln in ruta.read_text(encoding="utf-8").splitlines() if ln.strip()]


def protegidos(rutas=PROTEGIDOS):
    return [(f.get("id") or "", pregunta_de(f)) for ruta in rutas for f in leer(ruta)]


def fugas(entrenamiento, casos_protegidos, umbral=UMBRAL):
    """[(id_protegido, pregunta_entrenamiento, jaccard)] PURA."""
    bolsas = [(cid, palabras(p)) for cid, p in casos_protegidos]
    salida = []
    for fila in entrenamiento:
        texto = pregunta_de(fila)
        bolsa = palabras(texto)
        for cid, protegida in bolsas:
            similitud = jaccard(bolsa, protegida)
            if similitud >= umbral:
                salida.append((cid, texto, round(similitud, 2)))
    return salida


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit("uso: voto_antifuga.py RUTA_ENTRENAMIENTO.jsonl")
    filas = leer(argv[0])
    if not filas:
        raise SystemExit(f"ERROR: {argv[0]} no existe o está vacío")
    encontradas = fugas(filas, protegidos())
    for cid, texto, similitud in encontradas:
        print(f"[antifuga] {cid} ~ {similitud}: {texto[:120]}")
    print(f"[antifuga] {len(filas)} filas de entrenamiento, {len(encontradas)} fugas")
    return 1 if encontradas else 0


if __name__ == "__main__":
    sys.exit(main())
