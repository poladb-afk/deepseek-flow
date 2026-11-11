"""X193: cobertura de `utils/hitl_web.py` — cada ruta y cada chequeo del gate.

Las rutas del servidor (decisión, webhook, eventos, chat) y los chequeos de
seguridad (token, Host/Origin, topes de cuerpo, rate limit, persistencia).
Puerto 8796: test_hitl.py fija 8791–8794 y test_webhook.py usa 8795.

Límite declarado: la rama "detalle no simple" de `_parsear_evento` es
INCONSEGUIBLE por HTTP — `json.loads` solo produce dict/list/str/int/float/
bool/null — así que sus líneas no se cubren sin tocar el producto (X193 no lo
toca); la lista de la cobertura la nombra y este docstring la declara.
"""
import json
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

import utils.hitl_web as hw


def _pedir(puerto, ruta, datos=None, headers=None, metodo=None):
    """(código, cuerpo) contra el server real; atrapa HTTPError."""
    peticion = urllib.request.Request(f"http://127.0.0.1:{puerto}{ruta}",
                                      data=datos, headers=headers or {}, method=metodo)
    try:
        with urllib.request.urlopen(peticion, timeout=5) as respuesta:
            return respuesta.status, respuesta.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


@pytest.fixture
def servidor(monkeypatch, tmp_path):
    """Server real en 8796 con todo el estado de la sesión limpio."""
    for clave, valor in {
        "HITL_WEB_PORT": "8796", "HITL_WEB_TIMEOUT": "2", "WEBHOOK_TOKEN": "",
        "WEBHOOK_LOG": str(tmp_path / "webhooks.jsonl"),
        "WEBHOOK_MAX_BYTES": "512", "WEBHOOK_MAX_POR_MINUTO": "10",
    }.items():
        monkeypatch.setenv(clave, valor)
    monkeypatch.setattr(hw, "_servidor", None)
    monkeypatch.setattr(hw, "_url_impresa", True)
    with hw._lock:
        hw._pendientes.clear()
    with hw._eventos_lock:
        hw._eventos.clear()
    with hw._ventana_lock:
        hw._ventana_webhooks.clear()
    puerto = hw._arrancar()
    yield puerto
    if hw._servidor is not None:
        hw._servidor.shutdown()
        hw._servidor.server_close()
    monkeypatch.setattr(hw, "_servidor", None)


def _webchat_prendido(monkeypatch, sesion):
    """El módulo webchat simulado: habilitado y con una sesión controlada."""
    class GestorFalso:
        def crear(self):
            return sesion

        def obtener(self, id_sesion, token):
            return sesion if token == "tok" else None

        def cerrar(self, id_sesion, token):
            return True

    monkeypatch.setattr(hw.webchat, "habilitado", lambda: True)
    monkeypatch.setattr(hw.webchat, "gestor", lambda: GestorFalso())
    monkeypatch.setattr(hw.webchat, "evento_sse", lambda trozo: f"data: {trozo}\n\n")
    monkeypatch.setattr(hw.webchat, "pagina", lambda: "<p>chat</p>")


class _Sesion:
    id, token = "s1", "tok"

    def __init__(self, eventos=None, enviar=None):
        self._eventos = eventos or (lambda: iter(()))
        self._enviar = enviar or (lambda _texto: None)

    def eventos(self):
        return self._eventos()

    def enviar(self, texto):
        self._enviar(texto)


def test_pagina_sin_pendientes():
    """Sin pedidos, la página lo dice (no arma bloques vacíos)."""
    with hw._lock:
        hw._pendientes.clear()
    assert hw._pagina() == hw._SIN_PENDIENTES


def test_rutas_desconocidas_404(servidor):
    for metodo, ruta in ((None, "/no-existe"), ("POST", "/no-existe")):
        codigo, _ = _pedir(servidor, ruta, datos=b"" if metodo else None, metodo=metodo)
        assert codigo == 404, (metodo, ruta)


def test_eventos_con_origen_ajeno_403(servidor, monkeypatch):
    """GET /eventos tiene el mismo corte anti-DNS-rebinding que el webhook."""
    monkeypatch.setenv("WEBHOOK_TOKEN", "secreto")
    codigo, _ = _pedir(servidor, "/eventos", headers={"Origin": "http://evil.example"})
    assert codigo == 403


def test_webhook_si_no_persiste_da_503(servidor, monkeypatch):
    monkeypatch.setenv("WEBHOOK_TOKEN", "secreto")

    def romper(_evento):
        raise OSError("disco lleno")

    monkeypatch.setattr(hw, "registrar_evento", romper)
    datos = json.dumps({"tipo": "demo"}).encode()
    codigo, cuerpo = _pedir(servidor, "/webhook", datos,
                            headers={"X-Webhook-Token": "secreto"})
    assert codigo == 503 and "no se pudo persistir" in cuerpo


def test_chat_web_apagado_da_404(servidor):
    """WEBCHAT=0 (monkeypatch del módulo): las tres rutas del chat dan 404."""
    for metodo, ruta in ((None, "/chat"), (None, "/chat/stream"), ("POST", "/chat/sesion")):
        codigo, _ = _pedir(servidor, ruta, datos=b"{}" if metodo else None, metodo=metodo)
        assert codigo == 404, (metodo, ruta)


def test_chat_web_chequeos_con_sesion_controlada(servidor, monkeypatch):
    """Origen, JSON, texto y fallos de la sesión: cada borde con su código."""
    _webchat_prendido(monkeypatch, _Sesion())

    # GET /chat y /chat/stream: solo loopback
    assert _pedir(servidor, "/chat", headers={"Origin": "http://evil.example"})[0] == 403
    assert _pedir(servidor, "/chat/stream", headers={"Origin": "http://evil.example"})[0] == 403

    # cuerpos inválidos: no-JSON y JSON no-objeto
    assert _pedir(servidor, "/chat/sesion", b"esto no es json", metodo="POST")[0] == 400
    assert _pedir(servidor, "/chat/mensaje", b"[1, 2]", metodo="POST")[0] == 400

    # texto vacío o gigante
    assert _pedir(servidor, "/chat/mensaje",
                  json.dumps({"sesion": "s1", "token": "tok", "texto": ""}).encode(),
                  metodo="POST")[0] == 400
    assert _pedir(servidor, "/chat/mensaje",
                  json.dumps({"sesion": "s1", "token": "tok", "texto": "x" * 4001}).encode(),
                  metodo="POST")[0] == 400

    # el chat respondiendo 200 con una sesión válida
    assert _pedir(servidor, "/chat/mensaje",
                  json.dumps({"sesion": "s1", "token": "tok", "texto": "hola"}).encode(),
                  metodo="POST")[0] == 200


def test_chat_web_fallos_de_la_sesion(servidor, monkeypatch):
    """RuntimeError de la sesión (tope) → 429; OSError (hijo muerto) → 503."""
    def con_enviar(efecto):
        return _Sesion(enviar=lambda _texto: (_ for _ in ()).throw(efecto))

    _webchat_prendido(monkeypatch, con_enviar(RuntimeError("tope de sesiones")))
    codigo, cuerpo = _pedir(servidor, "/chat/mensaje",
                            json.dumps({"sesion": "s1", "token": "tok", "texto": "x"}).encode(),
                            metodo="POST")
    assert codigo == 429 and "tope de sesiones" in cuerpo

    _webchat_prendido(monkeypatch, con_enviar(OSError("hijo muerto")))
    codigo, _ = _pedir(servidor, "/chat/mensaje",
                       json.dumps({"sesion": "s1", "token": "tok", "texto": "x"}).encode(),
                       metodo="POST")
    assert codigo == 503


def test_stream_con_pestana_cerrada_no_rompe(servidor, monkeypatch):
    """BrokenPipeError del SSE: la sesión sigue y la respuesta cierra limpia."""
    def eventos():
        raise BrokenPipeError()

    _webchat_prendido(monkeypatch, _Sesion(eventos=eventos))
    codigo, cuerpo = _pedir(servidor, "/chat/stream?sesion=s1&token=tok")
    assert codigo == 200 and cuerpo == ""


def test_decision_con_form_en_el_cuerpo(servidor):
    """Token, respuesta y motivo pueden venir en el CUERPO del form (no en la
    query) y el motivo rechazado viaja URL-encoded hasta la Decision."""
    def votar(cuerpo, esperado, motivo):
        resultado = {}
        hilo = threading.Thread(target=lambda: resultado.update(d=hw.aprobar("¿?", "x")))
        hilo.start()
        token = ""
        for _ in range(100):
            with hw._lock:
                if hw._pendientes:
                    token = next(iter(hw._pendientes))
                    break
            time.sleep(0.02)
        assert token, "no hay pedido pendiente"
        codigo, _ = _pedir(servidor, "/decision",
                           cuerpo.format(token=token).encode(), metodo="POST")
        assert codigo == 200
        hilo.join(5)
        assert resultado["d"].ok is esperado and resultado["d"].motivo == motivo

    votar("token={token}&respuesta=s", True, "")
    votar("token={token}&respuesta=n&motivo=no+quiero", False, "no quiero")


def test_hosts_y_origen_si_el_server_no_arranca(monkeypatch):
    """Sin server, los hosts caen al puerto del setting y el Origin se rechaza."""
    monkeypatch.setenv("HITL_WEB_PORT", "8796")

    def no_arranca():
        raise OSError("sin puerto")

    monkeypatch.setattr(hw, "_arrancar", no_arranca)
    assert "127.0.0.1:8796" in hw._hosts_validos()
    handler = SimpleNamespace(headers={"Host": "127.0.0.1:8796",
                                       "Origin": "http://127.0.0.1:8796"})
    assert hw._origen_valido(handler) is False


def test_arrancar_salta_el_puerto_ocupado(monkeypatch):
    """Puerto elástico: si el base está tomado, prueba el siguiente."""
    monkeypatch.setenv("HITL_WEB_PORT", "8797")
    monkeypatch.setattr(hw, "_servidor", None)
    monkeypatch.setattr(hw, "_url_impresa", True)
    ocupado = socket.socket()
    ocupado.bind((hw.HOST, 8797))
    ocupado.listen(1)
    try:
        assert hw._arrancar() == 8798
    finally:
        if hw._servidor is not None:
            hw._servidor.shutdown()
            hw._servidor.server_close()
        monkeypatch.setattr(hw, "_servidor", None)
        ocupado.close()


def test_arrancar_sin_puerto_libre_falla_cerrado(monkeypatch):
    """Sin ningún puerto libre, deja subir el OSError (aprobar() lo atrapa)."""
    monkeypatch.setenv("HITL_WEB_PORT", "8799")
    monkeypatch.setattr(hw, "_servidor", None)

    class SiempreOcupado:
        def __init__(self, *_a, **_k):
            raise OSError("ocupado")

    monkeypatch.setattr(hw, "ThreadingHTTPServer", SiempreOcupado)
    with pytest.raises(OSError, match="ocupado"):
        hw._arrancar()


def test_cli_iniciar_y_main(monkeypatch, capsys):
    """`python3 main.py webhook`: CTRL+C devuelve 0; sin server, 1."""
    monkeypatch.setenv("WEBHOOK_TOKEN", "secreto")
    monkeypatch.setattr(hw, "_arrancar", lambda: 8796)
    monkeypatch.setattr(time, "sleep", lambda _s: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert hw.iniciar() == 0
    salida = capsys.readouterr().out
    assert "HITL+webhook en" in salida and "webhook habilitado: sí" in salida
    assert hw.main() == 0

    monkeypatch.setattr(hw, "_arrancar", lambda: (_ for _ in ()).throw(ValueError("sin puerto")))
    assert hw.iniciar() == 1
    assert "no se pudo levantar el servidor" in capsys.readouterr().out


def test_token_valido_sin_token_configurado(monkeypatch):
    """Sin WEBHOOK_TOKEN no hay token válido: falla cerrado."""
    monkeypatch.delenv("WEBHOOK_TOKEN", raising=False)
    assert hw.token_valido("") is False
    assert hw.token_valido("cualquiera") is False


def test_webhook_tipo_vacio_o_largo_da_400(servidor, monkeypatch):
    """El tipo es un string de 1 a 64: solo-espacios y 65 se rechazan."""
    monkeypatch.setenv("WEBHOOK_TOKEN", "secreto")
    for evento in ({"tipo": "   "}, {"tipo": "x" * 65}):
        codigo, _ = _pedir(servidor, "/webhook", json.dumps(evento).encode(),
                           headers={"X-Webhook-Token": "secreto"})
        assert codigo == 400, evento


def test_rate_limit_por_minuto(servidor, monkeypatch):
    """Con el tope en 1, el segundo webhook del minuto pide 429."""
    monkeypatch.setenv("WEBHOOK_TOKEN", "secreto")
    monkeypatch.setenv("WEBHOOK_MAX_POR_MINUTO", "1")
    with hw._ventana_lock:
        hw._ventana_webhooks.clear()
    datos = json.dumps({"tipo": "demo"}).encode()
    assert _pedir(servidor, "/webhook", datos, headers={"X-Webhook-Token": "secreto"})[0] == 200
    assert _pedir(servidor, "/webhook", datos, headers={"X-Webhook-Token": "secreto"})[0] == 429


def test_ventana_descarta_lo_viejo(monkeypatch):
    """La ventana de 60 s descarta lo anterior: un evento viejo no cuenta."""
    monkeypatch.setenv("WEBHOOK_MAX_POR_MINUTO", "1")
    with hw._ventana_lock:
        hw._ventana_webhooks[:] = [time.monotonic() - 120]
    try:
        assert hw._permitido_por_limite() is True
    finally:
        with hw._ventana_lock:
            hw._ventana_webhooks.clear()


def test_arrancar_imprime_la_url_una_sola_vez(monkeypatch, capsys):
    """La URL efectiva se imprime UNA vez por proceso, no por server."""
    monkeypatch.setattr(hw, "_url_impresa", False)
    for puerto in (8800, 8801, 8802):
        monkeypatch.setattr(hw, "_servidor", None)
        monkeypatch.setenv("HITL_WEB_PORT", str(puerto))
        assert hw._arrancar() == puerto
        hw._servidor.shutdown()
        hw._servidor.server_close()
    assert capsys.readouterr().out.count("[hitl_web] escuchando en") == 1


def test_arrancar_prueba_todo_el_rango_y_falla(monkeypatch):
    """Ocupado el rango entero (base..base+5), el OSError sube (sin puerto libre)."""
    monkeypatch.setattr(hw, "_servidor", None)
    monkeypatch.setattr(hw, "_url_impresa", True)
    monkeypatch.setenv("HITL_WEB_PORT", "8810")
    ocupados = []
    for puerto in range(8810, 8816):
        ocupado = socket.socket()
        ocupado.bind((hw.HOST, puerto))
        ocupado.listen(1)
        ocupados.append(ocupado)
    try:
        with pytest.raises(OSError):
            hw._arrancar()
    finally:
        for ocupado in ocupados:
            ocupado.close()
        monkeypatch.setattr(hw, "_servidor", None)


def test_timeout_acotado(monkeypatch):
    """El timeout vale en (0, 86400]; fuera de rango (86401, 0, inf, nan) default."""
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "86400")
    assert hw._timeout() == 86400.0
    for valor in ("86401", "0", "-1", "inf", "nan"):
        monkeypatch.setenv("HITL_WEB_TIMEOUT", valor)
        assert hw._timeout() == float(hw.TIMEOUT_DEFAULT), valor


def test_el_token_del_pedido_tiene_192_bits(servidor, monkeypatch):
    """Cada pedido nace con `token_urlsafe(24)` → 32 chars (192 bits)."""
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "0.05")
    resultado = {}
    hilo = threading.Thread(target=lambda: resultado.update(d=hw.aprobar("¿?", "x")))
    hilo.start()
    token = ""
    for _ in range(100):
        with hw._lock:
            if hw._pendientes:
                token = next(iter(hw._pendientes))
                break
        time.sleep(0.01)
    assert token and len(token) == len(secrets.token_urlsafe(24)) == 32
    hilo.join(5)
    assert resultado["d"].ok is False  # timeout: default seguro


def test_webhook_detalle_null_se_acepta(servidor, monkeypatch):
    """`detalle` es opcional y `null` es JSON simple: se acepta y se persiste."""
    monkeypatch.setenv("WEBHOOK_TOKEN", "secreto")
    codigo, _ = _pedir(servidor, "/webhook", json.dumps({"tipo": "x", "detalle": None}).encode(),
                       headers={"X-Webhook-Token": "secreto"})
    assert codigo == 200
    with hw._eventos_lock:
        assert hw._eventos[-1]["tipo"] == "x" and hw._eventos[-1]["detalle"] is None
