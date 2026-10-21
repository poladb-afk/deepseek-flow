"""Estilo humano del código: el harness no vuelve a la "firma" de la IA.

Evidencia y fuentes completas en
`docs/informes/codigo_ia_vs_humano_2026-10-19.md`. En corto:

- los papers miden que el código de agentes es más verboso y defensivo
  ("Show and Tell", arXiv 2511.13972; "SlopCodeBench", arXiv 2603.24755) y
  que el smell #1 en commits reales es el `except` amplio ("Debt Behind the
  AI Boom", arXiv 2603.28592);
- code-humanizer cataloga los tells estructurales: banners decorativos,
  docstrings de relleno, wrappers vacíos, comentarios que narran la línea;
- Claude Code docs: las instrucciones persistentes se mantienen cortas, un
  archivo inflado se ignora.

Acá se clavan SOLO los patrones deterministas y de bajo falso positivo. El
resto queda como review (AGENTS.md) o como ratchet (`excepts_amplios` en
`ratchet.py`). Los comentarios que explican el PORQUÉ son estilo del repo y
NO se tocan: el ruido es la decoración y la redundancia, no la explicación.
"""
import ast
import io
import re
import tokenize

from conftest import RAIZ

import ratchet

# Contexto de cada request: el prompt se mantiene corto. Con la directiva de
# forma mide ~900 chars; el techo deja aire para una o dos frases más.
LIMITE_PROMPT = 1400
_BANNER = re.compile(r"^#\s*[-=*#~_]{3,}\s*$")


def _fuentes():
    for ruta in ratchet.archivos_del_harness(RAIZ):
        yield ruta, ruta.read_text(encoding="utf-8")


def _fuentes_repo():
    """Todo el código versionado del repo (harness + tests + banco)."""
    patrones = ("*.py", "modules/*.py", "utils/*.py", "tests/test_*.py",
                "banco/*.py", "banco/probes/*.py")
    vistos = set()
    for patron in patrones:
        for ruta in RAIZ.glob(patron):
            if ruta.is_file() and ruta.name != "__init__.py":
                vistos.add(ruta)
    for ruta in sorted(vistos):
        yield ruta, ruta.read_text(encoding="utf-8")


def _normalizar(texto):
    return re.sub(r"[^a-z ]+", " ", texto.lower().replace("_", " ")).strip()


def test_sin_banners_decorativos():
    """Un banner (`# -----`) es el tell #14 de code-humanizer: no aporta y
    separa lo que el nombre de la función ya delimita. El harness llegó a 61
    banners en el código; el contrato lo deja en 0 y bloquea la reincidencia."""
    banners = []
    for ruta, src in _fuentes_repo():
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT and _BANNER.match(tok.string.strip()):
                banners.append(f"{ruta.relative_to(RAIZ)}:{tok.start[0]}")
    assert not banners, f"banners decorativos (ruido de IA): {banners}"


def test_sin_docstrings_de_relleno():
    """`def guardar(): \"\"\"Guardar.\"\"\"` no informa nada: el docstring va
    cuando agrega el porqué (o el contrato), no cuando repite el nombre."""
    relleno = []
    for ruta, src in _fuentes():
        for nodo in ast.walk(ast.parse(src)):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            doc = ast.get_docstring(nodo)
            if doc and _normalizar(doc) == _normalizar(nodo.name.lstrip("_")):
                relleno.append(f"{ruta.relative_to(RAIZ)}:{nodo.lineno}:{nodo.name}")
    assert not relleno, f"docstrings que repiten el nombre: {relleno}"


def test_sin_wrappers_vacios_sin_justificar():
    """Una función cuyo cuerpo es `return otro(...)` con los mismos argumentos
    no agrega nada, salvo que su docstring diga por qué existe."""
    vacios = []
    for ruta, src in _fuentes():
        for nodo in ast.walk(ast.parse(src)):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if ast.get_docstring(nodo):
                continue
            cuerpo = [
                n for n in nodo.body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and isinstance(n.value.value, str))
            ]
            if len(cuerpo) != 1 or not isinstance(cuerpo[0], ast.Return):
                continue
            llamada = cuerpo[0].value
            if not isinstance(llamada, ast.Call) or nodo.args.kwarg:
                continue
            argumentos = [a.arg for a in nodo.args.args if a.arg != "self"]
            pasados = [getattr(a, "id", getattr(a, "arg", None)) for a in llamada.args]
            if argumentos and pasados == argumentos:
                vacios.append(f"{ruta.relative_to(RAIZ)}:{nodo.lineno}:{nodo.name}")
    assert not vacios, f"wrappers que no agregan nada (documentá el porqué): {vacios}"


_JUSTIFICADO = re.compile(r"#\s*noqa:\s*BLE001\b\s*\(\s*[^)\s]")


def test_except_amplio_visible_y_justificado():
    """El `except` amplio es el smell #1 del código de IA (41.723 casos en
    commits reales, arXiv 2603.28592): está permitido solo en una frontera
    best-effort y con el motivo a la vista. Acotar a la excepción real es
    siempre mejor que atrapar `Exception`; el ratchet congela el total."""
    sin_justificar = []
    for ruta, src in _fuentes():
        for nodo in ast.walk(ast.parse(src)):
            if not isinstance(nodo, ast.ExceptHandler):
                continue
            amplio = nodo.type is None or (
                isinstance(nodo.type, ast.Name) and nodo.type.id in ("Exception", "BaseException"))
            if not amplio:
                continue
            linea = src.splitlines()[nodo.lineno - 1]
            if not _JUSTIFICADO.search(linea):
                sin_justificar.append(f"{ruta.relative_to(RAIZ)}:{nodo.lineno}: {linea.strip()}")
    assert not sin_justificar, (
        "except amplio sin motivo visible (acotalo a la excepción real o "
        f"documentá con `# noqa: BLE001 (motivo)`): {sin_justificar}")


def _test_asserta(nodo):
    """True si el test contiene una aserción explícita (assert, raises, fail)."""
    for sub in ast.walk(nodo):
        if isinstance(sub, (ast.Assert, ast.Raise)):
            return True
        if isinstance(sub, ast.With) and any("raises" in ast.dump(item) for item in sub.items):
            return True
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and (
                sub.func.attr in ("raises", "fail", "assert_")):
            return True
    return False


def test_todo_test_tiene_assert_o_raises():
    """Un test sin aserción es test slop: pasa siempre y no protege nada.
    La excepción "no levanta" también se asierta sobre un EFECTO observable."""
    sin_assert = []
    for ruta in sorted((RAIZ / "tests").glob("test_*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and nodo.name.startswith("test_") and not _test_asserta(nodo)):
                sin_assert.append(f"{ruta.name}:{nodo.lineno}:{nodo.name}")
    assert not sin_assert, f"tests sin aserción observable: {sin_assert}"


def test_prompt_forma_se_apaga_por_setting(monkeypatch):
    """PROMPT_FORMA=0 permite el A/B del banco sin duplicar el prompt."""
    import main

    monkeypatch.delenv("PROMPT_FORMA", raising=False)
    assert main.DIRECTIVA_FORMA in main.system_prompt()  # default encendido
    monkeypatch.setenv("PROMPT_FORMA", "0")
    assert main.DIRECTIVA_FORMA not in main.system_prompt()
    monkeypatch.setenv("PROMPT_FORMA", "1")
    assert main.DIRECTIVA_FORMA in main.system_prompt()


def test_prompt_fable_es_opt_in(monkeypatch):
    """PROMPT_FABLE=1 inyecta la directiva del método (exp/72 F0); el default 0
    deja el prompt de producción byte-idéntico."""
    import main

    monkeypatch.delenv("PROMPT_FABLE", raising=False)
    assert main.DIRECTIVA_FABLE not in main.system_prompt()
    monkeypatch.setenv("PROMPT_FABLE", "1")
    assert main.DIRECTIVA_FABLE in main.system_prompt()
    monkeypatch.setenv("PROMPT_FABLE", "0")
    assert main.DIRECTIVA_FABLE not in main.system_prompt()


def test_system_prompt_pide_codigo_minimo_y_no_crece():
    """La palanca de forma del producto: la directiva explícita de código
    mínimo baja 56–70% los tokens del código generado y se mantiene en los
    turnos siguientes, a diferencia de los ejemplos ("Show and Tell",
    arXiv 2511.13972). El prompt se mantiene corto: es contexto de cada
    request y uno inflado diluye las reglas (Claude Code docs)."""
    import main

    prompt = main.system_prompt()
    for frase in (
        "el mínimo que funciona",
        "sin defensas",
        "sin abstracciones especulativas",
        "Validación, seguridad y accesibilidad no se recortan",
    ):
        assert frase in prompt, f"el system prompt perdió la directiva de forma: {frase!r}"
    assert len(prompt) <= LIMITE_PROMPT, (
        f"el system prompt creció a {len(prompt)} chars (presupuesto {LIMITE_PROMPT}): "
        "lo que no cambia decisiones de forma va a AGENTS.md o a un skill bajo demanda"
    )
