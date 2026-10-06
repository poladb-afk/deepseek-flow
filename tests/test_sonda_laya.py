"""Tests deterministas de las métricas PURAS de sonda_laya.py.

La sonda carga un checkpoint de GB y tarda minutos: por eso la aritmética
de calibración (tabla por bucket, curva de compuerta, ECE) se verifica acá,
con casos sintéticos de confianza conocida, sin cargar ningún modelo. Si
estos números mienten, el informe de evidencia miente, y este test es el
que lo avisa antes de gastar una corrida."""
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def test_tabla_confiabilidad_cubre_los_cinco_buckets_y_los_bordes():
    from sonda_laya import tabla_confiabilidad

    casos = [
        {"conf": 0.55, "correcto": True},   # [0.50, 0.70)
        {"conf": 0.70, "correcto": False},  # borde exacto → [0.70, 0.85)
        {"conf": 0.90, "correcto": True},   # [0.85, 0.95)
        {"conf": 1.00, "correcto": True},   # 1.0 entra en el último bucket abierto [0.95, ∞)
        {"conf": 0.40, "correcto": True},   # bajo el primer borde: no aparece
    ]
    filas = tabla_confiabilidad(casos)
    assert len(filas) == 4, "los bordes default [0.5,0.7,0.85,0.95] dan un bucket por corte"
    assert [f["n"] for f in filas] == [1, 1, 1, 1], "0.40 queda fuera; el resto, uno por bucket"
    assert filas[1]["acierto"] == 0.0, "0.70 cae en el bucket de arriba (corte inferior inclusivo)"
    assert filas[3]["lo"] == 0.95 and filas[3]["conf_media"] == 1.0, "conf 1.0 entra en el bucket abierto [0.95, ∞)"


def test_curva_compuerta_mueve_cobertura_y_precision_con_el_umbral():
    from sonda_laya import curva_compuerta

    casos = [
        {"conf": 0.9, "correcto": True},
        {"conf": 0.9, "correcto": True},
        {"conf": 0.8, "correcto": False},
        {"conf": 0.5, "correcto": True},
    ]
    filas = {f["umbral"]: f for f in curva_compuerta(casos)}
    assert filas[0.5]["cobertura"] == 1.0 and filas[0.5]["precision"] == 0.75
    assert filas[0.85]["cobertura"] == 0.5 and filas[0.85]["n_locales"] == 2
    assert filas[0.5]["ahorro"] == filas[0.5]["cobertura"], "ahorro = cobertura (1 llamada por caso local)"


def test_ece_local_es_cero_si_calibra_y_uno_si_miente_siempre():
    from sonda_laya import ece_local

    # conf 0.75 con 3 de 4 aciertos: esperado 0.75 = observado 0.75 → gap 0
    calibrado = [{"conf": 0.75, "correcto": c} for c in (True, True, True, False)]
    assert ece_local(calibrado) == pytest.approx(0.0)
    # conf 1.0 con todo incorrecto: esperado 0 vs observado 1 → ECE 1
    wayward = [{"conf": 1.0, "correcto": False}] * 3
    assert ece_local(wayward) == pytest.approx(1.0)


def test_especificaciones_mapean_cada_checkpoint_a_su_pregunta():
    from sonda_laya import ESPECIFICACIONES

    assert set(ESPECIFICACIONES) == {"router", "voto", "supervisor", "base"}
    assert ESPECIFICACIONES["router"]["pregunta"] == "necesita_herramientas"
    assert ESPECIFICACIONES["voto"]["pregunta"] == "confirma_herramientas"
    assert ESPECIFICACIONES["supervisor"]["pregunta"] == "elegir_proxima"
    assert ESPECIFICACIONES["base"]["pregunta"] == "necesita_herramientas"
