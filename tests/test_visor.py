"""Mesa 8 — visor del trace: HTML puro y modo --watch (sin re-render al pedo).

Cubre contar_y_mtime (señal barata del watch), la elección de la traza más
reciente saltando vacías y una vuelta del watch real (corta con Ctrl+C).
"""
import json
import time

from conftest import RAIZ  # noqa: F401  (raíz en sys.path)

import visor


def _traza(ruta, eventos):
    ruta.write_text("".join(json.dumps(e) + "\n" for e in eventos), encoding="utf-8")


def test_contar_y_mtime_y_archivo_inexistente(tmp_path):
    ruta = tmp_path / "t.jsonl"
    assert visor.contar_y_mtime(ruta) == (0, 0.0)
    _traza(ruta, [{"ts": 1.0, "nodo": "A", "accion": "x", "seg": 1}])
    assert visor.contar_y_mtime(ruta)[0] == 1


def test_mas_reciente_salta_trazas_vacias(tmp_path, monkeypatch):
    vacia = tmp_path / "20261001_000000_1.jsonl"
    vacia.write_text("", encoding="utf-8")
    buena = tmp_path / "20261002_000000_2.jsonl"
    _traza(buena, [{"ts": 1.0, "nodo": "GetQuestion", "accion": "continue", "seg": 0}])
    monkeypatch.setattr(visor, "RUNS", tmp_path)
    assert visor.mas_reciente() == buena


def test_generar_es_determinista(tmp_path):
    ruta = tmp_path / "t.jsonl"
    _traza(ruta, [{"ts": 1.0, "nodo": "A", "accion": "x", "seg": 0.5},
                  {"ts": 2.0, "nodo": "B", "accion": "y", "seg": 1.5}])
    destino = visor.generar(ruta)
    primero = destino.read_text(encoding="utf-8")
    visor.generar(ruta)
    assert destino.read_text(encoding="utf-8") == primero
    assert "A" in primero and "B" in primero


def test_vigilar_genera_una_vez_y_corta_con_ctrl_c(tmp_path, monkeypatch, capsys):
    ruta = tmp_path / "t.jsonl"
    _traza(ruta, [{"ts": 1.0, "nodo": "A", "accion": "x", "seg": 0.1}])
    monkeypatch.setattr(time, "sleep", lambda _s: (_ for _ in ()).throw(KeyboardInterrupt))
    visor.vigilar([ruta], 0.1)
    salida = capsys.readouterr().out
    assert "watch terminado" in salida
    assert ruta.with_suffix(".html").is_file()
