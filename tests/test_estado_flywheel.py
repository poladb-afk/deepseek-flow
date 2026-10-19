"""Estado de la flywheel: números y umbrales pre-registrados de la revisión.

El probe es read-only (no escribe calibración): acá se prueba el join puro que
usa y el criterio de "revisión lista" (≥250 pares y ≥14 días, roadmap 16).
"""
import pytest

from banco.probes import estado_flywheel


def _fila(ts, etiqueta):
    return {"ts": ts, "etiqueta": etiqueta, "laya": "herramientas", "correcto": True}


def test_estado_cuenta_pares_directo_y_dias():
    filas = [
        _fila(1_000_000_000, "directo"),
        _fila(1_000_000_100, "herramientas"),
        _fila(1_000_100_000, "directo"),  # otro día
    ]
    e = estado_flywheel.estado(filas)
    assert e["pares"] == 3
    assert e["directo"] == 2
    assert e["base_rate"] == pytest.approx(2 / 3)
    assert e["dias"] == 2


def test_estado_sin_pares_no_divide_por_cero():
    e = estado_flywheel.estado([])
    assert e["pares"] == 0 and e["base_rate"] == 0.0 and e["listo"] is False


def test_listo_solo_con_pares_y_dias(monkeypatch):
    """Los dos criterios son necesarios: 3 pares en 15 días no alcanza; 250
    pares en 2 días tampoco. Los umbrales se parchean para no armar 250 filas."""
    monkeypatch.setattr(estado_flywheel, "REVISION_PARES", 3)
    monkeypatch.setattr(estado_flywheel, "REVISION_DIAS", 2)
    dos_dias = [_fila(1_000_000_000, "directo"), _fila(1_000_100_000, "herramientas"),
                _fila(1_000_100_100, "herramientas")]

    listo = estado_flywheel.estado(dos_dias)
    assert listo["listo"] is True and listo["faltan_pares"] == 0 and listo["faltan_dias"] == 0

    un_dia = [_fila(1_000_000_000, "directo"), _fila(1_000_000_100, "herramientas"),
              _fila(1_000_000_200, "herramientas")]
    assert estado_flywheel.estado(un_dia)["listo"] is False

    dos_pares = dos_dias[:2]
    dos_dias_ok = estado_flywheel.estado(dos_pares)
    assert dos_dias_ok["listo"] is False and dos_dias_ok["faltan_pares"] == 1
