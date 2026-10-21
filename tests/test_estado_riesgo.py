"""Tests de la sonda de readiness del juez de riesgo (exp/71).

El criterio es pre-registrado (roadmap ítem 5): ≥300 etiquetas orgánicas y
≥100 rechazos orgánicos. La sonda es read-only y separa `banco` (sintético)
de `web`/`terminal` (humano) — la fuga que medía "577 orgánicas" era tráfico
de la suite escrita como `terminal`."""

import json

from banco.probes.estado_riesgo import estado, leer_lineas


def _fila(origen, aprobado):
    return {"origen": origen, "aprobado": aprobado}


def test_estado_separa_organicas_de_banco(tmp_path):
    ruta = tmp_path / "riesgo.jsonl"
    filas = [
        _fila("terminal", True),
        _fila("terminal", False),
        _fila("web", True),
        _fila("banco", False),
        _fila(None, True),
    ]
    ruta.write_text("\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")
    e = estado(leer_lineas(ruta))
    assert e["organicas"] == 3 and e["rechazos"] == 1
    assert e["banco"] == 1 and e["listo"] is False


def test_estado_marca_listo_con_el_criterio_pre_registrado():
    filas = [_fila("terminal", True) for _ in range(300)]
    filas += [_fila("web", False) for _ in range(100)]
    e = estado(filas)
    assert e["listo"] is True and e["faltan_organicas"] == 0 and e["faltan_rechazos"] == 0


def test_leer_lineas_tolera_rotas_y_archivo_ausente(tmp_path):
    ruta = tmp_path / "riesgo.jsonl"
    ruta.write_text('{"origen": "web", "aprobado": true}\nno-json\n\n', encoding="utf-8")
    assert len(leer_lineas(ruta)) == 1
    assert leer_lineas(tmp_path / "no-existe.jsonl") == []
