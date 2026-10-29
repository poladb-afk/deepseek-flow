"""Contrafáctico 2 de la fase 4b-mín (banco/specs/fase4b_min.md): ¿alguna
pregunta REAL es amplia solo por la regex de palabras de `alcance_amplio`?

Lee `salidas/preguntas.jsonl` (solo origen web/terminal: el banco escribe el
suyo aparte desde X93) y clasifica cada pregunta con y sin `_PALABRAS_AMPLIAS`,
contra el disco del repo. Puro: no escribe nada, no llama al modelo.

Uso: AGENT_ALLOWED_DIRS=$PWD python3 banco/probes/alcance_sin_palabras.py [--ruta salidas/preguntas.jsonl]
"""
import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import nodes  # noqa: E402

NUNCA = re.compile(r"(?!)")


def clasificar(pregunta, raiz=RAIZ):
    """(con la regex, sin la regex) para una pregunta."""
    con = nodes.alcance_amplio(pregunta, raiz=raiz)
    original = nodes._PALABRAS_AMPLIAS
    nodes._PALABRAS_AMPLIAS = NUNCA
    try:
        sin = nodes.alcance_amplio(pregunta, raiz=raiz)
    finally:
        nodes._PALABRAS_AMPLIAS = original
    return con, sin


def preguntas(ruta):
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if fila.get("origen") in ("web", "terminal") and fila.get("pregunta"):
            yield fila["pregunta"]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="alcance_sin_palabras")
    parser.add_argument("--ruta", default=str(RAIZ / "salidas" / "preguntas.jsonl"))
    args = parser.parse_args(argv)
    if not Path(args.ruta).is_file():
        print(f"sin {args.ruta}")
        return 1
    total, amplias, cambian = 0, 0, []
    for pregunta in dict.fromkeys(preguntas(args.ruta)):
        total += 1
        con, sin = clasificar(pregunta)
        amplias += con
        if con and not sin:
            cambian.append(pregunta)
    print(f"{total} preguntas únicas · {amplias} amplias con la regex · "
          f"{len(cambian)} dejan de serlo sin ella")
    for pregunta in cambian:
        print(f"  - {pregunta[:160]}")
    print("4b-mín: " + ("PASA (se borra la regex)" if not cambian else "REVISAR caso por caso"))
    return 0 if not cambian else 2


if __name__ == "__main__":
    sys.exit(main())
