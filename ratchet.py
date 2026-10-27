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

Las dos métricas, una por clase de ratchet:

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

No tiene dependencias ni toca la red: es la palanca 3 de `calidad.sh` y de CI.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BASELINE = RAIZ / "ratchets" / "baseline.json"
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
            if isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Load):
                nombre = nodo.id
            elif isinstance(nodo, ast.Attribute) and isinstance(nodo.ctx, ast.Load):
                nombre = nodo.attr
            else:
                continue
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


def escanear_complejidad(raiz: Path, umbral: int = 12) -> dict[str, int]:
    """Funciones del harness con McCabe > umbral, contadas por RUFF (C901).

    Usa el mismo conteo exacto que el gate (ruff pinneado) en vez de
    reimplementar la fórmula: la métrica creíble es la que coincide con la
    herramienta. Devuelve {"archivo:Clase.funcion": cc}."""
    if shutil.which("ruff") is None:
        raise RuntimeError("ratchet: ruff no está en PATH (la métrica de complejidad lo usa)")
    rutas = [str(ruta) for ruta in archivos_del_harness(raiz)]
    proceso = subprocess.run(
        ["ruff", "check", "--isolated", "--select", "C901",
         "--config", f"lint.mccabe.max-complexity={umbral}",
         "--output-format", "concise", *rutas],
        cwd=raiz, capture_output=True, text=True,
    )
    detalle = {}
    for linea in proceso.stdout.splitlines():
        coincidencia = re.match(
            r"^(.+?):(\d+):\d+: C901 `([^`]+)` is too complex \((\d+) > \d+\)", linea)
        if not coincidencia:
            continue
        archivo, linea_def, funcion, complejidad = coincidencia.groups()
        # ruff imprime la ruta relativa a su cwd (= raiz): resolver antes de
        # calcular la ruta relativa del detalle.
        ruta = Path(archivo) if Path(archivo).is_absolute() else raiz / archivo
        calificado = _nombre_calificado(ruta).get(int(linea_def), funcion)
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
        "descripcion": "funciones con McCabe > 12 (C901 repo-wide; antes solo 2 archivos)",
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


_DIAGNOSTICOS = {
    "helpers_duplicados": _diag_helpers,
    "codigo_muerto_privado": _diag_muertas,
    "cuerpos_duplicados": _diag_cuerpos,
    "cuerpos_test_duplicados": _diag_cuerpos,
    "excepts_amplios": _diag_excepts,
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
    import hashlib

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
    import getpass

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

    if empeoro and actualizar:
        valida, motivo = clave_valida(raiz, os.environ.get(CLAVE_BYPASS))
        if not valida:
            salida(f"[ratchet] ROJO: --actualizar acepta un empeoramiento solo con la clave del operador ({motivo}).")
            return 1
    if empeoro and not actualizar:
        salida("[ratchet] ROJO: una métrica empeoró. Reusá/extraé en vez de duplicar y no borres tests; "
               "correr --actualizar es una decisión del operador, no del agente.")
        return 1

    if escribir and (previo is None or nuevo != previo or actualizar):
        guardar_baseline(nuevo, ruta_baseline)
        if previo is None:
            salida(f"[ratchet] SIN BASELINE: sembrado {_ruta_visible(ruta_baseline, raiz)} "
                   f"({_resumen_metricas(nuevo)}); commitealo")
        elif mejoro:
            salida(f"[ratchet] baseline actualizado ({_ruta_visible(ruta_baseline, raiz)}); commitealo")
    elif not escribir:
        salida("[ratchet] --no-escribir: baseline intacto")
    if actualizar and empeoro:
        salida("[ratchet] empeoramiento ACEPTADO por --actualizar (decisión humana); commiteá el baseline")
    salida("[ratchet] VERDE")
    return 0


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
    args = parser.parse_args(argv)
    if args.sembrar_clave:
        return sembrar_clave()
    return correr(
        raiz=args.raiz.resolve(),
        ruta_baseline=args.baseline.resolve(),
        escribir=not args.no_escribir,
        guardia=not args.sin_guardia,
        actualizar=args.actualizar,
    )


if __name__ == "__main__":
    sys.exit(main())
