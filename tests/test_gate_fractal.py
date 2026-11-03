"""El gate fractal (P2a): una política agregada una vez llega a todos los niveles.

El chat (`flow.create_agent_flow`), el supervisor y una copia anidada
(`kernel.agente`, o `kernel.loop` sobre un `Ctx.hijo`) son instancias del
mismo `kernel.loop`. La propiedad que los hace fractales no es compartir
archivo: es que cada política vive en UN punto y los tres niveles pasan por
ahí — el despacho con HITL y política de comandos (`fs_tools.run_tool_call`
→ `modules/coding.run_command`, la decisión en `utils/policy`), el saldo y
la compactación (la política `Contexto` sobre `utils/compaccion.compactar`,
montada por el mecanismo `politicas` del loop). El presupuesto tiene UNA
fuente por nivel: en el kernel es el `Ledger`; en el chat es `turno` (en
shared: lo corta Contexto, lo checkpointea resume, lo lee S9a) y el Ledger
es su proyección, derivada en cada `PasoChat.prep` (X140). Si un nivel gana
camino propio, este gate da rojo (P2a y S0) — y un loop sin freno FALLA
por timeout en vez de colgar la suite (X140).
"""
import builtins
import contextlib
import json
from types import SimpleNamespace as NS

import pytest

# X114: fuera de la lista blanca de pytest → la política dice "preguntar"
COMANDO = "pytest --pastebin=all"


@contextlib.contextmanager
def _sin_cuelgue(segundos=30):
    """X140: un loop al que le sacaron el freno tiene que FALLAR acá, no
    colgar la suite. `signal` de la stdlib: sin dependencias nuevas."""
    import signal

    def _timeout(signum, frame):
        raise TimeoutError(f"el loop no cerró en {segundos}s: le sacaron el freno")

    viejo = signal.signal(signal.SIGALRM, _timeout)
    signal.setitimer(signal.ITIMER_REAL, segundos)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, viejo)


def _llamada(nombre, args, id="c1"):
    """Tool call con la forma del SDK (atributos), como la normaliza el chat."""
    return NS(id=id, function=NS(name=nombre, arguments=json.dumps(args)))


def _msg(contenido=None, llamada=None):
    return NS(content=contenido, tool_calls=[llamada] if llamada else None)


def _correr_el_chat(monkeypatch, llm, entradas, techo=None, shared=None):
    """El chat REAL (el grafo de `flow.create_agent_flow`) con un modelo
    guionado; devuelve el shared. Misma receta que el candado de X136
    (tests/test_instrumentos_chat_real.py). `shared` pre-sembrado simula un
    thread rehidratado por resume (X140)."""
    import flow
    import nodes

    for clave, valor in {"CHAT_STREAM": "0", "PREFETCH": "0", "SKILLS": "0"}.items():
        monkeypatch.setenv(clave, valor)
    monkeypatch.setattr(nodes, "call_llm_agent", llm)
    respuestas = iter(entradas)
    monkeypatch.setattr(builtins, "input", lambda *a, **k: next(respuestas))
    if shared is None:
        shared = {"messages": [{"role": "system", "content": "s"}]}
    if techo is not None:
        shared["max_tool_rounds"] = techo
    with _sin_cuelgue():
        flow.create_agent_flow().run(shared)
    return shared


def _correr_el_supervisor(monkeypatch, tmp_path, llm, pasos):
    import supervisor

    monkeypatch.setattr(supervisor, "MAX_PASOS", pasos)
    monkeypatch.setattr(supervisor, "call_llm", lambda *a, **k: "síntesis")
    corrida = supervisor.Corrida(llm=llm)
    shared = supervisor.shared_de("tarea", str(tmp_path / "supervisor.md"))
    with _sin_cuelgue():
        supervisor.create_supervisor_flow(corrida).run(shared)
    return corrida


def _tool_de_modulo(nombre):
    """Una tool de módulo (run_command) como Tool del kernel, despachada por
    el ÚNICO camino (run_tool_call): el mismo que usan el chat y el
    supervisor."""
    import nodes
    from utils.fs_tools import run_tool_call
    from utils.kernel import Tool

    esquema = next(t for t in nodes.TOOLS if t["function"]["name"] == nombre)
    return Tool(nombre, esquema,
                lambda llamada, _ctx: run_tool_call(llamada, nodes.MODULE_IMPLS)["content"])


def _correr_una_copia(llm, saldo, herramientas):
    """Un árbol de dos niveles con la primitiva fractal: la raíz delega en
    `agente("copia")`, que corre su propio loop con el MISMO ledger (ctx.hijo)."""
    from utils.kernel import Ctx, Ledger, agente, loop, semilla

    ctx = Ctx(llm, Ledger(saldo))
    copia = agente("copia", "Resuelve el pedido autocontenido",
                   "Sos una copia anidada del mismo loop.", herramientas)
    shared = semilla("Sos la raíz y delegás en la copia.", "delegá: resolvé el pedido")
    with _sin_cuelgue():
        loop(ctx, [copia], wait=0).run(shared)
    return ctx, shared


def _resultado_tool(shared):
    return next(m["content"] for m in shared["messages"] if m.get("role") == "tool")


@pytest.fixture
def un_solo_humano(monkeypatch):
    """El punto único de la política, espiado: `clasificar` decide el nivel,
    `_approve` es el s/n y `_ejecutar` solo corre lo aprobado. El humano dice
    que no y nada se ejecuta."""
    import modules.coding as coding

    real = coding.clasificar
    espias = {"niveles": [], "pedidos": [], "ejecutados": []}

    def clasificar_espia(comando):
        nivel = real(comando)
        espias["niveles"].append(nivel)
        return nivel

    monkeypatch.setattr(coding, "clasificar", clasificar_espia)
    monkeypatch.setattr(coding, "_approve",
                        lambda p: espias["pedidos"].append(p) or False)
    monkeypatch.setattr(coding, "_ejecutar",
                        lambda c: espias["ejecutados"].append(c) or "exit 0")
    return espias


def test_un_rechazo_del_humano_llega_igual_al_chat_al_supervisor_y_a_una_copia(
        un_solo_humano, monkeypatch, tmp_path):
    """El HITL y la política de comandos están agregados UNA vez: el mismo
    comando clasifica igual, pregunta una vez por nivel y no se ejecuta en
    ninguno. Un nivel con camino propio (su propia política o su propio
    despacho) rompe los tres asserts del final."""
    # 1) el chat real
    import nodes
    import utils.fs_tools as fs

    real = fs.run_tool_call
    cruces = []

    def espia(llamada, impls=None):
        cruces.append(llamada["function"]["name"])
        return real(llamada, impls)

    monkeypatch.setattr(fs, "run_tool_call", espia)
    monkeypatch.setattr(nodes, "run_tool_call", espia)

    def llm_chat(mensajes, tools=None):
        if any(m.get("role") == "tool" for m in mensajes):
            return _msg("el humano lo rechazó")
        return _msg(None, _llamada("run_command", {"command": COMANDO}))

    shared = _correr_el_chat(monkeypatch, llm_chat,
                             ("corré los tests", "salir"))
    assert "RECHAZADO por el usuario" in _resultado_tool(shared)
    assert len(cruces) >= 1  # el chat despachó por el ÚNICO camino

    # 2) el supervisor real
    antes = len(cruces)

    def llm_sup(mensajes, tools=None):
        if any(m.get("role") == "tool" for m in mensajes):
            return _msg("tarea cerrada")
        return _msg(None, _llamada("run_command", {"command": COMANDO}))

    corrida = _correr_el_supervisor(monkeypatch, tmp_path, llm_sup, pasos=3)
    assert "RECHAZADO por el usuario" in corrida.ley["llamadas"][0]["resultado"]
    assert len(cruces) > antes  # el supervisor, por el mismo camino

    # 3) la copia anidada (profundidad 1, el saldo de la raíz)
    def llm_arbol(mensajes, tools=None):
        nombres = {t["function"]["name"] for t in tools or []}
        if "copia" in nombres:  # la raíz: delega una vez
            return _msg(None, _llamada("copia", {"pedido": "corré los tests"}))
        if any(m.get("role") == "tool" for m in mensajes):  # la copia ya vio el resultado
            return _msg(f"la copia vio: {_resultado_tool({'messages': mensajes})}")
        return _msg(None, _llamada("run_command", {"command": COMANDO}))

    antes_copia = len(cruces)
    ctx, shared_raiz = _correr_una_copia(llm_arbol, 4, [_tool_de_modulo("run_command")])
    assert "RECHAZADO por el usuario" in _resultado_tool(shared_raiz)
    assert (1, "run_command") in [e[:2] for e in ctx.traza]
    assert len(cruces) > antes_copia  # la copia, por el mismo camino

    # la propiedad: UNA definición consultada por los tres niveles
    assert un_solo_humano["niveles"] == ["preguntar"] * 3
    assert len(un_solo_humano["pedidos"]) == 3
    assert un_solo_humano["ejecutados"] == []


def test_sin_saldo_ningun_nivel_ejecuta_y_la_ultima_llamada_va_sin_tools(
        monkeypatch, tmp_path):
    """El presupuesto tiene UNA fuente por nivel (X140): en el chat es
    `turno` y el `kernel.Ledger` su proyección; en el supervisor y las copias
    es el Ledger. Agotado: la tool call pendiente no se ejecuta y la próxima
    llamada al modelo va sin tools — y en el chat, ADEMÁS con `AVISO_CIERRE`
    (A38: sin el aviso el modelo sigue emitiendo tool calls; el freno mudo
    del Ledger no lo reemplaza)."""
    import nodes
    from utils.fs_tools import run_tool_call as run_real

    ejecutadas = []

    def espia(llamada, impls=None):
        ejecutadas.append(llamada["function"]["name"])
        return run_real(llamada, impls)

    monkeypatch.setattr(nodes, "run_tool_call", espia)

    llamadas_chat = []

    def llm_chat(mensajes, tools=None):
        llamadas_chat.append(
            (tools, any(m.get("content") == nodes.AVISO_CIERRE for m in mensajes)))
        if tools is None:
            return _msg("cierro")
        return _msg(None, _llamada("read_file", {"path": "README.md"}))

    _correr_el_chat(monkeypatch, llm_chat, ("leé el README", "salir"), techo=1)
    assert ejecutadas == ["read_file"]        # una ronda y no más
    assert llamadas_chat[-1] == (None, True)  # la última: sin tools Y con aviso

    ejecutadas.clear()
    llamadas_sup = []

    def llm_sup(mensajes, tools=None):
        llamadas_sup.append(tools)
        if tools is None:
            return _msg("tarea cerrada")
        return _msg(None, _llamada("read_file", {"path": "README.md"}))

    corrida = _correr_el_supervisor(monkeypatch, tmp_path, llm_sup, pasos=1)
    assert [c["herramienta"] for c in corrida.ley["llamadas"]] == ["read_file"]
    assert llamadas_sup[-1] is None

    # la copia: la raíz gasta el saldo en delegar y a la copia no le queda
    # nada para tools → contesta sin ejecutar (el guion PIDE siempre que hay
    # tools: si el saldo no frenara, ejecutaría y el assert fallaría)
    from utils.kernel import Tool

    def llm_arbol(mensajes, tools=None):
        nombres = {t["function"]["name"] for t in tools or []}
        if "copia" in nombres:
            return _msg(None, _llamada("copia", {"pedido": "leé el README"}))
        if tools is None:
            return _msg("sin saldo para tools: contesto con lo que tengo")
        return _msg(None, _llamada("leer", {}))

    ctx, shared_raiz = _correr_una_copia(
        llm_arbol, 2, [Tool("leer", {"type": "function", "function": {"name": "leer"}},
                             lambda llamada, _ctx: ejecutadas.append("leer") or "x")])
    assert ejecutadas == []                          # nada corrió en el árbol
    assert [e[0] for e in ctx.traza] == [0]          # solo la raíz delegó (la copia, nada)
    assert "sin saldo para tools" in _resultado_tool(shared_raiz)

    # segundo árbol, con saldo para que la copia CORRA: las rondas de la copia
    # descuentan del ledger de la RAÍZ (ctx.hijo comparte el saldo, X119). Una
    # copia con ledger propio (o que no cobre su lugar) deja saldo en el padre
    # y este assert la denuncia.
    ejecutadas.clear()

    def llm_arbol_largo(mensajes, tools=None):
        nombres = {t["function"]["name"] for t in tools or []}
        if "copia" in nombres:
            return _msg(None, _llamada("copia", {"pedido": "leé todo"}))
        if tools is None:
            return _msg("la copia cerró sin saldo")
        return _msg(None, _llamada("leer", {}, id=f"c{len(mensajes)}"))

    ctx, _ = _correr_una_copia(
        llm_arbol_largo, 6, [Tool("leer", {"type": "function", "function": {"name": "leer"}},
                                   lambda llamada, _ctx: ejecutadas.append("leer") or "x")])
    assert ejecutadas == ["leer"] * 4   # delegación (1) + 4 rondas de la copia = 5 de 6
    assert ctx.ledger.rondas == 0       # la raíz quedó sin saldo: UN ledger para el árbol


def test_la_compactacion_es_una_politica_del_loop_y_corre_igual_en_una_copia(
        monkeypatch, tmp_path):
    """La compactación está agregada UNA vez (`utils/compaccion.compactar`,
    montada por la política `Contexto`): el mismo mecanismo `politicas` del
    kernel la corre en el chat y dentro de una copia anidada del MISMO loop.
    El supervisor no la declara (su loop va sin políticas): cada instancia
    declara sus políticas; lo que este gate fija es que no haya un segundo
    mecanismo propio del chat."""
    import nodes
    from utils.kernel import Ctx, Ledger, Tool, loop, semilla

    compactaciones = []
    real = nodes.compactar
    monkeypatch.setattr(nodes, "compactar",
                        lambda mensajes, tope, **kw: compactaciones.append(1)
                        or real(mensajes, tope, **kw))
    monkeypatch.setenv("COMPACTION_CHARS", "600")
    respuesta = "respuesta con contenido para pesar en la serialización. " * 4

    def llm_chat(mensajes, tools=None):
        return _msg(respuesta)

    # la ventana caliente son 6 unidades: hacen falta más de 8 para que haya
    # zona fría que compactar (compactar es no-op con menos)
    preguntas = tuple(f"pregunta {i}" for i in range(8)) + ("salir",)
    shared = _correr_el_chat(monkeypatch, llm_chat, preguntas)
    assert shared.get("compacciones", 0) >= 1

    # la copia anidada: el mismo loop (Ctx.hijo) con la MISMA política Contexto
    contador = iter(range(20))

    def llm_copia(mensajes, tools=None):
        n = next(contador)
        if n >= 8 or tools is None:
            return _msg("cierro")
        return _msg("ronda", _llamada("leer", {}, id=f"c{n}"))

    herramienta = Tool("leer", {"type": "function", "function": {"name": "leer"}},
                       lambda llamada, _ctx: "resultado de la lectura " * 8)
    ctx = Ctx(llm_copia, Ledger(12))
    shared_copia = semilla("Sos una copia anidada del mismo loop.", "leé todo")
    loop(ctx.hijo(), [herramienta], wait=0, politicas=(nodes.Contexto(),)).run(shared_copia)
    assert shared_copia.get("compacciones", 0) >= 1
    # UNA sola función de compactación atendió a los dos niveles
    assert len(compactaciones) >= 2


def test_el_saldo_del_chat_se_deriva_de_turno_en_cada_llamada():
    """X140: la fuente del presupuesto del chat es `turno` (en shared: lo
    checkpointea resume, lo lee S9a, lo corta Contexto) y el saldo del kernel
    es su PROYECCIÓN, derivada en CADA PasoChat.prep. Antes el Ledger se
    reseteaba solo al abrir la pregunta y bajaba con tomar(): dos cuentas del
    mismo número que coincidían por disciplina."""
    from conftest import ctx_chat

    import nodes

    paso = nodes.PasoChat(ctx_chat(rondas=99), [], max_retries=1, wait=0)
    for rondas, tope in ((0, 3), (2, 4), (4, 4)):
        shared = {"messages": [{"role": "system", "content": "s"}],
                  "turno": {**nodes.nuevo_turno(), "rondas": rondas},
                  "max_tool_rounds": tope}
        paso.prep(shared)
        assert paso.ctx.ledger.rondas == tope - rondas, (rondas, tope)


def test_el_loop_del_chat_cierra_por_el_saldo_del_kernel():
    """X140 (el mutante que pasaba): el chat ES una instancia del kernel — con
    el saldo en 0 y tool calls pendientes, su Paso también sale por la arista
    `cerrar`. En el flujo normal corta Contexto ANTES (con aviso); esta es la
    carrera de un árbol (X119) vista desde el chat, y sin este candado
    sacarle el freno al chat no rompe ningún test."""
    from conftest import ctx_chat

    import nodes

    paso = nodes.PasoChat(ctx_chat(rondas=0), [], max_retries=1, wait=0)
    shared = {"messages": [{"role": "system", "content": "s"},
                           {"role": "user", "content": "q"}],
              "turno": nodes.nuevo_turno()}
    assert paso.post(shared, None,
                     _msg(None, _llamada("read_file", {"path": "README.md"}))) == "cerrar"


def test_tras_un_resume_a_mitad_de_pregunta_el_presupuesto_se_reinicia(monkeypatch):
    """X140 (b): un thread rehidratado con el turno a mitad (rondas=2 de 4)
    llega con el presupuesto VIEJO en la caja; el primer mensaje nuevo
    reemplaza el turno ENTERO (exp/4: un mensaje nuevo reinicia el
    presupuesto). El gate fija que el saldo viejo no se filtre: el turno corre
    con su techo completo y cierra — ni una ronda menos ni una más."""
    import nodes

    llamadas = []

    def llm(mensajes, tools=None):
        llamadas.append(tools is None)
        if tools is None:
            return _msg("cierro")
        return _msg(None, _llamada("read_file", {"path": "README.md"},
                                   id=f"c{len(llamadas)}"))

    shared = {
        "messages": [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "leé el README"},
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "c9", "type": "function",
                             "function": {"name": "read_file",
                                          "arguments": '{"path": "README.md"}'}}]},
            {"role": "tool", "tool_call_id": "c9", "content": "contenido"},
        ],
        "turno": {**nodes.nuevo_turno(), "rondas": 2},
        "max_tool_rounds": 4,
    }
    _correr_el_chat(monkeypatch, llm, ("seguí", "salir"), shared=shared)
    assert sum(1 for sin_tools in llamadas if not sin_tools) == 4  # techo completo
    assert llamadas[-1] is True  # la última, sin tools (con aviso: el otro test)


def test_el_timeout_del_gate_falla_en_vez_de_colgar():
    """X140 (salvedad de la verificación externa): la red `_sin_cuelgue` en
    sí — M4c falla por las aserciones antes de llegar al timeout, así que la
    red no se ejercitaba nunca en verde. Un loop sin freno tiene que levantar
    TimeoutError acá, y la señal y el timer quedan restaurados (el segundo
    uso pasa limpio)."""
    import time

    with pytest.raises(TimeoutError, match="no cerró"), _sin_cuelgue(0.2):
        time.sleep(5)
    with _sin_cuelgue(1):  # restaurado: sin timer heredado del bloque anterior
        time.sleep(0)
