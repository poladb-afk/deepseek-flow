"""exp/52-B — convergencia del loop por novedad (huella tool+argumentos).

La regla va DETRÁS de un setting (CORTE_NOVEDAD, default 0=off): estos tests
clavan la detección de novedad acumulada, el corte por racha y que el default
apagado no cambie conducta. El A/B real (banco) es aparte.
"""
from conftest import RAIZ  # noqa: F401  (asegura la raíz en sys.path)

import nodes
import utils.tracing as tracing


def _tc(nombre, args):
    return {"id": "x", "type": "function",
            "function": {"name": nombre, "arguments": args}}


def _con_turno(**campos):
    """Un shared con la caja de la pregunta en el estado pedido."""
    return {"turno": {**nodes.nuevo_turno(), **campos}}


def test_huella_llamada_distingue_argumentos_y_nombre():
    a = nodes.huella_llamada(_tc("read_file", '{"path": "a.py"}'))
    b = nodes.huella_llamada(_tc("read_file", '{"path": "b.py"}'))
    c = nodes.huella_llamada(_tc("list_files", '{"path": "a.py"}'))
    assert len(a) == 8
    assert a != b and a != c
    assert a == nodes.huella_llamada(_tc("read_file", '{"path": "a.py"}'))


def test_novedad_acumulada_por_pregunta():
    shared = {}
    assert nodes.actualizar_novedad(shared, [_tc("read_file", '{"path": "a"}')]) is False
    assert shared["turno"]["racha_sin_novedad"] == 0
    assert nodes.actualizar_novedad(shared, [_tc("read_file", '{"path": "a"}')]) is True
    assert shared["turno"]["racha_sin_novedad"] == 1
    # intercalada A,B,A,B: la tercera no estrena nada aunque alternen
    shared2 = {}
    nodes.actualizar_novedad(shared2, [_tc("read_file", '{"path": "a"}')])
    nodes.actualizar_novedad(shared2, [_tc("read_file", '{"path": "b"}')])
    assert nodes.actualizar_novedad(shared2, [_tc("read_file", '{"path": "a"}')]) is True


def test_corte_por_novedad_apagado_por_default(monkeypatch):
    monkeypatch.delenv("CORTE_NOVEDAD", raising=False)
    shared = _con_turno(rondas=10, racha_sin_novedad=10)
    assert nodes.corte_por_novedad_activo(shared) is False


def test_corte_por_novedad_respeta_k_y_minimo(monkeypatch):
    monkeypatch.setenv("CORTE_NOVEDAD", "2")
    monkeypatch.setenv("CORTE_NOVEDAD_MIN", "3")
    assert nodes.corte_por_novedad_activo(_con_turno(rondas=2, racha_sin_novedad=2)) is False
    assert nodes.corte_por_novedad_activo(_con_turno(rondas=3, racha_sin_novedad=1)) is False
    assert nodes.corte_por_novedad_activo(_con_turno(rondas=3, racha_sin_novedad=2)) is True


def test_agent_step_retira_tools_con_corte_de_novedad(monkeypatch):
    """Con CORTE_NOVEDAD activo y la racha cumplida, Contexto sale a `cierre`
    (X96): el motivo se recalcula del turno, ya no es un flag que se consume."""
    monkeypatch.setenv("CORTE_NOVEDAD", "2")
    monkeypatch.setenv("CORTE_NOVEDAD_MIN", "3")
    shared = {"messages": [{"role": "user", "content": "hola"}],
              **_con_turno(rondas=4, racha_sin_novedad=2)}
    assert nodes.motivo_de_cierre(shared) == "sin_novedad"
    assert nodes.Contexto()._run(shared) == "cierre"
    mensajes, tools = nodes.Cierre().prep(shared)
    assert tools is None
    assert mensajes[-1]["content"] == nodes.AVISO_CIERRE
    assert "corte_novedad" not in shared["turno"]


def test_evento_tool_guarda_la_huella_sin_contenido(monkeypatch):
    capturado = {}
    monkeypatch.setattr(tracing, "_escribir", lambda dic: capturado.update(dic))
    tracing.evento_tool("read_file", True, 0.1, huella="ab12cd34")
    assert capturado["nodo"] == "read_file" and capturado["accion"] == "ok"
    assert capturado["huella"] == "ab12cd34"


def test_el_corte_que_no_es_el_techo_deja_su_evento(monkeypatch):
    """X96: el evento de política de un corte (no-progreso o sin-novedad) lo
    emite motivo_de_cierre — antes AgentStep.prep. El techo no deja evento
    propio (la traza ya muestra las rondas); los otros dos sí, una vez cada
    vez que Contexto los evalúa."""
    eventos = []
    monkeypatch.setattr(nodes, "evento_politica", lambda nombre, detalle="": eventos.append(nombre))
    assert nodes.motivo_de_cierre(_con_turno(rondas=99)) == "tope"
    assert nodes.motivo_de_cierre(_con_turno(sin_progreso=nodes.UMBRAL_SIN_PROGRESO)) == "sin_progreso"
    monkeypatch.setenv("CORTE_NOVEDAD", "2")
    assert nodes.motivo_de_cierre(_con_turno(rondas=4, racha_sin_novedad=2)) == "sin_novedad"
    assert nodes.motivo_de_cierre(_con_turno(rondas=1)) is None
    assert eventos == ["corte_no_progreso", "corte_sin_novedad"]
