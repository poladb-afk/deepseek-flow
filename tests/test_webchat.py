"""exp/59 — chat web MVP: sesiones aisladas, SSE y seguridad (stdlib).

El chat real corre en un subproceso; estos tests usan un hijo FALSO
(echo por stdin) para clavar el contrato sin gastar LLM: aislamiento por
sesión, token en tiempo constante, tope de sesiones, framing SSE y las rutas
HTTP sobre el server HITL.
"""
import http.client
import json
import sys
import time
import urllib.error
import urllib.request

import pytest
from conftest import RAIZ  # noqa: F401  (raíz en sys.path)

from utils import webchat

FAKE = [sys.executable, "-u", "-c",
        "import sys\n"
        "for linea in sys.stdin:\n"
        "    sys.stdout.write('echo:' + linea.strip() + '\\n')\n"
        "    sys.stdout.flush()\n"]


def _esperar(sesion, aguja, limite=10.0):
    """Junta la salida de la sesión hasta ver `aguja` (o timeout)."""
    acumulado, inicio = "", time.monotonic()
    for trozo in sesion.eventos():
        acumulado += trozo
        if aguja in acumulado:
            return acumulado
        if time.monotonic() - inicio > limite:
            break
    return acumulado


def test_sesion_aislada_echo_por_stdin(monkeypatch):
    monkeypatch.setattr(webchat, "COMANDO_CHAT", FAKE)
    sesion = webchat.Sesion()
    try:
        sesion.enviar("hola")
        assert "echo:hola" in _esperar(sesion, "echo:hola")
        sesion.enviar("segunda")
        assert "echo:segunda" in _esperar(sesion, "echo:segunda")
    finally:
        sesion.cerrar()


def test_gestor_valida_token_y_cierra(monkeypatch):
    monkeypatch.setattr(webchat, "COMANDO_CHAT", FAKE)
    monkeypatch.setattr(webchat, "_gestor", webchat.Gestor())
    gestor = webchat.gestor()
    sesion = gestor.crear()
    try:
        assert gestor.obtener(sesion.id, "token-malo") is None
        assert gestor.obtener(sesion.id, sesion.token) is sesion
        assert gestor.cerrar(sesion.id, sesion.token) is True
        assert gestor.obtener(sesion.id, sesion.token) is None
    finally:
        sesion.cerrar()


def test_tope_de_sesiones(monkeypatch):
    monkeypatch.setattr(webchat, "COMANDO_CHAT", FAKE)
    monkeypatch.setenv("WEBCHAT_MAX_SESIONES", "1")
    monkeypatch.setattr(webchat, "_gestor", webchat.Gestor())
    gestor = webchat.gestor()
    primera = gestor.crear()
    try:
        with pytest.raises(RuntimeError, match="tope"):
            gestor.crear()
    finally:
        primera.cerrar()


def test_evento_sse_es_json_framing():
    evento = webchat.evento_sse("hola\nmundo")
    assert evento.startswith("data: ") and evento.endswith("\n\n")
    assert json.loads(evento[len("data: "):])["t"] == "hola\nmundo"


def _pedir(puerto, ruta, datos=None, cabeceras=None):
    peticion = urllib.request.Request(f"http://127.0.0.1:{puerto}{ruta}",
                                      data=datos, headers=cabeceras or {})
    try:
        with urllib.request.urlopen(peticion, timeout=8) as respuesta:
            return respuesta.status, respuesta.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


@pytest.fixture
def servidor(monkeypatch, tmp_path):
    import utils.hitl_web as hitl

    monkeypatch.setenv("HITL_WEB_PORT", "8797")
    monkeypatch.setenv("WEBCHAT", "1")
    monkeypatch.setattr(webchat, "COMANDO_CHAT", FAKE)
    monkeypatch.setattr(webchat, "_gestor", webchat.Gestor())
    monkeypatch.setattr(hitl, "_servidor", None)
    monkeypatch.setattr(hitl, "_url_impresa", True)
    puerto = hitl._arrancar()
    yield hitl, puerto
    webchat.gestor()._limpiar()
    if hitl._servidor is not None:
        hitl._servidor.shutdown()
        hitl._servidor.server_close()
        monkeypatch.setattr(hitl, "_servidor", None)


def test_flujo_http_chat_crear_mensaje_stream_cerrar(servidor):
    _hitl, puerto = servidor
    codigo, cuerpo = _pedir(puerto, "/chat")
    assert codigo == 200 and "chat web" in cuerpo
    codigo, cuerpo = _pedir(puerto, "/chat/sesion", datos=b"{}",
                            cabeceras={"Content-Type": "application/json"})
    assert codigo == 200
    datos = json.loads(cuerpo)
    sesion, token = datos["sesion"], datos["token"]
    peticion = json.dumps({"sesion": sesion, "token": token, "texto": "hola"}).encode()
    codigo, _ = _pedir(puerto, "/chat/mensaje", datos=peticion,
                       cabeceras={"Content-Type": "application/json"})
    assert codigo == 200
    # SSE: acumular data: hasta ver el echo del hijo falso
    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=10)
    conexion.request("GET", f"/chat/stream?sesion={sesion}&token={token}")
    respuesta = conexion.getresponse()
    assert respuesta.status == 200
    acumulado = ""
    for _ in range(400):
        linea = respuesta.readline()
        if not linea:
            break
        if linea.startswith(b"data: "):
            acumulado += json.loads(linea[len(b"data: "):])["t"]
        if "echo:hola" in acumulado:
            break
    assert "echo:hola" in acumulado
    conexion.close()
    codigo, _ = _pedir(puerto, "/chat/cerrar",
                       datos=json.dumps({"sesion": sesion, "token": token}).encode(),
                       cabeceras={"Content-Type": "application/json"})
    assert codigo == 200


def test_chat_rechaza_token_malo_y_webchat_apagado(servidor, monkeypatch):
    _hitl, puerto = servidor
    peticion = json.dumps({"sesion": "x", "token": "malo", "texto": "hola"}).encode()
    codigo, _ = _pedir(puerto, "/chat/mensaje", datos=peticion,
                       cabeceras={"Content-Type": "application/json"})
    assert codigo == 401
    monkeypatch.setenv("WEBCHAT", "0")
    codigo, _ = _pedir(puerto, "/chat")
    assert codigo == 404
