"""Paso 5 del reentreno (pre-registro: banco/specs/voto_reentreno.md): combina
r2 (dataset Kaggle `flow-router-voto`, descargado por la persona el 2026-10-27)
con los 300 casos congelados (`salidas/evals/voto_dataset.jsonl`) en el archivo
de entrenamiento `salidas/evals/voto_entrenamiento.jsonl`.

Reglas fijadas ANTES de correr (auditoría del autor, 2026-10-27):

- los textos de los 300 no se tocan: el sha256 del congelado
  (2947b449…, líneas "id|pregunta" ordenadas) se verifica ANTES y DESPUÉS de
  combinar; la etiqueta final es `relabel` si la hay, si no `veredicto_juez`;
- r2 entra byte a byte; si un caso de r2 es fuga real contra el bench o el
  control (Jaccard >= 0,6 sobre bolsa de palabras), ESE caso sale del
  combinado — el umbral no se sube;
- si la fuga fuera de los 300, el script PARA sin escribir: los textos están
  congelados y esa decisión es de la persona;
- el combinado entero vuelve a pasar el anti-fuga: si queda una fuga, no se
  escribe nada.

Uso:
    python3 banco/probes/voto_combinar.py             # escribe el combinado
    python3 banco/probes/voto_combinar.py --verificar  # solo verifica lo ya escrito
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from voto_antifuga import fugas, leer, protegidos  # noqa: E402

DATASET = RAIZ / "salidas" / "evals" / "voto_dataset.jsonl"
R2 = RAIZ / "docs" / "informes" / "flow-router-voto" / "data" / "router_voto_verified.jsonl"
SALIDA = RAIZ / "salidas" / "evals" / "voto_entrenamiento.jsonl"

CONGELADO_SHA = "2947b4490fc49d542df88166c11e7e82ee9195c54cb25516faba1a67b8cbccfa"
# El contexto neutro del yaml de la task: los 300 se generaron y juzgaron sin
# contexto propio (PROMPT_ARBITRO_VOTO no lleva ninguno).
CONTEXTO_300 = "a terminal chat where an AI assistant can read local files, search the web and run pipelines"


def congelado_sha(filas):
    """La receta del congelamiento: líneas "id|pregunta" ordenadas, unidas."""
    lineas = sorted(f"{f['id']}|{f['pregunta']}" for f in filas)
    return hashlib.sha256("\n".join(lineas).encode()).hexdigest()


def fila_bmo(f):
    """Un caso congelado en el formato de r2 (campos iguales, texto intacto)."""
    etiqueta = f.get("relabel") or f["veredicto_juez"]
    assert etiqueta in ("herramientas", "directo"), f"{f['id']}: etiqueta {etiqueta!r}"
    return {"id": f["id"], "fields": {"pregunta": f["pregunta"]},
            "answers": {"confirma_herramientas": etiqueta},
            "context": CONTEXTO_300, "model": "deepseek-flash",
            "created": "2026-10-26", "options": [""]}


def sin_fugas_r2(r2, verbose=True):
    """r2 sin los casos que son fuga real; devuelve (limpio, sacados)."""
    sacados = fugas(r2, protegidos())
    malos = {texto for _, texto, _ in sacados}
    if verbose:
        for cid, texto, sim in sacados:
            print(f"[combinar] fuga r2 → fuera: {cid} ~ {sim}: {texto[:100]}")
    return [f for f in r2 if f["fields"]["pregunta"] not in malos], sacados


def verificar(ruta=SALIDA):
    """Chequea un archivo YA escrito: anti-fuga, congelado dentro, conteos."""
    combinado = leer(ruta)
    g = [f for f in combinado if f["id"].startswith("g")]
    r2 = [f for f in combinado if not f["id"].startswith("g")]
    encontradas = fugas(combinado, protegidos())
    print(f"[verificar] {ruta.name}: {len(combinado)} filas ({len(r2)} r2 + {len(g)} congelados)")
    print(f"[verificar] anti-fuga: {len(encontradas)} fugas")
    print("[verificar] etiquetas:", {e: sum(1 for f in combinado if f["answers"]["confirma_herramientas"] == e)
                                     for e in ("herramientas", "directo")})
    ok_congelado = congelado_sha([{"id": f["id"], "pregunta": f["fields"]["pregunta"]} for f in g]) == CONGELADO_SHA
    print(f"[verificar] congelado dentro ({len(g)}): {'OK ' + CONGELADO_SHA[:12] if ok_congelado else 'NO COINCIDE'}")
    print(f"[verificar] sha256 archivo: {hashlib.sha256(ruta.read_bytes()).hexdigest()}")
    return not encontradas and ok_congelado and len(g) == 300


def main(argv=None):
    parser = argparse.ArgumentParser(prog="voto_combinar", description="Paso 5: r2 + congelados → entrenamiento")
    parser.add_argument("--verificar", action="store_true", help="no escribe: verifica el combinado existente")
    args = parser.parse_args(argv)
    if args.verificar:
        return 0 if verificar() else 1

    congelado = leer(DATASET)
    assert len(congelado) == 300, f"congelado: {len(congelado)} filas, no 300"
    sha_antes = congelado_sha(congelado)
    assert sha_antes == CONGELADO_SHA, f"congelado movido: {sha_antes}"
    print(f"[combinar] congelado OK: 300 casos, sha {sha_antes[:12]}")

    r2 = leer(R2)
    print(f"[combinar] r2: {len(r2)} casos ({R2.relative_to(RAIZ)})")
    r2_limpio, _ = sin_fugas_r2(r2)
    print(f"[combinar] r2 limpio: {len(r2_limpio)} (fuera {len(r2) - len(r2_limpio)})")

    combinado = sorted(r2_limpio + [fila_bmo(f) for f in congelado], key=lambda f: f["id"])
    fugas_del_congelado = [(f["id"], sim) for f in combinado if f["id"].startswith("g")
                           for _, _, sim in fugas([f], protegidos())]
    if fugas_del_congelado:
        print("[combinar] FUGA EN LOS 300 — no escribo; decisión de la persona:", fugas_del_congelado[:10])
        return 1

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in combinado), encoding="utf-8")
    ok = verificar()
    print(f"[combinar] {'escrito' if ok else 'ESCRITO CON PROBLEMAS'} → {SALIDA}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
