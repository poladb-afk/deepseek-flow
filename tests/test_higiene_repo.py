"""Candado de higiene del árbol trackeado (X122).

Spec pre-registrada por el operador el 2026-11-01, ANTES de escribir este test
(M3): la higiene se venía haciendo a mano —`.gitignore` oculta artefactos pero
no los prohíbe, y los 47 `.patch` borrados podían volver— así que la regla
pasa a ser un gate. Falla si un archivo TRACKEADO:

(a) termina en `.zip` o `.patch`, o matchea `calidad_*.txt`;
(b) vive bajo `salidas/`, `.modelos/`, `.runs/`, `memoria/` o es `trazas.db`;
(c) supera 1 MB (al pre-registrar, el máximo eran 372.089 B de la bitácora);
(d) es un `.md` de la raíz que no sea `AGENTS.md` ni `README.md`.

Las excepciones van en `EXCEPCIONES`, con su motivo; hoy hay una sola y es un
desvío declarado del pre-registro, que las esperaba vacías: `memoria/.gitkeep`
versiona el directorio de la biblioteca (los `.md` de ahí están ignorados).
"""
import subprocess
from pathlib import Path

import pytest
from conftest import RAIZ, requiere_repo_git

MAX_BYTES = 1_000_000
SUFIJOS_ARTEFACTO = (".zip", ".patch")
CARPETAS_ARTEFACTO = ("salidas/", ".modelos/", ".runs/", "memoria/")
ARCHIVOS_ARTEFACTO = {"trazas.db"}
MD_PERMITIDOS_EN_RAIZ = {"AGENTS.md", "README.md"}
EXCEPCIONES = {
    "memoria/.gitkeep": "versiona el directorio de la biblioteca; no es un artefacto de corrida",
}


def _trackeados():
    salida = subprocess.run(
        ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=False
    )
    assert salida.returncode == 0, f"git ls-files falló: {salida.stderr[-300:]}"
    return [linea.strip() for linea in salida.stdout.splitlines() if linea.strip()]


def _motivo(rel):
    """Por qué un archivo trackeado viola la higiene, o None si está bien.

    Primero las reglas por nombre (a)-(b)-(d), al final la de tamaño: medir
    disco es lo único que necesita el archivo en el lugar.
    """
    nombre = Path(rel).name
    if rel.endswith(SUFIJOS_ARTEFACTO):
        return "es un artefacto de corrida (.zip/.patch)"
    if nombre.startswith("calidad_") and nombre.endswith(".txt"):
        return "es una salida de gate (calidad_*.txt)"
    if rel.startswith(CARPETAS_ARTEFACTO) or rel in ARCHIVOS_ARTEFACTO:
        return "vive en una carpeta de artefactos"
    if "/" not in rel and rel.endswith(".md") and rel not in MD_PERMITIDOS_EN_RAIZ:
        return "es un markdown en la raíz (sólo AGENTS.md y README.md)"
    if (RAIZ / rel).stat().st_size > MAX_BYTES:
        return f"supera {MAX_BYTES} B"
    return None


@pytest.mark.git
@requiere_repo_git
def test_higiene_del_arbol_trackeado():
    """La spec entera en un solo gate: si falla, el mensaje dice archivo y motivo."""
    trackeados = _trackeados()
    # Una excepción cuyo archivo deja de estar trackeado quedaría viva para
    # siempre: el candado se ataría a sí mismo a un fantasma (Auditor, X122).
    sueltas = sorted(set(EXCEPCIONES) - set(trackeados))
    assert not sueltas, f"excepciones sin archivo trackeado, borralas: {sueltas}"
    violaciones = {
        rel: motivo
        for rel in trackeados
        if rel not in EXCEPCIONES and (motivo := _motivo(rel)) is not None
    }
    assert not violaciones, "archivos trackeados que violan la higiene (X122): " + "; ".join(
        f"{rel} ({motivo})" for rel, motivo in sorted(violaciones.items())
    )


@pytest.mark.parametrize(
    ("rel", "motivo"),
    [
        ("docs/informes/probe.zip", "artefacto de corrida"),
        ("docs/informes/probe.patch", "artefacto de corrida"),
        ("docs/informes/calidad_2026-11-01.txt", "salida de gate"),
        ("salidas/corrida.json", "carpeta de artefactos"),
        ("memoria/nota.md", "carpeta de artefactos"),
        ("trazas.db", "carpeta de artefactos"),
        ("NOTAS.md", "markdown en la raíz"),
    ],
)
def test_el_candado_rechaza_cada_familia(rel, motivo):
    """Una por familia de la spec: el candado puede fallar y se ve en la suite."""
    assert motivo in _motivo(rel)


def test_el_candado_rechaza_un_archivo_de_mas_de_1_mb(monkeypatch):
    """La regla de tamaño con el umbral bajado: no hace falta un archivo real de 1 MB."""
    monkeypatch.setattr("test_higiene_repo.MAX_BYTES", 1)
    motivo = _motivo("docs/bitacora.md")
    assert motivo and motivo.startswith("supera")

