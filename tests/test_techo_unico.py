"""S6 (X132): un solo techo de rondas por pregunta (`banco/specs/s6_un_techo.md`).

El techo único es `MAX_TOOL_ROUNDS` (default 16) con un saldo en `turno` que se
descuenta por ronda. Las tres políticas que había —alcance amplio (exp/86),
no-progreso (exp/13) y corte por novedad (exp/52-B)— se borraron: estos tests
son el reemplazo de los suyos (el conteo no baja) y cubren el techo único.
"""
import json

from conftest import RAIZ, ctx_chat

import nodes


def _tc(path):
    return [{"function": {"name": "read_file", "arguments": json.dumps({"path": path})}}]


def _shared(**campos):
    return {"messages": [{"role": "system", "content": "s"}],
            "turno": {**nodes.nuevo_turno(), **campos}}


def test_el_techo_unico_es_16_y_el_override_gana():
    """S6: MAX_TOOL_ROUNDS=16 es el único techo; el override explícito sigue
    ganando (lo usan el banco y el delegado)."""
    assert nodes.MAX_TOOL_ROUNDS == 16
    assert nodes.presupuesto({}) == 16
    assert nodes.presupuesto({"max_tool_rounds": 3}) == 3


def test_el_techo_no_depende_de_lo_que_menciona_el_pedido():
    """El pedido ya no sube el techo: lo que antes clasificaba amplio (un
    árbol grande, masa de líneas) ahora corre con el mismo 16."""
    texto = "auditá todo el repo, el directorio exports con 20 archivos y 900 líneas"
    assert nodes.presupuesto({"_objetivo": texto}) == nodes.MAX_TOOL_ROUNDS
    assert nodes.presupuesto({"_objetivo": "qué hace esta línea?"}) == nodes.MAX_TOOL_ROUNDS


def test_el_techo_se_lee_en_runtime(monkeypatch):
    monkeypatch.setattr(nodes, "MAX_TOOL_ROUNDS", 5)
    assert nodes.presupuesto({}) == 5


def test_solo_el_techo_cierra_la_pregunta():
    """El único motivo de cierre es el techo: repetir la misma ronda no corta."""
    assert nodes.motivo_de_cierre(_shared(rondas=nodes.MAX_TOOL_ROUNDS - 1)) is None
    assert nodes.motivo_de_cierre(_shared(rondas=nodes.MAX_TOOL_ROUNDS)) == "tope"
    repetido = _shared(rondas=3)
    for _ in range(5):
        repetido["messages"].append({"role": "tool", "content": "r"})
    assert nodes.motivo_de_cierre(repetido) is None


def test_la_pregunta_nueva_reinicia_el_saldo():
    """L8: el saldo es POR pregunta; un mensaje nuevo del usuario lo reinicia."""
    shared = _shared(rondas=nodes.MAX_TOOL_ROUNDS)
    assert nodes.motivo_de_cierre(shared) == "tope"
    nodes.GetQuestion().post(shared, None, "otra pregunta")
    assert shared["turno"]["rondas"] == 0
    assert nodes.motivo_de_cierre(shared) is None


def test_observar_cuenta_rondas_y_agrega_la_nota(monkeypatch):
    """La ronda se cuenta una vez y la nota de presupuesto viaja en el último
    resultado de la anteúltima ronda (el modelo no ve la terminal)."""
    monkeypatch.setattr(nodes, "MAX_TOOL_ROUNDS", 2)
    observar = nodes.Observar()
    shared = {"messages": [{"role": "tool", "content": "r"}]}
    observar.post(shared, _tc("a.py"), None)
    assert shared["turno"]["rondas"] == 1
    assert "1/2" in shared["messages"][-1]["content"]


def test_no_hay_aviso_de_sin_progreso(monkeypatch):
    """La misma ronda repetida ya no deja el aviso de no-progreso: solo cuenta
    el saldo y su nota."""
    observar = nodes.Observar()
    shared = {"messages": [{"role": "tool", "content": "r"}]}
    for _ in range(3):
        shared["messages"].append({"role": "assistant", "content": "", "tool_calls": _tc("a.py")})
        shared["messages"].append({"role": "tool", "content": "r"})
        observar.post(shared, _tc("a.py"), None)
    assert shared["turno"]["rondas"] == 3
    assert "Sin progreso" not in shared["messages"][-1]["content"]


def test_contexto_sale_a_cierre_al_agotar_el_techo():
    """X96: al agotarse el techo, Contexto sale a `Cierre`, que llama sin
    tools y con el aviso efímero."""
    contexto = nodes.Contexto()
    assert contexto._run(_shared(rondas=0)) == "default"
    agotada = _shared(rondas=nodes.MAX_TOOL_ROUNDS)
    assert contexto._run(agotada) == "cierre"
    mensajes, tools = nodes.CierreChat(ctx_chat(rondas=0), []).prep(agotada)
    assert tools is None
    assert mensajes[-1]["content"] == nodes.AVISO_CIERRE


def test_el_saldo_del_turno_es_json_y_sobrevive_al_resume():
    """El saldo vive en `turno` como JSON (viaja en el checkpoint): un resume
    con el turno deserializado sigue cerrando por el techo."""
    turno = nodes.nuevo_turno()
    assert set(turno) == {"rondas", "skill", "uso_inicio"}
    assert json.loads(json.dumps(turno)) == turno
    resumido = {"messages": [], "turno": json.loads(json.dumps({**turno, "rondas": nodes.MAX_TOOL_ROUNDS}))}
    assert nodes.motivo_de_cierre(resumido) == "tope"


def test_el_saldo_baja_una_ronda_por_ronda(monkeypatch):
    monkeypatch.setattr(nodes, "MAX_TOOL_ROUNDS", 3)
    observar = nodes.Observar()
    shared = {"messages": [{"role": "tool", "content": "r"}]}
    for i in range(2):
        observar.post(shared, _tc("a.py"), None)
        assert nodes.motivo_de_cierre(shared) is None, i
    observar.post(shared, _tc("a.py"), None)
    assert shared["turno"]["rondas"] == 3
    assert nodes.motivo_de_cierre(shared) == "tope"


def test_la_nota_de_presupuesto_usa_el_techo_unico():
    nota = nodes.nota_presupuesto(15, 16)
    assert nota and "15/16" in nota and "ÚLTIMA" in nota
    assert nodes.nota_presupuesto(16, 16) is None


def test_los_nombres_de_las_politicas_viejas_no_estan_en_el_producto():
    """Criterio 4 del pre-registro: los cuatro nombres dan 0 coincidencias en
    el producto (comentarios incluidos), no solo 0 usos."""
    nombres = ("CORTE_NOVEDAD", "CORTE_NOVEDAD_MIN", "MAX_TOOL_ROUNDS_AMPLIO",
               "UMBRAL_SIN_PROGRESO")
    rutas = [RAIZ / "nodes.py", RAIZ / "main.py", RAIZ / "flow.py"]
    rutas += sorted((RAIZ / "utils").rglob("*.py")) + sorted((RAIZ / "modules").rglob("*.py"))
    for ruta in rutas:
        if not ruta.is_file():
            continue
        texto = ruta.read_text(encoding="utf-8")
        for nombre in nombres:
            assert nombre not in texto, f"{nombre} sigue en {ruta.relative_to(RAIZ)}"
