"""Tests del thread serializable (exp/48) — sin LLM, sin red, sin modelo.

Cubre las funciones PURAS de utils.thread_store (roundtrip, cola cortada,
apagado por setting, bookkeeping ante fallos, validador reusado, reparación de
pendientes de exp/49) y los CUATRO puntos seguros del chat: GetQuestion.post,
ExecuteTools.post, AgentStep.post(answer) y AgentStep.post(tool: la SELECCIÓN,
exp/49) escriben un checkpoint (contador de líneas).
"""
import json
from types import SimpleNamespace

from utils import thread_store
from utils.compaccion import PREFIJO_COMPACCION

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shared(n, tool_rounds=0, no_progress=0):
    """Un shared mínimo con historial agéntico VÁLIDO (system + user)."""
    mensajes = [{"role": "system", "content": "sos un agente"}]
    for i in range(n):
        mensajes.append({"role": "user", "content": f"pregunta {i}"})
        mensajes.append({"role": "assistant", "content": f"respuesta {i}"})
    return {"messages": mensajes, "tool_rounds": tool_rounds, "no_progress": no_progress}


def _lineas(archivo):
    return archivo.read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------------------
# 1. Roundtrip
# ---------------------------------------------------------------------------

def test_roundtrip_devuelve_el_ultimo(tmp_path, monkeypatch):
    monkeypatch.setenv("THREADS_DIR", str(tmp_path))
    primero = _shared(1, tool_rounds=0, no_progress=0)
    segundo = _shared(2, tool_rounds=3, no_progress=1)
    thread_store.checkpoint("t1", "GetQuestion", "continue", primero)
    thread_store.checkpoint("t1", "ExecuteTools", "default", segundo)

    cargado = thread_store.cargar("t1")
    assert cargado == segundo          # el ÚLTIMO (segundo), no el primero
    assert cargado != primero
    # igualdad canónica: serialización estable de los mensajes
    assert json.dumps(cargado, sort_keys=True) == json.dumps(segundo, sort_keys=True)


def test_checkpoint_escribe_una_linea_por_evento(tmp_path, monkeypatch):
    monkeypatch.setenv("THREADS_DIR", str(tmp_path))
    thread_store.checkpoint("t2", "GetQuestion", "continue", _shared(0))
    thread_store.checkpoint("t2", "ExecuteTools", "default", _shared(1))
    lineas = _lineas(tmp_path / "t2.jsonl")
    assert len(lineas) == 2
    evento = json.loads(lineas[0])
    assert evento["evento"] == "checkpoint"
    assert evento["nodo"] == "GetQuestion" and evento["accion"] == "continue"
    assert isinstance(evento["shared"], dict) and "messages" in evento["shared"]
    assert "ts" in evento


# ---------------------------------------------------------------------------
# 2. Cola cortada (crash a mitad de escritura)
# ---------------------------------------------------------------------------

def test_cola_cortada_devuelve_el_anterior(tmp_path, monkeypatch):
    monkeypatch.setenv("THREADS_DIR", str(tmp_path))
    bueno = _shared(2)
    thread_store.checkpoint("t3", "GetQuestion", "continue", bueno)
    # simula un crash: línea a medias, SIN \n final y con JSON roto
    with open(tmp_path / "t3.jsonl", "a", encoding="utf-8") as f:
        f.write('{"ts": 1.0, "evento": "checkpoint", "nodo": "Exec')

    cargado = thread_store.cargar("t3")   # no levanta
    assert cargado == bueno


def test_cola_cortada_sin_newline_final(tmp_path, monkeypatch):
    """Una línea completa sin \n final SÍ se lee (no es una cola cortada)."""
    monkeypatch.setenv("THREADS_DIR", str(tmp_path))
    bueno = _shared(1)
    linea = json.dumps({"ts": 1.0, "evento": "checkpoint", "nodo": "X",
                        "accion": "continue", "shared": bueno})
    (tmp_path / "t4.jsonl").write_text(linea, encoding="utf-8")  # sin \n
    assert thread_store.cargar("t4") == bueno


def test_varias_lineas_rotas_al_final(tmp_path, monkeypatch):
    monkeypatch.setenv("THREADS_DIR", str(tmp_path))
    bueno = _shared(2)
    thread_store.checkpoint("t5", "GetQuestion", "continue", bueno)
    with open(tmp_path / "t5.jsonl", "a", encoding="utf-8") as f:
        f.write("basura que no es json\n")
        f.write('{"ts": 2.0, "evento": "chec')   # segunda cola cortada
    assert thread_store.cargar("t5") == bueno


# ---------------------------------------------------------------------------
# 3. THREAD_PERSIST=0 apaga TODO (ni crea el directorio)
# ---------------------------------------------------------------------------

def test_persist_0_no_escribe_ni_crea_dir(tmp_path, monkeypatch):
    destino = tmp_path / "nunca"
    monkeypatch.setenv("THREADS_DIR", str(destino))
    monkeypatch.setenv("THREAD_PERSIST", "0")
    thread_store.checkpoint("t6", "GetQuestion", "continue", _shared(0))
    assert not destino.exists()
    assert not (destino / "t6.jsonl").exists()
    assert thread_store.cargar("t6") is None


def test_persist_default_escribe(tmp_path, monkeypatch):
    monkeypatch.setenv("THREADS_DIR", str(tmp_path))
    monkeypatch.delenv("THREAD_PERSIST", raising=False)
    thread_store.checkpoint("t7", "GetQuestion", "continue", _shared(0))
    assert (tmp_path / "t7.jsonl").exists()


# ---------------------------------------------------------------------------
# 4. None para id inexistente; fallo de escritura no levanta (bookkeeping)
# ---------------------------------------------------------------------------

def test_cargar_id_inexistente_devuelve_none(tmp_path, monkeypatch):
    monkeypatch.setenv("THREADS_DIR", str(tmp_path))
    assert thread_store.cargar("no_existe") is None


def test_checkpoint_fallo_de_escritura_no_levanta(tmp_path, monkeypatch):
    """Un fallo de escritura NO rompe el chat (bookkeeping).

    Se fuerza con THREADS_DIR apuntando a un ARCHIVO (no un dir): mkdir sobre
    él falla para cualquier uid (un chmod 0o500 lo ignoraría root)."""
    archivo = tmp_path / "soy_un_archivo"
    archivo.write_text("x", encoding="utf-8")
    monkeypatch.setenv("THREADS_DIR", str(archivo / "sub"))  # padre es archivo
    thread_store.checkpoint("t8", "GetQuestion", "continue", _shared(0))  # no levanta


# ---------------------------------------------------------------------------
# 5. valido(): reusa validar_historial (no reimplementa)
# ---------------------------------------------------------------------------

def test_valido_historial_valido_sin_violaciones():
    assert thread_store.valido(_shared(2)) == []


def test_valido_assistant_sin_sus_tools_es_violacion():
    """Un assistant con tool_calls sin las tools inmediatas → violación."""
    shared = {
        "messages": [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "a", "type": "function",
                             "function": {"name": "read_file", "arguments": "{}"}}]},
            # falta el mensaje role=tool con tool_call_id "a"
            {"role": "user", "content": "seguí"},
        ],
        "tool_rounds": 1,
    }
    violaciones = thread_store.valido(shared)
    assert violaciones and any("tool_calls" in v for v in violaciones)


def test_valido_reusa_el_validador_de_compaccion(monkeypatch):
    """No reimplementa: delega en utils.compaccion.validar_historial."""
    from utils import compaccion

    llamadas = []
    original = compaccion.validar_historial

    def espia(messages):
        llamadas.append(messages)
        return original(messages)

    monkeypatch.setattr(compaccion, "validar_historial", espia)
    assert thread_store.valido(_shared(1)) == []
    assert len(llamadas) == 1


def test_valido_no_levanta_con_estructura_rara():
    """Un shared sin messages o de tipo raro devuelve violaciones, no explota."""
    assert thread_store.valido({}) != []          # messages ausente → vacío inválido
    assert thread_store.valido("no soy dict") != []
    assert thread_store.valido({"messages": ["no soy dict"]}) != []


def test_shared_valido_con_compaccion_tambien_pasa():
    """Un historial con prefijo de compacción sigue siendo válido (invariantes)."""
    shared = _shared(2)
    shared["messages"].insert(1, {"role": "user", "content": f"{PREFIJO_COMPACCION} 4 omitidos"})
    assert thread_store.valido(shared) == []


# ---------------------------------------------------------------------------
# 6. Los TRES puntos seguros escriben checkpoint (contador de líneas)
# ---------------------------------------------------------------------------

def _contar(tmp_path, id_thread):
    archivo = tmp_path / f"{id_thread}.jsonl"
    return len(_lineas(archivo)) if archivo.exists() else 0


def test_punto_seguro_getquestion_post(tmp_path, monkeypatch):
    import nodes

    monkeypatch.setenv("THREADS_DIR", str(tmp_path))
    monkeypatch.setattr(nodes, "thread_id", lambda: "chat1")
    monkeypatch.setattr(nodes, "registrar_pregunta", lambda *a, **k: None)
    monkeypatch.setattr("utils.estado_sesion.recordar_usuario", lambda *a, **k: None)

    shared = {"messages": [{"role": "system", "content": "s"}], "tool_rounds": 9}
    assert nodes.GetQuestion().post(shared, None, "hola") == "continue"
    assert _contar(tmp_path, "chat1") == 1
    linea = json.loads(_lineas(tmp_path / "chat1.jsonl")[0])
    assert linea["nodo"] == "GetQuestion" and linea["accion"] == "continue"
    assert linea["shared"]["messages"][-1]["content"] == "hola"


def test_punto_seguro_executetools_post(tmp_path, monkeypatch):
    import nodes

    monkeypatch.setenv("THREADS_DIR", str(tmp_path))
    monkeypatch.setattr(nodes, "thread_id", lambda: "chat2")
    # ejecución de tools simulada: el post solo mira los resultados y el fingerprint
    shared = {"messages": [], "tool_rounds": 0}
    prep_res = [{"function": {"name": "read_file", "arguments": "{}"}}]
    exec_res = [{"tool_call_id": "a", "content": "ok"}]
    assert nodes.ExecuteTools().post(shared, prep_res, exec_res) == "default"
    assert _contar(tmp_path, "chat2") == 1
    linea = json.loads(_lineas(tmp_path / "chat2.jsonl")[0])
    assert linea["nodo"] == "ExecuteTools" and linea["accion"] == "default"
    assert linea["shared"]["tool_rounds"] == 1


def test_punto_seguro_agentstep_post_answer(tmp_path, monkeypatch):
    import nodes

    monkeypatch.setenv("THREADS_DIR", str(tmp_path))
    monkeypatch.setenv("CHAT_STREAM", "0")
    monkeypatch.setattr(nodes, "thread_id", lambda: "chat3")
    respuesta = SimpleNamespace(content="listo", tool_calls=None)
    shared = {"messages": [], "tool_rounds": 2}
    assert nodes.AgentStep().post(shared, None, respuesta) == "answer"
    assert _contar(tmp_path, "chat3") == 1
    linea = json.loads(_lineas(tmp_path / "chat3.jsonl")[0])
    assert linea["nodo"] == "AgentStep" and linea["accion"] == "answer"


def test_punto_seguro_agentstep_checkpointea_la_seleccion(tmp_path, monkeypatch):
    """exp/49: el camino "tool" SÍ es punto seguro (la SELECCIÓN, factor 8).

    Con tool_calls se escribe una línea "tool" (llamadas seleccionadas pero NO
    ejecutadas); sin tool_calls se escribe "answer" y NUNCA "tool"."""
    import nodes

    monkeypatch.setenv("THREADS_DIR", str(tmp_path))
    monkeypatch.setattr(nodes, "thread_id", lambda: "chat4")
    respuesta = SimpleNamespace(
        content=None,
        tool_calls=[SimpleNamespace(id="x", function=SimpleNamespace(name="read_file", arguments="{}"))],
    )
    shared = {"messages": [], "tool_rounds": 0}
    assert nodes.AgentStep().post(shared, None, respuesta) == "tool"
    assert _contar(tmp_path, "chat4") == 1
    linea = json.loads(_lineas(tmp_path / "chat4.jsonl")[0])
    assert linea["nodo"] == "AgentStep" and linea["accion"] == "tool"
    # sin tool_calls: "answer" y NO "tool"
    monkeypatch.setenv("CHAT_STREAM", "0")
    monkeypatch.setattr(nodes, "thread_id", lambda: "chat4b")
    respuesta_answer = SimpleNamespace(content="listo", tool_calls=None)
    assert nodes.AgentStep().post({"messages": [], "tool_rounds": 0}, None, respuesta_answer) == "answer"
    linea = json.loads(_lineas(tmp_path / "chat4b.jsonl")[0])
    assert linea["accion"] == "answer" and linea["accion"] != "tool"


# ---------------------------------------------------------------------------
# thread_id(): idempotente por proceso, mismo stem que el trace si hay tracing
# ---------------------------------------------------------------------------

def test_thread_id_idempotente_por_proceso():
    from utils import tracing

    monkeypatch_backup = tracing._id_thread
    tracing._id_thread = None
    try:
        primero = tracing.thread_id()
        assert primero == tracing.thread_id()          # idempotente
        assert primero and isinstance(primero, str)
    finally:
        tracing._id_thread = monkeypatch_backup


def test_thread_id_reusa_el_stem_del_trace(monkeypatch):
    from utils import tracing

    monkeypatch.setattr(tracing, "_salida", SimpleNamespace(name="20261014_120000_1234.jsonl"))
    monkeypatch.setattr(tracing, "_id_thread", None)
    assert tracing.thread_id() == "20261014_120000_1234"


# ---------------------------------------------------------------------------
# 7. reparar_pendientes(): los tool_calls huérfanos del ÚLTIMO assistant (exp/49)
# ---------------------------------------------------------------------------

def _assistant_con_tool_calls(ids):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": i, "type": "function",
                            "function": {"name": "read_file", "arguments": "{}"}}
                           for i in ids]}


def test_reparar_pendientes_repara_los_huerfanos_del_final():
    """(a) assistant con 2 tool_calls sin sus tools → 2 mensajes tool, devuelve 2."""
    shared = {"messages": [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        _assistant_con_tool_calls(["a", "b"]),
    ]}
    n = thread_store.reparar_pendientes(shared)
    assert n == 2
    tools = shared["messages"][-2:]
    assert [t["role"] for t in tools] == ["tool", "tool"]
    assert [t["tool_call_id"] for t in tools] == ["a", "b"]
    for t in tools:
        assert "interrumpido" in t["content"]
    # la reparación deja el historial VÁLIDO (antes violaba)
    assert thread_store.valido(shared) == []


def test_reparar_pendientes_es_idempotente():
    """Llamarla dos veces: la segunda repara 0 y no toca nada más."""
    shared = {"messages": [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        _assistant_con_tool_calls(["a", "b"]),
    ]}
    assert thread_store.reparar_pendientes(shared) == 2
    antes = len(shared["messages"])
    assert thread_store.reparar_pendientes(shared) == 0
    assert len(shared["messages"]) == antes


def test_reparar_pendientes_historial_pareado_no_cambia():
    """(b) historial ya pareado → 0 y sin cambios."""
    shared = {"messages": [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        _assistant_con_tool_calls(["a"]),
        {"role": "tool", "tool_call_id": "a", "content": "ok"},
        {"role": "assistant", "content": "listo"},
    ]}
    copia = [dict(m) for m in shared["messages"]]
    assert thread_store.reparar_pendientes(shared) == 0
    assert shared["messages"] == copia


def test_reparar_pendientes_no_toca_pares_viejos_rotos_en_el_medio():
    """(c) pares rotos VIEJOS en el medio NO se tocan: solo el final es interrupción."""
    shared = {"messages": [
        {"role": "system", "content": "s"},
        _assistant_con_tool_calls(["viejo"]),  # huérfano viejo, SIN su tool
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "seguí"},
    ]}
    copia = [dict(m) for m in shared["messages"]]
    # el último assistant NO tiene tool_calls: nada que reparar
    assert thread_store.reparar_pendientes(shared) == 0
    assert shared["messages"] == copia
    # y el huérfano viejo sigue siendo una violación (la caza el validador)
    assert thread_store.valido(shared) != []


def test_reparar_pendientes_shared_sin_messages_no_explota():
    """(d) shared sin messages (o de tipo raro) → 0 sin explotar."""
    assert thread_store.reparar_pendientes({}) == 0
    assert thread_store.reparar_pendientes("no soy dict") == 0
    assert thread_store.reparar_pendientes({"messages": []}) == 0
    assert thread_store.reparar_pendientes({"messages": "no soy lista"}) == 0


# ---------------------------------------------------------------------------
# 8. resume end-to-end: reparar ANTES de validar salva un thread a mitad de ronda
# ---------------------------------------------------------------------------

def test_resume_repara_una_seleccion_pendiente(tmp_path, monkeypatch):
    """Un thread que termina en selección pendiente: cargar → reparar → valido []."""
    from utils import thread_store as ts

    monkeypatch.setenv("THREADS_DIR", str(tmp_path))
    shared = {"messages": [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        _assistant_con_tool_calls(["x"]),
    ], "tool_rounds": 1}
    ts.checkpoint("crash", "AgentStep", "tool", shared)

    cargado = ts.cargar("crash")
    # antes de reparar, el historial viola el invariante de la API
    assert ts.valido(cargado) != []
    n = ts.reparar_pendientes(cargado)
    assert n == 1
    assert ts.valido(cargado) == []
