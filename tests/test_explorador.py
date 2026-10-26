"""Explorador aislado (exp/97): contexto fresco, whitelist de sólo lectura,
presupuesto propio que declara lo usado. Sin LLM ni red (fakes)."""
import explorador as ex
import supervisor as sup


class MsgFake:
    def __init__(self, tool_calls=None, content=None):
        self.tool_calls, self.content = tool_calls, content


def tc_fake(nombre, args, i=1):
    return type("TC", (), {"id": f"c{i}", "type": "function",
                           "function": type("F", (), {"name": nombre, "arguments": args})()})()


def test_explorador_contexto_fresco_whitelist_y_presupuesto(tmp_path, monkeypatch):
    """C1: el LLM del explorador ve SOLO el system del explorador y la
    pregunta (nada del padre); la whitelist no tiene escritura ni
    run_command; el presupuesto se respeta y se declara; el retorno es texto."""
    monkeypatch.setattr(ex, "MAX_PASOS_EXPLORADOR", 2)
    monkeypatch.setattr("utils.fs_tools.read_file", lambda **k: "contenido de a.py")

    vistos = []

    def call_llm_agent_fake(messages, tools=None):
        vistos.append(([dict(m) for m in messages], tools))
        if len(vistos) == 1:
            return MsgFake(tool_calls=[tc_fake("read_file", '{"path": "a.py"}')])
        return MsgFake(tool_calls=[tc_fake("read_file", '{"path": "b.py"}', 2)])

    monkeypatch.setattr(ex, "call_llm_agent", call_llm_agent_fake)

    texto = ex.explorar("¿dónde se define la whitelist?")
    # desde H2 el cierre forzado es la llamada SIN tools: con saldo 2 hay 3 llamadas

    # contexto fresco: la 1ª llamada ve exactamente system + pregunta
    primeros = vistos[0][0]
    assert [m["role"] for m in primeros] == ["system", "user"]
    assert primeros[1]["content"] == "¿dónde se define la whitelist?"
    assert "sub-agente de INVESTIGACIÓN" in primeros[0]["content"]
    # whitelist: ninguna tool que escriba o ejecute
    nombres = {t["function"]["name"] for t in vistos[0][1]}
    assert nombres == {"read_file", "list_files", "search_files"}
    assert not nombres & {"run_command", "write_file", "edit_file"}
    # presupuesto: agotadas las 2 rondas las tools se retiran (cierre forzado)
    assert vistos[1][1] is not None
    assert vistos[2][1] is None
    assert isinstance(texto, str)
    assert "usó 2 de 2 rondas" in texto


def test_explorador_tool_fuera_de_la_whitelist_no_existe(tmp_path, monkeypatch):
    """C2: aunque el modelo pida run_command, run_tool_call no la conoce para
    el explorador (el permiso es el mapa) y no se ejecuta nada."""
    ejecutados = []
    monkeypatch.setattr("utils.fs_tools.read_file", lambda **k: ejecutados.append(k) or "x")

    pasos = {"n": 0}

    def call_llm_agent_fake(messages, tools=None):
        pasos["n"] += 1
        if pasos["n"] == 1:
            return MsgFake(tool_calls=[tc_fake("run_command", '{"command": "rm -rf /"}')])
        return MsgFake(content="cerrado")

    monkeypatch.setattr(ex, "call_llm_agent", call_llm_agent_fake)

    texto = ex.explorar("intentá escribir")
    assert ejecutados == []
    assert "cerrado" in texto


def test_explorador_cableado_en_supervisor_solo_con_setting(tmp_path, monkeypatch):
    """exp/97 §2: con EXPLORAR=1 la tool entra al catálogo y al REGISTRO; sin
    el setting, catálogo y REGISTRO quedan como antes (default off)."""
    import importlib

    monkeypatch.setenv("EXPLORAR", "1")
    sup_encendido = importlib.reload(sup)
    nombres = {t["function"]["name"] for t in sup_encendido._TODAS}
    assert "explorar" in nombres
    assert sup_encendido.REGISTRO["explorar"] is ex.explorar

    monkeypatch.delenv("EXPLORAR", raising=False)
    sup_apagado = importlib.reload(sup)
    assert "explorar" not in {t["function"]["name"] for t in sup_apagado._TODAS}
    assert "explorar" not in sup_apagado.REGISTRO
    importlib.reload(sup)


def test_supervisor_no_anuncia_explorar_en_la_ultima_ronda(monkeypatch):
    """exp/97 §3: en la última ronda `explorar` no se anuncia (evita cerrar
    con una exploración colgada). Desde H2 PR 2 lo garantiza el kernel: un
    sub-agente solo se ofrece si queda saldo para él y su loop (≥ 2)."""
    import supervisor as sup
    from utils.kernel import Paso

    monkeypatch.setattr(sup, "_TODAS", sup._TODAS + [ex.TOOL_EXPLORAR])
    shared = sup.semilla("tarea", "salidas/sup.md", llm=lambda m, t: None)

    shared["ctx"].ledger.rondas = 1
    _, _, tools = Paso().prep(shared)
    assert "explorar" not in {t["function"]["name"] for t in tools}
    assert "read_file" in {t["function"]["name"] for t in tools}

    shared["ctx"].ledger.rondas = sup.MAX_PASOS
    _, _, tools = Paso().prep(shared)
    assert "explorar" in {t["function"]["name"] for t in tools}


def test_explorar_por_el_flow_completo(tmp_path, monkeypatch):
    """El loop real (el kernel: nodos + Flow) con el LLM mockeado: sin tools
    pedidas cierra en una llamada, con el resumen como texto y 0 rondas."""
    vistos = []
    monkeypatch.setattr(ex, "call_llm_agent",
                        lambda messages, tools=None: vistos.append(tools) or MsgFake(content="resumen: a.py:3"))
    texto = ex.explorar("¿dónde está?")
    assert texto.startswith("resumen: a.py:3")
    assert "usó 0 de" in texto
    assert len(vistos) == 1 and {t["function"]["name"] for t in vistos[0]} == set(ex.PERMITIDAS)


def test_el_explorador_como_tool_del_kernel_usa_su_system(monkeypatch):
    """La tool que el supervisor va a llamar desde el kernel (PR 2) corre con
    el MISMO system de solo lectura que explorar(): no uno vacío."""
    import json

    from utils.kernel import Ctx, Ledger

    vistos = []

    def llm(messages, tools=None):
        vistos.append(messages[0]["content"])
        return MsgFake(content="resumen")

    llamada = {"id": "1", "function": {"name": "explorar",
                                        "arguments": json.dumps({"pregunta": "¿dónde está X?"})}}
    assert ex.AGENTE.correr(llamada, Ctx(llm, Ledger(3))) == "resumen"
    assert "sub-agente de INVESTIGACIÓN" in vistos[0] and "¿dónde está X?" in vistos[0]
    assert ex.AGENTE.efecto == "lectura"
