"""Replay de trazas (exp/41, Mesa 1): niveles A-C contra los grafos vivos.

Los niveles son funciones PURAS sobre listas de eventos: se testean sin
tocar disco ni red. Los grafos vivos se construyen una vez por módulo
(importar replay dispara lo mismo que viz: todos los flujos del registro).
"""
from pathlib import Path

import pytest

import replay

# Fijuras: grafos vivos + una caminata realista del chat


@pytest.fixture(scope="module")
def vivos():
    clases, aristas = replay._grafos_vivos()
    herramientas = replay._herramientas_vivas()
    return clases, aristas, herramientas


def _ev(nodo, accion, seg=0.1):
    return {"ts": 0.0, "nodo": nodo, "accion": accion, "seg": seg}


def _caminata_chat():
    """Una vuelta realista del chat de HOY (X106, un solo camino): pregunta →
    respuesta sin tools; pregunta → agente con tools → respuesta; salida.
    Incluye evento_tool intercalado (la forma real de la traza)."""
    return [
        _ev("GetQuestion", "continue"), _ev("PreFetch", "continue"), _ev("Skills", "continue"),
        _ev("Contexto", "herramientas"), _ev("AgentStep", "answer"), _ev("VerificarCitas", "default"),
        _ev("GetQuestion", "continue"), _ev("PreFetch", "continue"), _ev("Skills", "continue"),
        _ev("Contexto", "herramientas"), _ev("AgentStep", "tool"),
        _ev("read_file", "ok", 0.3),      # evento_tool entre AgentStep y ExecuteTools
        _ev("ExecuteTools", "default"), _ev("Observar", "default"),
        _ev("Contexto", "herramientas"), _ev("AgentStep", "answer"), _ev("VerificarCitas", "default"),
        _ev("GetQuestion", "exit"), _ev("ExitChat", "None"),
    ]


# Grafos vivos


def test_grafos_vivos_traen_el_chat_de_un_solo_camino(vivos):
    """X106: un solo grafo del chat, sin la variante ±router."""
    clases, aristas, _ = vivos
    for nodo in ("GetQuestion", "PreFetch", "Skills", "Contexto", "AgentStep",
                 "ExecuteTools", "Observar", "Cierre", "ExitChat"):
        assert nodo in clases, nodo
    for nodo in ("LayaRouter", "DirectAnswer"):
        assert nodo not in clases, nodo
    assert ("GetQuestion", "exit", "ExitChat") in aristas
    assert ("Skills", "continue", "Contexto") in aristas
    assert ("AgentStep", "tool", "ExecuteTools") in aristas
    # los pasajes transparentes: las caminatas sin PreFetch/Skills/Contexto valen
    assert ("PreFetch", "continue", "AgentStep") in aristas
    assert ("GetQuestion", "continue", "AgentStep") in aristas


def test_grafos_vivos_traen_los_inline_y_las_tools(vivos):
    clases, _, herramientas = vivos
    # debate y rag se construyen inline: igualmente presentes
    for nodo in ("Proponente", "Critico", "JuezDebate", "ChunkDocs", "SaveIndex"):
        assert nodo in clases, nodo
    # el action space vivo: las tools del CORE + los módulos
    for herramienta in ("read_file", "run_command", "answer_verified", "memory_save"):
        assert herramienta in herramientas, herramienta


# Nivel A — emisibilidad


def test_caminata_con_cierre_es_valida(vivos):
    """X96: un turno que agota el presupuesto termina en Cierre."""
    clases, aristas, _ = vivos
    cerrado = [_ev("GetQuestion", "continue"), _ev("PreFetch", "continue"), _ev("Skills", "continue"),
               _ev("Contexto", "herramientas"), _ev("AgentStep", "tool"), _ev("ExecuteTools", "default"),
               _ev("Observar", "default"), _ev("Contexto", "cierre"), _ev("Cierre", "answer"),
               _ev("VerificarCitas", "default"), _ev("GetQuestion", "exit"), _ev("ExitChat", "None")]
    assert replay.nivel_b_chat(cerrado, clases, aristas) == []
    assert replay.nivel_a(cerrado, clases) == []


def test_una_traza_del_router_se_ve_en_el_replay(vivos):
    """X106: el replay existe para esto — una caminata de producción que el
    código de HOY ya no puede dar. El router y la ruta directa son nodos
    desconocidos (A′) y sus aristas, adyacencia rota (B)."""
    clases, aristas, herramientas = vivos
    vieja = [_ev("GetQuestion", "continue"), _ev("LayaRouter", "directo"),
             _ev("Contexto", "directo"), _ev("DirectAnswer", "answer")]
    assert replay.nivel_a_desconocidos(vieja, clases, herramientas) == [
        ("LayaRouter", "directo"), ("DirectAnswer", "answer")]
    assert ("GetQuestion", "continue", "LayaRouter") in replay.nivel_b_chat(vieja, clases, aristas)


def test_caminata_valida_sin_violaciones(vivos):
    clases, aristas, herramientas = vivos
    eventos = _caminata_chat()
    assert replay.nivel_a(eventos, clases) == []
    assert replay.nivel_a_desconocidos(eventos, clases, herramientas) == []
    assert replay.nivel_b_chat(eventos, clases, aristas) == []
    assert replay.nivel_c_tools(eventos, clases, herramientas) == []


def test_accion_renombrada_no_es_emisible(vivos):
    """El caso del guard (exp/39) pero hacia atrás: una acción que YA no está
    cableada — incluida la ruta directa de Contexto, borrada en X106."""
    clases, *_ = vivos
    eventos = [_ev("AgentStep", "respuesta_vieja"), _ev("Contexto", "directo")]
    assert sorted(replay.nivel_a(eventos, clases)) == [
        ("AgentStep", "respuesta_vieja"), ("Contexto", "directo")]


def test_error_trazado_y_terminales_son_emisibles(vivos):
    """Las excepciones las traza el wrapper (error:Tipo): emisibles por
    cualquier nodo. Un terminal cerrando el flujo ('None'), también."""
    clases, *_ = vivos
    eventos = [
        _ev("AgentStep", "error:ValueError"),
        _ev("ExitChat", "None"),
        _ev("Entregar", "None"),
    ]
    assert replay.nivel_a(eventos, clases) == []


# Nivel B — adyacencia del chat


def test_adyacencia_rota_del_chat(vivos):
    """Un salto que el chat actual no puede dar: continue directo a
    ExecuteTools (el bug de aristas faltantes, en su forma de replay)."""
    clases, aristas, _ = vivos
    eventos = [_ev("GetQuestion", "continue"), _ev("ExecuteTools", "default")]
    assert replay.nivel_b_chat(eventos, clases, aristas) == [
        ("GetQuestion", "continue", "ExecuteTools")]


def test_no_chat_no_adyacencia(vivos):
    """Las trazas que no son del chat (batch/concurrentes) no se juzgan por
    adyacencia: sus reinicios de iteración e intercalados son legítimos."""
    clases, aristas, _ = vivos
    eventos = [
        _ev("Planner", "None"),
        _ev("Researcher", "None"),
        _ev("Synthesizer", "research"),
        _ev("Planner", "None"),  # loop del research: arista real
    ]
    assert replay.nivel_b_chat(eventos, clases, aristas) == []


def test_chat_con_flujo_interno_adyacencia(vivos):
    """La lección de la primera corrida real (246 falsos): el chat despacha
    supervisor/debate por tools y sus eventos quedan EN EL MISMO archivo.
    Los runs de nodos del chat se validan; los del flujo interno se saltan
    (ElegirSiguiente→EjecutarPaso es arista del SUPERVISOR, no del chat)."""
    clases, aristas, herramientas = vivos
    eventos = [
        _ev("GetQuestion", "continue"),
        _ev("AgentStep", "tool"),
        _ev("run_supervisor", "ok", 30.0),     # la tool que lanza el flujo
        _ev("ElegirSiguiente", "ejecutar"),     # eventos del flujo interno:
        _ev("EjecutarPaso", "elegir"),          # intercalados en la traza
        _ev("ElegirSiguiente", "sintetizar"),
        _ev("Sintetizar", "None"),
        _ev("ExecuteTools", "default"),         # el chat retoma su camino
        _ev("AgentStep", "answer"),
    ]
    assert replay.nivel_b_chat(eventos, clases, aristas) == []
    assert replay.nivel_a(eventos, clases) == []


def test_batch_interno_es_clase_viva(vivos):
    """La recursión dentro de los Flow/BatchFlow anidados: las clases del
    flujo interno de auditoría (CarpetaScan, Seccion) no eran alcanzables
    por successors — quedaban 'desconocidas' (medido: 16 falsos)."""
    clases, _, herramientas = vivos
    for nodo in ("CarpetaScan", "Seccion", "AnalizeFile", "ReduceGlobal"):
        assert nodo in clases, nodo
    eventos = [_ev("CarpetaScan", "None"), _ev("Seccion", "None")]
    assert replay.nivel_a_desconocidos(eventos, clases, herramientas) == []


# Nivel C — registro de tools


def test_tools_del_action_space_y_fantasmas(vivos):
    clases, _, herramientas = vivos
    eventos = [
        _ev("run_informe", "ok"),          # viva
        _ev("sql", "error"),               # viva
        _ev("bash", "ok"),                 # alias histórica tolerada
        _ev("corte_no_progreso", "ok"),    # marca de incidente tolerada
        _ev("tool_fantasma", "ok"),        # ya no existe
    ]
    assert replay.nivel_c_tools(eventos, clases, herramientas) == [
        ("tool_fantasma", "ok")]


def test_los_eventos_de_bookkeeping_no_son_desconocidos(vivos):
    """X97: `evento_llm`, `evento_hitl` y `evento_politica` (utils/tracing)
    los emite el código actual en cada sesión; contarlos como desconocidos
    inflaba el nivel A′ con miles de falsos positivos (el baseline de replay
    del 2026-10-13 los tiene adentro). Un nodo inventado con esas acciones
    fuera de su forma sí sigue siendo desconocido."""
    clases, _, herramientas = vivos
    eventos = [_ev("llm", "usage"), _ev("hitl_comando", "aprobado"),
               _ev("hitl_escritura", "rechazado"), _ev("corte_no_progreso", "politica"),
               _ev("corte_sin_novedad", "politica"),
               _ev("llm", "aprobado"), _ev("NodoViejo", "usage")]
    assert replay.nivel_a_desconocidos(eventos, clases, herramientas) == [
        ("llm", "aprobado"), ("NodoViejo", "usage")]


def test_nodo_desconocido_sin_clase_ni_tool(vivos):
    """A′ es para huérfanos de grafo; los tool-shaped (ok/error) son del
    nivel C — separación limpia, sin doble conteo (lección de la corrida)."""
    clases, _, herramientas = vivos
    eventos = [_ev("NodoViejo", "continue"), _ev("tool_fantasma", "ok")]
    assert replay.nivel_a_desconocidos(eventos, clases, herramientas) == [
        ("NodoViejo", "continue")]


# End-to-end sobre tmp: corrida, baseline y veredicto


def test_replay_runs_end_to_end(tmp_path, vivos, monkeypatch):
    """Dos trazas (una limpia, una rota): el informe cuenta por nivel, el
    markdown se escribe y el baseline compara."""
    runs = tmp_path / ".runs"
    runs.mkdir()
    (runs / "limpia.jsonl").write_text(
        "\n".join(_json(e) for e in _caminata_chat()) + "\n", encoding="utf-8")
    (runs / "rota.jsonl").write_text(
        _json(_ev("GetQuestion", "continue")) + "\n"
        + _json(_ev("AgentStep", "accion_renombrada")) + "\n"
        + _json(_ev("tool_fantasma", "ok")) + "\n"
        + _json(_ev("ExecuteTools", "default")) + "\n", encoding="utf-8")
    informe = replay.replay_runs(runs)
    assert informe["trazas"] == 2
    assert informe["trazas_chat"] == 2
    assert informe["violaciones"]["a"] == 1        # accion_renombrada
    assert informe["violaciones"]["c"] == 1        # tool_fantasma
    assert "d" not in informe["violaciones"]       # X106: sin nivel D
    # la rota.jsonl tiene un salto GetQuestion→AgentStep (válido) y
    # AgentStep(accion_renombrada)→tool_fantasma→ExecuteTools: los pares
    # con la tool filtrada quedan AgentStep→ExecuteTools, que NO es arista
    assert informe["violaciones"]["b"] >= 1

    # PRIMERA CORRIDA sin baseline; REGRESIÓN al volver con MÁS violaciones
    baseline = tmp_path / "replay_baseline.json"
    comparacion = replay.comparar_baseline(informe, ruta=baseline)
    assert comparacion["veredicto"] == "PRIMERA CORRIDA"
    replay.guardar_baseline(informe, ruta=baseline, sha="test")
    anterior = dict(informe)
    anterior["violaciones"] = {k: v - 1 for k, v in informe["violaciones"].items()}
    assert replay.comparar_baseline(anterior, ruta=baseline)["veredicto"] == "OK"
    mejorado = dict(informe)
    mejorado["violaciones"] = {k: v - 1 for k, v in informe["violaciones"].items()}
    empeorado = dict(informe)
    empeorado["violaciones"] = {k: v + 1 for k, v in informe["violaciones"].items()}
    assert replay.comparar_baseline(empeorado, ruta=baseline)["veredicto"] == "REGRESIÓN"
    assert replay.comparar_baseline(mejorado, ruta=baseline)["veredicto"] == "OK"

    # el informe markdown se escribe con la sección de límites primero
    destino = replay.generar(runs, dir_salida=tmp_path / "salidas", sha="test")
    texto = destino.read_text(encoding="utf-8")
    assert "Límite honesto" in texto
    assert "accion_renombrada" in texto and "tool_fantasma" in texto
    assert "Nivel D" not in texto


def _json(e):
    import json as _json

    return _json.dumps(e, ensure_ascii=False)


def test_main_replay_escribe(tmp_path, monkeypatch):
    """El CLI escribe el informe y SIN la flag no pisa el baseline."""
    runs = tmp_path / ".runs"
    runs.mkdir()
    (runs / "unica.jsonl").write_text(
        "\n".join(_json(e) for e in _caminata_chat()) + "\n", encoding="utf-8")
    baseline = tmp_path / "base.json"
    destino = replay.main([
        "--dir", str(runs), "--salida", str(tmp_path / "salidas")])
    assert Path(destino).is_file()
    assert not baseline.exists()  # nunca se guardó nada sin la flag
