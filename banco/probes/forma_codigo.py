"""exp/51 — la directiva de forma, medida: A/B sobre el system prompt.

Pregunta: `main.DIRECTIVA_FORMA` ("mínimo que funciona, sin defensas ni
docstrings no pedidos…") ¿hace que el modelo escriba código más chico y menos
ruidoso, o es folklore? La literatura dice que sí (Show & Tell, arXiv
2511.13972: −56/−70% de tokens con directivas explícitas y persistencia en el
turno siguiente), pero eso se midió con Gemini 2.5 Pro en una tarea; acá se
mide con NUESTRO modelo y NUESTRO prompt.

**Criterio PRE-REGISTRADO (antes de correr):**
- Éxito: la directiva baja la mediana de SLOC **y** la densidad de docstrings,
  sin aumentar la tasa de código que no parsea.
- Escepticismo: con n=4 por brazo por tarea una diferencia menor al 10% en
  SLOC no se considera evidencia de nada; se reporta como no concluyente.
- No se recorta nada a mano: mide el código tal como sale.

Uso: python3 banco/probes/forma_codigo.py [--runs 4]
Gasta centavos de API y no toca el repo: escribe en salidas/probes/ (ignorado).
"""
import argparse
import ast
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import main  # noqa: E402  (necesita la raíz en sys.path)
import utils.call_llm as llm  # noqa: E402  (cliente directo: queremos usage real)

TAREAS = [
    {
        "nombre": "csv_stats",
        "prompt": (
            "Escribí un módulo Python completo en un solo archivo que escanee un "
            "directorio buscando archivos CSV, valide que tengan las columnas "
            "timestamp, user_id, event_type y value, y escriba un JSON de salida "
            "con el total de eventos, los usuarios únicos y el promedio de value "
            "por event_type. Devolvé SOLO el código en un bloque ```python."
        ),
    },
    {
        "nombre": "config_loader",
        "prompt": (
            "Escribí un módulo Python completo en un solo archivo para leer la "
            "configuración de una app desde un JSON, con defaults y validación de "
            "las claves obligatorias. Devolvé SOLO el código en un bloque "
            "```python."
        ),
    },
]
BRAZOS = (("sin_forma", False), ("con_forma", True))
_METRICAS = ("sloc", "tokens_completion", "tokens_prompt", "funciones", "docstrings_densidad", "try",
             "except_amplios", "except_pass", "asserts", "none_checks",
             "comentarios", "banners", "docstrings_relleno")


def extraer_codigo(texto):
    """El primer bloque ```python (o ```) del response; None si no hay."""
    m = re.search(r"```(?:python)?\s*\n(.*?)```", texto or "", re.S)
    return m.group(1).strip() if m else None


def analizar_codigo(codigo):
    """Métricas objetivas del código generado (AST; sin LLM)."""
    lineas = codigo.splitlines()
    sloc = sum(1 for ln in lineas if ln.strip() and not ln.strip().startswith("#"))
    filas = {"sloc": sloc, "tokens_completion": None, "tokens_prompt": None,
             "funciones": 0, "docstrings_densidad": 0.0, "try": 0,
             "except_amplios": 0, "except_pass": 0, "asserts": 0,
             "none_checks": 0, "comentarios": len(lineas) - sloc,
             "banners": 0, "docstrings_relleno": 0}
    for ln in lineas:
        if re.match(r"^\s*#\s*[-=*#~_]{3,}\s*$", ln):
            filas["banners"] += 1
    arbol = ast.parse(codigo)
    funciones = [n for n in ast.walk(arbol) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    filas["funciones"] = len(funciones)
    con_doc = 0
    for fn in funciones:
        doc = ast.get_docstring(fn)
        if doc:
            con_doc += 1
            normal = re.sub(r"[^a-z ]+", " ", doc.lower().replace("_", " ")).strip()
            if normal == re.sub(r"[^a-z ]+", " ", fn.name.lstrip("_").replace("_", " ")).strip():
                filas["docstrings_relleno"] += 1
    filas["docstrings_densidad"] = round(con_doc / len(funciones), 3) if funciones else 0.0
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Try):
            filas["try"] += 1
            for handler in nodo.handlers:
                amplio = handler.type is None or (
                    isinstance(handler.type, ast.Name) and handler.type.id in ("Exception", "BaseException"))
                if amplio:
                    filas["except_amplios"] += 1
                if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                    filas["except_pass"] += 1
        elif isinstance(nodo, ast.Assert):
            filas["asserts"] += 1
        elif isinstance(nodo, ast.Compare) and any(
                isinstance(op, (ast.Is, ast.IsNot)) for op in nodo.ops) and any(
                isinstance(c, ast.Constant) and c.value is None for c in nodo.comparators):
            filas["none_checks"] += 1
    return filas


def llamar(sistema, prompt):
    """Una llamada de chat sin tools; devuelve (texto, usage) del proveedor."""
    respuesta = llm._client().chat.completions.create(
        model=llm._model(),
        messages=[{"role": "system", "content": sistema},
                  {"role": "user", "content": prompt}],
    )
    uso = respuesta.usage
    return respuesta.choices[0].message.content or "", {
        "completion_tokens": getattr(uso, "completion_tokens", None),
        "prompt_tokens": getattr(uso, "prompt_tokens", None),
    }


def mediana(rows, metrica):
    valores = [r["metricas"][metrica] for r in rows if r.get("metricas")]
    return round(statistics.median(valores), 3) if valores else None


def main_probe(argv=None):
    parser = argparse.ArgumentParser(description="A/B de la directiva de forma del system prompt (exp/51)")
    parser.add_argument("--runs", type=int, default=4, help="corridas por brazo por tarea (default 4)")
    parser.add_argument("--modelo", default=None,
                        help="override del modelo (env LLM_MODEL); default: el configurado (deepseek-flash)")
    args = parser.parse_args(argv)

    if args.modelo:
        os.environ["LLM_MODEL"] = args.modelo
    filas = []
    t0 = time.perf_counter()
    print(f"== exp/51 — modelo: {llm._model()} · runs={args.runs} ==", flush=True)
    for turno in range(args.runs):
        for tarea in TAREAS:
            for brazo, incluir_forma in BRAZOS:
                etiqueta = f"{tarea['nombre']}/{brazo}/r{turno + 1}"
                print(f"  · {etiqueta}…", flush=True)
                crudo, uso = llamar(main.system_prompt(incluir_forma=incluir_forma), tarea["prompt"])
                codigo = extraer_codigo(crudo)
                fila = {"tarea": tarea["nombre"], "brazo": brazo, "run": turno + 1,
                        "codigo": codigo, "error": None, "metricas": None}
                if not codigo:
                    fila["error"] = "sin bloque de código"
                else:
                    try:
                        fila["metricas"] = analizar_codigo(codigo)
                        fila["metricas"]["tokens_completion"] = uso["completion_tokens"]
                        fila["metricas"]["tokens_prompt"] = uso["prompt_tokens"]
                    except SyntaxError as exc:
                        fila["error"] = f"syntax: {exc}"
                filas.append(fila)

    salida = RAIZ / "salidas" / "probes"
    salida.mkdir(parents=True, exist_ok=True)
    destino = salida / f"forma_codigo_{datetime.now():%Y%m%d_%H%M%S}.json"
    destino.write_text(json.dumps({"fecha": datetime.now().isoformat(timespec="seconds"),
                                   "modelo": llm._model(), "runs": args.runs, "filas": filas},
                                  ensure_ascii=False, indent=1),
                       encoding="utf-8")

    print(f"\n== exp/51 — directiva de forma (n={args.runs} por brazo y tarea) ==")
    print(f"{'métrica':22} {'sin_forma':>10} {'con_forma':>10} {'delta':>9}")
    for metrica in _METRICAS:
        sin = mediana([f for f in filas if f["brazo"] == "sin_forma"], metrica)
        con = mediana([f for f in filas if f["brazo"] == "con_forma"], metrica)
        if sin is None or con is None:
            continue
        delta = f"{(con - sin) / sin * 100:+.0f}%" if sin else "n/a"
        print(f"{metrica:22} {sin:>10} {con:>10} {delta:>9}")
    errores = [f for f in filas if f["error"]]
    print(f"\nno parseables / sin bloque: {len(errores)}/{len(filas)}")
    print(f"artefacto: {destino.relative_to(RAIZ)} · {time.perf_counter() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main_probe())
