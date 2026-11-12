#!/usr/bin/env python3
"""Ratchet de métricas estructurales — "la regla no cambió, cambió el costo de romperla".

Mecanismo adaptado de [git-agent-ratchet](https://github.com/monk-eee/git-agent-ratchet)
(MIT): una métrica se cuenta con CÓDIGO (AST, sin LLM, mismo árbol ⇒ mismo
resultado) y se compara contra un baseline versionado en
`ratchets/baseline.json`. La invariante es la del original: la métrica puede
mejorar o quedarse igual, **empeorar exige que un humano lo autorice**. Si
mejora, el baseline se reescribe solo y viaja en el mismo commit: el número
clavado es lo que impide que la deuda vuelva.

Por qué existe acá: las reglas blandas del repo (no bifurcar helpers, no
perder tests) vivían solo en prosa. El contrato para agentes está en
`AGENTS.md`; este archivo es el gate de las dos que se pueden contar.

Las métricas, una por clase de ratchet (las siete de elegancia, de X91, se
describen en `docs/elegancia.md`):

- `helpers_duplicados` (**menor mejor**, ratchet de DEUDA): funciones privadas
  `_foo` de nivel superior que aparecen en 2+ archivos del harness. Un agente
  que necesita un helper en otro archivo lo COPIA en vez de extraerlo a
  `utils/`; el ratchet congela el número y obliga a pagar la deuda cuando se
  toque ese módulo. Se juzga por movimiento: si el número no baja nunca, es
  una sinecura y hay que retirarlo.
- `tests_definidos` (**mayor mejor**, ratchet de COBERTURA): CASOS de test en
  `tests/*.py` — cada `@pytest.mark.parametrize` multiplica (argvalues no
  literales cuentan 1, límite declarado). `tests/inventario_tests.txt` es la foto del PR 4 y solo vigila
  esos 527 tests; los nuevos podían desaparecer en silencio. Este ratchet no
  deja que el total baje sin una decisión humana explícita.
- `codigo_muerto_privado` (**menor mejor**, ratchet de RUIDO): funciones y
  clases privadas de nivel superior sin NINGUNA referencia en el código
  (tests y banco cuentan como referencia). Es el tell de "código por si
  acaso": helpers especulativos que ningún camino llama.
- `cuerpos_duplicados` (**menor mejor**, ratchet de RUIDO): cuerpos de
  función idénticos tras renombrar argumentos/variables locales (>=3
  sentencias). Detecta la reimplementación con otro nombre — el "signature
  tell" que el conteo por nombre no ve.
- `cuerpos_test_duplicados` (**menor mejor**, ratchet de TEST SLOP): el mismo
  detector sobre `tests/`: tests copiados que piden parametrizar o fusionar.
- `excepts_amplios` (**menor mejor**, ratchet de RUIDO): handlers `except:`,
  `except Exception` y `except BaseException` de nivel superior. Es el smell
  #1 del código generado por IA (41.723 casos en el estudio de commits reales:
  "Broad exception handling") y el patrón D8 de code-humanizer: convierten un
  crash visible en corrupción invisible. No se prohíben (hay rutas
  best-effort legítimas): se congela el número y no puede crecer sin decisión
  humana. Evidencia y fuentes en docs/informes/codigo_ia_vs_humano_2026-10-19.md.

Guardia anti-bypass (el "Ratchet C" del original): el baseline solo puede
moverse en la dirección que mejora. Si el archivo versionado empeoró respecto
de HEAD —o HEAD respecto de HEAD~1, o sea un bypass ya commiteado— y no hay
CLAVE DEL OPERADOR válida, es bypass y falla. Sin esta guardia el ratchet
sería decorativo: el primer agente que lo vea editaría el JSON.

La clave es un SECRETO, no una bandera: `HUMAN_RATCHET_BYPASS_KEY` tiene que
coincidir con el sha256 commiteado en `ratchets/clave_operador.sha256`, leído
de la HISTORIA (HEAD y HEAD~1), no del disco. Medido (2026-10-26): con la
guardia vieja bastaba `HUMAN_RATCHET_BYPASS_KEY=1`, y un agente la exportó
"porque el operador ya había aprobado" aunque AGENTS.md lo prohibía. La regla
en prosa no alcanzó; la estructura sí: el agente no tiene el texto de la
clave, y cambiar el hash es un commit visible que, si llega junto con el
empeoramiento, exige la clave VIEJA. El operador la siembra una vez con
`python3 ratchet.py --sembrar-clave` (la lee de la terminal, no la guarda).

Uso:
    python3 ratchet.py                  # el gate (exit 0/1); auto-mejora el baseline
    python3 ratchet.py --no-escribir    # diagnóstico: compara y NO toca el baseline
    python3 ratchet.py --actualizar     # HUMANO (con la clave): acepta un empeoramiento deliberado
    python3 ratchet.py --sembrar-clave  # HUMANO: escribe el sha256 de su clave (commitealo)
    python3 ratchet.py --sin-guardia    # diagnóstico: saltea la guardia git
    python3 ratchet.py --cobertura      # etapa 5/6: cobertura por archivo (la corre calidad.sh)
    python3 ratchet.py --cobertura --sembrar-entorno  # siembra la sección del Python que corre
    python3 ratchet.py --pyright        # etapa 6/6: errores de tipo del producto (lee .pyright/datos.json)
    python3 ratchet.py --pyright --sembrar-pyright    # siembra el baseline de tipos si no existe
    python3 ratchet.py --pyright-entorno  # etapa 6/6: prepara el venv VACÍO fijo e imprime su intérprete

No tiene dependencias ni toca la red: es la palanca 3 de `calidad.sh` y de CI.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import getpass
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tokenize
import tomllib
from pathlib import Path

import coverage
import yaml

RAIZ = Path(__file__).resolve().parent
BASELINE = RAIZ / "ratchets" / "baseline.json"
BASELINE_COBERTURA = RAIZ / "ratchets" / "cobertura.json"
DATOS_COBERTURA = RAIZ / ".cobertura" / "datos"
BASELINE_PYRIGHT = RAIZ / "ratchets" / "pyright.json"
DATOS_PYRIGHT = RAIZ / ".pyright" / "datos.json"
CLAVE_BYPASS = "HUMAN_RATCHET_BYPASS_KEY"
HASH_CLAVE = RAIZ / "ratchets" / "clave_operador.sha256"

# Alcance: el harness que se entrega. `tests/` queda afuera (es el instrumento
# que mide) y `banco/` también (material de auditoría): duplicados ahí no son
# deuda del producto.
PATRONES = ("*.py", "modules/*.py", "utils/*.py")
ARCHIVOS_IGNORADOS = {"__init__.py"}


# inventario

def archivos_del_harness(raiz: Path) -> list[Path]:
    """Los `.py` del harness: raíz + `modules/` + `utils/`, sin `__init__.py`."""
    vistos = set()
    for patron in PATRONES:
        for ruta in raiz.glob(patron):
            if ruta.is_file() and ruta.name not in ARCHIVOS_IGNORADOS:
                vistos.add(ruta)
    return sorted(vistos)


def _relativa(ruta: Path, raiz: Path) -> str:
    return ruta.relative_to(raiz).as_posix()


# métricas

def escanear_helpers(raiz: Path) -> dict[str, list[str]]:
    """Nombres de funciones privadas de nivel superior definidos en 2+ archivos.

    `_foo` es privado por convención: si aparece en dos archivos, o es el
    mismo helper copiado (deuda) o son dos cosas distintas con el mismo nombre
    (confusión). El ratchet no obliga a unificarlas: congela el número y
    premia cualquier unificación futura.
    """
    definidos: dict[str, set[str]] = {}
    for ruta in archivos_del_harness(raiz):
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for nodo in arbol.body:
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not nodo.name.startswith("_") or nodo.name.startswith("__"):
                continue
            definidos.setdefault(nodo.name, set()).add(_relativa(ruta, raiz))
    duplicados = {nombre: sorted(archivos) for nombre, archivos in definidos.items() if len(archivos) >= 2}
    return dict(sorted(duplicados.items()))


def _casos_de_test(nodo: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Cuántos casos recolecta pytest para este test (parametrize literal)."""
    casos = 1
    for decorador in nodo.decorator_list:
        if not (isinstance(decorador, ast.Call) and isinstance(decorador.func, ast.Attribute)
                and decorador.func.attr == "parametrize"):
            continue
        if len(decorador.args) < 2:
            continue
        valores = decorador.args[1]
        if isinstance(valores, (ast.List, ast.Tuple)):
            casos *= max(1, len(valores.elts))
        # argvalues no literal (variable, fixture): no se puede contar → 1
    return casos


def escanear_tests(raiz: Path) -> dict[str, int]:
    """Casos de test por archivo (`def test_*` × parametrize, en tests/)."""
    por_archivo: dict[str, int] = {}
    for ruta in sorted((raiz / "tests").glob("test_*.py")):
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        cuenta = sum(
            _casos_de_test(nodo)
            for nodo in ast.walk(arbol)
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and nodo.name.startswith("test_")
        )
        por_archivo[_relativa(ruta, raiz)] = cuenta
    return dict(sorted(por_archivo.items()))


def escanear_excepts(raiz: Path) -> dict[str, list[int]]:
    """Handlers de excepción AMPLIOS por archivo (el smell de ruido #1 de la IA).

    Amplio = `except:`, `except Exception`, `except BaseException`. Un
    `except (OSError, ValueError)` no cuenta: nombra lo que espera manejar.
    """
    amplios: dict[str, list[int]] = {}
    for ruta in archivos_del_harness(raiz):
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        lineas = [
            nodo.lineno
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ExceptHandler)
            and (
                nodo.type is None
                or (isinstance(nodo.type, ast.Name) and nodo.type.id in ("Exception", "BaseException"))
            )
        ]
        if lineas:
            amplios[_relativa(ruta, raiz)] = sorted(lineas)
    return dict(sorted(amplios.items()))


# Referencias: el harness + tests + banco. Un helper privado usado solo por un
# test sigue siendo código vivo (el test es consumidor); docs/ no cuenta.
PATRONES_REFERENCIA = ("*.py", "modules/*.py", "utils/*.py", "tests/*.py",
                       "banco/*.py", "banco/probes/*.py")


def archivos_de_referencia(raiz: Path) -> list[Path]:
    vistos = set()
    for patron in PATRONES_REFERENCIA:
        for ruta in raiz.glob(patron):
            if ruta.is_file() and "__pycache__" not in str(ruta):
                vistos.add(ruta)
    return sorted(vistos)


def _rangos_privadas(raiz: Path) -> dict[str, list[tuple[Path, int, int]]]:
    """Nombre → (archivo, línea inicio, línea fin) de las privadas del harness."""
    rangos: dict[str, list[tuple[Path, int, int]]] = {}
    for ruta in archivos_del_harness(raiz):
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for nodo in arbol.body:
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and (
                    nodo.name.startswith("_") and not nodo.name.startswith("__")):
                rangos.setdefault(nodo.name, []).append((ruta, nodo.lineno, nodo.end_lineno or nodo.lineno))
    return rangos


def _nombre_leido(nodo) -> str | None:
    """El nombre que un nodo LEE (`x` o `obj.x`), o None si no lee ninguno."""
    if isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Load):
        return nodo.id
    if isinstance(nodo, ast.Attribute) and isinstance(nodo.ctx, ast.Load):
        return nodo.attr
    return None


def escanear_muertas(raiz: Path) -> list[str]:
    """Privadas de nivel superior sin ninguna referencia fuera de su definición.

    La recursión propia no cuenta como uso: una función que solo se llama a sí
    misma está muerta igual.
    """
    rangos = _rangos_privadas(raiz)
    usos = dict.fromkeys(rangos, 0)
    for ruta in archivos_de_referencia(raiz):
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for nodo in ast.walk(arbol):
            nombre = _nombre_leido(nodo)
            if nombre not in usos:
                continue
            dentro_de_si = any(
                ruta == archivo and inicio <= nodo.lineno <= fin
                for archivo, inicio, fin in rangos[nombre]
            )
            if not dentro_de_si:
                usos[nombre] += 1
    muertas = []
    for nombre, contador in sorted(usos.items()):
        if contador:
            continue
        for archivo, inicio, _ in rangos[nombre]:
            muertas.append(f"{_relativa(archivo, raiz)}:{inicio}:{nombre}")
    return sorted(muertas)


class _NormalizarCuerpo(ast.NodeTransformer):
    """Renombra argumentos y variables locales; conserva llamadas y atributos.

    Así dos copias con nombres distintos colisionan, pero dos funciones que
    llaman a operaciones distintas (`json.loads` vs `yaml.safe_load`) no.
    Con `constantes=True` (tests) también se reemplazan los literales: los
    tests copiados difieren justo en los datos, y esa copia es el candidato a
    parametrizar.
    """

    def __init__(self, locales: set[str], constantes: bool = False):
        self.locales = locales
        self.constantes = constantes

    def visit_FunctionDef(self, nodo):  # pragma: no cover - el cuerpo se normaliza aparte
        return nodo

    def visit_Name(self, nodo):
        # locals renombradas tanto en lectura como en escritura: dos copias
        # con variables distintas colisionan; llamadas/atributos se conservan.
        if nodo.id in self.locales:
            nodo.id = "_v"
        return nodo

    def visit_Constant(self, nodo):
        if self.constantes:
            nodo.value = "_c"
        return nodo


def _cuerpo_normalizado(nodo: ast.FunctionDef | ast.AsyncFunctionDef,
                        constantes: bool = False) -> str | None:
    """Firma estructural del cuerpo (>=3 sentencias), o None si es muy corto."""
    cuerpo = [
        x for x in nodo.body
        if not (isinstance(x, ast.Expr) and isinstance(x.value, ast.Constant) and isinstance(x.value.value, str))
    ]
    if len(cuerpo) < 3:
        return None
    locales = {a.arg for a in nodo.args.args + nodo.args.kwonlyargs}
    for sub in ast.walk(nodo):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Param)):
            locales.add(sub.id)
    modulo = ast.Module(body=cuerpo, type_ignores=[])
    return ast.dump(_NormalizarCuerpo(locales, constantes=constantes).visit(modulo))


def escanear_cuerpos(raiz: Path) -> dict[str, list[str]]:
    """Grupos de cuerpos idénticos (renombrando locales) en 2+ funciones."""
    grupos: dict[str, list[str]] = {}
    for ruta in archivos_del_harness(raiz):
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            firma = _cuerpo_normalizado(nodo)
            if firma is None:
                continue
            grupos.setdefault(firma, []).append(f"{_relativa(ruta, raiz)}:{nodo.lineno}:{nodo.name}")
    duplicados = {firma: sorted(filas) for firma, filas in grupos.items() if len(set(filas)) >= 2}
    return dict(sorted(duplicados.items()))


def escanear_cuerpos_tests(raiz: Path) -> dict[str, list[str]]:
    """Grupos de tests con el mismo cuerpo (normalizado) — test slop por copia."""
    grupos: dict[str, list[str]] = {}
    for ruta in sorted((raiz / "tests").glob("test_*.py")):
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not nodo.name.startswith("test_"):
                continue
            firma = _cuerpo_normalizado(nodo, constantes=True)
            if firma is None:
                continue
            grupos.setdefault(firma, []).append(f"{_relativa(ruta, raiz)}:{nodo.lineno}:{nodo.name}")
    duplicados = {firma: sorted(filas) for firma, filas in grupos.items() if len(set(filas)) >= 2}
    return dict(sorted(duplicados.items()))


def _metrica_cuerpos_tests(raiz: Path) -> tuple[int, dict[str, list[str]]]:
    detalle = escanear_cuerpos_tests(raiz)
    return sum(len(filas) for filas in detalle.values()), detalle


def _metrica_muertas(raiz: Path) -> tuple[int, list[str]]:
    detalle = escanear_muertas(raiz)
    return len(detalle), detalle


def _metrica_cuerpos(raiz: Path) -> tuple[int, dict[str, list[str]]]:
    detalle = escanear_cuerpos(raiz)
    return sum(len(filas) for filas in detalle.values()), detalle


def _nombre_calificado(ruta: Path) -> dict[int, str]:
    """{línea del def: "Clase.metodo"} para desambiguar nombres repetidos."""
    nombres: dict[int, str] = {}

    def visitar(nodo, prefijo):
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nombres[hijo.lineno] = prefijo + hijo.name
                visitar(hijo, prefijo + hijo.name + ".")
            elif isinstance(hijo, ast.ClassDef):
                visitar(hijo, prefijo + hijo.name + ".")
            else:
                visitar(hijo, prefijo)

    with contextlib.suppress(OSError, SyntaxError):
        visitar(ast.parse(ruta.read_text(encoding="utf-8")), "")
    return nombres


MAX_COMPLEJIDAD = 10  # X180: escalón desde 12


def escanear_complejidad(raiz: Path, umbral: int = MAX_COMPLEJIDAD) -> dict[str, int]:
    """Funciones del harness con McCabe > umbral, contadas por RUFF (C901).

    Usa el mismo conteo exacto que el gate (ruff pinneado) en vez de
    reimplementar la fórmula: la métrica creíble es la que coincide con la
    herramienta. Devuelve {"archivo:Clase.funcion": cc}.

    X180: se lee el JSON de ruff, no su texto. Con FORCE_COLOR=1 el texto
    viene pintado, ninguna línea matcheaba y la métrica daba 0 (medido)."""
    if shutil.which("ruff") is None:
        raise RuntimeError("ratchet: ruff no está en PATH (la métrica de complejidad lo usa)")
    rutas = [str(ruta) for ruta in archivos_del_harness(raiz)]
    proceso = subprocess.run(
        ["ruff", "check", "--isolated", "--select", "C901",
         "--config", f"lint.mccabe.max-complexity={umbral}",
         "--output-format", "json", *rutas],
        cwd=raiz, capture_output=True, text=True,
    )
    detalle = {}
    for hallazgo in json.loads(proceso.stdout or "[]"):
        coincidencia = re.match(r"`([^`]+)` is too complex \((\d+) > \d+\)", hallazgo["message"])
        if not coincidencia:
            continue
        funcion, complejidad = coincidencia.groups()
        ruta = raiz / Path(hallazgo["filename"]).relative_to(raiz.resolve())
        calificado = _nombre_calificado(ruta).get(hallazgo["location"]["row"], funcion)
        detalle[f"{_relativa(ruta, raiz)}:{calificado}"] = int(complejidad)
    return dict(sorted(detalle.items()))


CONTROL_ANIDADO = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try,
                   ast.With, ast.AsyncWith, ast.Match)


def _anidacion_maxima(nodo) -> int:
    """Máxima profundidad de control anidado DENTRO de la función (sin contar
    funciones/clases internas, que son otra unidad).

    `elif` NO suma: en el AST es un `If` dentro del `orelse`, pero es una
    cadena plana (contarlo inflaba funciones con dispatch por casos)."""
    sin_contar = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)

    def profundidad(actual, nivel):
        mejor = nivel
        for campo, valor in ast.iter_fields(actual):
            hijos = valor if isinstance(valor, list) else [valor]
            for hijo in hijos:
                if not isinstance(hijo, ast.AST) or isinstance(hijo, sin_contar):
                    continue
                es_elif = isinstance(hijo, ast.If) and isinstance(actual, ast.If) and campo == "orelse"
                es_control = isinstance(hijo, (*CONTROL_ANIDADO, ast.If))
                interno = nivel + (1 if es_control and not es_elif else 0)
                mejor = max(mejor, profundidad(hijo, interno))
        return mejor

    return profundidad(nodo, 0)


def escanear_anidacion(raiz: Path, maximo: int = 3) -> dict[str, int]:
    """Funciones del harness con anidación de control > maximo (deuda de
    guard clauses). Puro AST; devuelve {"archivo:funcion": profundidad}."""
    detalle = {}
    for ruta in archivos_del_harness(raiz):
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        calificados = _nombre_calificado(ruta)
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            profundidad = _anidacion_maxima(nodo)
            if profundidad > maximo:
                nombre = calificados.get(nodo.lineno, nodo.name)
                detalle[f"{_relativa(ruta, raiz)}:{nombre}"] = profundidad
    return dict(sorted(detalle.items()))


def _metrica_complejidad(raiz: Path) -> tuple[int, dict[str, int]]:
    detalle = escanear_complejidad(raiz)
    return len(detalle), detalle


def _metrica_anidacion(raiz: Path) -> tuple[int, dict[str, int]]:
    detalle = escanear_anidacion(raiz)
    return len(detalle), detalle


def _metrica_helpers(raiz: Path) -> tuple[int, dict[str, list[str]]]:
    detalle = escanear_helpers(raiz)
    return sum(len(archivos) for archivos in detalle.values()), detalle


def _metrica_tests(raiz: Path) -> tuple[int, dict[str, int]]:
    detalle = escanear_tests(raiz)
    return sum(detalle.values()), detalle


def _metrica_excepts(raiz: Path) -> tuple[int, dict[str, list[int]]]:
    detalle = escanear_excepts(raiz)
    return sum(len(lineas) for lineas in detalle.values()), detalle


# elegancia (fase 0 del refactor, docs/elegancia.md): lo que el refactor tiene
# que bajar, congelado antes de tocar nada. Las claves de detalle son el ÁMBITO
# de nivel superior (función, clase o constante), no la línea: las líneas se
# mueven con cualquier edición y los nombres no.

CORE = ("nodes.py", "flow.py", "main.py")  # más utils/: lo que no es un módulo
LABORATORIO = {"banco", "BANCO", "DELEGADO"}

# X142: el LÍMITE producto/laboratorio. El producto es lo que el operador
# usa: el chat con su kernel (núcleo) y sus capacidades. El laboratorio
# MIDE (banco/, fable/, tests/, docs/ y las herramientas de medición de la
# raíz). No hace falta separarlos físicamente: el producto ya corre solo
# (todo subcomando de laboratorio se monta perezoso desde main) y no lo
# nombra (`producto_conoce_lab` = 0); lo que faltaba era poder CONTARLO —
# ese número es `lineas_del_producto` y solo puede bajar (P1).
PRODUCTO_RAIZ = (
    # núcleo
    "main.py", "flow.py", "nodes.py", "supervisor.py",
    # capacidades del producto (las que expone main y el chat)
    "informe.py", "juez.py", "juez_lote.py", "fable_judge.py", "auditoria.py",
    "research.py", "debate.py", "rag.py", "delegar.py", "heartbeat.py",
    "resume.py", "mcp_server.py", "visor.py", "effective_n.py",
)
LABORATORIO_RAIZ = (
    "ratchet.py", "evals.py", "bench_juez.py", "replay.py",
    "carga_trazas.py", "triaje_trazas.py", "minar_errores.py", "tablero.py",
    "instrumentos.py",
)

LECTORES_SETTINGS = (
    r'_(?:setting|entero|real|umbral)\(\s*["\']([A-Z][A-Z0-9_]+)["\']',
    r'environ(?:\.get)?\(\s*["\']([A-Z][A-Z0-9_]+)["\']',
    r'environ\[\s*["\']([A-Z][A-Z0-9_]+)',
    r'setting(?:_modelo)?\s*=\s*["\']([A-Z][A-Z0-9_]+)["\']',
    r'(?:disponible|agente)\(\s*["\']([A-Z][A-Z0-9_]+)["\']',
)
METODOS_DE_NODO = {"prep", "exec", "post", "exec_fallback", "prep_async", "exec_async", "post_async"}
MAX_LINEAS_NODO = 40
MIN_VOCABULARIO = 5
_TILDE = re.compile(r"[áéíóúñ]")
_PALABRA = re.compile(r"[a-záéíóúñü ]+")


def _arboles(raiz: Path):
    for ruta in archivos_del_harness(raiz):
        try:
            yield ruta, ast.parse(ruta.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue


def _nombre_de(sentencia) -> str:
    if isinstance(sentencia, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return sentencia.name
    objetivos = getattr(sentencia, "targets", None) or [getattr(sentencia, "target", None)]
    nombres = [o.id for o in objetivos if isinstance(o, ast.Name)]
    return nombres[0] if nombres else "<módulo>"


def _contar_por_ambito(raiz: Path, arboles, es_hallazgo) -> dict[str, int]:
    """{"archivo:ámbito": hallazgos}. `es_hallazgo(nodo, en_def)` recibe si el
    nodo vive dentro de una función o clase de nivel superior."""
    detalle: dict[str, int] = {}
    for ruta, arbol in arboles:
        for sentencia in arbol.body:
            en_def = isinstance(sentencia, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            cuenta = sum(1 for nodo in ast.walk(sentencia) if es_hallazgo(nodo, en_def))
            if cuenta:
                clave = f"{_relativa(ruta, raiz)}:{_nombre_de(sentencia)}"
                detalle[clave] = detalle.get(clave, 0) + cuenta
    return dict(sorted(detalle.items()))


def _importa_modulos(nodo, _en_def) -> bool:
    """`from modules.x import ...`: el CORE nombrando una capacidad concreta.
    `from modules import discover` es el registro y no cuenta."""
    if isinstance(nodo, ast.ImportFrom):
        return nodo.level == 0 and (nodo.module or "").startswith("modules.")
    return isinstance(nodo, ast.Import) and any(a.name.startswith("modules.") for a in nodo.names)


def escanear_core_importa_modulos(raiz: Path) -> dict[str, int]:
    """Imports de módulos concretos desde el CORE: con uno solo, borrar el
    archivo del módulo rompe el chat (la promesa "quitar = borrarlo")."""
    del_core = ((ruta, arbol) for ruta, arbol in _arboles(raiz)
                if _relativa(ruta, raiz) in CORE or _relativa(ruta, raiz).startswith("utils/"))
    return _contar_por_ambito(raiz, del_core, _importa_modulos)


def _es_del_laboratorio(modulo: str) -> bool:
    """`banco` o una pieza de LABORATORIO_RAIZ (X167: `modules/evals.py`
    importaba `evals` y la métrica no lo veía porque solo buscaba `banco`)."""
    raiz = modulo.split(".")[0]
    return raiz == "banco" or f"{raiz}.py" in LABORATORIO_RAIZ


def _toca_laboratorio(nodo, _en_def) -> bool:
    """Import del laboratorio o un literal CORTO (un nombre, no prosa) suyo:
    el producto decidiendo según si lo están midiendo, o dependiendo de lo
    que lo mide. Los subcomandos de laboratorio que `main` monta por nombre
    no son import y no cuentan."""
    if isinstance(nodo, ast.ImportFrom):
        return _es_del_laboratorio(nodo.module or "")
    if isinstance(nodo, ast.Import):
        return any(_es_del_laboratorio(a.name) for a in nodo.names)
    if isinstance(nodo, ast.keyword):
        return nodo.arg in LABORATORIO
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and len(nodo.value) <= 40:
        return nodo.value in LABORATORIO or "GROUND-TRUTH" in nodo.value.upper()
    return False


def escanear_producto_conoce_lab(raiz: Path) -> dict[str, int]:
    """Lo que mira es el PRODUCTO: las piezas de LABORATORIO_RAIZ (el ratchet
    incluido, que nombra al laboratorio para buscarlo) se importan entre sí
    sin contar."""
    producto = ((ruta, arbol) for ruta, arbol in _arboles(raiz)
                if _relativa(ruta, raiz) not in LABORATORIO_RAIZ)
    return _contar_por_ambito(raiz, producto, _toca_laboratorio)


def _es_lista_de_palabras(nodo) -> bool:
    elementos = getattr(nodo, "elts", [])
    textos = [e.value for e in elementos if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    if len(textos) < MIN_VOCABULARIO or len(textos) != len(elementos):
        return False
    return all(_PALABRA.fullmatch(t) for t in textos) and any(_TILDE.search(t) for t in textos)


def _patron_de_palabras(patron: str, sin_caso: bool = False) -> bool:
    """Una regex sin distinción de mayúsculas, con ≥5 alternativas y alguna tilde."""
    sin_caso = sin_caso or "(?i)" in patron
    return sin_caso and patron.count("|") >= MIN_VOCABULARIO - 1 and bool(_TILDE.search(patron))


def _es_regex_de_palabras(nodo) -> bool:
    funcion = nodo.func
    if not (isinstance(funcion, ast.Attribute) and isinstance(funcion.value, ast.Name)
            and funcion.value.id in ("re", "_re") and nodo.args):
        return False
    patron = nodo.args[0]
    if not (isinstance(patron, ast.Constant) and isinstance(patron.value, str)):
        return False
    banderas = ast.unparse(nodo.args[1:] + [k.value for k in nodo.keywords])
    sin_caso = "IGNORECASE" in banderas or bool(re.search(r"\bre\.I\b", banderas))
    return _patron_de_palabras(patron.value, sin_caso)


def _es_vocabulario(nodo, _en_def) -> bool:
    """Una colección de ≥5 palabras en español, o una regex sin distinción de
    mayúsculas con ≥5 alternativas y alguna tilde: decidir por palabras
    sueltas en vez de por un mecanismo general (el hardcodeo prohibido)."""
    if isinstance(nodo, (ast.Set, ast.List, ast.Tuple)):
        return _es_lista_de_palabras(nodo)
    return isinstance(nodo, ast.Call) and _es_regex_de_palabras(nodo)


def _vocabulario_de_skills(raiz: Path) -> dict[str, int]:
    """La `condicion` de `skills/*.yaml` decide igual que una regex del código
    (X112: el AST no la veía). Un YAML ilegible no cuenta: no es código."""
    detalle = {}
    for ruta in sorted((raiz / "skills").glob("*.yaml")):
        try:
            datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        condicion = datos.get("condicion") if isinstance(datos, dict) else None
        if isinstance(condicion, str) and _patron_de_palabras(condicion):
            detalle[f"{_relativa(ruta, raiz)}:condicion"] = 1
    return detalle


def escanear_vocabulario(raiz: Path) -> dict[str, int]:
    detalle = _contar_por_ambito(raiz, _arboles(raiz), _es_vocabulario)
    return dict(sorted({**detalle, **_vocabulario_de_skills(raiz)}.items()))


def _es_import_perezoso(nodo, en_def) -> bool:
    return en_def and isinstance(nodo, (ast.Import, ast.ImportFrom))


def escanear_imports_perezosos(raiz: Path) -> dict[str, int]:
    """Imports dentro de funciones: casi siempre un ciclo esquivado o una
    dependencia que el diseño no hizo explícita."""
    return _contar_por_ambito(raiz, _arboles(raiz), _es_import_perezoso)


def escanear_settings(raiz: Path) -> dict[str, list[str]]:
    """{SETTING: [archivos que lo leen]}. Cada setting es una rama que alguien
    tiene que entender; los brazos de A/B cerrados se borran con su rama."""
    detalle: dict[str, set[str]] = {}
    for ruta in archivos_del_harness(raiz):
        texto = ruta.read_text(encoding="utf-8")
        for patron in LECTORES_SETTINGS:
            for nombre in re.findall(patron, texto):
                detalle.setdefault(nombre, set()).add(_relativa(ruta, raiz))
    return {nombre: sorted(archivos) for nombre, archivos in sorted(detalle.items())}


def _clases_de_nodo(raiz: Path):
    """Las clases del harness con `prep`/`exec`/`post` (o sus variantes async)."""
    for ruta, arbol in _arboles(raiz):
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.ClassDef):
                continue
            metodos = {m.name for m in nodo.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
            if metodos & METODOS_DE_NODO:
                yield ruta, nodo


def _lineas_de_codigo(fuente: str) -> set[int]:
    """Líneas con al menos un token fuera de strings, comentarios y blancos.

    X134: el texto que el nodo imprime (docstrings, prompts, plantillas
    markdown y sus interpolaciones, aunque estén en un f-string multilínea)
    no es una arista escondida y no cuenta. Una línea de lógica que menciona
    strings (`if d.get("k") != "v":`) sí tiene tokens propios y cuenta."""
    lineas: set[int] = set()
    en_fstring = 0
    for token in tokenize.generate_tokens(io.StringIO(fuente).readline):
        if token.type == getattr(tokenize, "FSTRING_START", -1):
            en_fstring += 1
        elif token.type == getattr(tokenize, "FSTRING_END", -1):
            en_fstring = max(0, en_fstring - 1)
        elif not en_fstring and token.type in (tokenize.NAME, tokenize.NUMBER, tokenize.OP):
            lineas.add(token.start[0])
    return lineas


def _rango_de_lineas(nodo) -> range:
    """Las líneas físicas de la clase (Pyright ve `end_lineno` opcional)."""
    return range(nodo.lineno, (nodo.end_lineno or nodo.lineno) + 1)


def escanear_nodos_largos(raiz: Path, maximo: int = MAX_LINEAS_NODO) -> dict[str, int]:
    """Nodos (clases con prep/exec/post) de más de `maximo` líneas de CÓDIGO:
    un nodo que hace varias cosas esconde aristas que el grafo debería
    mostrar. X134: el texto impreso no es una arista; el conteo físico viejo
    queda en `escanear_nodos_fisicos` como diagnóstico no gateado."""
    fuentes: dict[Path, set[int]] = {}
    detalle = {}
    for ruta, nodo in _clases_de_nodo(raiz):
        if ruta not in fuentes:
            fuentes[ruta] = _lineas_de_codigo(ruta.read_text(encoding="utf-8"))
        codigo = fuentes[ruta]
        lineas = sum(1 for i in _rango_de_lineas(nodo) if i in codigo)
        if lineas > maximo:
            detalle[f"{_relativa(ruta, raiz)}:{nodo.name}"] = lineas
    return dict(sorted(detalle.items()))


def escanear_nodos_fisicos(raiz: Path) -> dict[str, int]:
    """El conteo histórico (líneas FÍSICAS de la clase), diagnóstico de X134:
    se conserva para comparar contra la definición vieja, no decide el
    semáforo."""
    detalle = {}
    for ruta, nodo in _clases_de_nodo(raiz):
        lineas = len(_rango_de_lineas(nodo))
        if lineas > MAX_LINEAS_NODO:
            detalle[f"{_relativa(ruta, raiz)}:{nodo.name}"] = lineas
    return dict(sorted(detalle.items()))


def escanear_lineas_del_producto(raiz: Path) -> dict[str, int]:
    """Líneas de CÓDIGO del PRODUCTO (X142): PRODUCTO_RAIZ + utils/ + modules/
    — el número que solo puede bajar (P1). El laboratorio (banco/, fable/,
    tests/, docs/, LABORATORIO_RAIZ) no entra; el texto impreso no cuenta
    (misma definición que `nodos_largos`, X134). Los skills YAML quedan
    fuera: los cuenta `vocabulario_hardcodeado` por su contenido y acá lo
    que se gatea es el código."""
    rutas = [raiz / nombre for nombre in PRODUCTO_RAIZ]
    rutas += sorted((raiz / "utils").glob("*.py"))
    rutas += sorted((raiz / "modules").glob("*.py"))
    detalle = {}
    for ruta in rutas:
        if ruta.is_file():
            detalle[_relativa(ruta, raiz)] = len(_lineas_de_codigo(
                ruta.read_text(encoding="utf-8")))
    return dict(sorted(detalle.items()))


def escanear_texto_de_prompt(raiz: Path) -> dict[str, int]:
    """Caracteres literales que pueden entrar al system prompt del chat: el
    f-string de `main.system_prompt` y cada `DIRECTIVA_*`. Es AST y no la
    llamada real porque el prompt incluye el CWD y las raíces (cambia por
    máquina); acá se mide solo el texto que escribió una persona."""
    ruta = raiz / "main.py"
    if not ruta.is_file():
        return {}
    detalle = {}
    for sentencia in ast.parse(ruta.read_text(encoding="utf-8")).body:
        nombre = _nombre_de(sentencia)
        if nombre.startswith("DIRECTIVA_") and isinstance(sentencia.value, ast.Constant):
            detalle[nombre] = len(sentencia.value.value)
        elif nombre == "system_prompt":
            retornos = [n.value for n in ast.walk(sentencia) if isinstance(n, ast.Return)]
            partes = [p for r in retornos if isinstance(r, ast.JoinedStr) for p in r.values]
            detalle[nombre] = sum(len(p.value) for p in partes if isinstance(p, ast.Constant))
    return dict(sorted(detalle.items()))


def _bytes_literales(nodo) -> int:
    """Los bytes UTF-8 de todo el texto literal bajo `nodo` (claves, valores y
    las partes fijas de un f-string). Lo interpolado no cuenta: depende de la
    máquina, igual que en `texto_de_prompt`."""
    return sum(len(n.value.encode("utf-8")) for n in ast.walk(nodo)
               if isinstance(n, ast.Constant) and isinstance(n.value, str))


# X198 (D1=A): lo que de verdad viaja en el primer request. Los `TOOLS` de los
# módulos ya no van (el chat los alcanza por el catálogo), así que cuentan el
# system prompt y estos dos archivos, nada más.
FIJO_DEL_REQUEST = ("utils/fs_tools.py", "utils/catalogo.py")


def escanear_bytes_primer_request(raiz: Path) -> dict[str, int]:
    """Lo fijo que viaja en CADA request antes del pedido (P1, X124): el texto
    del system prompt y los esquemas del set FIJO (CORE + catálogo y uso, X198).
    Los `TOOLS` de los módulos ya no viajan: entran por el catálogo, y contarlos
    acá medía un request que no existe. Se cuenta por AST, sin importar los
    módulos (uno opcional ausente no cambia la métrica) y sin la serialización
    JSON."""
    detalle = {f"main.py:{k}": v for k, v in escanear_texto_de_prompt(raiz).items()}
    for relativa in FIJO_DEL_REQUEST:
        ruta = raiz / relativa
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for sentencia in arbol.body:
            if _nombre_de(sentencia) == "TOOLS" and getattr(sentencia, "value", None) is not None:
                detalle[f"{relativa}:TOOLS"] = _bytes_literales(sentencia.value)
    return dict(sorted(detalle.items()))


LOOP = ("utils/kernel.py", "nodes.py", "flow.py")  # el loop del agente: uno solo desde S9b A′ (el chat corre sobre kernel.loop)


def escanear_lineas_del_loop(raiz: Path) -> dict[str, int]:
    """Líneas no vacías y que no son solo comentario del loop del agente (P1,
    X124). Los docstrings cuentan: también se leen."""
    detalle = {}
    for relativa in LOOP:
        ruta = raiz / relativa
        if ruta.is_file():
            lineas = ruta.read_text(encoding="utf-8").splitlines()
            detalle[relativa] = sum(1 for linea in lineas if linea.strip() and not linea.strip().startswith("#"))
    return detalle


ELEGANCIA = ("core_importa_modulos", "producto_conoce_lab", "vocabulario_hardcodeado",
             "settings_leidos", "imports_perezosos", "nodos_largos", "texto_de_prompt",
             "bytes_primer_request", "lineas_del_loop")


def _metrica_suma(escanear):
    def calcular(raiz: Path) -> tuple[int, dict]:
        detalle = escanear(raiz)
        return sum(detalle.values()), detalle
    return calcular


def _metrica_cantidad(escanear):
    def calcular(raiz: Path) -> tuple[int, dict]:
        detalle = escanear(raiz)
        return len(detalle), detalle
    return calcular


# direccion: `menor_mejor` = deuda (baja = mejora); `mayor_mejor` = cobertura
# (sube = mejora). Cada métrica declara su dirección y su descripción: el
# resultado se imprime loud y sin `--quiet` a propósito.
METRICAS: dict[str, dict] = {
    "helpers_duplicados": {
        "direccion": "menor_mejor",
        "descripcion": "helpers privados `_foo` bifurcados en 2+ archivos del harness",
        "calcular": _metrica_helpers,
    },
    "tests_definidos": {
        "direccion": "mayor_mejor",
        "descripcion": "casos de test en tests/ (parametrize incluido)",
        "calcular": _metrica_tests,
    },
    "codigo_muerto_privado": {
        "direccion": "menor_mejor",
        "descripcion": "privadas de nivel superior sin referencia (código por si acaso)",
        "calcular": _metrica_muertas,
    },
    "cuerpos_duplicados": {
        "direccion": "menor_mejor",
        "descripcion": "cuerpos idénticos con variables renombradas (reimplementación)",
        "calcular": _metrica_cuerpos,
    },
    "cuerpos_test_duplicados": {
        "direccion": "menor_mejor",
        "descripcion": "tests con el mismo cuerpo (candidatos a parametrizar)",
        "calcular": _metrica_cuerpos_tests,
    },
    "funciones_complejas": {
        "direccion": "menor_mejor",
        "conjunto": True,
        "descripcion": f"funciones con McCabe > {MAX_COMPLEJIDAD} (C901 repo-wide; era 12 hasta X180)",
        "calcular": _metrica_complejidad,
    },
    "funciones_anidadas": {
        "direccion": "menor_mejor",
        "conjunto": True,
        "descripcion": "funciones con anidación de control > 3 (guard clauses)",
        "calcular": _metrica_anidacion,
    },
    "excepts_amplios": {
        "direccion": "menor_mejor",
        "descripcion": "handlers `except:` / `except Exception` (el smell #1 del código de IA)",
        "calcular": _metrica_excepts,
    },
    "core_importa_modulos": {
        "direccion": "menor_mejor",
        "conjunto": True,
        "descripcion": "imports de modules.<x> desde el CORE (borrar un módulo rompe el chat)",
        "calcular": _metrica_suma(escanear_core_importa_modulos),
    },
    "producto_conoce_lab": {
        "direccion": "menor_mejor",
        "conjunto": True,
        "descripcion": "el producto nombra o importa al laboratorio (banco, LABORATORIO_RAIZ, BANCO, DELEGADO, GROUND-TRUTH)",
        "calcular": _metrica_suma(escanear_producto_conoce_lab),
    },
    "vocabulario_hardcodeado": {
        "direccion": "menor_mejor",
        "conjunto": True,
        "descripcion": "listas de palabras / regex de vocabulario que deciden por keywords",
        "calcular": _metrica_suma(escanear_vocabulario),
    },
    "settings_leidos": {
        "direccion": "menor_mejor",
        "conjunto": True,
        "descripcion": "settings distintos que lee el harness (cada uno es una rama)",
        "calcular": _metrica_cantidad(escanear_settings),
    },
    "imports_perezosos": {
        "direccion": "menor_mejor",
        "descripcion": "imports dentro de funciones (ciclos esquivados, dependencias ocultas)",
        "calcular": _metrica_suma(escanear_imports_perezosos),
    },
    "nodos_largos": {
        "direccion": "menor_mejor",
        "conjunto": True,
        "descripcion": (f"nodos de más de {MAX_LINEAS_NODO} líneas de código "
                        "(aristas escondidas en prep/post; el texto impreso no cuenta)"),
        "calcular": _metrica_cantidad(escanear_nodos_largos),
    },
    "texto_de_prompt": {
        "direccion": "menor_mejor",
        "descripcion": "chars literales del system prompt + directivas (el prompt no arregla conductas)",
        "calcular": _metrica_suma(escanear_texto_de_prompt),
    },
    "bytes_primer_request": {
        "direccion": "menor_mejor",
        "descripcion": "bytes literales fijos de cada request: system prompt + esquemas de tools (P1)",
        "calcular": _metrica_suma(escanear_bytes_primer_request),
    },
    "lineas_del_loop": {
        "direccion": "menor_mejor",
        "descripcion": "líneas de código del loop del agente: kernel + chat (P1; S9b las une)",
        "calcular": _metrica_suma(escanear_lineas_del_loop),
    },
    "lineas_del_producto": {
        "direccion": "menor_mejor",
        "descripcion": ("líneas de código del PRODUCTO (núcleo + capacidades + "
                        "utils/ + modules/; sin el laboratorio): el número que "
                        "solo puede bajar (P1, X142)"),
        "calcular": _metrica_suma(escanear_lineas_del_producto),
    },
}


# comparación

def comparar(actual: int, previo: int, direccion: str) -> str:
    """La decisión del ratchet: IGUAL / MEJORÓ / EMPEORÓ. Una sola función para
    que las dos direcciones (deuda y cobertura) no se contradigan."""
    if actual == previo:
        return "IGUAL"
    if direccion == "menor_mejor":
        return "MEJORÓ" if actual < previo else "EMPEORÓ"
    return "MEJORÓ" if actual > previo else "EMPEORÓ"


def _diag_helpers(actual: dict, previo: dict) -> list[str]:
    lineas = []
    for helper, archivos in actual.items():
        previos = previo.get(helper, [])
        if len(archivos) > len(previos):
            lineas.append(f"    {helper}: {', '.join(archivos)}")
    return lineas


def _diag_muertas(actual: dict, _previo: dict) -> list[str]:
    return [f"    {definicion}" for definicion in actual]


def _diag_cuerpos(actual: dict, _previo: dict) -> list[str]:
    return ["    ≈ " + " · ".join(grupo) for grupo in actual.values()]


def _diag_excepts(actual: dict, previo: dict) -> list[str]:
    lineas = []
    for archivo, lineas_actuales in actual.items():
        previas = previo.get(archivo, [])
        if len(lineas_actuales) > len(previas):
            lineas.append(f"    {archivo}: {len(previas)} → {len(lineas_actuales)} excepts amplios")
    return lineas


def _diag_tests(actual: dict, previo: dict) -> list[str]:
    lineas = []
    for archivo, cuenta in actual.items():
        previa = previo.get(archivo, 0)
        if cuenta < previa:
            lineas.append(f"    {archivo}: {previa} → {cuenta} tests")
    return lineas


def _diag_crecio(actual: dict, previo: dict) -> list[str]:
    """Las claves que crecieron (conteo o lista de archivos)."""
    def tamano(valor):
        return len(valor) if isinstance(valor, list) else (valor or 0)

    return [f"    {clave}: {tamano(previo.get(clave))} → {tamano(valor)}"
            for clave, valor in actual.items() if tamano(valor) > tamano(previo.get(clave))]


_DIAGNOSTICOS = {
    "helpers_duplicados": _diag_helpers,
    "codigo_muerto_privado": _diag_muertas,
    "cuerpos_duplicados": _diag_cuerpos,
    "cuerpos_test_duplicados": _diag_cuerpos,
    "excepts_amplios": _diag_excepts,
    **dict.fromkeys(ELEGANCIA, _diag_crecio),
}


def _diagnostico(nombre: str, actual: dict, previo: dict) -> list[str]:
    """Nombra QUÉ empeoró: un número sin causa no se puede arreglar.

    Tabla en vez de cadena de `if`: cada métrica tiene su diagnóstico chico y
    el default (tests por archivo) queda explícito."""
    return _DIAGNOSTICOS.get(nombre, _diag_tests)(actual, previo or {})


# baseline (I/O)

def cargar_baseline(ruta: Path) -> dict | None:
    """El baseline versionado, o None si todavía no existe (primera corrida).
    Ilegible o con forma rara = error ruidoso: no se regenera a ciegas."""
    if not ruta.is_file():
        return None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"ratchet: baseline ilegible en {ruta} ({exc}); corregilo o borralo para sembrar de nuevo"
        ) from exc
    if not isinstance(datos, dict) or not isinstance(datos.get("ratchets"), dict):
        raise SystemExit(f"ratchet: {ruta} no tiene la forma {{'ratchets': {{...}}}}")
    return datos


def guardar_baseline(datos: dict, ruta: Path) -> None:
    """JSON canónico (claves ordenadas, indent 2, newline final): el baseline es
    un dato versionado, no una preferencia de estilo. Sin timestamps: dos
    corridas sobre el mismo árbol tienen que dar los MISMOS bytes."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(datos, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ruta.write_text(texto, encoding="utf-8")


# guardia anti-bypass

def _texto_de_git(raiz: Path, ref: str, ruta: Path) -> str | None:
    """El archivo tal como estaba en `ref`, o None (sin git, sin archivo)."""
    try:
        relativa = ruta.resolve().relative_to(raiz.resolve()).as_posix()
        r = subprocess.run(["git", "-C", str(raiz), "show", f"{ref}:{relativa}"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def clave_valida(raiz: Path, clave: str | None, ruta_hash: Path | None = None) -> tuple[bool, str]:
    """(válida, motivo). La clave vale si su sha256 coincide con TODOS los
    hashes commiteados en HEAD y HEAD~1 (de la historia, no del disco):
    editar el archivo en el working tree no sirve, y un commit que cambia el
    hash junto con un empeoramiento exige la clave anterior. Sin hash
    commiteado no hay bypass posible (falla cerrado)."""
    ruta_hash = ruta_hash or raiz / "ratchets" / "clave_operador.sha256"
    if not (clave or "").strip():
        return False, f"sin {CLAVE_BYPASS}"
    hashes = {h.strip() for h in (_texto_de_git(raiz, ref, ruta_hash) for ref in ("HEAD", "HEAD~1")) if h}
    if not hashes:
        return False, ("no hay clave del operador commiteada (ratchets/clave_operador.sha256): "
                       "el operador la siembra con `python3 ratchet.py --sembrar-clave`")
    if any(sha256(clave.strip()) != h for h in hashes):
        return False, f"{CLAVE_BYPASS} no coincide con la clave del operador"
    return True, "clave del operador"


def sembrar_clave(ruta_hash: Path = HASH_CLAVE, salida=print, leer=None) -> int:
    """Pide la clave por la TERMINAL (getpass) y escribe solo su sha256."""
    leer = leer or getpass.getpass
    try:
        clave = leer("Clave del operador (no se guarda; solo su sha256): ").strip()
        repetida = leer("Repetila: ").strip()
    except (EOFError, KeyboardInterrupt, OSError):
        salida("[ratchet] sin terminal: la clave se siembra a mano, no desde un agente")
        return 1
    if not clave or clave != repetida or len(clave) < 12:
        salida("[ratchet] la clave tiene que coincidir y tener al menos 12 caracteres")
        return 1
    ruta_hash.parent.mkdir(parents=True, exist_ok=True)
    ruta_hash.write_text(sha256(clave) + "\n", encoding="utf-8")
    salida(f"[ratchet] hash sembrado en {ruta_hash.name}: commitealo (cambiarlo después es un commit visible)")
    return 0


def _baseline_de_git(raiz: Path, ref: str, ruta: Path) -> dict | None:
    """El baseline tal como estaba en `ref` (HEAD, HEAD~1). Best-effort: sin
    git, sin el archivo o con el ref fuera del clon (CI shallow), None."""
    texto = _texto_de_git(raiz, ref, ruta)
    try:
        datos = json.loads(texto) if texto is not None else None
    except json.JSONDecodeError:
        return None
    return datos if isinstance(datos, dict) else None


def hallazgos_bypass(en_disco: dict | None, en_head: dict | None, en_anterior: dict | None) -> list[str]:
    """La invariante: el baseline solo se mueve hacia la mejora. Compara la
    dirección que EMPEORA (deuda que sube, cobertura que baja) entre disco y
    HEAD, y entre HEAD y HEAD~1 (bypass ya commiteado)."""
    hallazgos = []
    comparaciones = (
        ("el baseline en disco", en_disco, "HEAD", en_head),
        ("el baseline commiteado en HEAD", en_head, "HEAD~1", en_anterior),
    )
    for etiqueta_actual, datos_actual, etiqueta_previa, datos_previos in comparaciones:
        if not isinstance(datos_actual, dict) or not isinstance(datos_previos, dict):
            continue
        for nombre, meta in METRICAS.items():
            actual = ((datos_actual.get("ratchets") or {}).get(nombre) or {}).get("metrica")
            previo = ((datos_previos.get("ratchets") or {}).get(nombre) or {}).get("metrica")
            if not isinstance(actual, int) or not isinstance(previo, int):
                continue
            if comparar(actual, previo, meta["direccion"]) == "EMPEORÓ":
                hallazgos.append(
                    f"{nombre}: {etiqueta_actual} ({actual}) empeoró respecto de {etiqueta_previa} ({previo})"
                )
    return hallazgos


def guardia_bypass(raiz: Path, ruta: Path, salida=print) -> bool:
    """True si hay que BLOQUEAR (bypass detectado sin clave del operador)."""
    hallazgos = hallazgos_bypass(
        cargar_baseline(ruta),
        _baseline_de_git(raiz, "HEAD", ruta),
        _baseline_de_git(raiz, "HEAD~1", ruta),
    )
    if not hallazgos:
        return False
    valida, motivo = clave_valida(raiz, os.environ.get(CLAVE_BYPASS))
    if valida:
        salida("[ratchet] bypass del operador (clave verificada): la guardia no bloquea")
        return False
    salida(f"[ratchet] BYPASS: el baseline empeoró respecto de la historia ({motivo}).")
    for linea in hallazgos:
        salida(f"    {linea}")
    salida(f"  Un agente no edita el baseline ni exporta {CLAVE_BYPASS}. Si el empeoramiento "
           "es deliberado, lo acepta el operador con SU clave (y --actualizar).")
    return True


# gate

def _resumen_metricas(datos: dict) -> str:
    return " · ".join(
        f"{nombre} {valor.get('metrica', '?')}" for nombre, valor in sorted((datos.get("ratchets") or {}).items())
    )


def _ruta_visible(ruta: Path, raiz: Path) -> str:
    try:
        return ruta.resolve().relative_to(raiz.resolve()).as_posix()
    except ValueError:
        return str(ruta)


def _reportar_nuevas(nombre: str, detalle_actual: dict, valor_previo: dict,
                     flecha: str, salida=print) -> bool:
    """Reporta funciones nuevas del conjunto (aunque el total no suba)."""
    if not isinstance(valor_previo.get("detalle"), dict):
        return False
    nuevos = sorted(set(detalle_actual) - set(valor_previo["detalle"]))
    if not nuevos:
        return False
    salida(f"[ratchet] {nombre}: {flecha} → EMPEORÓ "
           f"({len(nuevos)} función(es) nueva(s) en el conjunto)")
    for clave in nuevos:
        salida(f"    + {clave} ({detalle_actual[clave]})")
    return True


def _evaluar(actuales: dict, previo: dict | None, salida=print) -> tuple[bool, bool]:
    """Compara cada métrica contra el baseline y narra la decisión.

    Devuelve (empeoro, mejoro). Las métricas de CONJUNTO comparan además la
    identidad: un arreglo no habilita una función nueva compleja aunque el
    total baje."""
    empeoro = mejoro = False
    for nombre, meta in METRICAS.items():
        valor_previo = ((previo or {}).get("ratchets") or {}).get(nombre) or {}
        metrica_actual = actuales[nombre]["metrica"]
        if not isinstance(valor_previo.get("metrica"), int):
            salida(f"[ratchet] {nombre}: {metrica_actual} (sin baseline: se siembra)")
            continue
        decision = comparar(metrica_actual, valor_previo["metrica"], meta["direccion"])
        flecha = f"{valor_previo['metrica']} → {metrica_actual}"
        if meta.get("conjunto") and _reportar_nuevas(
                nombre, actuales[nombre]["detalle"], valor_previo, flecha, salida):
            empeoro = True
            continue
        if decision == "MEJORÓ":
            mejoro = True
            salida(f"[ratchet] {nombre}: {flecha} → MEJORÓ ({meta['descripcion']})")
        elif decision == "EMPEORÓ":
            salida(f"[ratchet] {nombre}: {flecha} → EMPEORÓ ({meta['descripcion']})")
            for linea in _diagnostico(nombre, actuales[nombre]["detalle"],
                                      valor_previo.get("detalle") or {}):
                salida(linea)
            empeoro = True
        else:
            salida(f"[ratchet] {nombre}: {metrica_actual} → IGUAL ({meta['descripcion']})")
    return empeoro, mejoro


def _escribir_baseline(nuevo, previo, ruta, raiz, escribir, actualizar, mejoro, salida) -> None:
    """Persiste el baseline cuando corresponde y lo narra (X180: salió de correr)."""
    if not escribir:
        salida("[ratchet] --no-escribir: baseline intacto")
        return
    if previo is not None and nuevo == previo and not actualizar:
        return
    guardar_baseline(nuevo, ruta)
    if previo is None:
        salida(f"[ratchet] SIN BASELINE: sembrado {_ruta_visible(ruta, raiz)} "
               f"({_resumen_metricas(nuevo)}); commitealo")
    elif mejoro:
        salida(f"[ratchet] baseline actualizado ({_ruta_visible(ruta, raiz)}); commitealo")


def correr(
    raiz: Path = RAIZ,
    ruta_baseline: Path = BASELINE,
    escribir: bool = True,
    guardia: bool = True,
    actualizar: bool = False,
    salida=print,
) -> int:
    """Corre las métricas y decide. Expuesto para tests y para `main.py ratchet`."""
    if guardia and guardia_bypass(raiz, ruta_baseline, salida=salida):
        return 1

    previo = cargar_baseline(ruta_baseline)
    actuales = {}
    for nombre, meta in METRICAS.items():
        metrica, detalle = meta["calcular"](raiz)
        actuales[nombre] = {"metrica": metrica, "detalle": detalle}
    nuevo = {"version": 1, "ratchets": {
        nombre: {"metrica": actuales[nombre]["metrica"], "detalle": actuales[nombre]["detalle"]}
        for nombre in METRICAS
    }}

    empeoro, mejoro = _evaluar(actuales, previo, salida)
    # X134: el número viejo (líneas físicas) no gatea; se conserva visible para
    # poder comparar contra la definición anterior y auditar la redefinición.
    salida(f"[ratchet] nodos_largos: diagnóstico no gateado — "
           f"{len(escanear_nodos_fisicos(raiz))} nodos con más de "
           f"{MAX_LINEAS_NODO} líneas físicas")

    if empeoro and actualizar:
        valida, motivo = clave_valida(raiz, os.environ.get(CLAVE_BYPASS))
        if not valida:
            salida(f"[ratchet] ROJO: --actualizar acepta un empeoramiento solo con la clave del operador ({motivo}).")
            return 1
    if empeoro and not actualizar:
        salida("[ratchet] ROJO: una métrica empeoró. Reusá/extraé en vez de duplicar y no borres tests; "
               "correr --actualizar es una decisión del operador, no del agente.")
        return 1

    _escribir_baseline(nuevo, previo, ruta_baseline, raiz, escribir, actualizar, mejoro, salida)
    if actualizar and empeoro:
        salida("[ratchet] empeoramiento ACEPTADO por --actualizar (decisión humana); commiteá el baseline")
    salida("[ratchet] VERDE")
    return 0


# cobertura (X175): líneas del producto que ningún test ejecuta, POR ARCHIVO.
# La mide `coverage` en la etapa funcional de `calidad.sh`, con los tests que
# dependen del entorno (red, datos, laya, git, cobertura) afuera y con la única
# rama del producto que dependía del árbol de trabajo ya corregida
# (`utils/citas._por_nombre_suelto` escanea solo raíces versionadas): medido,
# un clon limpio y este árbol con artefactos dan el MISMO detalle por archivo
# (X175, dictamen del Auditor). La sección del baseline es la del INTÉRPRETE
# que corre (decisión del operador, X175): 3.12 (el CI) y 3.14 (la máquina del
# operador) no cuentan igual las líneas ejecutables —medido: `juez.py` 29
# contra 31 por las cláusulas `except OSError:` de `:89` y `:451`—. Acá solo
# se lee y se compara: ningún archivo puede sumar líneas sin test y uno nuevo
# entra cubierto o con la clave; el total no esconde lo que pasa en cada uno.

def version_de_python() -> str:
    """La clave de sección del baseline de cobertura: "3.14"."""
    return f"{sys.version_info[0]}.{sys.version_info[1]}"


def escanear_cobertura(raiz: Path, datos: Path) -> dict[str, int] | None:
    """{archivo del producto: líneas sin ejecutar}, o None si no hay datos."""
    if not datos.is_file():
        return None
    medicion = coverage.Coverage(data_file=str(datos))
    medicion.load()
    return {archivo: len(medicion.analysis2(str(raiz / archivo))[3])
            for archivo in escanear_lineas_del_producto(raiz)}


def hallazgos_cobertura(actual: dict, previo: dict) -> list[str]:
    """Lo que empeoró: un archivo con más líneas sin test, o uno nuevo con alguna."""
    return [f"{archivo}: {previo.get(archivo, 0)} → {n} líneas sin test"
            for archivo, n in sorted(actual.items()) if n > previo.get(archivo, 0)]


def _archivos(datos: dict | None, version: str | None = None) -> dict | None:
    """El detalle por archivo de la cobertura del intérprete `version` (default:
    el que corre). Cada sección tiene la forma de un ratchet de métricas, así la
    lee el mismo `cargar_baseline`."""
    secciones = ((datos or {}).get("ratchets") or {}).get("cobertura") or {}
    return (secciones.get(version or version_de_python()) or {}).get("detalle")


def _guardar_seccion(ruta: Path, actual: dict, version: str) -> None:
    """Reescribe SOLO la sección del intérprete que corre: el baseline de otro
    Python no se pisa desde acá."""
    datos = cargar_baseline(ruta) or {"version": 1, "ratchets": {}}
    datos["ratchets"].setdefault("cobertura", {})[version] = {
        "metrica": sum(actual.values()), "detalle": actual}
    guardar_baseline(datos, ruta)


def correr_cobertura(raiz: Path = RAIZ, ruta_baseline: Path = BASELINE_COBERTURA,
                     datos: Path = DATOS_COBERTURA, actualizar: bool = False,
                     sembrar: bool = False, escribir: bool = True, salida=print) -> int:
    """El gate de cobertura, con las reglas del ratchet: mejorar reescribe la
    sección del intérprete que corre, empeorar (o un empeoramiento ya commiteado)
    exige la clave, y sin datos o sin sección es ROJO. La sección que falta se
    siembra con `--sembrar-entorno`: ES la medición del intérprete que corre, no
    una aceptación, y por eso no pide clave (ni toca otra sección). Con
    `escribir=False` (X185) una mejora se informa pero NO se persiste: la
    corrida no es válida (p.ej. la suite no pasó) y el baseline no se mueve."""
    actual = escanear_cobertura(raiz, datos)
    if actual is None:
        salida(f"[cobertura] ROJO: no hay datos en {_ruta_visible(datos, raiz)}: corré ./calidad.sh entero")
        return 1
    version = version_de_python()
    previo = _archivos(cargar_baseline(ruta_baseline), version)
    if previo is None:
        if sembrar:
            _guardar_seccion(ruta_baseline, actual, version)
            salida(f"[cobertura] sección {version} sembrada en {_ruta_visible(ruta_baseline, raiz)} "
                   f"({sum(actual.values())} líneas sin test); commiteala")
            return 0
        salida(f"[cobertura] ROJO: no hay sección para Python {version} en "
               f"{_ruta_visible(ruta_baseline, raiz)}: sembrala con "
               "`python3 ratchet.py --cobertura --sembrar-entorno`")
        return 1
    if sembrar:
        salida(f"[cobertura] ROJO: la sección {version} ya existe; --sembrar-entorno solo crea la que falta")
        return 1
    historia = [_archivos(_baseline_de_git(raiz, ref, ruta_baseline), version) for ref in ("HEAD", "HEAD~1")]
    bypass = [h for a, b in ((previo, historia[0]), (historia[0], historia[1])) if a and b
              for h in hallazgos_cobertura(a, b)]
    peores = hallazgos_cobertura(actual, previo)
    total = sum(actual.values())
    salida(f"[cobertura] {total} líneas del producto sin test en Python {version}"
           f" (antes {sum(previo.values())})")
    for linea in peores + [f"BYPASS: {h}" for h in bypass]:
        salida(f"    {linea}")
    if peores or bypass:
        valida, motivo = clave_valida(raiz, os.environ.get(CLAVE_BYPASS))
        if not (actualizar and valida):
            salida(f"[cobertura] ROJO: hay líneas nuevas sin test. Escribí el test; aceptarlo es "
                   f"del operador con su clave y --actualizar ({motivo if actualizar else 'sin --actualizar'}).")
            return 1
    if previo != actual:
        if escribir:
            _guardar_seccion(ruta_baseline, actual, version)
            salida(f"[cobertura] baseline actualizado ({_ruta_visible(ruta_baseline, raiz)}); commitealo")
        else:
            salida("[cobertura] mejora detectada, pero --no-escribir: baseline intacto")
    salida("[cobertura] VERDE")
    return 0


# tipos del producto con Pyright (X184)

def _config_pyright(raiz: Path) -> dict:
    """La sección [tool.pyright] de pyproject.toml: la fuente del target fijo."""
    try:
        with (raiz / "pyproject.toml").open("rb") as archivo:
            return (tomllib.load(archivo).get("tool") or {}).get("pyright") or {}
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _leer_datos_pyright(datos: Path) -> dict | None:
    """El JSON de `pyright --outputjson`, o None si no existe o no es válido."""
    if not datos.is_file():
        return None
    try:
        carga = json.loads(datos.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(carga, dict) or not isinstance(carga.get("generalDiagnostics"), list):
        return None
    return carga


def _detalle_de_carga(carga: dict, raiz: Path) -> dict[str, int]:
    """{archivo:regla: errores}. Solo `severity == "error"`: los warnings (el DSL
    de PocketFlow usa `>>` por efecto) son diagnóstico y no gatean (X184)."""
    detalle: dict[str, int] = {}
    for diagnostico in carga["generalDiagnostics"]:
        if diagnostico.get("severity") != "error":
            continue
        archivo = _relativa(Path(diagnostico["file"]), raiz)
        clave = f"{archivo}:{diagnostico.get('rule') or 'sin-regla'}"
        detalle[clave] = detalle.get(clave, 0) + 1
    return dict(sorted(detalle.items()))


def escanear_pyright(raiz: Path, datos: Path) -> dict[str, int] | None:
    """Los errores de tipo por archivo:regla, o None si no hay datos válidos."""
    carga = _leer_datos_pyright(datos)
    return None if carga is None else _detalle_de_carga(carga, raiz)


def hallazgos_pyright(actual: dict, previo: dict) -> list[str]:
    """Lo que empeoró: un (archivo, regla) con más errores, o uno nuevo."""
    return [f"{clave}: {previo.get(clave, 0)} → {n} errores"
            for clave, n in sorted(actual.items()) if n > previo.get(clave, 0)]


def _detalle_pyright(datos: dict | None) -> dict | None:
    """El detalle del baseline de tipos (la forma de un ratchet de métricas)."""
    seccion = ((datos or {}).get("ratchets") or {}).get("pyright") or {}
    detalle = seccion.get("detalle")
    return detalle if isinstance(detalle, dict) else None


def _guardar_pyright(ruta: Path, actual: dict, version: str, python_version: str) -> None:
    guardar_baseline({"version": 1, "pyright": version, "pythonVersion": python_version,
                      "ratchets": {"pyright": {"metrica": sum(actual.values()), "detalle": actual}}}, ruta)


def _peores_y_bypass_pyright(raiz: Path, ruta_baseline: Path,
                             actual: dict, previo: dict) -> tuple[list[str], list[str]]:
    """Lo que empeoró contra el disco/HEAD/HEAD~1 (bypass commiteado incluido)."""
    historia = [_detalle_pyright(_baseline_de_git(raiz, ref, ruta_baseline)) for ref in ("HEAD", "HEAD~1")]
    bypass = [hallazgo for a, b in ((previo, historia[0]), (historia[0], historia[1])) if a and b
              for hallazgo in hallazgos_pyright(a, b)]
    return hallazgos_pyright(actual, previo), bypass


def correr_pyright(raiz: Path = RAIZ, ruta_baseline: Path = BASELINE_PYRIGHT,
                   datos: Path = DATOS_PYRIGHT, actualizar: bool = False,
                   sembrar: bool = False, escribir: bool = True, salida=print) -> int:
    """Etapa 6/6: errores de tipo del producto con las reglas del ratchet.

    Lee el JSON que dejó `pyright --outputjson` (nunca corre Pyright), compara
    por `archivo:regla` contra `ratchets/pyright.json` (solo baja) y fija la
    versión con la que se midió: si la versión de Pyright o el target de Python
    no son los del baseline, es ROJO (el baseline no se mueve por cambiar la
    herramienta sin decisión). La primera foto se siembra con
    `--sembrar-pyright`: es la medición honesta de la deuda, no una aceptación,
    y solo si no existe. Con `escribir=False` (diagnóstico) informa la mejora
    pero no toca el baseline: es lo que usa la etapa 6 cuando la suite no pasó
    (X190: una corrida roja de X189 movió 17 → 4 sola, sin clave)."""
    carga = _leer_datos_pyright(datos)
    if carga is None:
        salida(f"[pyright] ROJO: no hay datos válidos en {_ruta_visible(datos, raiz)}: "
               "corré ./calidad.sh entero")
        return 1
    version = str(carga.get("version") or "")
    target = str(_config_pyright(raiz).get("pythonVersion") or "")
    actual = _detalle_de_carga(carga, raiz)
    baseline = cargar_baseline(ruta_baseline)
    previo = _detalle_pyright(baseline)
    if baseline is None or previo is None:
        if sembrar:
            _guardar_pyright(ruta_baseline, actual, version, target)
            salida(f"[pyright] baseline sembrado en {_ruta_visible(ruta_baseline, raiz)} "
                   f"({sum(actual.values())} errores de tipo); commitealo")
            return 0
        salida(f"[pyright] ROJO: no hay baseline en {_ruta_visible(ruta_baseline, raiz)}: sembralo "
               "con `python3 ratchet.py --pyright --sembrar-pyright`")
        return 1
    if sembrar:
        salida("[pyright] ROJO: el baseline ya existe; --sembrar-pyright solo crea el que falta")
        return 1
    if (version, target) != (baseline.get("pyright"), baseline.get("pythonVersion")):
        salida(f"[pyright] ROJO: el baseline se midió con pyright {baseline.get('pyright')} y "
               f"Python {baseline.get('pythonVersion')}, y esta corrida es {version} / {target}: "
               "corré la versión pinneada o re-sembrá el baseline con decisión (--actualizar y la clave)")
        return 1
    peores, bypass = _peores_y_bypass_pyright(raiz, ruta_baseline, actual, previo)
    salida(f"[pyright] {sum(actual.values())} errores de tipo en el producto con pyright {version} "
           f"(antes {sum(previo.values())}); los warnings son diagnóstico, no gatean")
    for linea in peores + [f"BYPASS: {hallazgo}" for hallazgo in bypass]:
        salida(f"    {linea}")
    if peores or bypass:
        valida, motivo = clave_valida(raiz, os.environ.get(CLAVE_BYPASS))
        if not (actualizar and valida):
            salida("[pyright] ROJO: hay errores de tipo nuevos. Arreglá el tipo; aceptarlo es del "
                   f"operador con su clave y --actualizar ({motivo if actualizar else 'sin --actualizar'}).")
            return 1
    if previo != actual:
        _publicar_pyright(raiz, ruta_baseline, actual, version, target, escribir, salida)
    salida("[pyright] VERDE")
    return 0


def _publicar_pyright(raiz: Path, ruta_baseline: Path, actual: dict, version: str,
                      target: str, escribir: bool, salida=print) -> None:
    """Publica la foto nueva, o la informa sin persistir si es diagnóstica.

    X190: una corrida con la suite roja no mueve el baseline de tipos (mismo
    criterio que X185 en cobertura); la mejora se informa y no se escribe."""
    if escribir:
        _guardar_pyright(ruta_baseline, actual, version, target)
        salida(f"[pyright] baseline actualizado ({_ruta_visible(ruta_baseline, raiz)}); commitealo")
    else:
        salida("[pyright] mejora detectada, pero --no-escribir: baseline intacto")


def entorno_pyright(raiz: Path = RAIZ) -> Path:
    """El intérprete del entorno VACÍO fijo con el que analiza Pyright (X187).

    Pyright resuelve los imports contra el Python que descubre: con el venv del
    gate veía los tipos de las dependencias instaladas (63 errores) y con el
    Python del sistema no (52), así que el mismo código daba dos números y un
    gate corrido en un entorno más rico bajaba el baseline SIN clave (el mismo
    agujero que X185 cerró en cobertura). El análisis se ancla acá: un venv sin
    pip y VACÍO, recreado en cada corrida para que no haya estado local que lo
    contamine, y creado con `sys.executable` (nunca con el `python3` del PATH).
    La métrica gatea el código propio contra typeshed, no las firmas de
    terceros, que además cambian con su versión; el costo declarado es que los
    diagnósticos que hablan de tipos de `openai`, `numpy`, `yaml` y PocketFlow
    dejan de gatearse."""
    destino = raiz / ".pyright" / "entorno"
    subprocess.run([sys.executable, "-m", "venv", "--clear", "--without-pip", str(destino)],
                   check=True, capture_output=True)
    return destino / "bin" / "python"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ratchet.py",
        description="Ratchet de métricas del harness: la métrica puede mejorar o quedar igual, "
                    "nunca empeorar sin decisión humana.",
    )
    parser.add_argument("--baseline", type=Path, default=BASELINE, help=f"baseline versionado (default: {BASELINE})")
    parser.add_argument("--raiz", type=Path, default=RAIZ, help="raíz a escanear (default: la del repo)")
    parser.add_argument("--no-escribir", action="store_true",
                        help="compara pero NO reescribe el baseline (diagnóstico)")
    parser.add_argument("--sin-guardia", action="store_true", help="saltea la guardia anti-bypass (diagnóstico)")
    parser.add_argument("--actualizar", action="store_true",
                        help=f"HUMANO: acepta un empeoramiento deliberado (requiere {CLAVE_BYPASS} = la clave del operador)")
    parser.add_argument("--sembrar-clave", action="store_true",
                        help="HUMANO: escribe ratchets/clave_operador.sha256 con el sha256 de su clave")
    parser.add_argument("--cobertura", action="store_true",
                        help="el gate de cobertura por archivo (lee .cobertura/datos; lo corre calidad.sh)")
    parser.add_argument("--sembrar-entorno", action="store_true",
                        help="siembra la sección de cobertura del intérprete que corre si falta "
                             "(no acepta empeoramientos ni pide clave)")
    parser.add_argument("--pyright", action="store_true",
                        help="etapa 6/6: errores de tipo del producto (lee .pyright/datos.json; lo corre calidad.sh)")
    parser.add_argument("--sembrar-pyright", action="store_true",
                        help="siembra el baseline de tipos si no existe "
                             "(no acepta empeoramientos ni pide clave)")
    parser.add_argument("--pyright-entorno", action="store_true",
                        help="etapa 6/6: prepara el venv vacío fijo del análisis y "
                             "escribe su intérprete (lo usa calidad.sh)")
    args = parser.parse_args(argv)
    if args.sembrar_clave:
        return sembrar_clave()
    if args.cobertura:
        return correr_cobertura(raiz=args.raiz.resolve(), actualizar=args.actualizar,
                                sembrar=args.sembrar_entorno, escribir=not args.no_escribir)
    if args.pyright_entorno:
        print(entorno_pyright(args.raiz.resolve()))
        return 0
    if args.pyright:
        return correr_pyright(raiz=args.raiz.resolve(), actualizar=args.actualizar,
                              sembrar=args.sembrar_pyright, escribir=not args.no_escribir)
    return correr(
        raiz=args.raiz.resolve(),
        ruta_baseline=args.baseline.resolve(),
        escribir=not args.no_escribir,
        guardia=not args.sin_guardia,
        actualizar=args.actualizar,
    )


if __name__ == "__main__":
    sys.exit(main())
