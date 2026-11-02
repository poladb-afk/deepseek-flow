"""La huella de llamada que deja la traza (antes exp/52-B; S6 se llevó el corte
por novedad y su tracking, `banco/specs/s6_un_techo.md`). No hay estado de
novedad en el turno: la huella corta solo identifica la llamada en `.runs`."""
from conftest import RAIZ  # noqa: F401  (asegura la raíz en sys.path)

import nodes
import utils.tracing as tracing


def _tc(nombre, args):
    return {"id": "x", "type": "function",
            "function": {"name": nombre, "arguments": args}}


def test_huella_llamada_distingue_argumentos_y_nombre():
    a = nodes.huella_llamada(_tc("read_file", '{"path": "a.py"}'))
    b = nodes.huella_llamada(_tc("read_file", '{"path": "b.py"}'))
    c = nodes.huella_llamada(_tc("list_files", '{"path": "a.py"}'))
    assert len(a) == 8
    assert a != b and a != c
    assert a == nodes.huella_llamada(_tc("read_file", '{"path": "a.py"}'))


def test_evento_tool_guarda_la_huella_sin_contenido(monkeypatch):
    capturado = {}
    monkeypatch.setattr(tracing, "_escribir", lambda dic: capturado.update(dic))
    tracing.evento_tool("read_file", True, 0.1, huella="ab12cd34")
    assert capturado["nodo"] == "read_file" and capturado["accion"] == "ok"
    assert capturado["huella"] == "ab12cd34"
