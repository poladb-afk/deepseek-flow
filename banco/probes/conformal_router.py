"""Sonda conformal del router (exp/30) - sin LLM y sin cargar Laya.

Pregunta que responde: si en vez de la compuerta a mano (0.85) se elige un
riesgo alpha y el umbral SALE de la calibracion, cuanto se decide local
(llamadas a DeepSeek evitadas) y con que cobertura y precision.

Lee la evidencia ya medida por sonda_laya.py (salidas/evals/
laya_evidencia_router.json: 30 casos con esperado/obtenido/conf) y aplica
utils/conformal.py. Re-ejecutable: mismo archivo, mismos numeros.

Uso: python3 banco/probes/conformal_router.py [ruta.json]
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

from utils.conformal import cobertura_loo, cuantil_conformal, puntaje  # noqa: E402

EVIDENCIA = RAIZ / "salidas" / "evals" / "laya_evidencia_router.json"
ALPHAS = (0.05, 0.10, 0.15, 0.20, 0.30)


def main(argv=None):
    ruta = Path((argv or sys.argv[1:] or [EVIDENCIA])[0])
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    casos = [{"conf": c["conf"], "correcto": bool(c["correcto"])} for c in datos["casos"]]
    n = len(casos)
    print("# Sonda conformal del router -", ruta.name)
    print()
    print("checkpoint:", datos["checkpoint"], "| n =", n,
          "| crudo", round(datos["score"], 4), "| ECE", round(datos["ece"], 4),
          "(" + datos["ece_fuente"] + ")")
    print()
    print("| alpha | q | umbral 1-q | aceptadas (local) | cobertura LOO | precision |")
    print("|---|---|---|---|---|---|")
    for alpha in ALPHAS:
        puntajes = [puntaje(c["conf"], c["correcto"]) for c in casos]
        q = cuantil_conformal(puntajes, alpha)
        m = cobertura_loo(casos, alpha)
        umbral = "inf (deriva siempre)" if q == float("inf") else format(1.0 - q, ".3f")
        precision = "-" if m["precision"] is None else format(m["precision"], ".3f")
        print("|", format(alpha, ".2f"), "|", format(q, ".3f"), "|", umbral, "|",
              format(m["aceptadas"], ".3f"), "|", format(m["cobertura"], ".3f"), "|",
              precision, "|")
    fijos = [c for c in datos["casos"] if c["conf"] >= 0.85]
    if fijos:
        aciertos = sum(1 for c in fijos if c["correcto"])
        print()
        print("Referencia - compuerta fija 0.85 (la de hoy):", len(fijos), "de", n,
              "locales (" + format(len(fijos) / n, ".3f") + "), precision",
              format(aciertos / len(fijos), ".3f"))
    print()
    print("Limite honesto: n =", n, ". Con alpha=0.05 el indice de la correccion")
    print("de muestra finita cae en el maximo de los puntajes (umbral permisivo);")
    print("alpha=0.02 no tiene cota con este n y derivaria siempre. Para apretar")
    print("el umbral hace falta mas calibracion etiquetada.")


if __name__ == "__main__":
    main()
