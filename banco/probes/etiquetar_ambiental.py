"""La etiqueta AMBIENTAL del router (exp/43) — código puro, sin LLM.

En modo shadow la ruta APLICADA es siempre herramientas, así que DeepSeek corre
con tools: si responde SIN llamar ninguna (rondas == 0), la pregunta era
"directo" EN LA PRÁCTICA. Esa es la etiqueta ambiental — gratis, en la
distribución exacta de producción, y crece sola con el uso. Este probe UNE por
`id` las decisiones de `salidas/routing.jsonl` (líneas con `p_directo`) con sus
líneas `"evento": "resultado"` (que emite nodes.AgentStep al responder) y
produce el JSONL de calibración — drop-in para utils.conformal.leer_calibracion
(claves `conf` + `correcto`) y hermano de banco/calibracion_router_2026-10-08.jsonl.

LÍMITE HONESTO: la etiqueta mide lo que DeepSeek HIZO, no lo que la pregunta
NECESITABA — un modelo que responde de memoria una pregunta de archivos etiqueta
"directo" aunque otro hubiese leído. Es ruido declarado; el volumen lo compensa.

Uso: python3 banco/probes/etiquetar_ambiental.py [--ruta salidas/routing.jsonl]
     [--salida banco/calibracion_ambiental_FECHA.jsonl]
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))


def unir(lineas):
    """PURA: las líneas ya parseadas del routing log → filas de calibración.

    - las líneas con "evento": "resultado" se indexan por `id`;
    - una línea de decisión con `p_directo` numérico Y con su `resultado` emite
      una fila {"ts", "pregunta"? (solo si la trae), "laya" (propuesta),
      "conf" (p_directo si propuesta == "directo" sino 1 - p_directo),
      "etiqueta" ("herramientas" si uso_tools sino "directo"),
      "correcto" (propuesta == etiqueta), "fuente"};
    - decisiones sin resultado (ciclo abortado) o sin `p_directo` (respuesta
      inválida) se saltan;
    - resultado huérfano (id sin decisión) se ignora.
    """
    resultados = {}
    for linea in lineas:
        if not isinstance(linea, dict):
            continue
        if linea.get("evento") == "resultado":
            resultados[linea.get("id")] = linea

    filas = []
    for linea in lineas:
        if not isinstance(linea, dict):
            continue
        if linea.get("evento") == "resultado":
            continue  # resultado huérfano: id sin decisión → ignorado
        p_directo = linea.get("p_directo")
        if not isinstance(p_directo, (int, float)) or isinstance(p_directo, bool):
            continue  # sin p_directo: respuesta inválida, no hay par calibrable
        resultado = resultados.get(linea.get("id"))
        if resultado is None:
            continue  # decisión sin resultado: ciclo abortado
        propuesta = linea.get("propuesta")
        uso_tools = bool(resultado.get("uso_tools"))
        etiqueta = "herramientas" if uso_tools else "directo"
        conf = p_directo if propuesta == "directo" else 1 - p_directo
        fila = {
            "ts": linea.get("ts"),
            "laya": propuesta,
            "conf": conf,
            "etiqueta": etiqueta,
            "correcto": propuesta == etiqueta,
            "fuente": "etiqueta ambiental exp/43",
        }
        if "pregunta" in linea:
            fila["pregunta"] = linea["pregunta"]
        filas.append(fila)
    return filas


def leer_lineas(ruta):
    """Las líneas JSON del routing log; las ilegibles se saltan."""
    path = Path(ruta)
    if not path.is_file():
        return []
    salida = []
    for cruda in path.read_text(encoding="utf-8").splitlines():
        if not cruda.strip():
            continue
        try:
            salida.append(json.loads(cruda))
        except json.JSONDecodeError:
            continue
    return salida


def main(argv=None):
    parser = argparse.ArgumentParser(prog="etiquetar_ambiental")
    parser.add_argument("--ruta", default=str(RAIZ / "salidas" / "routing.jsonl"))
    parser.add_argument(
        "--salida",
        default=str(RAIZ / "banco" / ("calibracion_ambiental_" + date.today().isoformat() + ".jsonl")),
    )
    args = parser.parse_args(argv)
    filas = unir(leer_lineas(args.ruta))
    destino = Path(args.salida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    directo = herramientas = 0
    with open(destino, "w", encoding="utf-8") as f:
        for fila in filas:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
            f.flush()
            if fila["etiqueta"] == "directo":
                directo += 1
            else:
                herramientas += 1
    print("# Etiqueta ambiental exp/43 → " + str(destino))
    print("  n=" + str(len(filas)) + "  directo=" + str(directo) + "  herramientas=" + str(herramientas))


if __name__ == "__main__":
    main()
