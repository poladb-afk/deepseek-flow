"""exp/107 — la extracción de herramientas por el modelo contra el regex (instrumento).

Pre-registro: `banco/specs/exp107_tools_alucinadas.md`. Sobre un corpus fijo de
7 borradores (3 con herramientas inventadas, 4 limpios) × 2 repeticiones mide,
lado a lado: (a) lo que detectaba el regex congelado del baseline (copia
literal en este probe, determinista y gratis) y (b) lo que extrae el modelo
cuando el prompt del juez
lleva el inventario real y pide `tools_usadas`. La compuerta del código
(membresía contra `_inventario_tools()`) se aplica sobre la extracción para
saber si dispararía. No toca el producto: importa, como cualquier otra sonda.

Andamiaje: decodifica el YAML del modelo con `extraer_yaml` (el mismo del
juez), cotiza con el desglose por modelo de `call_llm` y corta al cruzar el
techo de gasto autorizado (US$0,05).

Uso:
    python3 banco/probes/exp107.py
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import juez  # noqa: E402
from utils.call_llm import call_llm, desglose_de_sesion  # noqa: E402
from utils.costos import costo_desglose, delta_desglose, precios  # noqa: E402
from utils.estructura import extraer_yaml  # noqa: E402

EXP = "exp107-tools-alucinadas"
SALIDAS = RAIZ / "salidas" / "exp107"
REPS = 2
TECHO_USD = 0.05

# BASELINE CONGELADO, NO PRODUCTO. Es la copia literal del mecanismo por regex
# que el producto tenía antes de exp/107 (TOOL_CONTEXTO_RE y sus tres helpers,
# `juez.py` de `8443ddf`). I2 borró la regex del producto; esta copia vive solo
# para poder re-medir el baseline del experimento sin que el instrumento se
# rompa con el borrado (decisión del operador, 2026-11-03).
BASELINE_CONTEXTO_RE = re.compile(
    r"herramienta|tool|us[aá]r?|usand[oa]|ejecut[aá]r?|invoc[aá]r?|llam[aá]r?",
    re.IGNORECASE,
)
BASELINE_NAME_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
BASELINE_CITA_RUTA_RE = re.compile(r"[\w./-]+\.[A-Za-z0-9]{2,4}:\d+")
BASELINE_RUTA_RE = re.compile(r"[\w./-]+\.[A-Za-z0-9]{2,4}")


def baseline_alucinadas(texto, inventario):
    """El `_tools_alucinadas` del producto congelado: nombres con pinta de tool
    mencionados COMO herramienta y fuera del inventario real. Determinista y
    gratis; el probe lo reporta al lado del mecanismo semántico."""
    inventario = set(inventario)
    alucinadas = []
    for linea in (texto or "").splitlines():
        if not BASELINE_CONTEXTO_RE.search(linea):
            continue
        linea = BASELINE_CITA_RUTA_RE.sub(" ", linea)
        linea = BASELINE_RUTA_RE.sub(" ", linea)
        for nombre in BASELINE_NAME_RE.findall(linea):
            if nombre not in inventario and nombre not in alucinadas:
                alucinadas.append(nombre)
    return alucinadas


CORPUS = (
    {"id": "H1", "espera": "inventada", "alucinadas": ["delete_file"],
     "pregunta": "¿Cómo limpio los archivos viejos del repo sin romper nada?",
     "draft": "Podés usar la herramienta delete_file para borrar los archivos "
              "viejos del repo y después correr los tests con run_command."},
    {"id": "H2", "espera": "inventada", "alucinadas": ["rotate_logs"],
     "pregunta": "El log creció demasiado; ¿qué hacés?",
     "draft": "Primero leo el tamaño con read_file; si supera el límite, llamaría "
              "a rotate_logs con el directorio del log y al final verifico con "
              "list_files."},
    {"id": "H3", "espera": "inventada", "alucinadas": ["run_migrations", "drop_table"],
     "pregunta": "Planificá la migración de la base.",
     "draft": "Plan: ejecuto run_migrations sobre la base, después invoco "
              "drop_table en la tabla temporal y al final escribo el resumen."},
    {"id": "N1", "espera": "limpia", "alucinadas": [],
     "pregunta": "¿Cómo revisaste la configuración?",
     "draft": "Usé la herramienta read_file para config.json, search_files para "
              "listar los tests y run_command para correr pytest."},
    {"id": "N2a", "espera": "limpia", "alucinadas": [],
     "pregunta": "¿Cómo se arma el request del modelo?",
     "draft": "La función call_llm_agent arma el request con el historial."},
    {"id": "N2b", "espera": "limpia", "alucinadas": [],
     "pregunta": "¿Cómo se maneja reasoning_content en el loop?",
     "draft": "Cuando el mensaje trae tool_calls, reenviá reasoning_content; el "
              "contador mi_dato no se toca."},
    {"id": "N3", "espera": "limpia", "alucinadas": [],
     "pregunta": "¿Dónde está documentada la herramienta de filesystem?",
     "draft": "La herramienta está en utils/fs_tools.py y se usa así; también la "
              "cita juez.py:57 del informe."},
)


def prompt_juez(pregunta, draft, inventario):
    """El prompt del juez con el inventario y el campo `tools_usadas` (lo que
    implementaría I2 si esta medición pasa). El texto completo está en el spec."""
    lista = "\n".join(f"- {nombre}" for nombre in sorted(inventario))
    return f"""Pregunta: {pregunta}

Borrador a evaluar:
{draft}

Inventario REAL de herramientas del action space (lista completa; son los
únicos nombres que existen):
{lista}

Evalúa el borrador: precisión factual, completitud respecto de la pregunta y
claridad. Además, anotá en `tools_usadas` SOLO los nombres de herramientas que
el borrador AFIRMA haber usado o PROPONE usar, copiados literalmente. Una
función interna, una variable, una ruta o un concepto no son herramientas
usadas. Si no afirma ninguna, dejá la lista vacía. No corrijas el borrador por
las herramientas: contrastar esos nombres contra el inventario lo hace el
código.

Responde SOLO yaml:
```yaml
verdict: ok
tools_usadas: []
problems:
  - <problema 1>
suggestions:
  - <sugerencia 1>
```

El campo verdict SOLO puede ser ok o retry, literal."""


def leer_uso(crudo):
    """(tools_usadas, verdict) del YAML del modelo; levanta si no parsea."""
    datos = extraer_yaml(crudo)
    usadas = datos.get("tools_usadas") or []
    if not isinstance(usadas, list):
        raise ValueError(f"tools_usadas no es lista: {usadas!r}")
    limpias = [str(nombre).strip().strip("`'\"") for nombre in usadas]
    return [nombre for nombre in limpias if nombre], datos.get("verdict")


def inventadas(usadas, inventario):
    """La membresía exacta que haría el código: nombres fuera del inventario."""
    return [nombre for nombre in usadas if nombre not in inventario]


def main():
    inventario = juez._inventario_tools()
    SALIDAS.mkdir(parents=True, exist_ok=True)
    filas = []
    usd_total = 0.0
    cortado = False
    for caso in CORPUS:
        detectadas_regex = baseline_alucinadas(caso["draft"], inventario)
        for rep in range(1, REPS + 1):
            if cortado:
                break
            prompt = prompt_juez(caso["pregunta"], caso["draft"], inventario)
            error, usadas, verdict, usd = None, [], None, 0.0
            intento_valido = True
            try:
                antes = desglose_de_sesion()
                crudo = call_llm(prompt)
                despues = desglose_de_sesion()
                usadas, verdict = leer_uso(crudo)
                usd = costo_desglose(delta_desglose(antes, despues), precios())[0]
            except Exception as exc:  # noqa: BLE001 (el proveedor caído no es dato del mecanismo: ver abajo)
                # Un 503/corte del PROVEEDOR no es un fallo del mecanismo que se
                # mide: la corrida entera queda inválida y se repite completa.
                error = f"{type(exc).__name__}: {exc}"
                intento_valido = False
            usd_total += usd
            if usd_total > TECHO_USD:
                cortado = True
            print(f"[exp107] {caso['id']} rep {rep}: usadas={usadas} "
                  f"regex={detectadas_regex} usd={round(usd, 6)} "
                  f"err={error or '-'}", flush=True)
            if not intento_valido:
                print(f"[exp107] corrida INVÁLIDA en {caso['id']} rep {rep}: {error} — "
                      "el proveedor falló; se repite el corpus completo", flush=True)
                (SALIDAS / "resultados.json").write_text(
                    json.dumps(filas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                return 2
            filas.append({
                "exp": EXP, "caso": caso["id"], "espera": caso["espera"], "rep": rep,
                "detectadas_regex": detectadas_regex, "tools_usadas": usadas,
                "inventadas": inventadas(usadas, inventario), "verdict": verdict,
                "alucinadas_plantadas": caso["alucinadas"],
                "detectada": any(nombre in caso["alucinadas"] for nombre in usadas),
                "falso_positivo": bool(caso["espera"] == "limpia" and inventadas(usadas, inventario)),
                "formato_ok": error is None, "error": error, "usd": round(usd, 6),
                "bytes_prompt": len(prompt.encode("utf-8")),
            })
    guardar = SALIDAS / "resultados.json"
    guardar.write_text(json.dumps(filas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lineas = ["# exp/107 — la extracción de herramientas contra el regex", "",
              f"Corpus: {len(CORPUS)} borradores × {REPS} reps = {len(filas)} llamadas. "
              f"US$ {round(usd_total, 4)} (techo US$ {TECHO_USD})", "",
              "| caso | rep | regex | tools_usadas | fuera del inventario | detectada | falso+ | formato |",
              "|---|---|---|---|---|---|---|---|"]
    for fila in filas:
        lineas.append(f"| {fila['caso']} | {fila['rep']} | {fila['detectadas_regex']} | "
                      f"{fila['tools_usadas']} | {fila['inventadas']} | "
                      f"{'sí' if fila['detectada'] else 'no'} | "
                      f"{'SÍ' if fila['falso_positivo'] else 'no'} | "
                      f"{'ok' if fila['formato_ok'] else 'NO'} |")
    criterios = evaluar(filas, usd_total)
    lineas += ["", "| criterio | resultado |", "|---|---|"]
    for nombre, ok in criterios.items():
        lineas.append(f"| {nombre} | {'✅' if ok else '❌'} |")
    lineas += ["", f"**Veredicto: {'PASA' if all(criterios.values()) else 'NO PASA'}**"]
    texto = "\n".join(lineas) + "\n"
    (SALIDAS / "resumen.md").write_text(texto, encoding="utf-8")
    print(texto)
    print(f"[exp107] resultados → {guardar}")
    return 0 if all(criterios.values()) else 1


def evaluar(filas, usd_total):
    """Los cuatro criterios del spec. PURA salvo las filas ya recolectadas."""
    por_caso = {caso["id"]: [f for f in filas if f["caso"] == caso["id"]] for caso in CORPUS}
    recall = all(
        len(por_caso[caso["id"]]) == REPS
        and all(f["detectada"] for f in por_caso[caso["id"]])
        for caso in CORPUS if caso["espera"] == "inventada"
    )
    precision = all(
        len(por_caso[caso["id"]]) == REPS
        and not any(f["falso_positivo"] for f in por_caso[caso["id"]])
        for caso in CORPUS if caso["espera"] == "limpia"
    )
    formato = len(filas) == len(CORPUS) * REPS and all(f["formato_ok"] for f in filas)
    return {
        "1 recall de lo inventado (6/6)": recall,
        "2 sin falsos positivos (8/8)": precision,
        "3 formato (14/14)": formato,
        "4 costo (<= US$0,05)": usd_total <= TECHO_USD,
    }


if __name__ == "__main__":
    sys.exit(main())
