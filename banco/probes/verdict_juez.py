"""Sonda del verdict estocástico del juez (exp/21, fase A).

Pregunta que responde: ¿QUÉ formas toma el `verdict` del Judge cuando su
YAML no valida contra el contrato (`verdict in ("ok", "retry")`)? exp/20
midió `AssertionError: verdict inválido` en 5/17 y 3/17 casos, siempre
distintos: ~1 de cada 4-5 evaluaciones. Acá capturamos los crudos reales
en vez de adivinarlos.

Mecánica (código puro de orchestration + LLM real; NO toca juez.py):
- Monkeypatchea `juez.call_llm` con un wrapper que registra CADA respuesta
  cruda. Los prompts del Judge contienen "Evalúa el borrador"; los del
  Draft no — así se etiqueta el rol de cada llamada.
- Corre `juez.responder_con_juez(pregunta)` para las 8 preguntas víctimas
  (ids de abajo), leídas de banco/juez_preguntas.jsonl, 1 corrida cada una.
- Si `responder_con_juez` levanta (verdict inválido tras los retries), la
  sonda atrapa la excepción POR PREGUNTA y sigue (los crudos ya quedaron
  registrados por el wrapper).
- Clasifica CADA crudo del Judge con `estructura.extraer_yaml` (el mismo
  parseo de producción) y reporta forma/validez.
- Escribe salidas/evals/verdict_shapes_<FECHA>.jsonl (una línea por
  respuesta del Judge) e imprime un resumen con la tabla de shapes.

Uso: python3 banco/probes/verdict_juez.py  (gasta LLM: 8 preguntas ×
hasta 3 rondas × 2 llamadas; lo corre la auditoría, no a mano).
"""
import json
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import juez  # noqa: E402
from utils.estructura import extraer_yaml  # noqa: E402

PREGUNTAS_JSONL = RAIZ / "banco" / "juez_preguntas.jsonl"

# ids que YA fueron víctimas del verdict inválido en alguna corrida de exp/20.
IDS_VICTIMAS = [
    "ventana-caliente",
    "read-max",
    "trampa-pdf-filesapi",
    "memoria-slug",
    "a2a-protocolo",
    "modelo-default",
    "core-tools",
    "supervisor-umbral",
]

# El Judge pide el veredicto con esta frase; sirve para separar sus llamadas
# de las del Draft dentro del mismo flujo.
MARCA_JUDGE = "Evalúa el borrador"

# Contrato de producción (juez.Judge.exec): solo ok/retry son válidos.
VERDICTS_VALIDOS = ("ok", "retry")


def leer_preguntas(path=PREGUNTAS_JSONL):
    """Devuelve {id: pregunta} del banco de preguntas del juez."""
    preguntas = {}
    for linea in Path(path).read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        obj = json.loads(linea)
        preguntas[obj["id"]] = obj["pregunta"]
    return preguntas


def clasificar(crudo):
    """Clasifica un crudo del Judge con el MISMO parseo de producción.

    Devuelve dict: parseo ∈ {dict, fence-genérico, yaml-pelado, ROTO},
    verdict_crudo (valor tal cual o None), valido (bool) y shape (etiqueta
    corta de la forma observada)."""
    # --- forma de parseo (espejo de estructura.extraer_yaml) ---
    if "```yaml" in crudo:
        forma = "fence-yaml"
    elif "```" in crudo:
        forma = "fence-genérico"
    else:
        forma = "yaml-pelado"

    try:
        datos = extraer_yaml(crudo)
    except Exception as e:  # noqa: BLE001 — el crudo puede romper de cualquier forma
        return {
            "parseo": "ROTO",
            "verdict_crudo": None,
            "valido": False,
            "shape": f"yaml roto: {type(e).__name__}",
        }

    # extraer_yaml garantiza dict; la forma fina del fence la reportamos aparte.
    if forma == "fence-yaml":
        parseo = "dict"
    elif forma == "fence-genérico":
        parseo = "fence-genérico"
    else:
        parseo = "yaml-pelado"
    if "verdict" not in datos:
        return {
            "parseo": parseo,
            "verdict_crudo": None,
            "valido": False,
            "shape": "sin clave verdict",
        }

    crudo_verdict = datos["verdict"]
    valido = crudo_verdict in VERDICTS_VALIDOS
    if valido:
        shape = "ok" if crudo_verdict == "ok" else "retry"
    else:
        # etiqueta corta y legible de la forma inválida real
        shape = f"{crudo_verdict!r} (inválido)"
    return {
        "parseo": parseo,
        "verdict_crudo": crudo_verdict,
        "valido": valido,
        "shape": shape,
    }


def correr_sonda(preguntas_ids=None):
    """Corre responder_con_juez por cada víctima con el wrapper puesto.

    Devuelve (registros, tabla_shapes): registros = una entrada por llamada
    del Judge; tabla_shapes = [(shape, conteo), ...] ordenada desc."""
    preguntas = leer_preguntas()
    ids = preguntas_ids or IDS_VICTIMAS

    registros = []
    # contexto mutable: qué pregunta está corriendo el flujo ahora.
    ctx = {"id": None}
    call_llm_original = juez.call_llm

    def wrapper(prompt):
        respuesta = call_llm_original(prompt)
        es_judge = MARCA_JUDGE in prompt
        registros.append({
            "pregunta_id": ctx["id"],
            "rol": "judge" if es_judge else "draft",
            "crudo": respuesta,
            "es_judge": es_judge,
        })
        return respuesta

    juez.call_llm = wrapper
    errores = {}
    try:
        for pid in ids:
            if pid not in preguntas:
                print(f"⚠️  pregunta id desconocida: {pid!r} (se saltea)")
                continue
            ctx["id"] = pid
            try:
                juez.responder_con_juez(preguntas[pid])
            except Exception as e:  # noqa: BLE001 — la sonda NO se muere: sigue
                errores[pid] = f"{type(e).__name__}: {e}"
                print(f"  ↯ {pid}: {type(e).__name__}: {e} (sigo)")
    finally:
        juez.call_llm = call_llm_original

    # clasificar SOLO las respuestas del Judge (las del Draft no llevan verdict)
    filas = []
    for reg in registros:
        if not reg["es_judge"]:
            continue
        info = clasificar(reg["crudo"])
        filas.append({
            "pregunta_id": reg["pregunta_id"],
            "parseo": info["parseo"],
            "verdict_crudo": info["verdict_crudo"],
            "valido": info["valido"],
            "shape": info["shape"],
        })

    return filas, errores


def escribir_salida(filas, fecha=None):
    fecha = fecha or date.today().isoformat()
    salida = RAIZ / "salidas" / "evals" / f"verdict_shapes_{fecha}.jsonl"
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8") as f:
        for fila in filas:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return salida


def tabla_shapes(filas):
    """[(shape, conteo), ...] ordenada por conteo desc, luego shape."""
    conteo = {}
    for fila in filas:
        conteo[fila["shape"]] = conteo.get(fila["shape"], 0) + 1
    return sorted(conteo.items(), key=lambda kv: (-kv[1], kv[0]))


def main():
    filas, errores = correr_sonda()
    salida = escribir_salida(filas)

    n = len(filas)
    validas = sum(1 for f in filas if f["valido"])
    invalidas = n - validas

    print()
    print("=== Sonda del verdict del juez (exp/21, fase A) ===")
    print(f"respuestas del Judge: {n}")
    print(f"válidas: {validas}   inválidas: {invalidas}")
    if errores:
        print(f"preguntas que levantaron (atrapadas): {len(errores)}")
        for pid, err in errores.items():
            print(f"  - {pid}: {err}")
    print()
    print("shape                              conteo")
    print("---------------------------------  ------")
    for shape, c in tabla_shapes(filas):
        print(f"{shape:<33}  {c:>6}")
    print()
    print(f"escrito: {salida}")

    if invalidas == 0:
        print()
        print("⚠️  0 formas inválidas: la mala suerte dio 0. Correr una")
        print("    segunda vuelta (tasa esperada ~20%: con 8-16 evaluaciones")
        print("    se esperan 2-3 capturas).")


if __name__ == "__main__":
    main()
