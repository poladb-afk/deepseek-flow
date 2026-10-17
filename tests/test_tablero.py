"""Herramienta de tablero (F5): corre sobre un .runs mínimo y escribe md/json."""
import json


def test_tablero_genera_reporte(tmp_path):
    import tablero

    runs = tmp_path / "runs"
    runs.mkdir()
    lineas = [
        {"ts": 1, "nodo": "read_file", "accion": "error", "seg": 1.0,
         "codigo": "ERROR:ruta"},
        {"ts": 2, "nodo": "read_file", "accion": "ok", "seg": 0.5},
        {"ts": 3, "nodo": "hitl_run_command", "accion": "rechazado", "seg": 0.1,
         "nivel": "preguntar"},
        {"ts": 4, "nodo": "ExecuteTools", "accion": "default", "seg": 0.2},
    ]
    (runs / "20260101_000000_1.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lineas) + "\n", encoding="utf-8")
    out = tmp_path / "out"
    assert tablero.main(["--runs", str(runs), "--salida", str(out),
                         "--gate", str(tmp_path / "no-existe.log")]) == 0
    md = (out / "tablero.md").read_text(encoding="utf-8")
    data = json.loads((out / "tablero.json").read_text(encoding="utf-8"))
    assert "Errores de tool" in md and "HITL registrado" in md
    assert data["tools"]["errores"] == 1
    assert data["hitl"]["rechazados"] == 1
    assert data["causas"] == {"ERROR:ruta": 1}
