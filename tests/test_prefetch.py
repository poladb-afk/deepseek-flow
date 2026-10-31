"""Tests del pre-fetch declarativo (exp/50) — escritos por el conductor.

Tercera sesión que entrega el código sin sus tests (patrón medido: exp/44,
exp/46 parcial, exp/50); los candados de la spec §4 van acá."""

import nodes
from utils import prefetch
from utils.prefetch import PREFIJO_PREFETCH, decidir, mensaje


def _ajustes(monkeypatch, **valores):
    monkeypatch.setattr(
        prefetch, "_setting", lambda nombre, default=None: valores.get(nombre, default)
    )


def _pregunta_con(path):
    return f"¿Qué contiene exactamente {path}? Citálo."


# decidir: matching, contención, topes

def test_decidir_ruta_existente_del_repo(monkeypatch):
    _ajustes(monkeypatch)
    rutas = decidir(_pregunta_con("flow.py"))
    assert rutas and str(rutas[0][0]).endswith("flow.py")
    assert "create_agent_flow" in rutas[0][1]


def test_decidir_sin_match_o_inexistente(monkeypatch):
    _ajustes(monkeypatch)
    assert decidir("¿Por qué el cielo es azul?") == []
    assert decidir("¿Qué dice noexiste.xyz?") == []
    assert decidir("") == []
    assert decidir(None) == []


def test_decidir_fuera_del_perimetro_es_vacio(monkeypatch):
    """La contención del resolvedor existente manda: /etc/passwd no entra."""
    _ajustes(monkeypatch)
    assert decidir(_pregunta_con("/etc/passwd")) == []


def test_decidir_respeta_el_tope_de_archivos(monkeypatch):
    _ajustes(monkeypatch)
    monkeypatch.setattr(prefetch, "MAX_ARCHIVOS", 1)  # constante desde X101
    rutas = decidir("Compará flow.py y nodes.py línea por línea.")
    assert len(rutas) == 1


def test_decidir_apagado_es_vacio(monkeypatch):
    _ajustes(monkeypatch, PREFETCH="0")
    assert decidir(_pregunta_con("flow.py")) == []


# mensaje: la forma y la ley de ausencia

def test_mensaje_con_prefijo_y_none_sin_match():
    texto = mensaje([("flow.py", "contenido")])
    assert texto is not None and texto.startswith(PREFIJO_PREFETCH)
    assert "flow.py" in texto and "contenido" in texto
    assert mensaje([]) is None


# el nodo: appendea, no rompe invariantes, y es no-op apagado

def _shared_con_pregunta(texto):
    return {"messages": [
        {"role": "system", "content": "s"},
        {"role": "user", "content": texto},
    ]}


def test_prefetch_node_appendea_y_valida(monkeypatch):
    from utils.compaccion import validar_historial

    _ajustes(monkeypatch)
    shared = _shared_con_pregunta(_pregunta_con("flow.py"))
    assert validar_historial(shared["messages"]) == []
    nodo = nodes.PreFetch()
    assert nodo.post(shared, nodo.prep(shared), nodo.exec(nodo.prep(shared))) == "continue"
    assert validar_historial(shared["messages"]) == []
    assert shared["messages"][-1]["role"] == "user"
    assert shared["messages"][-1]["content"].startswith(PREFIJO_PREFETCH)


def test_prefetch_node_no_op_sin_match(monkeypatch):
    _ajustes(monkeypatch)
    shared = _shared_con_pregunta("¿Por qué el cielo es azul?")
    antes = len(shared["messages"])
    nodo = nodes.PreFetch()
    nodo.post(shared, "", nodo.exec(""))
    assert len(shared["messages"]) == antes


def test_prefetch_prep_saltea_mensajes_prefetch(monkeypatch):
    """El prep del propio nodo tampoco se traga un prefetch viejo como
    pregunta (idempotente en conversaciones largas)."""
    _ajustes(monkeypatch)
    shared = _shared_con_pregunta("pregunta buena")
    shared["messages"].append({"role": "user", "content": f"{PREFIJO_PREFETCH} flow.py …"})
    assert nodes.PreFetch().prep(shared) == "pregunta buena"




# marcador del banco: positiva la línea real, negativo el template

def test_marcador_prefetch_del_banco():
    import re

    from banco.banco import MARCADORES

    patron = MARCADORES["prefetch"]
    assert re.search(patron, "  [pre-fetch] /repo/flow.py")
    assert not re.search(patron, 'print(colorear(f"  {PREFIJO_PREFETCH} {path}", "info"))'), (
        "el template del código NO debe matchear (lección H2/Fix 10)"
    )


def test_pregunta_en_curso_saltea_prefetch_y_skill():
    """§3 de exp/50 sin router (X106): PreFetch y Skills leen la PREGUNTA
    aunque el pre-fetch o el skill hayan quedado últimos."""
    from utils.skills import PREFIJO_SKILL

    mensajes = [{"role": "user", "content": "¿Quién ganó el último mundial?"},
                {"role": "user", "content": f"{PREFIJO_PREFETCH} algo.md …"},
                {"role": "user", "content": f"{PREFIJO_SKILL} revision — x"}]
    assert nodes.pregunta_en_curso(mensajes) == "¿Quién ganó el último mundial?"
