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
- `tests_definidos` (**mayor mejor**, ratchet de COBERTURA): `def test_*` en
  `tests/*.py`. `tests/inventario_tests.txt` es la foto del PR 4 y solo vigila
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
- `excepts_amplios` (**menor mejor**, ratchet de RUIDO): handlers `except:`,
  `except Exception` y `except BaseException` de nivel superior. Es el smell
  #1 del código generado por IA (41.723 casos en el estudio de commits reales:
  "Broad exception handling") y el patrón D8 de code-humanizer: convierten un
  crash visible en corrupción invisible. No se prohíben (hay rutas
  best-effort legítimas): se congela el número y no puede crecer sin decisión
  humana. Evidencia y fuentes en docs/informes/codigo_ia_vs_humano_2026-10-19.md.

Guardia anti-bypass (el "Ratchet C" del original): el baseline solo puede
moverse en la dirección que mejora. Si el archivo versionado empeoró respecto
de HEAD —o HEAD respecto de HEAD~1, o sea un bypass ya commiteado— y no está
`HUMAN_RATCHET_BYPASS_KEY` exportada, es bypass y falla. Sin esta guardia el
ratchet sería decorativo: el primer agente que lo vea editaría el JSON.

Uso:
    python3 ratchet.py                  # el gate (exit 0/1); auto-mejora el baseline
    python3 ratchet.py --no-escribir    # diagnóstico: compara y NO toca el baseline
    python3 ratchet.py --actualizar     # HUMANO: acepta un empeoramiento deliberado
    python3 ratchet.py --sin-guardia    # diagnóstico: saltea la guardia git

No tiene dependencias ni toca la red: es la palanca 3 de `calidad.sh` y de CI.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BASELINE = RAIZ / "ratchets" / "baseline.json"
CLAVE_BYPASS = "HUMAN_RATCHET_BYPASS_KEY"

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


def escanear_tests(raiz: Path) -> dict[str, int]:
    """Tests definidos por archivo (`def test_*` en `tests/test_*.py`)."""
    por_archivo: dict[str, int] = {}
    for ruta in sorted((raiz / "tests").glob("test_*.py")):
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        cuenta = sum(
            1 for nodo in ast.walk(arbol)
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
    """

    def __init__(self, locales: set[str]):
        self.locales = locales

    def visit_FunctionDef(self, nodo):  # pragma: no cover - el cuerpo se normaliza aparte
        return nodo

    def visit_Name(self, nodo):
        # locals renombradas tanto en lectura como en escritura: dos copias
        # con variables distintas colisionan; llamadas/atributos se conservan.
        if nodo.id in self.locales:
            nodo.id = "_v"
        return nodo


def _cuerpo_normalizado(nodo: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
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
    return ast.dump(_NormalizarCuerpo(locales).visit(modulo))


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


def _metrica_muertas(raiz: Path) -> tuple[int, list[str]]:
    detalle = escanear_muertas(raiz)
    return len(detalle), detalle


def _metrica_cuerpos(raiz: Path) -> tuple[int, dict[str, list[str]]]:
    detalle = escanear_cuerpos(raiz)
    return sum(len(filas) for filas in detalle.values()), detalle


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
        "descripcion": "tests `def test_*` definidos en tests/",
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


def _diagnostico(nombre: str, actual: dict, previo: dict) -> list[str]:
    """Nombra QUÉ empeoró: un número sin causa no se puede arreglar."""
    lineas = []
    if nombre == "helpers_duplicados":
        for helper, archivos in actual.items():
            previos = previo.get(helper, [])
            if len(archivos) > len(previos):
                lineas.append(f"    {helper}: {', '.join(archivos)}")
    elif nombre == "codigo_muerto_privado":
        for definicion in actual:
            lineas.append(f"    {definicion}")
    elif nombre == "cuerpos_duplicados":
        for grupo in actual.values():
            lineas.append("    ≈ " + " · ".join(grupo))
    elif nombre == "excepts_amplios":
        for archivo, lineas_actuales in actual.items():
            previas = previo.get(archivo, [])
            if len(lineas_actuales) > len(previas):
                lineas.append(f"    {archivo}: {len(previas)} → {len(lineas_actuales)} excepts amplios")
    else:
        for archivo, cuenta in actual.items():
            previa = previo.get(archivo, 0)
            if cuenta < previa:
                lineas.append(f"    {archivo}: {previa} → {cuenta} tests")
    return lineas


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

def _baseline_de_git(raiz: Path, ref: str, ruta: Path) -> dict | None:
    """El baseline tal como estaba en `ref` (HEAD, HEAD~1). Best-effort: sin
    git, sin el archivo o con el ref fuera del clon (CI shallow), None."""
    try:
        relativa = ruta.resolve().relative_to(raiz.resolve()).as_posix()
    except ValueError:
        return None
    try:
        crudo = subprocess.run(
            ["git", "-C", str(raiz), "show", f"{ref}:{relativa}"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if crudo.returncode != 0:
        return None
    try:
        datos = json.loads(crudo.stdout)
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
    """True si hay que BLOQUEAR (bypass detectado sin clave humana)."""
    if os.environ.get(CLAVE_BYPASS, "").strip():
        salida(f"[ratchet] bypass humano declarado ({CLAVE_BYPASS} en el entorno): la guardia no bloquea")
        return False
    hallazgos = hallazgos_bypass(
        cargar_baseline(ruta),
        _baseline_de_git(raiz, "HEAD", ruta),
        _baseline_de_git(raiz, "HEAD~1", ruta),
    )
    if not hallazgos:
        return False
    salida("[ratchet] BYPASS: el baseline empeoró respecto de la historia.")
    for linea in hallazgos:
        salida(f"    {linea}")
    salida(f"  Un agente no edita el baseline. Si el empeoramiento es deliberado, el operador "
           f"exporta {CLAVE_BYPASS} (y lo revierte) y corre --actualizar.")
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

    empeoro = False
    mejoro = False
    for nombre, meta in METRICAS.items():
        valor_previo = ((previo or {}).get("ratchets") or {}).get(nombre) or {}
        metrica_actual = actuales[nombre]["metrica"]
        if not isinstance(valor_previo.get("metrica"), int):
            salida(f"[ratchet] {nombre}: {metrica_actual} (sin baseline: se siembra)")
            continue
        decision = comparar(metrica_actual, valor_previo["metrica"], meta["direccion"])
        flecha = f"{valor_previo['metrica']} → {metrica_actual}"
        if decision == "MEJORÓ":
            mejoro = True
            salida(f"[ratchet] {nombre}: {flecha} → MEJORÓ ({meta['descripcion']})")
        elif decision == "EMPEORÓ":
            salida(f"[ratchet] {nombre}: {flecha} → EMPEORÓ ({meta['descripcion']})")
            for linea in _diagnostico(nombre, actuales[nombre]["detalle"], valor_previo.get("detalle") or {}):
                salida(linea)
            empeoro = True
        else:
            salida(f"[ratchet] {nombre}: {metrica_actual} → IGUAL ({meta['descripcion']})")

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
                        help=f"HUMANO: acepta un empeoramiento deliberado (requiere {CLAVE_BYPASS} si la guardia lo frena)")
    args = parser.parse_args(argv)
    return correr(
        raiz=args.raiz.resolve(),
        ruta_baseline=args.baseline.resolve(),
        escribir=not args.no_escribir,
        guardia=not args.sin_guardia,
        actualizar=args.actualizar,
    )


if __name__ == "__main__":
    sys.exit(main())
