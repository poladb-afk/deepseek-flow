"""Linter de reglas y deriva docs↔código (mecanismo de ruleward, adaptado).

`ruleward` lintea AGENTS.md/CLAUDE.md contra el código buscando conflicto,
duplicación, bloat y deriva. Acá se adopta lo **determinista y de alto valor**
para este repo, sin heurísticas de lenguaje natural:

- **bloat**: `AGENTS.md` es contexto de cada request y tiene presupuesto.
- **deriva**: toda ruta y todo test citados en `AGENTS.md` existen; cada regla
  no negociable nombra un gate que existe (una regla sin gate es prosa).
- **deriva del tablero**: cada test que `docs/estado.md` dice que cubre un
  hallazgo existe de verdad (la regla del tablero deja de ser honor system).

Lo que NO se adoptó: detección de conflictos por NLI y near-duplicates sobre
prosa (ruido en español; ver docs/informes/ratchets_y_reglas_agente_2026-10-19.md).
"""
import ast
import re

from conftest import RAIZ

AGENTS = RAIZ / "AGENTS.md"
ESTADO = RAIZ / "docs" / "estado.md"
LIMITE_LINEAS = 160
LIMITE_CHARS = 12000
DOCS_DE_ARRANQUE = ("docs/estado.md", "docs/design.md", "docs/bitacora.md", "docs/roadmap.md")

_RUTA = re.compile(r"[\w./-]+\.(?:py|sh|md|json|txt|ya?ml)")
_TEST = re.compile(r"test_[A-Za-z0-9_]+")
_TEST_ARCHIVO = re.compile(r"test_[A-Za-z0-9_]+\.py")


def _documento(ruta):
    assert ruta.is_file(), f"falta {ruta}"
    return ruta.read_text(encoding="utf-8")


def _tokens(texto):
    """Todo lo que está entre backticks: el inventario de artefactos citados."""
    return {m.group(1).strip() for m in re.finditer(r"`([^`\n]+)`", texto)}


def _defs_de_tests():
    """Los `def test_*` que existen, por nombre (AST: sin recolectar)."""
    nombres = set()
    for archivo in sorted((RAIZ / "tests").glob("test_*.py")):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        nombres |= {
            nodo.name for nodo in ast.walk(arbol)
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and nodo.name.startswith("test_")
        }
    return nombres


def _existe_ruta(token):
    """True/False si la ruta citada existe; None si es un patrón/ejemplo."""
    limpio = token[2:] if token.startswith("./") else token
    if any(marca in limpio for marca in ("*", "<", "…", "...")) or limpio.startswith(("/", "~")):
        return None
    return (RAIZ / limpio).exists()


def test_agents_md_respeta_el_presupuesto_de_contexto():
    """Bloat (ruleward): AGENTS.md es contexto por request, no un manual."""
    texto = _documento(AGENTS)
    lineas = len(texto.splitlines())
    assert lineas <= LIMITE_LINEAS, (
        f"AGENTS.md tiene {lineas} líneas y el presupuesto es {LIMITE_LINEAS}: "
        "mové el detalle a docs/ y dejá acá solo lo que cambia una decisión"
    )
    assert len(texto) <= LIMITE_CHARS, f"AGENTS.md tiene {len(texto)} chars (presupuesto: {LIMITE_CHARS})"


def test_toda_ruta_citada_en_agents_md_existe():
    """Deriva (ruleward): una ruta que no existe manda al agente a la nada."""
    faltan = [
        token for token in _tokens(_documento(AGENTS))
        if _RUTA.fullmatch(token) and _existe_ruta(token) is False
    ]
    assert not faltan, f"AGENTS.md cita rutas inexistentes: {sorted(faltan)}"


def test_todo_test_citado_en_agents_md_existe():
    """Deriva: un test citado como gate tiene que existir en la suite."""
    tokens = _tokens(_documento(AGENTS))
    defs = _defs_de_tests()
    faltan = [t for t in tokens if _TEST.fullmatch(t) and t not in defs]
    assert not faltan, f"AGENTS.md cita tests que no existen: {sorted(faltan)}"
    archivos = RAIZ / "tests"
    faltan_archivos = [
        t for t in tokens
        if _TEST_ARCHIVO.fullmatch(t) and not (archivos / t).exists() and not (RAIZ / t).exists()
    ]
    assert not faltan_archivos, f"AGENTS.md cita archivos de test inexistentes: {sorted(faltan_archivos)}"


def test_agents_md_nombra_los_docs_de_arranque():
    """El contrato sirve solo si manda a leer el tablero, el diseño y la bitácora."""
    tokens = _tokens(_documento(AGENTS))
    faltan = [doc for doc in DOCS_DE_ARRANQUE if doc not in tokens]
    assert not faltan, f"AGENTS.md dejó de nombrar docs de arranque: {faltan}"


def test_cada_regla_no_negociable_nombra_un_gate_que_existe():
    """Enforcement (git-agent-ratchet): sin gate, la regla es una sugerencia.

    Se parsea la tabla `| R<n> | regla | gate |`: cada fila tiene que nombrar al
    menos un artefacto vigente (archivo, test o script) que la haga cumplir.
    """
    texto = _documento(AGENTS)
    filas = [linea for linea in texto.splitlines() if re.match(r"\|\s*R\d+\s*\|", linea)]
    assert len(filas) >= 8, f"la tabla de reglas no negociables tiene {len(filas)} filas (se esperaban 8+)"
    defs = _defs_de_tests()
    for fila in filas:
        celdas = [celda.strip() for celda in fila.strip().strip("|").split("|")]
        assert len(celdas) >= 3, f"fila de tabla incompleta: {fila}"
        gate = celdas[2]
        tokens = re.findall(r"`([^`\n]+)`", gate)
        # Una variable de entorno (`HUMAN_RATCHET_BYPASS_KEY`) configura el gate:
        # se permite nombrarla, pero la regla igual tiene que nombrar el artefacto.
        artefactos = [t for t in tokens if not re.fullmatch(r"[A-Z][A-Z0-9_]+", t)]
        assert artefactos, f"la regla no nombra un artefacto de enforcement: {fila}"
        for token in artefactos:
            vigente = token in defs or (_RUTA.fullmatch(token) is not None and _existe_ruta(token))
            assert vigente, f"el gate citado no existe: {token} (en {fila})"


# deriva del tablero

def test_estado_cita_tests_que_existen():
    """La regla del tablero: un ✅ no puede apoyarse en un test fantasma."""
    tokens = _tokens(_documento(ESTADO))
    defs = _defs_de_tests()
    faltan = sorted(t for t in tokens if _TEST.fullmatch(t) and t not in defs)
    assert not faltan, f"docs/estado.md cita tests que ya no existen: {faltan}"


def test_estado_cita_archivos_de_test_que_existen():
    """Las filas viejas citan archivos enteros: también tienen que existir."""
    tokens = _tokens(_documento(ESTADO))
    archivos = RAIZ / "tests"
    faltan = sorted(
        t for t in tokens
        if _TEST_ARCHIVO.fullmatch(t) and not (archivos / t).exists() and not (RAIZ / t).exists()
    )
    assert not faltan, f"docs/estado.md cita archivos de test inexistentes: {faltan}"
