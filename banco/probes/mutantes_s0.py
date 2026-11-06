"""X183: mutantes en las fronteras de S0, como instrumento que corre el operador.

Cada mutante cambia UNA expresión de `utils/policy.py`, `utils/aprobaciones.py` o
`utils/fs_tools.py` (comparación invertida, `and`↔`or`, `not` quitado, booleano
negado, entero +1, `any`↔`all`) y corre la suite de S0 entera con `-x`. Si
ningún test falla, el mutante queda **vivo**: o hay un test que falta, o el
cambio es equivalente (no altera la conducta) y se anota por qué.

Retoma solo: el estado vive en un JSON y cada mutante se escribe al terminar,
así que cortarlo y volver a correrlo sigue donde quedó. No toca el árbol: cada
worker trabaja en su copia temporal.

En serie (`--workers 1`, el default): `tests/test_hitl.py` fija los puertos
8791–8794 y dos copias de esa suite en paralelo mueren por colisión, no por el
mutante (medido: 1 failed cada una en paralelo, 27 passed en serie).

Uso:
    python3 banco/probes/mutantes_s0.py [--workers 1] [--estado salidas/mutantes_s0/estado.json]
    python3 banco/probes/mutantes_s0.py --resumen     # solo lista los vivos
"""
import argparse
import ast
import copy
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
OBJETIVOS = {
    "utils/policy.py": [
        "_sin_dup_stderr", "_tokens", "_empieza_con", "_opciones_permitidas", "_opcion_permitida", "_toma_valor",
        "configuracion", "_segmento_es_auto", "_tiene_flag_peligroso", "_grupo_corto", "_saltar_opciones",
        "_sin_envoltorios", "_normalizar_rm", "_posicionales_git", "_global_git", "_globales_git", "_normalizar_git",
        "_normalizar", "_segmento_nivel", "irreversible", "segmentos", "_segmentos_para_la_negra", "ilegible",
        "declarado", "_subcomando_de_scope", "opaco", "clasificar"],
    "utils/aprobaciones.py": ["ruta_prohibida", "dentro_de_scope", "por_scope", "pedir_aprobacion"],
    "utils/fs_tools.py": ["sin_enlaces", "allowed_roots", "_raiz_que_contiene", "_resolve", "escribir_salida",
                          "escribir_atomico", "run_tool_call"],
}
# Los rápidos y específicos primero: con -x, un mutante que muere cuesta poco.
SUITE_S0 = [
    "tests/test_policy_bypass.py", "tests/test_policy_datos.py", "tests/test_comandos_reales.py",
    "tests/test_fs_tools.py", "tests/test_absurdos_funcionales.py", "tests/test_policy.py",
    "tests/test_auditoria_2026_10_26.py", "tests/test_delegar.py", "tests/test_hitl.py",
    "tests/test_gate_fractal.py", "tests/test_consolidacion.py", "tests/test_pendientes.py",
    "tests/test_banco.py", "tests/test_policy_generativo.py",
]
_OPUESTO = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE,
            ast.LtE: ast.Gt, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}


def mutaciones(nodo):
    """(descripción, nodo mutado) de un nodo de expresión."""
    if isinstance(nodo, ast.Compare):
        for i, op in enumerate(nodo.ops):
            if type(op) in _OPUESTO:
                otro = copy.deepcopy(nodo)
                otro.ops[i] = _OPUESTO[type(op)]()
                yield f"{type(op).__name__}→{_OPUESTO[type(op)].__name__}", otro
    elif isinstance(nodo, ast.BoolOp):
        otro = copy.deepcopy(nodo)
        otro.op = ast.Or() if isinstance(nodo.op, ast.And) else ast.And()
        yield ("and→or" if isinstance(nodo.op, ast.And) else "or→and"), otro
    elif isinstance(nodo, ast.UnaryOp) and isinstance(nodo.op, ast.Not):
        yield "sin not", copy.deepcopy(nodo.operand)
    elif isinstance(nodo, ast.Constant) and isinstance(nodo.value, bool):
        yield f"{nodo.value}→{not nodo.value}", ast.Constant(not nodo.value)
    elif isinstance(nodo, ast.Constant) and type(nodo.value) is int:
        yield f"{nodo.value}→{nodo.value + 1}", ast.Constant(nodo.value + 1)
    elif isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and nodo.func.id in ("any", "all"):
        otro = copy.deepcopy(nodo)
        nombre = "all" if nodo.func.id == "any" else "any"
        otro.func = ast.Name(id=nombre, ctx=ast.Load())
        yield f"{nodo.func.id}→{nombre}", otro


def enumerar(raiz=RAIZ):
    """Todos los mutantes que compilan, con su fuente completa ya mutada."""
    mutantes = []
    for archivo, funciones in OBJETIVOS.items():
        texto = (raiz / archivo).read_text(encoding="utf-8")
        crudo = texto.encode()
        inicios = [0]
        for linea in texto.splitlines(keepends=True):
            inicios.append(inicios[-1] + len(linea.encode()))
        for funcion in ast.parse(texto).body:
            if not (isinstance(funcion, ast.FunctionDef) and funcion.name in funciones):
                continue
            for nodo in ast.walk(funcion):
                if not isinstance(nodo, ast.expr):
                    continue
                for desc, otro in mutaciones(nodo):
                    # Un nodo del AST parseado siempre trae posiciones; el assert
                    # es para el chequeo de tipos, no una defensa en runtime.
                    assert nodo.lineno is not None and nodo.end_lineno is not None
                    assert nodo.col_offset is not None and nodo.end_col_offset is not None
                    ini = inicios[nodo.lineno - 1] + nodo.col_offset
                    fin = inicios[nodo.end_lineno - 1] + nodo.end_col_offset
                    fuente = crudo[:ini] + f"({ast.unparse(otro)})".encode() + crudo[fin:]
                    try:
                        compile(fuente, archivo, "exec")
                    except SyntaxError:
                        continue
                    mutantes.append({"id": f"{archivo}:{nodo.lineno}:{nodo.col_offset}:{desc}", "archivo": archivo,
                                     "funcion": funcion.name, "linea": nodo.lineno, "desc": desc,
                                     "original": (ast.get_source_segment(texto, nodo) or "")[:120],
                                     "fuente": fuente.decode()})
    return mutantes


def correr_suite(raiz, timeout=180):
    """("vivo"|"muerto", primer test que falló)."""
    env = {**os.environ, "PREGUNTAS_LOG": "0", "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *SUITE_S0],
                           cwd=raiz, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return "muerto", "timeout"
    if r.returncode == 0:
        return "vivo", ""
    fallo = [linea for linea in r.stdout.splitlines() if linea.startswith(("FAILED", "ERROR"))]
    return "muerto", (fallo[0] if fallo else r.stdout[-160:])[:200]


def _copias(n):
    copias = []
    for i in range(n):
        destino = Path(tempfile.mkdtemp(prefix=f"mutantes_s0_{i}_")) / "r"
        shutil.copytree(RAIZ, destino, ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", ".cobertura", ".hypothesis", "salidas", ".runs", ".modelos"))
        copias.append(destino)
    return copias


def correr(estado_ruta, workers):
    estado: dict = json.loads(estado_ruta.read_text(encoding="utf-8")) if estado_ruta.exists() else {"resultados": {}}
    mutantes = enumerar()
    estado["total"] = len(mutantes)
    pendientes = [m for m in mutantes if m["id"] not in estado["resultados"]]
    print(f"[mutantes_s0] {len(mutantes)} mutantes, {len(pendientes)} pendientes, {workers} workers", flush=True)
    copias = _copias(workers)
    if "control" not in estado:
        estado["control"] = correr_suite(copias[0])[0]
        if estado["control"] != "vivo":
            raise SystemExit("[mutantes_s0] el control (sin mutar) no pasa: arreglá la suite antes de medir")
    libres = queue.Queue()
    for copia in copias:
        libres.put(copia)
    inicio = time.time()

    def uno(mutante):
        copia = libres.get()
        try:
            ruta = copia / mutante["archivo"]
            original = ruta.read_text(encoding="utf-8")
            ruta.write_text(mutante["fuente"], encoding="utf-8")
            try:
                resultado, detalle = correr_suite(copia)
            finally:
                ruta.write_text(original, encoding="utf-8")
            fila = {k: v for k, v in mutante.items() if k not in ("fuente", "id")}
            return mutante["id"], {**fila, "estado": resultado, "detalle": detalle}
        finally:
            libres.put(copia)

    estado_ruta.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(workers) as pool:
        for i, (clave, fila) in enumerate(pool.map(uno, pendientes), 1):
            estado["resultados"][clave] = fila
            estado_ruta.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
            if i % 10 == 0:
                print(f"  {i}/{len(pendientes)} en {round(time.time() - inicio)} s", flush=True)
    for copia in copias:
        shutil.rmtree(copia.parent, ignore_errors=True)
    resumen(estado)


def resumen(estado):
    filas = estado["resultados"].values()
    vivos = sorted((f for f in filas if f["estado"] == "vivo"), key=lambda f: (f["archivo"], f["linea"]))
    print(f"[mutantes_s0] {len(estado['resultados'])}/{estado['total']} medidos · {len(vivos)} vivos")
    for f in vivos:
        print(f"  {f['archivo']}:{f['linea']} {f['funcion']} {f['desc']} | {f['original']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mutantes en las fronteras de S0 (X183)")
    # Serial por defecto: `tests/test_hitl.py` fija los puertos 8791–8794 y en
    # paralelo los mutantes morirían por colisión, no por el mutante.
    parser.add_argument("--workers", type=int, default=1,
                        help="en serie: test_hitl.py fija 8791–8794 y en paralelo moriría por colisión")
    parser.add_argument("--estado", default=str(RAIZ / "salidas" / "mutantes_s0" / "estado.json"))
    parser.add_argument("--resumen", action="store_true", help="solo lista los vivos del estado guardado")
    args = parser.parse_args(argv)
    estado_ruta = Path(args.estado)
    if args.resumen:
        resumen(json.loads(estado_ruta.read_text(encoding="utf-8")))
        return
    correr(estado_ruta, max(1, args.workers))


if __name__ == "__main__":
    main()
