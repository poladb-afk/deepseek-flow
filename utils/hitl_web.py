"""HITL web: aprobación humana desde el navegador en vez de la terminal.

Cuando el setting `HITL_WEB=1`, las aprobaciones de write_file,
edit_file y run_command (módulos `escritura` y `coding`) no preguntan
`s/n` por stdin: la función `aprobar(titulo, cuerpo)` levanta (perezoso,
una sola vez) un servidor HTTP local en 127.0.0.1:8765 que sirve una
página simple con el título, el cuerpo (dentro de `<pre>`) y dos forms
con botones Aprobar / Rechazar que hacen POST a `/decision`.

Contrato y contención:

- Solo stdlib (`http.server` + `threading`). Sin dependencias nuevas.
- Un solo pedido pendiente a la vez. Cada pedido lleva su PROPIO Event y
  su propia decisión (objeto `_Pedido`), más un token secreto que viaja en
  la página y en el form: un POST de un pedido anterior (o de otra
  pestaña) no puede resolver el vigente.
- Defensa anti-CSRF / DNS-rebinding: el POST a `/decision` solo se acepta
  si el header Host es de loopback y, si viene Origin, también es loopback.
  Una página ajena puede auto-postear, pero su Origin la delata y se
  ignora sin decidir (loopback solo NO alcanzaba como contención).
- `aprobar()` espera el Event con timeout (`HITL_WEB_TIMEOUT`, 300s de
  default) y devuelve True o False. Timeout o error => False: el mismo
  default seguro que el CLI (un rechazo nunca bloquea al agente).
- El servidor escucha SOLO en 127.0.0.1 (loopback): no se expone a la
  red. El puerto es configurable con `HITL_WEB_PORT` (default 8765).
"""
import html
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils.call_llm import _setting

HOST = "127.0.0.1"
PUERTO_DEFAULT = 8765
TIMEOUT_DEFAULT = 300

_lock = threading.Lock()          # serializa aprobar(): un pedido a la vez
_pendiente = None                   # Pedido actual (o None): titulo, cuerpo, token, evento
_servidor = None                  # ThreadingHTTPServer (arranque perezoso)


class _Pedido:
    """Un pedido HITL con su propia decisión y su propio Event.

    La decisión va ATADA al pedido (no a una global): un POST que traiga la
    decisión de un pedido anterior (o de otra pestaña) no puede resolver
    este. El token secreto viaja en la página y en el form."""

    def __init__(self, titulo, cuerpo, token):
        self.titulo = titulo
        self.cuerpo = cuerpo
        self.token = token
        self.evento = threading.Event()
        self.decision = None  # True/False que dejó el navegador


def _hosts_validos():
    """Hosts aceptados en el header Host: solo loopback (defensa anti
    DNS-rebinding: un POST con Host ajeno no decide)."""
    try:
        puerto = _arrancar()
    except Exception:
        puerto = _setting("HITL_WEB_PORT", str(PUERTO_DEFAULT))
    nombres = {"127.0.0.1", "localhost", "[::1]", "::1"}
    return {f"{n}:{puerto}" for n in nombres} | nombres


def _origen_valido(handler):
    """True si el POST viene de un contexto legítimo de la propia página:
    Host de loopback y, si viene Origin, que sea loopback (bloquea CSRF:
    una página ajena puede auto-postear, pero su Origin no es loopback)."""
    host = (handler.headers.get("Host") or "").strip()
    if host and host not in _hosts_validos():
        return False
    origin = (handler.headers.get("Origin") or "").strip()
    if origin:
        puerto = _arrancar()
        permitidos = {f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}"}
        if origin not in permitidos:
            return False
    return True

_PAGINA = """<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>HITL — {titulo}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 60rem; }}
pre {{ background: #f6f6f6; border: 1px solid #ddd; padding: 1rem;
       overflow: auto; white-space: pre-wrap; }}
form {{ display: inline-block; margin-right: .5rem; }}
button {{ font-size: 1rem; padding: .6rem 1.4rem; cursor: pointer; }}
.aprobar {{ background: #2e7d32; color: #fff; border: 0; }}
.rechazar {{ background: #b71c1c; color: #fff; border: 0; }}
</style></head>
<body>
<h2>{titulo}</h2>
<pre>{cuerpo}</pre>
<form method="post" action="/decision">
  <input type="hidden" name="token" value="{token}">
  <button class="aprobar" name="decision" value="aprobar">Aprobar</button>
</form>
<form method="post" action="/decision">
  <input type="hidden" name="token" value="{token}">
  <button class="rechazar" name="decision" value="rechazar">Rechazar</button>
</form>
</body></html>
"""

_GRACIAS = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>HITL</title></head>
<body><p>Decisión registrada: <b>{decision}</b>. Podés cerrar esta pestaña.</p></body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencio: nada al stderr del agente
        pass

    def _responder(self, codigo, cuerpo, tipo="text/html; charset=utf-8"):
        datos = cuerpo.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        global _pendiente
        if self.path.split("?")[0] not in ("/", "/index.html"):
            self._responder(404, "<p>404</p>")
            return
        # mismo corte que do_POST: un GET de página ajena (DNS-rebinding) no
        # puede leer el pedido pendiente ni su token (hallazgo de auditoría)
        if not _origen_valido(self):
            self._responder(403, "<p>Origen no permitido.</p>")
            return
        pedido = _pendiente
        if pedido is None:
            self._responder(200, "<p>No hay ningún pedido pendiente.</p>")
            return
        self._responder(200, _PAGINA.format(
            titulo=html.escape(pedido.titulo),
            cuerpo=html.escape(pedido.cuerpo),
            token=html.escape(pedido.token)))

    def do_POST(self):
        if self.path.split("?")[0] != "/decision":
            self._responder(404, "<p>404</p>")
            return
        # Contención del gate: un POST de una página ajena (CSRF) o con Host
        # ajeno (DNS-rebinding) se ignora SIN decidir ni revelar el pedido.
        if not _origen_valido(self):
            self._responder(403, "<p>Origen no permitido.</p>")
            return
        largo = int(self.headers.get("Content-Length") or 0)
        datos = self.rfile.read(largo).decode("utf-8", errors="replace")
        # el form manda decision=aprobar|rechazar y el token del pedido
        decision, token = "rechazar", ""
        for campo in datos.split("&"):
            clave, _, valor = campo.partition("=")
            if clave == "decision":
                decision = valor
            elif clave == "token":
                token = valor
        pedido = _pendiente
        # token obligatorio y atado al pedido vigente: un POST de un pedido
        # ya terminado (o de otra pestaña) no puede resolver este.
        if pedido is None or not secrets.compare_digest(token, pedido.token):
            self._responder(403, "<p>Decisión inválida o expirada.</p>")
            return
        pedido.decision = (decision == "aprobar")
        pedido.evento.set()
        self._responder(200, _GRACIAS.format(
            decision="Aprobar" if pedido.decision else "Rechazar"))


def _arrancar():
    """Levanta el servidor una sola vez (perezoso) y devuelve el puerto."""
    global _servidor
    if _servidor is not None:
        return _servidor.server_address[1]
    # OJO: acá el valor inválido DEBE fallar (lo atrapa aprobar() y devuelve
    # False al instante). Endurecerlo con _entero arrancaría el servidor en el
    # puerto default y la aprobación esperaría los 300 s del timeout.
    puerto = int(_setting("HITL_WEB_PORT", str(PUERTO_DEFAULT)))
    _servidor = ThreadingHTTPServer((HOST, puerto), _Handler)
    threading.Thread(target=_servidor.serve_forever, daemon=True).start()
    return _servidor.server_address[1]


def _timeout():
    """Timeout del pedido en segundos; cualquier valor inválido usa el default."""
    try:
        return float(_setting("HITL_WEB_TIMEOUT", str(TIMEOUT_DEFAULT)))
    except (TypeError, ValueError):
        return float(TIMEOUT_DEFAULT)


def aprobar(titulo, cuerpo):
    """Registra el pedido, sirve la página y espera la decisión del navegador.

    Devuelve True si el navegador aprobó dentro del timeout, False en
    cualquier otro caso (rechazo, timeout o error): el default seguro.
    """
    global _pendiente
    with _lock:
        try:
            puerto = _arrancar()
        except Exception as e:  # puerto ocupado, inválido, etc.: default seguro
            print(f"[hitl_web] no se pudo levantar el servidor: {e}")
            return False

        pedido = _Pedido(str(titulo), str(cuerpo), secrets.token_urlsafe(24))
        _pendiente = pedido
        print(f"[hitl_web] aprobación pendiente en http://{HOST}:{puerto}")

        try:
            listo = pedido.evento.wait(_timeout())
        except Exception as e:  # nunca colgar al agente por un fallo del HITL
            print(f"[hitl_web] error esperando la decisión: {e}")
            listo = False
        decidido = pedido.decision
        _pendiente = None
        if not listo:
            print("[hitl_web] timeout sin decisión: se rechaza (default seguro)")
            return False
    return bool(decidido)
