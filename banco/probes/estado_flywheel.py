"""Estado de la flywheel del router (exp/43): pares y días acumulados.

READ-ONLY: NO toca la calibración desplegada. El artefacto de
`etiquetar_ambiental.py` (salida default `banco/calibracion_ambiental_<fecha>.jsonl`)
es el que `.env` usa para el umbral conformal: pisarlo durante la acumulación
cambiaría la política SIN la revisión pre-registrada. Por eso este probe solo
LEE el routing log y aplica el join puro `unir()`.

Regla pre-registrada (roadmap ítem 16 + `veredicto_router.py`): la revisión de
ROI corre con **≥250 pares y ≥14 días** con datos.

Recordatorio de cómo se acumula: el resultado etiquetado solo se registra en
`LAYA_MODO=shadow` (exp/43: en enforce la ruta aplicada ya cambió el contexto
y mediría la política). Uso: ventanas de uso real con `LAYA_MODO=shadow`.

Uso: python3 banco/probes/estado_flywheel.py [--ruta salidas/routing.jsonl]
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from banco.probes.etiquetar_ambiental import leer_lineas, unir  # noqa: E402
from banco.probes.veredicto_router import REVISION_PARES  # noqa: E402

REVISION_DIAS = 14  # pre-registrado en roadmap 16 junto a los 250 pares


def _dia(fila):
    ts = fila.get("ts")
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts).date().isoformat()
    return "sin-ts"


def estado(filas):
    """Los números de la flywheel y qué falta para la revisión de ROI."""
    pares = len(filas)
    directo = sum(1 for fila in filas if fila.get("etiqueta") == "directo")
    dias = len({_dia(fila) for fila in filas})
    return {
        "pares": pares,
        "directo": directo,
        "base_rate": directo / pares if pares else 0.0,
        "dias": dias,
        "faltan_pares": max(0, REVISION_PARES - pares),
        "faltan_dias": max(0, REVISION_DIAS - dias),
        "listo": pares >= REVISION_PARES and dias >= REVISION_DIAS,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="estado_flywheel", description="pares/días del router (read-only)")
    parser.add_argument("--ruta", default=str(RAIZ / "salidas" / "routing.jsonl"))
    args = parser.parse_args(argv)
    e = estado(unir(leer_lineas(args.ruta)))
    print("# Flywheel exp/43 — estado (read-only)")
    print(f"pares: {e['pares']}/{REVISION_PARES} (faltan {e['faltan_pares']}) · "
          f"directo {e['directo']} ({e['base_rate']:.1%})")
    print(f"días con datos: {e['dias']}/{REVISION_DIAS} (faltan {e['faltan_dias']})")
    print("revisión de ROI: LISTA (correr etiquetar_ambiental + veredicto_router)"
          if e["listo"] else "revisión de ROI: PENDIENTE (faltan pares y/o días)")
    return e


if __name__ == "__main__":
    main()
