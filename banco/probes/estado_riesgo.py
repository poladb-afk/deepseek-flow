"""Estado del juez de riesgo (exp/44): etiquetas orgánicas hacia el fine-tune.

READ-ONLY: lee el log de decisiones HITL y aplica el criterio pre-registrado
de la roadmap (ítem 5): **≥300 etiquetas orgánicas y ≥100 rechazos
orgánicos**. `origen` separa humano (`web`/`terminal`) del sintético
(`banco`, lo aprueba el driver por scope). `requiere_revision` casi no dispara
(5/1467): esa es la dimensión que el fine-tune tiene que arreglar.

Límite de procedencia: las filas previas a exp/71 no son confiables —la suite
escribía `origen=terminal` y cargaba el checkpoint del juez—, así que ese log
quedó en cuarentena (`salidas/riesgo_pre_exp71_2026-10-21.jsonl`) y NO cuenta.

Uso: python3 banco/probes/estado_riesgo.py [--ruta salidas/riesgo.jsonl]
"""
import argparse
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ORIGENES_ORGANICOS = ("web", "terminal")
CRITERIO_ORGANICAS = 300
CRITERIO_RECHAZOS = 100


def leer_lineas(ruta):
    """Filas válidas del log (una por línea). Tolerante: una línea rota no
    tira el reporte, y un archivo ausente es una log vacío."""
    filas = []
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    filas.append(json.loads(linea))
                except ValueError:
                    continue  # bookkeeping: la línea rota no es un dato
    except OSError:
        pass
    return filas


def estado(filas):
    """Las etiquetas orgánicas y qué falta para el criterio pre-registrado."""
    organicas = [f for f in filas if f.get("origen") in ORIGENES_ORGANICOS]
    rechazos = sum(1 for f in organicas if not f.get("aprobado"))
    return {
        "organicas": len(organicas),
        "rechazos": rechazos,
        "banco": sum(1 for f in filas if f.get("origen") == "banco"),
        "faltan_organicas": max(0, CRITERIO_ORGANICAS - len(organicas)),
        "faltan_rechazos": max(0, CRITERIO_RECHAZOS - rechazos),
        "listo": (
            len(organicas) >= CRITERIO_ORGANICAS
            and rechazos >= CRITERIO_RECHAZOS
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="estado_riesgo", description="etiquetas orgánicas del juez (read-only)"
    )
    parser.add_argument("--ruta", default=str(RAIZ / "salidas" / "riesgo.jsonl"))
    args = parser.parse_args(argv)
    e = estado(leer_lineas(args.ruta))
    print("# Juez de riesgo exp/44 — estado (read-only)")
    print(
        f"orgánicas: {e['organicas']}/{CRITERIO_ORGANICAS} "
        f"(faltan {e['faltan_organicas']}) · rechazos: "
        f"{e['rechazos']}/{CRITERIO_RECHAZOS} (faltan {e['faltan_rechazos']})"
    )
    print(f"filas de banco (no cuentan): {e['banco']}")
    print(
        "fine-tune: LISTO (revisar `requiere_revision` y balance antes de entrenar)"
        if e["listo"]
        else "fine-tune: PENDIENTE (faltan etiquetas orgánicas)"
    )
    return e


if __name__ == "__main__":
    main()
