"""Aprobaciones humanas: escritura/coding, gate web, historial y pedido al humano (PR 4)."""


def test_edit_file_quirurgico(tmp_path, monkeypatch):
    import modules.coding as coding

    archivo = tmp_path / "demo.py"
    archivo.write_text("def suma(a, b):\n    return a + b\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(coding, "_approve", lambda p: True)

    # happy path: ocurrencia única, reemplazo exacto
    r = coding.edit_file(str(archivo), "a + b", "a - b")
    assert r.startswith("Editado")
    assert "a - b" in archivo.read_text(encoding="utf-8")

    # no aparece: falla ruidoso, el archivo queda intacto
    antes = archivo.read_text(encoding="utf-8")
    r = coding.edit_file(str(archivo), "texto_que_no_esta", "x")
    assert r.startswith("ERROR") and "no aparece" in r
    assert archivo.read_text(encoding="utf-8") == antes

    # ambiguo: dos ocurrencias piden más contexto
    archivo.write_text("base = 1\nbase = base + 1\n", encoding="utf-8")
    r = coding.edit_file(str(archivo), "base = ", "valor = ")
    assert "2 veces" in r
    assert "base" in archivo.read_text(encoding="utf-8")

    # rechazado: el diff se muestra pero el disco queda intacto
    monkeypatch.setattr(coding, "_approve", lambda p: False)
    r = coding.edit_file(str(archivo), "base = 1", "base = 10")
    assert r.startswith("RECHAZADO")
    assert "base = 1" in archivo.read_text(encoding="utf-8")

def test_hitl_web(monkeypatch):
    """HITL web: el navegador decide (aprobar/rechazar) y el timeout cae a
    un default seguro (False). Se prueba el servidor en un puerto propio."""
    import threading
    import urllib.parse
    import urllib.request

    import utils.hitl_web as hitl

    puerto = 8791
    monkeypatch.setenv("HITL_WEB_PORT", str(puerto))
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "5")
    monkeypatch.setattr(hitl, "_servidor", None)  # puerto propio (aislado)
    assert hitl._arrancar() == puerto

    import time as _t

    # exp/49b: pendientes MÚLTIPLES — el token vive en el dict _pendientes
    def _token_unico():
        for _ in range(100):
            with hitl._lock:
                if hitl._pendientes:
                    return next(iter(hitl._pendientes))
            _t.sleep(0.02)
        return None

    def post(respuesta):
        token = _token_unico()
        req = urllib.request.Request(
            f"http://127.0.0.1:{puerto}/decision?token={token}&respuesta={respuesta}",
            data=b"")
        return urllib.request.urlopen(req, timeout=5).read()

    resultados = {}

    # 1) aprobar: la función espera el Event y devuelve True
    hilo = threading.Thread(
        target=lambda: resultados.update(ok=hitl.aprobar("¿Escribir?", "diff de prueba")))
    hilo.start()
    assert _token_unico() is not None
    post("s")
    hilo.join(5)
    assert resultados["ok"] is True

    # 2) rechazar: POST de rechazar devuelve False
    hilo = threading.Thread(
        target=lambda: resultados.update(ok=hitl.aprobar("¿Ejecutar?", "ls -la")))
    hilo.start()
    assert _token_unico() is not None
    post("n")
    hilo.join(5)
    assert resultados["ok"] is False

    # 3) timeout: nadie vota y expira -> default seguro False
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "0.2")
    assert hitl.aprobar("¿Aplicar?", "diff huérfano") is False

    # 4) timeout inválido (setting corrupto) no rompe: cae al default seguro
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "no-es-numero")
    assert hitl._timeout() == float(hitl.TIMEOUT_DEFAULT)

def test_hitl_web_rechaza_post_cross_origin(monkeypatch):
    """Contención real del gate humano (medido: loopback NO alcanza).

    Un POST a /decision con Origin ajeno (CSRF/DNS-rebinding: la víctima
    solo tiene que cargar una página mientras hay un pedido pendiente) debe
    ser ignorado, no aprobar. El mismo pedido con Origin/Host de loopback
    sí decide. Regresión del hallazgo del juez: faltaba validar Origin/Host."""
    import threading
    import time as _t
    import urllib.error
    import urllib.parse
    import urllib.request

    import utils.hitl_web as hitl

    puerto = 8792
    monkeypatch.setenv("HITL_WEB_PORT", str(puerto))
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "5")
    monkeypatch.setattr(hitl, "_servidor", None)  # puerto propio (aislado)
    assert hitl._arrancar() == puerto

    def post(decision, origin, token):
        datos = urllib.parse.urlencode({"decision": decision}).encode()
        cabeceras = {"Content-Type": "application/x-www-form-urlencoded"}
        if origin is not None:
            cabeceras["Origin"] = origin
        req = urllib.request.Request(
            f"http://127.0.0.1:{puerto}/decision?token={token}", data=datos, headers=cabeceras)
        try:
            return urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as e:
            return e  # 403 esperado para el POST cross-origin

    resultados = {}

    # 1) POST con Origin ajeno: NO debe decidir (el pedido sigue pendiente)
    hilo = threading.Thread(
        target=lambda: resultados.update(ok=hitl.aprobar("¿Escribir?", "diff")))
    hilo.start()
    token = ""
    for _ in range(100):
        with hitl._lock:
            if hitl._pendientes:
                token = next(iter(hitl._pendientes))
                break
        _t.sleep(0.02)
    assert token, "no hay pedido pendiente"
    r = post("aprobar", origin="http://evil.example", token=token)
    assert getattr(r, "status", getattr(r, "code", None)) == 403, "el POST cross-origin no fue rechazado"
    _t.sleep(0.1)
    with hitl._lock:
        assert token in hitl._pendientes, "un Origin ajeno decidió el pedido"
    assert not resultados.get("ok"), "el pedido se resolvió por un POST cross-origin"

    # 2) POST legítimo (sin Origin, mismo-origen vía loopback) con el token: sí decide
    req = urllib.request.Request(
        f"http://127.0.0.1:{puerto}/decision?token={token}&respuesta=s",
        data=b"")
    urllib.request.urlopen(req, timeout=5)
    hilo.join(5)
    assert resultados["ok"] is True

def test_hitl_web_post_tardio_no_contamina_el_siguiente(monkeypatch):
    """Un POST que trae una decisión vieja (llega mientras el pedido
    siguiente ya está esperando) NO puede decidirlo: la decisión va atada
    al pedido, no a una global suelta. Se ejerce la ventana real: un POST
    concurrente dentro del wait() de B no debe resolverlo."""
    import threading
    import time as _t
    import urllib.parse
    import urllib.request

    import utils.hitl_web as hitl

    puerto = 8793
    monkeypatch.setenv("HITL_WEB_PORT", str(puerto))
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "300")
    monkeypatch.setattr(hitl, "_servidor", None)  # puerto propio (aislado)
    assert hitl._arrancar() == puerto

    def post(decision, token=""):
        datos = urllib.parse.urlencode({"decision": decision, "token": token}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{puerto}/decision", data=datos)
        try:
            return urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as e:
            return e  # 403 esperado para el POST viejo

    # pedido A: expira por timeout sin que nadie vote. Su token queda viejo.
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "0.15")
    assert hitl.aprobar("¿A?", "a") is False
    post("aprobar", token="token-viejo-de-A")  # POST TARDÍO de A: nadie espera
    _t.sleep(0.05)

    # pedido B: espera SU decisión. El POST de A (token viejo) no lo resuelve,
    # y el timeout corto de B debe dar el default seguro False.
    resultados = {}
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "0.3")
    hilo = threading.Thread(
        target=lambda: resultados.update(ok=hitl.aprobar("¿B?", "b")))
    hilo.start()
    hilo.join(5)
    assert resultados["ok"] is False, "una decisión con token viejo resolvió B"

def test_hitl_web_puerto_ocupado_default_seguro(monkeypatch):
    """Si el servidor no puede levantar (puerto inválido), aprobar() devuelve
    False en vez de propagar la excepción: el HITL nunca cuelga al agente."""
    import utils.hitl_web as hitl

    monkeypatch.setattr(hitl, "_servidor", None)  # forzar arranque
    monkeypatch.setenv("HITL_WEB_PORT", "no-es-un-puerto")
    assert hitl.aprobar("¿Escribir?", "algo") is False

def test_hitl_web_get_valida_origen():
    """Corte ligero (auditoría): un GET con Host ajeno (DNS-rebinding) no
    puede leer el pedido pendiente ni su token — mismo corte que el POST."""
    from types import SimpleNamespace

    import utils.hitl_web as hw

    hw._pendiente = SimpleNamespace(titulo="t", cuerpo="secreto",
                                    token="x", evento=__import__("threading").Event())
    try:
        puerto = hw._arrancar()  # el real (otros tests pueden haberlo movido)
        handler = SimpleNamespace(headers={"Host": f"evil.example.com:{puerto}"})
        assert hw._origen_valido(handler) is False
        handler_ok = SimpleNamespace(headers={"Host": f"127.0.0.1:{puerto}"})
        assert hw._origen_valido(handler_ok) is True
    finally:
        hw._pendiente = None

def test_get_question_slash_aprobaciones(monkeypatch, capsys):
    """/aprobaciones muestra el historial HITL sin llegar al modelo."""
    import nodes
    import utils.aprobaciones as ap

    ap.limpiar()
    ap.registrar("run_command", "echo hola", True, "auto")
    shared = {"messages": [], "tool_rounds": 0}
    # exp/36: el comando se atiende en el BUCLE DE ENTRADA y no vuelve a post,
    # así no llega al modelo ni consume el presupuesto de la vuelta anterior.
    entradas = iter(["/aprobaciones", "hola"])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(entradas))
    pregunta = nodes.GetQuestion().exec(None)
    salida = capsys.readouterr().out
    assert pregunta == "hola"          # el comando se consumió en el bucle
    assert "✓ [auto] run_command: echo hola" in salida
    assert shared["messages"] == []  # no entra al historial del modelo
    # una pregunta normal sí entra al historial
    nodes.GetQuestion().post(shared, None, "hola")
    assert shared["messages"][-1]["content"] == "hola"
    ap.limpiar()

def test_historial_aprobaciones(monkeypatch):
    """El registro de aprobaciones cuenta aprobadas/rechazadas de la sesión."""
    import utils.aprobaciones as ap

    ap.limpiar()
    assert "No hay aprobaciones" in ap.resumen()

    ap.registrar("run_command", "echo hola", True, "auto")
    ap.registrar("write_file", "/tmp/x.py", False)
    r = ap.resumen()
    assert "2 (1 aprobadas, 1 rechazadas)" in r
    assert "✓ [auto] run_command: echo hola" in r
    assert "✗ write_file: /tmp/x.py" in r
    # el buffer no crece sin techo
    for i in range(300):
        ap.registrar("run_command", f"c{i}", True)
    assert len(ap.eventos()) == 200
    ap.limpiar()

def test_approve_registra_aprobaciones(monkeypatch, tmp_path):
    """write_file/run_command registran su aprobación (aprobada o rechazada)."""
    import modules.coding as coding
    import modules.escritura as esc
    import utils.aprobaciones as ap

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setenv("HITL_AUTO", "0")
    ap.limpiar()

    # run_command rechazado: queda registrado como rechazo
    monkeypatch.setattr(coding, "_approve", lambda p: False)
    coding.run_command("echo x")
    assert ap.eventos()[-1]["tipo"] == "run_command"
    assert ap.eventos()[-1]["decision"] is False

    # write_file aprobado: queda registrado como aprobación
    monkeypatch.setattr(esc, "_approve", lambda p: True)
    esc.write_file(str(tmp_path / "nuevo.txt"), "contenido")
    assert ap.eventos()[-1]["tipo"] == "write_file"
    assert ap.eventos()[-1]["decision"] is True
    ap.limpiar()

def test_edit_file_diagnostico_whitespace_y_candidatos():
    """exp/10: edit_file generaba el 63% de los errores del harness (27/43)
    con un feedback ciego ('releé el archivo'). Ahora diagnostica la causa
    clásica (indentación) y ofrece candidatos con línea — el reintento
    debería ser uno y sin relectura completa."""
    from modules.coding import _contiene_subsecuencia, _normalizar_ws, candidatos_similares

    # archivo con indentación MIXTA: def g usa un tab real
    archivo = "def f():\n    x = 1\n    return x\ndef g():\n\ty = 2\n    return y\n"
    # old_string 'igual' pero con 4 espacios donde el archivo tiene tab
    viejo_espacios = "def g():\n    y = 2\n    return y"

    # el match exacto falla, pero la subsecuencia normalizada está
    assert "def g():\n\ty = 2\n    return y" not in viejo_espacios
    lineas_txt = _normalizar_ws(archivo).split("\n")
    lineas_old = _normalizar_ws(viejo_espacios).split("\n")
    assert _contiene_subsecuencia(lineas_txt, lineas_old)

    # candidatos: la ventana correcta con su línea exacta (base 1)
    cands = candidatos_similares(archivo, viejo_espacios)
    assert cands and cands[0][0] == 4, "la ventana def g() arranca en L4"
    assert "y = 2" in cands[0][1]

    # cadena totalmente ajena: sin candidatos
    assert candidatos_similares(archivo, "import numpy as np\nimport pandas") == []

# ---------------------------------------------------------------------------
# exp/49 — request_human_input: el humano como tool call (factor 7)
# ---------------------------------------------------------------------------

def test_request_human_input_devuelve_lo_tecleado(monkeypatch, capsys):
    """Con `input` fakeado, la tool devuelve el texto y etiqueta la pregunta."""
    import modules.humano as humano

    monkeypatch.setattr("builtins.input", lambda: "la respuesta del humano")
    r = humano.request_human_input("¿qué archivo?")
    assert r == "la respuesta del humano"
    salida = capsys.readouterr().out
    assert "[humano] ¿qué archivo?" in salida

def test_request_human_input_eof_no_es_crash(monkeypatch):
    """EOF → '(sin respuesta del humano: ...)': dato, no excepción."""
    import modules.humano as humano

    def eof():
        raise EOFError()

    monkeypatch.setattr("builtins.input", eof)
    r = humano.request_human_input("¿algo?")
    assert r.startswith("(sin respuesta del humano")

def test_request_human_input_en_el_registro_del_modulo():
    """La tool queda en TOOLS/IMPL del módulo, como las demás."""
    import modules.humano as humano

    nombres = {t["function"]["name"] for t in humano.TOOLS}
    assert "request_human_input" in nombres
    assert "request_human_input" in humano.IMPL
    assert humano.IMPL["request_human_input"] is humano.request_human_input

def test_request_human_input_llega_al_action_space():
    """El registro completo (discover) expone la tool al chat."""
    from nodes import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    assert "request_human_input" in nombres


def test_aprobaciones_emite_evento_hitl_sin_contenido(monkeypatch):
    """La decisión HITL viaja a .runs en formato compacto (tipo/nivel/decisión)
    sin el resumen: es lo que vuelve medible la fricción (F4/A31)."""
    from utils import aprobaciones, tracing

    capturado = []
    monkeypatch.setattr(tracing, "evento_hitl",
                        lambda *a, **k: capturado.append((a, k)))
    aprobaciones.registrar("write_file", "contenido que no debe persistirse",
                           False, "preguntar")
    try:
        assert capturado
        args, _kwargs = capturado[0]
        assert args == ("write_file", "preguntar", False)
        assert "contenido que no debe persistirse" not in repr(capturado)
    finally:
        aprobaciones.limpiar()
