"""Módulos y tools: discover, action space, visión/PDF y a2a (PR 4)."""
import pytest


def test_elegir_exposicion_nombre_desconocido():
    """Un nombre de MCP_EXPOSE sin implementación (typo) no se expone y el
    aviso lo menciona (antes: continue mudo)."""
    from mcp_server import elegir_exposicion

    expuestas, aviso = elegir_exposicion(
        {"list_files", "no_existe"}, {"list_files": lambda: None}, {"list_files": "lista"}
    )
    assert expuestas == ["list_files"]
    assert aviso and "no_existe" in aviso and "sin implementación" in aviso

def test_elegir_exposicion_sin_descripcion():
    """Un nombre con implementación pero sin esquema en TOOLS se expone
    igual, y el aviso avisa que va sin descripción (antes: vacía muda)."""
    from mcp_server import elegir_exposicion

    expuestas, aviso = elegir_exposicion(
        {"list_files", "read_file"},
        {"list_files": lambda: None, "read_file": lambda: None},
        {"list_files": "lista"},  # read_file no tiene descripción
    )
    assert expuestas == ["list_files", "read_file"]
    assert aviso and "read_file" in aviso and "sin descripción" in aviso

def test_elegir_exposicion_normal_sin_aviso():
    """Caso normal: todo expuesto y aviso None."""
    from mcp_server import elegir_exposicion

    expuestas, aviso = elegir_exposicion(
        {"list_files", "read_file"},
        {"list_files": lambda: None, "read_file": lambda: None},
        {"list_files": "lista", "read_file": "lee"},
    )
    assert expuestas == ["list_files", "read_file"]
    assert aviso is None

# Vision/PDF (cola final): ver_imagen (data-URL base64) y ver_pdf (Files API)

PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f5c0000000049454e44ae426082"
)

def test_mime_por_contenido_ignora_el_nombre():
    """El tipo se valida por CONTENIDO (magic bytes), no por extensión."""
    import modules.vision as vision

    assert vision._mime_por_contenido(PNG_1x1) == "image/png"
    assert vision._mime_por_contenido(b"\xff\xd8\xff\xe0" + b"x" * 20) == "image/jpeg"
    assert vision._mime_por_contenido(b"GIF89a" + b"y" * 20) == "image/gif"
    assert vision._mime_por_contenido(b"GIF87a" + b"y" * 20) == "image/gif"
    assert vision._mime_por_contenido(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    # texto con nombre .png → ninguna firma coincide
    assert vision._mime_por_contenido(b"soy texto, no una imagen") is None

def test_ver_imagen_data_url_bien_formada(tmp_path, monkeypatch):
    """Sin red: el POST se mockea y se verifica la FORMA del request (data
    URL base64 en un message de USER con content=[text, image_url])."""
    import modules.vision as vision

    img = tmp_path / "foto.png"
    img.write_bytes(PNG_1x1)
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(vision, "get_api_key", lambda: "sk-test")

    capturado = {}

    class Resp:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "un pixel rojo"}}]}

    def post_fake(url, headers=None, json=None, timeout=None):
        capturado.update(url=url, headers=headers, body=json, timeout=timeout)
        return Resp()

    monkeypatch.setattr(vision.requests, "post", post_fake)

    r = vision.ver_imagen(str(img), "¿qué color es?")
    assert r == "un pixel rojo"
    assert capturado["url"].endswith("/chat/completions")
    assert capturado["headers"]["Authorization"] == "Bearer sk-test"
    msgs = capturado["body"]["messages"]
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    contenido = msgs[0]["content"]
    assert contenido[0]["type"] == "text" and contenido[0]["text"] == "¿qué color es?"
    assert contenido[1]["type"] == "image_url"
    data_url = contenido[1]["image_url"]["url"]
    assert data_url.startswith("data:image/png;base64,")
    import base64 as _b64

    assert _b64.b64decode(data_url.split(",", 1)[1]) == PNG_1x1

def test_ver_imagen_tipo_invalido_por_contenido(tmp_path, monkeypatch):
    """Un archivo de texto con nombre .png se rechaza SIN llamar a la red."""
    import modules.vision as vision

    falso = tmp_path / "disfraz.png"
    falso.write_text("no soy una imagen", encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))

    def no_llamar(*a, **k):
        raise AssertionError("no debía llamar a la API")

    monkeypatch.setattr(vision.requests, "post", no_llamar)
    r = vision.ver_imagen(str(falso), "¿qué es?")
    assert r.startswith("ERROR") and "no es una imagen soportada" in r

def test_ver_imagen_demasiado_grande_sin_llamar(tmp_path, monkeypatch):
    """Imagen > 32 MiB → ERROR legible y NINGUNA llamada."""
    import modules.vision as vision

    grande = tmp_path / "grande.png"
    grande.write_bytes(PNG_1x1)
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(vision, "IMAGEN_MAX_BYTES", 10)  # tope minúsculo para el test

    def no_llamar(*a, **k):
        raise AssertionError("no debía llamar a la API")

    monkeypatch.setattr(vision.requests, "post", no_llamar)
    r = vision.ver_imagen(str(grande), "¿qué es?")
    assert r.startswith("ERROR") and "tope para una imagen" in r

def test_ver_pdf_rasteriza_y_consulta(tmp_path, monkeypatch):
    """El contrato nuevo (medido): Files API NO acepta PDFs → pdftoppm
    rasteriza y las páginas van como imágenes al modelo. Mock del POST y
    del rasterizador; PDF real mínimo para pasar la firma %PDF."""
    import subprocess

    import modules.vision as vision

    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF-1.4 + firma + EOF")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(vision, "get_api_key", lambda: "sk-test")
    from pathlib import Path as _P
    Path = _P

    # pdftoppm falso: produce dos PNG de página
    paginas = []
    def pdftoppm_fake(*args, **kwargs):
        # argv de pdftoppm: [cmd, -png, -r, 110, INPUT, BASE_OUT] — el
        # output es el ÚLTIMO argumento; las páginas nacen ahí
        argv = args[0]
        base = argv[-1]
        pag1 = Path(base + "-1.png")
        pag1.write_bytes(b"\x89PNG" + b"fake" * 10)
        pag2 = Path(base + "-2.png")
        pag2.write_bytes(b"\x89PNG" + b"fake" * 10)
        paginas.extend([pag1, pag2])
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(vision.subprocess, "run", pdftoppm_fake)

    llamadas = []

    class RespChat:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "Total: $100"}}]}

    def post_fake(url, headers=None, **kwargs):
        llamadas.append({"url": url, "headers": headers, "json": kwargs.get("json")})
        return RespChat()

    monkeypatch.setattr(vision.requests, "post", post_fake)

    r = vision.ver_pdf(str(pdf), "¿cuál es el total?")
    assert r == "Total: $100"

    assert len(llamadas) == 1
    consulta = llamadas[0]
    assert consulta["url"].endswith("/chat/completions")
    assert consulta["headers"]["Authorization"] == "Bearer sk-test"
    contenido = consulta["json"]["messages"][0]["content"]
    assert contenido[0]["type"] == "text" and "2 páginas" in contenido[0]["text"]
    imagenes = [c for c in contenido if c["type"] == "image_url"]
    assert len(imagenes) == 2  # una por página, en orden
    assert imagenes[0]["image_url"]["url"].startswith("data:image/png;base64,")

def test_ver_pdf_no_pdf_por_contenido(tmp_path, monkeypatch):
    """Un archivo .pdf que no empieza con %PDF se rechaza sin subir nada."""
    import modules.vision as vision

    falso = tmp_path / "disfraz.pdf"
    falso.write_text("no soy un pdf", encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))

    def no_llamar(*a, **k):
        raise AssertionError("no debía llamar a la API")

    monkeypatch.setattr(vision.requests, "post", no_llamar)
    r = vision.ver_pdf(str(falso), "¿qué dice?")
    assert r.startswith("ERROR") and "no es un PDF" in r

def test_ver_pdf_demasiado_grande_sin_llamar(tmp_path, monkeypatch):
    """PDF > 64 MiB → ERROR legible y NINGUNA subida."""
    import modules.vision as vision

    pdf = tmp_path / "grande.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(vision, "PDF_MAX_BYTES", 4)  # tope minúsculo para el test

    def no_llamar(*a, **k):
        raise AssertionError("no debía llamar a la API")

    monkeypatch.setattr(vision.requests, "post", no_llamar)
    r = vision.ver_pdf(str(pdf), "¿qué dice?")
    assert r.startswith("ERROR") and "tope para un PDF" in r

# A2A (cola final): agentes_remotos y a2a_tarea contra un servidor fake


class _ServidorA2A:
    """Servidor HTTP mínimo que habla (a medias) el protocolo A2A: sirve el
    agent card en los well-known que se pidan (path de la spec actual y/o el
    legado) y responde JSON-RPC en /. Usa ThreadingHTTPServer de stdlib;
    registra el último payload recibido."""

    # El drift de spec (exp/40): la spec actual sirve el card en
    # agent-card.json; el legado, en agent.json. El default del fake expone
    # AMBOS (un server moderno con compatibilidad).
    CARD_NUEVO = "/.well-known/agent-card.json"
    CARD_LEGADO = "/.well-known/agent.json"

    def __init__(self):
        self.ultimo = None

    def arrancar(self, responder=None, card=None, card_paths=None):
        import json as _json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.ultimo = None
        card = card if card is not None else {
            "name": "eco", "description": "agente de prueba",
            "skills": [{"id": "echo", "description": "repite texto"}],
        }
        card_paths = card_paths if card_paths is not None else (self.CARD_NUEVO, self.CARD_LEGADO)
        responder = responder or (lambda payload: {"jsonrpc": "2.0", "id": payload.get("id"), "result": {"echo": payload["params"]["message"]}})
        estado = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.split("?")[0] in card_paths:
                    cuerpo = _json.dumps(card).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(cuerpo)))
                    self.end_headers()
                    self.wfile.write(cuerpo)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                largo = int(self.headers.get("Content-Length") or 0)
                payload = _json.loads(self.rfile.read(largo) or b"{}")
                estado.ultimo = payload
                cuerpo = _json.dumps(responder(payload)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{srv.server_address[1]}", srv

def test_a2a_sin_setting(monkeypatch):
    """Sin setting (o vacío / JSON roto) las tools lo dicen claro, sin red."""
    import modules.a2a as a2a

    for valor in (None, "", "   ", "{no soy json}", "[]"):
        if valor is None:
            monkeypatch.delenv("A2A_AGENTS", raising=False)
        else:
            monkeypatch.setenv("A2A_AGENTS", valor)
        monkeypatch.setattr(a2a, "_agentes", lambda: {})
        r = a2a.agentes_remotos()
        assert "No hay agentes remotos A2A configurados" in r
        r2 = a2a.a2a_tarea("x", "hola")
        assert "No hay agentes remotos A2A configurados" in r2

    # JSON roto se trata como vacío (degradación)
    monkeypatch.setenv("A2A_AGENTS", "{no soy json}")
    assert a2a._agentes() == {}

def test_a2a_lista_y_tarea(monkeypatch):
    """Con setting a un servidor fake: agentes_remotos lista el card y
    a2a_tarea envía JSON-RPC message/send y parsea el result."""
    import json

    import modules.a2a as a2a

    srv = _ServidorA2A()
    base, httpd = srv.arrancar()
    try:
        monkeypatch.setenv("A2A_AGENTS", json.dumps({"eco": base}))

        listado = a2a.agentes_remotos()
        assert "eco" in listado and base in listado
        assert "agente de prueba" in listado
        assert "echo" in listado and "repite texto" in listado

        r = a2a.a2a_tarea("eco", "hola mundo")
        payload = json.loads(r)
        # el echo devuelve el message tal cual llegó (messageId incluido, exp/40)
        echo = payload["echo"]
        assert echo["role"] == "user"
        assert echo["parts"] == [{"type": "text", "text": "hola mundo"}]
        assert isinstance(echo["messageId"], str) and echo["messageId"]

        # la FORMA del request enviado: JSON-RPC 2.0 message/send, con el
        # messageId que exige la spec actual (exp/40: los servers viejos lo
        # ignoran como campo extra)
        enviado = srv.ultimo
        assert enviado["jsonrpc"] == "2.0"
        assert enviado["method"] == "message/send"
        assert enviado["params"]["message"]["role"] == "user"
        assert enviado["params"]["message"]["parts"] == [{"type": "text", "text": "hola mundo"}]
        assert isinstance(enviado["params"]["message"]["messageId"], str)
        assert enviado["params"]["message"]["messageId"]
        assert isinstance(enviado["id"], int)
    finally:
        httpd.shutdown()

def test_a2a_card_path_nuevo(monkeypatch):
    """El path de la spec ACTUAL (agent-card.json) resuelve solo: el cliente
    lo prueba primero (exp/40)."""
    import json as _json

    import modules.a2a as a2a

    srv = _ServidorA2A()
    base, httpd = srv.arrancar(card_paths=(_ServidorA2A.CARD_NUEVO,))
    try:
        monkeypatch.setenv("A2A_AGENTS", _json.dumps({"eco": base}))
        listado = a2a.agentes_remotos()
        assert "agente de prueba" in listado
        assert "inaccesible" not in listado
    finally:
        httpd.shutdown()

def test_a2a_card_path_legado_fallback(monkeypatch):
    """Un server que solo sirve el path LEGADO (agent.json) también resuelve:
    el 404 del path nuevo cae al fallback (exp/40)."""
    import json as _json

    import modules.a2a as a2a

    srv = _ServidorA2A()
    base, httpd = srv.arrancar(card_paths=(_ServidorA2A.CARD_LEGADO,))
    try:
        monkeypatch.setenv("A2A_AGENTS", _json.dumps({"eco": base}))
        listado = a2a.agentes_remotos()
        assert "agente de prueba" in listado
        assert "inaccesible" not in listado
    finally:
        httpd.shutdown()

def test_a2a_error_jsonrpc(monkeypatch):
    """Un error JSON-RPC del agente se devuelve como texto, no rompe."""
    import json as _json

    import modules.a2a as a2a

    srv = _ServidorA2A()
    base, httpd = srv.arrancar(
        responder=lambda payload: {"jsonrpc": "2.0", "id": payload.get("id"),
                                   "error": {"code": -32000, "message": "no puedo"}})
    try:
        monkeypatch.setenv("A2A_AGENTS", _json.dumps({"eco": base}))
        r = a2a.a2a_tarea("eco", "hola")
        assert r.startswith("ERROR JSON-RPC") and "no puedo" in r
    finally:
        httpd.shutdown()

def test_a2a_agente_caido_es_inaccesible(monkeypatch):
    """Un agente caído se reporta 'inaccesible' (degradación, no crash)."""
    import json as _json

    import modules.a2a as a2a

    monkeypatch.setenv("A2A_AGENTS", _json.dumps({"caido": "http://127.0.0.1:1"}))
    r = a2a.agentes_remotos()
    assert "inaccesible" in r and "caido" in r

    r2 = a2a.a2a_tarea("caido", "hola")
    assert r2.startswith("ERROR") and "inaccesible" in r2

    # nombre no configurado: texto claro, sin red
    monkeypatch.setenv("A2A_AGENTS", _json.dumps({"otro": "http://127.0.0.1:1"}))
    r3 = a2a.a2a_tarea("inexistente", "hola")
    assert r3.startswith("ERROR") and "no configurado" in r3

def test_a2a_card_agente_caido_no_corta_el_listado(monkeypatch):
    """Con un agente sano y otro caído, el listado muestra el card del sano
    e 'inaccesible' para el caído (el caído no corta el listado)."""
    import json as _json

    import modules.a2a as a2a

    srv = _ServidorA2A()
    base, httpd = srv.arrancar()
    try:
        monkeypatch.setenv("A2A_AGENTS", _json.dumps({"sano": base, "caido": "http://127.0.0.1:1"}))
        r = a2a.agentes_remotos()
        assert "sano" in r and "agente de prueba" in r
        assert "caido" in r and "inaccesible" in r
    finally:
        httpd.shutdown()

@pytest.mark.red
def test_search_web_degrada_a_error_sin_red(monkeypatch):
    """Fix 4 (deuda): una búsqueda que falla NO propaga la excepción —
    devuelve un string 'ERROR: …' que research ve como dato y sigue con las
    queries que sí pueden salir. Es el candado que pedía la spec."""
    ddgs = pytest.importorskip("ddgs")

    import utils.websearch as ws

    llamadas = []

    class SinRed:
        def text(self, consulta, max_results=5):
            llamadas.append((consulta, max_results))
            raise RuntimeError("sin red")

    monkeypatch.setenv("SEARCH_PROVIDER", "ddgs")
    monkeypatch.setattr(ddgs, "DDGS", SinRed)

    r = ws.search_web("x", k=3)

    # si esto falla, el test no llegó a la llamada que debía reventar
    assert llamadas == [("x", 3)]
    assert isinstance(r, str) and r.startswith("ERROR: búsqueda web falló"), r
