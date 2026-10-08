"""Etiquetador de calibración para la compuerta conformal del router (exp/33).

Produce el JSONL que consume LAYA_CALIBRACION_ROUTER (exp/31): por cada
pregunta REAL, la decisión del router local (Laya) y la del ÁRBITRO
(DeepSeek, el mismo prompt del voto de confirmación). "correcto" = coinciden.

Por qué así: la cascada existe para NO llamar al árbitro; la cota conformal
mide con qué frecuencia se puede omitir manteniendo SU decisión. Las
preguntas salen de los TURNOS DE LOS ESCENARIOS del banco: son entradas
reales al chat (el driver las tipea). Los .log NO sirven — medido: el PTY
corre con echo off, así que "Tú:" queda pegado a la salida del chat y la
pregunta tipeada no está en el archivo. El set de test del fine-tune tampoco
sirve para calibrar: la cota dejaría de valer.

Límite declarado: la muestra está sesgada a tareas de banco (prompts largos y
dirigidos, casi todos "herramientas"). Es la distribución del banco, no la del
tráfico natural; el sesgo se reporta junto con los resultados.

Costo: 1 llamada DeepSeek por pregunta (p50 medido 2,1 s) + 1 inferencia local
(~0,2 s) + la carga del checkpoint (~10 s, 2,86 GiB). Escribe incremental: si
la API corta (402/429), lo ya etiquetado queda.

Uso: python3 banco/probes/etiquetar_router.py [n] [--salida ruta.jsonl]
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

from nodes import PREGUNTA_ROUTER  # noqa: E402
from utils.call_llm import call_llm  # noqa: E402
from utils.estructura import extraer_yaml  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
RE_TU = re.compile(r"^Tú:\s*(.+)$", re.MULTILINE)
IGNORAR = {"salir", "exit", "quit"}
MIN_LARGO = 10

PROMPT_ARBITRO = """Pregunta del usuario:
{pregunta}

¿Responderla requiere USAR HERRAMIENTAS (leer/buscar archivos, web, ejecutar
una capacidad: debate, investigación, informe, sql...) o se responde DIRECTO
de conocimiento? Un imperativo de acción (debatá, investigá, generá, medí...)
casi siempre es herramientas.

Responde SOLO yaml:
```yaml
veredicto: herramientas|directo
```"""


def preguntas_de_archivo(ruta):
    """Preguntas de un archivo: el JSONL del log del chat (exp/34, clave
    "pregunta") o una por línea. Así el tráfico REAL del chat entra al set de
    calibración sin conversiones."""
    path = Path(ruta)
    if not path.is_file():
        return []
    salida = []
    for linea in path.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        texto = linea
        if linea.lstrip().startswith("{"):
            try:
                texto = json.loads(linea).get("pregunta", "")
            except json.JSONDecodeError:
                texto = ""
        limpia = " ".join(texto.split())
        if len(limpia) >= MIN_LARGO:
            salida.append(limpia)
    return salida


def preguntas_de_escenarios():
    """Los turnos de los escenarios del banco: entradas REALES al chat (el
    driver las tipea), aunque dirigidas por spec y por lo tanto sesgadas a
    'herramientas'. Se declara en el artefacto."""
    import yaml

    salida = []
    for archivo in sorted((RAIZ / "banco" / "escenarios").glob("*.yaml")):
        datos = yaml.safe_load(archivo.read_text(encoding="utf-8")) or {}
        for turno in datos.get("turnos", []):
            linea = " ".join((turno.get("linea") or "").split())
            if len(linea) >= MIN_LARGO and linea.lower() not in IGNORAR:
                salida.append(linea)
    return salida


def etiquetar(preguntas, salida):
    """Laya local + juicio del árbitro por pregunta; escribe incremental."""
    from utils.laya import disponible, preguntar

    if not disponible():
        raise SystemExit("laya no disponible: sin checkpoint no hay calibración")
    ya = set()
    if Path(salida).is_file():          # reanudable: no re-etiqueta lo hecho
        for linea in Path(salida).read_text(encoding="utf-8").splitlines():
            if linea.strip():
                ya.add(json.loads(linea).get("pregunta"))
        print("  (reanudando: " + str(len(ya)) + " casos ya etiquetados)")
    hechas, acuerdos = 0, 0
    with open(salida, "a", encoding="utf-8") as f:
        for pregunta in preguntas:
            if pregunta in ya:
                continue
            try:
                eleccion, conf = preguntar({"pregunta": pregunta[:1000]}, PREGUNTA_ROUTER)["necesita_herramientas"]
            except Exception as e:
                print("  [laya] falló (" + type(e).__name__ + "): " + str(e))
                continue
            try:
                crudo = call_llm(PROMPT_ARBITRO.format(pregunta=pregunta))
                etiqueta = extraer_yaml(crudo).get("veredicto", "herramientas")
            except Exception as e:
                print("  [arbitro] falló (" + type(e).__name__ + "): " + str(e) + " - corto acá")
                break
            correcto = eleccion == etiqueta
            acuerdos += correcto
            hechas += 1
            f.write(json.dumps({
                "pregunta": pregunta, "laya": eleccion, "conf": round(float(conf), 4),
                "etiqueta": etiqueta, "correcto": bool(correcto),
                "fuente": "transcripts de banco (sesgo declarado)",
            }, ensure_ascii=False) + "\n")
            f.flush()
            print("  " + str(hechas).rjust(3) + ". laya=" + eleccion.ljust(12)
                  + " arbitro=" + etiqueta.ljust(12) + " conf=" + format(float(conf), ".2f"))
    return hechas, acuerdos


def main(argv=None):
    parser = argparse.ArgumentParser(prog="etiquetar_router")
    parser.add_argument("n", nargs="?", type=int, default=20)
    parser.add_argument("--salida", default=None)
    parser.add_argument("--extra", default=None, help="archivo con una pregunta por línea")
    args = parser.parse_args(argv)
    salida = Path(args.salida or RAIZ / "banco" / ("calibracion_router_" + date.today().isoformat() + ".jsonl"))
    candidatas = preguntas_de_escenarios()
    if args.extra:
        candidatas += preguntas_de_archivo(args.extra)
    vistas, preguntas = set(), []
    for pregunta in candidatas:            # dedupe preservando el orden
        if pregunta not in vistas:
            vistas.add(pregunta)
            preguntas.append(pregunta)
        if len(preguntas) >= args.n:
            break
    print("# Etiquetando " + str(len(preguntas)) + " preguntas -> " + str(salida))
    hechas, acuerdos = etiquetar(preguntas, salida)
    if not hechas:
        raise SystemExit("sin casos etiquetados")
    print("\n" + str(hechas) + " casos - acuerdo router/arbitro: " + str(acuerdos) + "/" + str(hechas)
          + " = " + format(acuerdos / hechas, ".3f"))
    try:
        from utils.conformal import leer_calibracion, q_de_calibracion

        casos = leer_calibracion(salida)
        for alpha in (0.05, 0.10, 0.20):
            q = q_de_calibracion(casos, alpha)
            print("  alpha=" + format(alpha, ".2f") + " -> q=" + ("sin cota" if q is None else format(q, ".3f")))
    except Exception as e:
        print("  (no se pudo calcular el q: " + type(e).__name__ + ": " + str(e) + ")")
    print("\nPara activar la compuerta: LAYA_CALIBRACION_ROUTER=" + str(salida)
          + "  LAYA_ALPHA=0.10")


if __name__ == "__main__":
    main()
