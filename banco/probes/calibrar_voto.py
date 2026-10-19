"""Etiquetador de calibración para la compuerta conformal del VOTO (Mesa 3).

Hermano de etiquetar_router.py, un nivel abajo en la cascada. El voto local
(LAYA_MODEL_VOTO) decide los acuerdos Y desacuerdos confiables antes de
llamar al árbitro DeepSeek; el umbral de esa decisión vivía FIJO
(LAYA_UNSURE_HIGH_VOTO=0.7). Acá se produce el JSONL {conf, correcto} que
permite que el umbral del voto SALGA de los datos (misma cota conformal que
el router), en vez de ser una constante elegida a mano.

Por qué así: la cascada del voto existe para NO llamar al segundo árbitro;
la cota conformal mide con qué frecuencia se puede omitir manteniendo SU
decisión. "correcto" = la elección local coincide con el árbitro (DeepSeek,
el mismo prompt de voto_confirmacion_router). El set de test del fine-tune
NO sirve para calibrar: la cota dejaría de valer.

Límite declarado (igual que el router): la muestra sale de los TURNOS de los
escenarios del banco — entradas reales al chat (el driver las tipea), pero
prompts dirigidos por spec y sesgados a "herramientas". Es la distribución
del banco, no la del tráfico natural; el sesgo se declara en cada línea.

Costo: 1 llamada DeepSeek por pregunta (el árbitro) + 1 inferencia local del
voto (~0,2 s) + la carga del checkpoint `router_voto` (~10 s). Escribe
incremental: si la API corta (402/429), lo ya etiquetado queda.

Uso: python3 banco/probes/calibrar_voto.py [n] [--salida ruta.jsonl]
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

from nodes import PREGUNTA_VOTO  # noqa: E402
from utils.call_llm import call_llm  # noqa: E402
from utils.estructura import extraer_yaml  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
IGNORAR = {"salir", "exit", "quit"}
MIN_LARGO = 10

PROMPT_ARBITRO = """Pregunta del usuario:
{pregunta}

Segunda opinión antes de responder directo: ¿esta consulta requiere DE VERDAD
correr herramientas (leer o buscar archivos, web, o ejecutar una capacidad:
debate, investigación, informe, sql...) — los imperativos de acción casi
siempre sí — o se responde solo de conocimiento?

Responde SOLO yaml:
```yaml
veredicto: herramientas|directo
```"""


def preguntas_de_archivo(ruta):
    """Preguntas de un archivo: JSONL del log del chat (exp/34, clave
    "pregunta") o una por línea."""
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
    driver las tipea), aunque dirigidas por spec y sesgadas a 'herramientas'.
    Se declara en el artefacto."""
    import yaml

    salida = []
    for archivo in sorted((RAIZ / "banco" / "escenarios").glob("*.yaml")):
        try:
            datos = yaml.safe_load(archivo.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            # escenarios viejos con formato propio (líneas: {RAIZ}/... sin comillas)
            # que PyYAML no parsea: se saltan, no rompen el etiquetado.
            continue
        for turno in datos.get("turnos", []):
            linea = " ".join((turno.get("linea") or "").split())
            if len(linea) >= MIN_LARGO and linea.lower() not in IGNORAR:
                salida.append(linea)
    return salida


def etiquetar(preguntas, salida):
    """El voto local (LAYA_MODEL_VOTO) + juicio del árbitro por pregunta;
    escribe incremental en el formato {conf, correcto} de utils/conformal."""
    from utils.laya import disponible, preguntar

    if not disponible("LAYA_MODEL_VOTO"):
        raise SystemExit("laya voto no disponible: sin checkpoint router_voto no hay calibración")
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
                eleccion, conf = preguntar(
                    {"pregunta": pregunta[:1000]}, PREGUNTA_VOTO, setting="LAYA_MODEL_VOTO"
                )["confirma_herramientas"]
            except Exception as e:
                print("  [voto] falló (" + type(e).__name__ + "): " + str(e))
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
                "pregunta": pregunta, "voto": eleccion, "conf": round(float(conf), 4),
                "etiqueta": etiqueta, "correcto": bool(correcto),
                "fuente": "transcripts de banco (sesgo declarado)",
            }, ensure_ascii=False) + "\n")
            f.flush()
            print("  " + str(hechas).rjust(3) + ". voto=" + eleccion.ljust(12)
                  + " arbitro=" + etiqueta.ljust(12) + " conf=" + format(float(conf), ".2f"))
    return hechas, acuerdos


def main(argv=None):
    parser = argparse.ArgumentParser(prog="calibrar_voto")
    parser.add_argument("n", nargs="?", type=int, default=20)
    parser.add_argument("--salida", default=None)
    parser.add_argument(
        "--extra", default=None,
        help="preguntas extra: una por línea, o JSONL con la clave 'pregunta' "
             "(el log del chat exp/34 o salidas/routing.jsonl)",
    )
    args = parser.parse_args(argv)
    salida = Path(args.salida or RAIZ / "banco" / ("calibracion_voto_" + date.today().isoformat() + ".jsonl"))
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
    print("\n" + str(hechas) + " casos - acuerdo voto/arbitro: " + str(acuerdos) + "/" + str(hechas)
          + " = " + format(acuerdos / hechas, ".3f"))
    try:
        from utils.conformal import leer_calibracion, q_de_calibracion

        casos = leer_calibracion(salida)
        for alpha in (0.05, 0.10, 0.20):
            q = q_de_calibracion(casos, alpha)
            print("  alpha=" + format(alpha, ".2f") + " -> q=" + ("sin cota" if q is None else format(q, ".3f")))
    except Exception as e:
        print("  (no se pudo calcular el q: " + type(e).__name__ + ": " + str(e) + ")")
    print("\nPara activar la compuerta: LAYA_CALIBRACION_VOTO=" + str(salida)
          + "  LAYA_ALPHA_VOTO=0.10")


if __name__ == "__main__":
    main()
