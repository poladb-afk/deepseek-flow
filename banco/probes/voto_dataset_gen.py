"""Generador del dataset de reentreno de router_voto (X87/X88, lado generación).

La receta de exp/13 con las cercas de X88: los candidatos los genera un LLM
a partir de un pedido que describe SOLO LAS FAMILIAS (el texto del autor de
la enmienda, público, sin contenido del control); un juez ciego (el árbitro
de producción, PROMPT_ARBITRO_VOTO) los etiqueta sin ver familias ni
etiquetas; la persona relabelea una muestra (--muestra) y --relabel aplica
sus correcciones. El archivo final se valida con voto_antifuga.py ANTES de
entrenar. Ningún caso se escribe a mano: si hace falta más volumen, se
vuelve a generar con --mas.

Ninguna persona ni agente que haya leído el control escribe casos: este
script es la única puerta de entrada de texto al dataset.

Uso:
    python3 banco/probes/voto_dataset_gen.py --por-familia 60          # genera y juzga
    python3 banco/probes/voto_dataset_gen.py --muestra 30              # para tu relabel
    python3 banco/probes/voto_dataset_gen.py --relabel correcciones.txt # id etiqueta por línea
    python3 banco/probes/voto_dataset_gen.py --mas 20 --familia ganador # top-up
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from voto_antifuga import jaccard, palabras  # noqa: E402  (misma normalización que la cerca)

from nodes import PROMPT_ARBITRO_VOTO  # noqa: E402
from utils.call_llm import call_llm  # noqa: E402

SALIDA = RAIZ / "salidas" / "evals" / "voto_dataset.jsonl"

# El pedido de familias: texto del autor de la enmienda (2026-10-27), público,
# sin contenido del control. Las tres familias, incluida la de contraejemplos
# directos que protege control_ahorro (sin ella el voto aprende la regla ciega
# "debatí → herramientas").
FAMILIAS = {
    "deliberacion": {
        "intencion": "herramientas",
        "pedido": (
            "Familia DELIBERACIÓN EN VARIAS RONDAS: pedidos que piden debatir "
            "o contraponer posiciones en N rondas y cerrar con un veredicto."
        ),
    },
    "ganador": {
        "intencion": "herramientas",
        "pedido": (
            "Familia GANADOR MÁS RECIENTE: quién ganó la última edición de "
            "una competencia o elección, sin fecha en la pregunta."
        ),
    },
    "contraejemplo": {
        "intencion": "directo",
        "pedido": (
            "Familia CONTRAEJEMPLOS DIRECTOS de las mismas familias: un "
            "pedido de opinión de una sola vuelta, o una pregunta histórica "
            "cerrada como «¿quién ganó el mundial de 1986?» (edición pasada "
            "o fecha explícita; respuesta estable de conocimiento)."
        ),
    },
}

RE_VEREDICTO = re.compile(r"veredicto:\s*(herramientas|directo)", re.IGNORECASE)
TOPICOS = (
    "tecnología, software, IA, deporte, política, economía, ciencia, "
    "cultura, cine, música, historia, gastronomía, salud, educación, "
    "viajes, negocios, videojuegos, ambiente, autos, moda"
)


def generar_lote(familia, n, evitar=()):
    """Un lote de candidatos de la familia: SOLO el pedido de familias + \
    mecánica de diversidad. Sin ejemplos, sin vocabulario del control."""
    pedido = (
        f"{FAMILIAS[familia]['pedido']}\n\n"
        f"Generá {n} preguntas en español, una por línea, numeradas. "
        f"Temas y dominios variados ({TOPICOS}); verbos y estructuras "
        "diversos, sin repetir plantillas. Autocontenidas, una sola línea "
        "cada una. No expliques nada: solo la lista numerada."
    )
    if evitar:
        pedido += "\nEvitá arrancar como: " + ", ".join(sorted(evitar)[:40]) + "."
    respuesta = call_llm(pedido)
    preguntas = []
    for linea in respuesta.splitlines():
        m = re.match(r"\s*\d+[.)]\s*(.+)", linea.strip())
        if m and len(m.group(1).strip()) > 12:
            preguntas.append(m.group(1).strip())
    return preguntas


def juzgar(pregunta):
    """El árbitro de producción, a ciegas (sin familia ni etiqueta previa)."""
    try:
        respuesta = call_llm(PROMPT_ARBITRO_VOTO.format(pregunta=pregunta))
    except Exception as e:  # noqa: BLE001 (el juez es best-effort: se relabelea)
        return None, f"error juez: {type(e).__name__}"
    m = RE_VEREDICTO.search(respuesta)
    return (m.group(1).lower() if m else None), None


def cargar():
    if not SALIDA.is_file():
        return []
    return [json.loads(linea) for linea in SALIDA.read_text(encoding="utf-8").splitlines() if linea.strip()]


def guardar(filas):
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")


def siguiente_id(filas):
    return max((int(f["id"][1:]) for f in filas if f["id"][1:].isdigit()), default=0) + 1


def generar(familia, n):
    filas = cargar()
    existentes = [palabras(f["pregunta"]) for f in filas]
    arrancan = {f["pregunta"].split()[0].lower() for f in filas}
    nuevos, n_id = [], siguiente_id(filas)
    for pregunta in generar_lote(familia, n * 2, arrancan):
        bolsa = palabras(pregunta)
        if any(jaccard(bolsa, e) >= 0.8 for e in existentes + [palabras(x["pregunta"]) for x in nuevos]):
            continue
        veredicto, err = juzgar(pregunta)
        fila = {"id": f"g{n_id:04d}", "familia": familia,
                "intencion": FAMILIAS[familia]["intencion"], "pregunta": pregunta,
                "veredicto_juez": veredicto, "relabel": None, "error": err}
        nuevos.append(fila)
        existentes.append(bolsa)
        n_id += 1
        if len(nuevos) >= n:
            break
    guardar(filas + nuevos)
    return nuevos


def muestra(n):
    filas = cargar()
    elegidas = random.sample(filas, min(n, len(filas)))
    elegidas.sort(key=lambda f: int(f["id"][1:]))
    print(f"# Relabel manual — {len(elegidas)} de {len(filas)}. Respondé en un archivo")
    print("# con una línea por caso: <id> <herramientas|directo> [nota]")
    print("# y aplicalo con --relabel. Semilla de la muestra: no hay (aleatoria).")
    for f in elegidas:
        marca = "" if f["veredicto_juez"] == f["intencion"] else "  # ⚠️ juez≠familia"
        print(f"{f['id']} [{f['familia']}/{f['intencion']}] juez={f['veredicto_juez']}{marca}")
        print(f"    {f['pregunta']}")


def aplicar_relabel(ruta):
    filas = cargar()
    por_id = {f["id"]: f for f in filas}
    cambiadas = 0
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        partes = linea.split()
        if len(partes) >= 2 and partes[0] in por_id and partes[1] in ("herramientas", "directo"):
            por_id[partes[0]]["relabel"] = partes[1]
            cambiadas += 1
    guardar(filas)
    dataset = [f for f in filas if f["relabel"] or f["veredicto_juez"]]
    etiqueta_final = lambda f: f["relabel"] or f["veredicto_juez"]  # noqa: E731
    from collections import Counter
    print(f"relabel aplicado: {cambiadas} casos")
    print("balance final:", dict(Counter(etiqueta_final(f) for f in dataset)))
    print("final para entrenar (etiqueta = relabel si hubo, si no juez):",
          SALIDA)
    print("ANTES de entrenar: python3 banco/probes/voto_antifuga.py", SALIDA)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="voto_dataset_gen",
                                     description="Dataset de reentreno: generador por familias + juez ciego (X87/X88)")
    parser.add_argument("--por-familia", type=int, default=None, help="genera N por familia (juzga cada caso)")
    parser.add_argument("--mas", type=int, default=None, help="top-up: N más de --familia")
    parser.add_argument("--familia", choices=sorted(FAMILIAS), default=None)
    parser.add_argument("--muestra", type=int, default=None, help="imprime N casos para relabel manual")
    parser.add_argument("--relabel", default=None, help="archivo 'id etiqueta' con tus correcciones")
    args = parser.parse_args(argv)
    if args.por_familia:
        for familia in FAMILIAS:
            nuevos = generar(familia, args.por_familia)
            print(f"[gen] {familia}: {len(nuevos)} nuevos (juez aplicado)")
    if args.mas:
        if not args.familia:
            parser.error("--mas exige --familia")
        nuevos = generar(args.familia, args.mas)
        print(f"[gen] {args.familia}: {len(nuevos)} nuevos")
    if args.muestra:
        muestra(args.muestra)
    if args.relabel:
        aplicar_relabel(args.relabel)
    if not any((args.por_familia, args.mas, args.muestra, args.relabel)):
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
