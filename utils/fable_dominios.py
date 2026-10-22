"""Dominios de fable: los adapters de sector como datos versionados.

F3 del port (mapeo §4.3): un adapter cambia los nouns, nunca el loop —
define qué es evidencia, quién manda y cuáles son los fraudes de UN sector.
El juez de trabajo (fable_judge) lo usa para juzgar trabajo no-código con
la fraud table del dominio en vez de la de código.

Los adapters viven en banco/material/fable/dominios/*.md (portados de
Sahir619/fable-method @9924067, MIT), versionados como las calibraciones —
producto leyendo banco/ es precedente (evals.py, utils/conformal.py). La
validación es la del TEMPLATE upstream: las secciones vinculantes
(`Minimum evidence set` y `Fraud table`) tienen que estar — el mismo grep
que corre el CI del repo original. Un .md sin ellas se saltea con aviso
(patrón de skills y módulos: nada roto tumba nada).
"""
import re
import sys
from pathlib import Path

DOMINIOS_DIR = Path(__file__).resolve().parent.parent / "banco" / "material" / "fable" / "dominios"

# Secciones vinculantes del TEMPLATE.md upstream: sin ambas no es un adapter
SECCIONES_OBLIGATORIAS = ("Minimum evidence set", "Fraud table")

# El nombre del sector sale del título ("# Domain adapter: marketing and
# content" → "marketing and content"); el id de archivo es el que matchea el
# parámetro `sector` del llamador.
TITULO_RE = re.compile(r"^#\s+Domain adapter:\s+(.+)$", re.MULTILINE)

_cache: dict[str, dict] | None = None


def _secciones(texto):
    """Parte el adapter en {encabezado: cuerpo} por sus `## secciones`."""
    partes: dict[str, str] = {}
    actual = ""
    for linea in texto.splitlines():
        if linea.startswith("## "):
            actual = linea[3:].strip()
            partes[actual] = ""
        elif actual:
            partes[actual] += linea + "\n"
    return partes


def _cargar_dominios():
    dominios = {}
    for ruta in sorted(DOMINIOS_DIR.glob("*.md")):
        if ruta.name == "TEMPLATE.md":
            continue  # el schema, no un adapter
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        secciones = _secciones(texto)
        if not all(any(clave in enc for enc in secciones) for clave in SECCIONES_OBLIGATORIAS):
            print(f"[dominios] {ruta.name} no tiene las secciones obligatorias "
                  f"({', '.join(SECCIONES_OBLIGATORIAS)}): se saltea", file=sys.stderr)
            continue
        titulo = TITULO_RE.search(texto)
        dominios[ruta.stem] = {
            "id": ruta.stem,
            "nombre": titulo.group(1).strip() if titulo else ruta.stem,
            "aplica": (texto.split("Applies when", 1)[1].split("\n")[0].strip()
                       if "Applies when" in texto else ""),
            "evidencia": "".join(
                cuerpo for enc, cuerpo in secciones.items()
                if "Minimum evidence set" in enc),
            "fuentes": "".join(
                cuerpo for enc, cuerpo in secciones.items()
                if "Evidence and primary sources" in enc),
            "autoridad": "".join(
                cuerpo for enc, cuerpo in secciones.items()
                if enc == "Authority order"),
            "fraudes": "".join(
                cuerpo for enc, cuerpo in secciones.items()
                if "Fraud table" in enc).strip(),
        }
    return dominios


def disponibles():
    """Los adapters cargados {id: nombre}; {} si el directorio no existe."""
    global _cache
    if _cache is None:
        _cache = _cargar_dominios() if DOMINIOS_DIR.is_dir() else {}
    return dict(_cache)


def adaptador(sector):
    """El adapter de un sector, o None si no existe (typo del llamador)."""
    return disponibles().get((sector or "").strip().lower())
