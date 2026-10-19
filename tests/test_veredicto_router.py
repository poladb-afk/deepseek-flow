"""exp/45 — el veredicto del router con datos propios (lógica pura).

La sonda `banco/probes/veredicto_router.py` aplica el criterio PRE-REGISTRADO:
con ≥100 pares etiquetados, base rate de `directo` <10% → apagar; si no →
elegir alpha propio y enforce. Estos tests clavan la regla (para que un cambio
futuro no la reinterprete después de ver los datos) y la selección de alpha.
"""
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import veredicto_router as vr  # noqa: E402

_AHORA = datetime.now().timestamp()


def _fila(conf, correcto, laya, etiqueta=None, ts=_AHORA):
    return {"conf": conf, "correcto": correcto, "laya": laya,
            "etiqueta": etiqueta or ("directo" if correcto else "herramientas"), "ts": ts}


def test_decidir_respeta_el_umbral_pre_registrado():
    assert vr.decidir(0.09) == "APAGAR"
    assert vr.decidir(0.10) == "SEGUIR"   # el borde NO apaga
    assert vr.decidir(0.176) == "SEGUIR"


def test_composicion_calcula_base_rate_recall_y_dias():
    ayer = _AHORA - 86400
    filas = [
        _fila(0.99, True, "directo", "directo", ayer),
        _fila(0.93, False, "directo", "herramientas", _AHORA),
        _fila(0.90, True, "herramientas", "herramientas", _AHORA),
        _fila(0.80, True, "herramientas", "herramientas", _AHORA),
    ]
    comp = vr.composicion(filas)
    assert comp["n"] == 4 and comp["directo"] == 1
    assert comp["base_rate"] == 0.25
    assert comp["propuestas_directo"] == 2           # una correcta y una falsa
    assert comp["precision_directo"] == 0.5
    assert comp["recall"] == 2.0                     # 2 propuestas / 1 directo real
    assert len(comp["por_dia"]) == 2


def test_curva_marca_los_directos_aceptados_por_alpha():
    filas = [
        _fila(0.998, True, "directo"),
        _fila(0.995, True, "directo"),
        _fila(0.93, False, "directo"),     # falso directo de confianza alta
        _fila(0.99, True, "herramientas"),
        _fila(0.95, True, "herramientas"),
        _fila(0.90, True, "herramientas"),
        _fila(0.85, True, "herramientas"),
    ]
    tabla = vr.curva(filas, alphas=(0.02, 0.05, 0.30))
    assert len(tabla) == 3
    for f in tabla:
        assert f["directo_ok"] <= f["directo_aceptado"]
        assert f["directo_precision"] is None or 0.0 <= f["directo_precision"] <= 1.0
    # alpha permisivo acepta al menos tantos directos como el estricto
    assert tabla[2]["directo_aceptado"] >= tabla[0]["directo_aceptado"]


def test_elegir_alpha_exige_precision_y_prefiere_mas_directos():
    tabla = [
        {"alpha": 0.02, "cobertura": 0.15, "directo_aceptado": 2, "directo_ok": 2, "directo_precision": 1.0},
        {"alpha": 0.05, "cobertura": 0.38, "directo_aceptado": 8, "directo_ok": 6, "directo_precision": 0.75},
    ]
    assert vr.elegir_alpha(tabla)["alpha"] == 0.02
    assert vr.elegir_alpha(tabla, precision_min=0.7)["alpha"] == 0.05
    assert vr.elegir_alpha(tabla, precision_min=1.01) is None


def test_informe_contiene_criterio_veredicto_y_config():
    filas = [_fila(0.99, True, "directo"), _fila(0.90, True, "herramientas"),
             _fila(0.80, True, "herramientas")]
    texto = vr.informe("banco/calibracion_test.jsonl", filas)
    assert "Criterio pre-registrado" in texto
    assert "## Veredicto" in texto
    assert "base rate" in texto


def test_calibraciones_versionadas_no_llevan_texto_de_preguntas():
    """Privacidad: la calibración que se versiona solo tiene números (conf +
    correcto + etiqueta); el texto de la pregunta queda en salidas/ (ignorado)."""
    import json
    for ruta in (RAIZ / "banco").glob("calibracion_ambiental_*.jsonl"):
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                assert "pregunta" not in json.loads(linea), f"texto de pregunta versionado en {ruta}"


def test_decidir_roi_pre_registrado():
    """Criterio de ROI pre-registrado para la próxima revisión."""
    assert vr.decidir_roi(0.049) == "APAGAR"
    assert vr.decidir_roi(0.05) == "SEGUIR"   # el borde mantiene
    assert vr.decidir_roi(0.10) == "SEGUIR"


def test_roi_calcula_ahorro_exigiendo_precision_de_directos():
    filas = [_fila(0.99, True, "directo") for _ in range(4)]
    curva_ok = {"directo_aceptado": 1, "directo_precision": 1.0}
    r = vr.roi(filas, curva_ok)
    assert r["elegible"] is True and r["ahorro"] == 0.25
    curva_mala = {"directo_aceptado": 2, "directo_precision": 0.95}
    assert vr.roi(filas, curva_mala)["elegible"] is False


def test_informe_incluye_roi_y_estado_de_revision():
    filas = [_fila(0.99, True, "directo"), _fila(0.90, True, "herramientas"),
             _fila(0.80, True, "herramientas")]
    texto = vr.informe("banco/calibracion_test.jsonl", filas)
    assert "ROI (criterio pre-registrado" in texto
    assert "Estado de revisión" in texto
