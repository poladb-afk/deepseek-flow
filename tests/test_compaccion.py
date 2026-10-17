"""Compactación del historial: zona fría, unidades indivisibles y validación (PR 4)."""


def _historial_sintetico(n_vueltas=50, relleno=400):
    """Historial canónico grande: system + N vueltas (user → assistant con
    tool_calls → tool → assistant texto). Cada vuelta son 4 mensajes, así
    que n_vueltas=50 da 201 mensajes, con mezcla real de tools."""
    msgs = [{"role": "system", "content": "system prompt estable " + "x" * 200}]
    for i in range(n_vueltas):
        msgs.append({"role": "user", "content": f"pedido {i} " + "u" * relleno})
        msgs.append({
            "role": "assistant", "content": None,
            "tool_calls": [{"id": f"call_{i}", "type": "function",
                            "function": {"name": "read_file", "arguments": "{}"}}],
        })
        msgs.append({"role": "tool", "tool_call_id": f"call_{i}",
                     "content": f"resultado {i} " + "t" * relleno})
        msgs.append({"role": "assistant", "content": f"respuesta {i} " + "a" * relleno})
    return msgs

def test_compaccion_noop_historial_corto():
    """Con menos de ventana+2 mensajes devuelve intacto (no-op documentado)."""
    from utils.compaccion import compactar

    corto = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hola " + "x" * 5000},
        {"role": "assistant", "content": "chau " + "y" * 5000},
    ]
    out = compactar(corto, max_chars=10)
    assert out == corto  # intacto aunque supere max_chars

def test_compaccion_noop_si_entra_en_max_chars():
    """Si el historial ya entra en max_chars, no toca nada."""
    from utils.compaccion import compactar, serializar

    largo = _historial_sintetico(n_vueltas=10)
    out = compactar(largo, max_chars=len(serializar(largo)) + 10)
    assert out == largo

def test_compaccion_conserva_system_y_ventana_caliente():
    """El system y los últimos N mensajes quedan intactos; la zona fría se
    reemplaza por UN resumen [compacción]."""
    from utils.compaccion import PREFIJO_COMPACCION, VENTANA_DEFAULT, compactar

    largo = _historial_sintetico(n_vueltas=40)
    out = compactar(largo, max_chars=100)
    # system intacto
    assert out[0] == largo[0]
    # resumen sintético en el medio
    assert out[1]["role"] == "user"
    assert out[1]["content"].startswith(PREFIJO_COMPACCION)
    # la ventana caliente son los últimos N mensajes, idénticos byte a byte
    assert out[-(VENTANA_DEFAULT):] == largo[-(VENTANA_DEFAULT):]
    assert len(out) < len(largo)

def test_compaccion_unidad_indivisible():
    """Compactar nunca deja un assistant con tool_calls sin su tool, ni una
    tool huérfana."""
    from utils.compaccion import compactar, validar_historial

    largo = _historial_sintetico(n_vueltas=40)
    out = compactar(largo, max_chars=100)
    assert validar_historial(out) == []
    # ninguna tool huérfana: cada tool tiene su assistant con tools antes
    ids_con_tools = {
        tc["id"]
        for m in out if m.get("role") == "assistant"
        for tc in m.get("tool_calls", [])
    }
    for j, m in enumerate(out):
        if m.get("role") == "tool":
            assert m["tool_call_id"] in ids_con_tools, f"tool huérfana en [{j}]"

def test_compaccion_no_parte_unidad_al_recortar():
    """Caso borde: si el corte por ventana cae en medio de una unidad, la
    unidad entra completa (la ventana puede quedar en más de N mensajes)."""
    from utils.compaccion import compactar, validar_historial

    largo = _historial_sintetico(n_vueltas=40)
    out = compactar(largo, max_chars=100)
    assert validar_historial(out) == []
    # ninguna unidad (assistant con tools) quedó a medias
    for i, m in enumerate(out):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            assert i + 1 < len(out) and out[i + 1].get("role") == "tool"

def test_compaccion_determinista():
    """Mismo input → mismo output (dos llamadas)."""
    from utils.compaccion import compactar

    largo = _historial_sintetico(n_vueltas=30)
    a = compactar(largo, max_chars=100)
    b = compactar(largo, max_chars=100)
    assert a == b

def test_compaccion_invariantes_antes_y_despues():
    """El test que clava los invariantes del modo thinking: el sintético
    grande (200+ mensajes con tools) valida ANTES y DESPUÉS de compactar."""
    from utils.compaccion import compactar, validar_historial

    largo = _historial_sintetico(n_vueltas=50)
    assert len(largo) >= 201
    assert validar_historial(largo) == []  # ANTES: válido
    out = compactar(largo, max_chars=100)
    assert validar_historial(out) == []  # DESPUÉS: sigue válido

    # y validar_historial SÍ detecta cada rotura (no es un chequeo vacuo)
    con_reasoning = [dict(m) for m in largo]
    con_reasoning[5]["reasoning_content"] = "trace"
    assert validar_historial(con_reasoning)
    sin_tools = [dict(m) for m in largo]
    del sin_tools[3]  # saca la tool de la vuelta 0: su head queda sin tool
    assert validar_historial(sin_tools)
    sin_system = list(largo[1:])
    assert validar_historial(sin_system)

def test_agent_step_prep_compacta_y_cuenta(monkeypatch, capsys):
    """Integración: con COMPACTION_CHARS chico, AgentStep.prep devuelve el
    historial compactado y cuenta en shared['compacciones']. Y no re-compacta
    la misma ronda (huella)."""
    import nodes
    from utils.compaccion import PREFIJO_COMPACCION

    monkeypatch.setenv("COMPACTION_CHARS", "200")
    largo = _historial_sintetico(n_vueltas=40)
    shared = {"messages": list(largo), "tool_rounds": 0}

    mensajes, tools = nodes.AgentStep().prep(shared)
    assert shared["compacciones"] == 1
    assert mensajes is shared["messages"]
    assert len(mensajes) < len(largo)
    assert mensajes[1]["content"].startswith(PREFIJO_COMPACCION)
    assert mensajes[0] == largo[0]
    assert "zona fría" in capsys.readouterr().out

    # segunda llamada con el MISMO historial ya compactado: no re-compacta
    nodes.AgentStep().prep(shared)
    assert shared["compacciones"] == 1

    # un historial corto no dispara compacción
    shared2 = {"messages": largo[:3], "tool_rounds": 0}
    nodes.AgentStep().prep(shared2)
    assert "compacciones" not in shared2

def test_compactar_dispara_por_caracteres_con_umbral_de_mensajes():
    """El disparador de `compactar` es el TAMAÑO en CARACTERES (`_tamano >
    max_chars`), pero con la compuerta de mensajes: con `ventana + 2` o más
    mensajes (9 >= 6+2) compacta en cuanto los caracteres pasan el tope;
    por debajo de `ventana + 2` es no-op aunque los caracteres lo superen."""
    from utils.compaccion import compactar

    system = {"role": "system", "content": "s" * 5000}
    turnos = [{"role": "user", "content": "u" * 5000} for _ in range(8)]
    messages = [system] + turnos  # 9 mensajes >= ventana+2

    # 9 mensajes + max_chars=1: los caracteres pasan el tope -> COMPACTA.
    out = compactar(messages, max_chars=1)
    assert out is not messages and out != messages
    assert out[0] == messages[0]  # system conservado
    assert out[0]["role"] == "system"
    assert len(out) < len(messages)  # los totales bajan
    # la ventana caliente sobrevive byte a byte al final del compactado
    assert out[-6:] == messages[-6:]

    # 7 mensajes (menos de ventana+2) + max_chars=1: no-op por la compuerta.
    mensajes_7 = [system] + turnos[:6]  # 7 mensajes < 8
    assert compactar(mensajes_7, max_chars=1) == mensajes_7

    # 9 mensajes pero max_chars enorme: los caracteres NO pasan el tope -> no-op.
    assert compactar(messages, max_chars=10**9) == messages

def test_un_typo_en_un_setting_numerico_no_mata_el_chat(monkeypatch):
    """exp/37 (barrida): un ".env" con COMPACTION_CHARS=sesenta mil reventaba
    en AgentStep.prep — que corre FUERA del retry del nodo — y mataba el chat.
    _entero/_real avisan y usan el default."""
    import nodes
    from utils import call_llm

    monkeypatch.setattr(
        call_llm, "_setting",
        lambda nombre, default=None: "sesenta mil" if nombre == "COMPACTION_CHARS" else default,
    )
    shared = {"messages": [{"role": "system", "content": "s"}], "tool_rounds": 0}
    mensajes, tools = nodes.AgentStep().prep(shared)   # no debe levantar
    assert mensajes and tools is not None

def test_compactar_no_devuelve_mas_contexto_del_que_recibio():
    """exp/37: si la ventana caliente sola pesa más que el tope, la compacción
    no achica (medido: 9 mensajes/60.403 chars → 8/60.644) y el llamador
    re-compactaba en cada ronda sin bajar nunca."""
    from utils.compaccion import compactar

    mensajes = [{"role": "system", "content": "s" * 100}]
    mensajes += [{"role": "user", "content": "u"}, {"role": "assistant", "content": "a"}]
    mensajes += [{"role": "user", "content": "x" * 10040} for _ in range(6)]
    salida = compactar(mensajes, 60000)
    assert len(salida) == len(mensajes), "compactó sin achicar"
    assert salida == mensajes

def test_validar_historial_no_levanta_con_ids_none():
    """exp/37: el docstring promete que NUNCA levanta; sorted(ids) con None
    explotaba con TypeError."""
    from utils.compaccion import validar_historial

    historial = [
        {"role": "system", "content": "s"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": None, "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": "r"},
    ]
    fallas = validar_historial(historial)      # no debe levantar
    assert fallas                              # y sí detecta la inconsistencia


def test_compaction_conserva_la_tarea_vigente():
    """La zona fría se lleva la pregunta original; el marcador debe conservar
    la tarea vigente (medido en vivo: a la ronda 11 el modelo ya no sabía qué
    le habían pedido)."""
    from utils.compaccion import PREFIJO_COMPACCION, compactar

    mensajes = [{"role": "system", "content": "s"}]
    for _ in range(12):
        mensajes.append({"role": "user", "content": "u" * 500})
        mensajes.append({"role": "assistant", "content": "a" * 500})
    out = compactar(mensajes, 1000, objetivo="Auditá inconsistencias semánticas")
    assert out[1]["content"].startswith(PREFIJO_COMPACCION)
    assert "Tarea vigente: Auditá inconsistencias semánticas" in out[1]["content"]
