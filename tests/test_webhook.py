"""exp/57 — webhook autenticado sobre el server HITL (Mesa 7).

Seguridad primero: token en tiempo constante (vacío = endpoint deshabilitado),
Host/Origin de loopback (anti DNS-rebinding), cuerpo máximo, rate limit por
minuto y persistencia JSONL. Los tests levantan el server real en un puerto
propio y hablan HTTP; no hay red externa.
"""
import json
import urllib.error
import urllib.request

import pytest
from conftest import RAIZ  # noqa: F401  (raíz en sys.path)


def _pedir(puerto, ruta, datos=None, headers=None):
    """(código, cuerpo). Atrapa HTTPError para poder testear rechazos."""
    peticion = urllib.request.Request(f"http://127.0.0.1:{puerto}{ruta}",
                                      data=datos, headers=headers or {})
    try:
        with urllib.request.urlopen(peticion, timeout=5) as respuesta:
            return respuesta.status, respuesta.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


@pytest.fixture
def webhook(monkeypatch, tmp_path):
    """Server real en puerto propio con token y log temporales."""
    import utils.hitl_web as hitl

    monkeypatch.setenv("HITL_WEB_PORT", "8795")
    monkeypatch.setenv("WEBHOOK_TOKEN", "secreto-de-prueba")
    monkeypatch.setenv("WEBHOOK_LOG", str(tmp_path / "webhooks.jsonl"))
    monkeypatch.setenv("WEBHOOK_MAX_BYTES", "512")
    monkeypatch.setenv("WEBHOOK_MAX_POR_MINUTO", "10")
    monkeypatch.setattr(hitl, "_servidor", None)
    monkeypatch.setattr(hitl, "_url_impresa", True)
    with hitl._lock:
        hitl._pendientes.clear()
    with hitl._eventos_lock:
        hitl._eventos.clear()
    with hitl._ventana_lock:
        hitl._ventana_webhooks.clear()
    puerto = hitl._arrancar()
    yield hitl, puerto, tmp_path
    if hitl._servidor is not None:
        hitl._servidor.shutdown()
        hitl._servidor.server_close()
        monkeypatch.setattr(hitl, "_servidor", None)


def _auth(token="secreto-de-prueba", extra=None):
    headers = {"X-Webhook-Token": token, "Content-Type": "application/json"}
    headers.update(extra or {})
    return headers


def test_post_valido_persiste_y_eventos(webhook):
    hitl, puerto, tmp_path = webhook
    payload = json.dumps({"tipo": "ci", "detalle": {"estado": "ok"}, "id": "e1"}).encode()
    codigo, cuerpo = _pedir(puerto, "/webhook", payload, _auth())
    assert codigo == 200 and json.loads(cuerpo)["ok"] is True
    linea = json.loads((tmp_path / "webhooks.jsonl").read_text(encoding="utf-8").strip())
    assert linea["tipo"] == "ci" and linea["id"] == "e1" and "ts" in linea
    codigo, cuerpo = _pedir(puerto, "/eventos", headers=_auth())
    assert codigo == 200
    eventos = json.loads(cuerpo)
    assert len(eventos) == 1 and eventos[0]["tipo"] == "ci"


def test_token_incorrecto_rechaza_y_no_persiste(webhook):
    hitl, puerto, tmp_path = webhook
    payload = json.dumps({"tipo": "ci"}).encode()
    codigo, _ = _pedir(puerto, "/webhook", payload, _auth(token="otro"))
    assert codigo == 401
    assert not (tmp_path / "webhooks.jsonl").exists()


def test_sin_token_configurado_el_endpoint_esta_deshabilitado(webhook, monkeypatch):
    hitl, puerto, _tmp = webhook
    monkeypatch.setenv("WEBHOOK_TOKEN", "")
    codigo, cuerpo = _pedir(puerto, "/webhook",
                            json.dumps({"tipo": "ci"}).encode(), _auth())
    assert codigo == 503 and "deshabilitado" in cuerpo
    codigo, _ = _pedir(puerto, "/eventos", headers=_auth())
    assert codigo == 503


def test_get_eventos_sin_token_401(webhook):
    _hitl, puerto, _tmp = webhook
    codigo, _ = _pedir(puerto, "/eventos")
    assert codigo == 401


def test_host_ajeno_rechaza_dns_rebinding(webhook):
    """Unitario sobre el corte de origen (el server real ya lo aplica igual)."""
    from utils import hitl_web as hitl

    class Falso:
        headers = {"Host": "evil.example:8795"}

    class Loopback:
        headers = {"Host": "127.0.0.1:8795"}

    assert not hitl._origen_valido(Falso())
    assert hitl._origen_valido(Loopback())


def test_cuerpo_invalido_y_sin_tipo(webhook):
    _hitl, puerto, tmp_path = webhook
    codigo, _ = _pedir(puerto, "/webhook", b"no-es-json", _auth())
    assert codigo == 400
    codigo, _ = _pedir(puerto, "/webhook", json.dumps({"detalle": {}}).encode(), _auth())
    assert codigo == 400
    assert not (tmp_path / "webhooks.jsonl").exists()


def test_cuerpo_demasiado_grande(webhook):
    _hitl, puerto, _tmp = webhook
    payload = json.dumps({"tipo": "ci", "detalle": "x" * 900}).encode()
    codigo, cuerpo = _pedir(puerto, "/webhook", payload, _auth())
    assert codigo == 413 and "512" in cuerpo


def test_rate_limit_por_minuto(webhook, monkeypatch):
    hitl, puerto, _tmp = webhook
    monkeypatch.setenv("WEBHOOK_MAX_POR_MINUTO", "1")
    payload = json.dumps({"tipo": "ci"}).encode()
    assert _pedir(puerto, "/webhook", payload, _auth())[0] == 200
    assert _pedir(puerto, "/webhook", payload, _auth())[0] == 429


def test_token_nunca_se_devuelve(webhook):
    _hitl, puerto, _tmp = webhook
    _, cuerpo = _pedir(puerto, "/webhook", json.dumps({"tipo": "x"}).encode(), _auth())
    assert "secreto-de-prueba" not in cuerpo


def test_token_valido_en_tiempo_constante(webhook, monkeypatch):
    hitl, _puerto, _tmp = webhook
    assert hitl.token_valido("secreto-de-prueba") is True
    assert hitl.token_valido("otro") is False
    assert hitl.token_valido("") is False
    monkeypatch.setenv("WEBHOOK_TOKEN", "")
    assert hitl.token_valido("") is False


def test_parsear_evento_valida_forma():
    from utils.hitl_web import _parsear_evento

    assert _parsear_evento(b'{"tipo": "ci", "detalle": {"a": 1}}')["tipo"] == "ci"
    for crudo in (b"[1, 2]", b'{"detalle": 1}', b'{"tipo": ""}', b'{"tipo": "' + b"x" * 65 + b'"}'):
        with pytest.raises(ValueError):
            _parsear_evento(crudo)
