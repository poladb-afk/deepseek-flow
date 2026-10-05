"""HITL web: aprobación humana desde el navegador en vez de la terminal.

Cuando el setting `HITL_WEB=1`, las aprobaciones de write_file,
edit_file y run_command (módulos `escritura` y `coding`) no preguntan
`s/n` por stdin: la función `aprobar(titulo, cuerpo)` levanta (perezoso,
una sola vez) un servidor HTTP local en 127.0.0.1:8765 que sirve una
página simple con el título, el cuerpo (dentro de `<pre>`) y dos forms
con botones Aprobar / Rechazar que hacen POST a `/decision`.

Contrato y contención:

- Solo stdlib (`http.server` + `threading`). Sin dependencias nuevas.
- Un solo pedido pendiente a la vez, protegido con `threading.Event`.
- `aprobar()` espera el Event con timeout (`HITL_WEB_TIMEOUT`, 300s de
  default) y devuelve True o False. Timeout o error => False: el mismo
  default seguro que el CLI (un rechazo nunca bloquea al agente).
- El servidor escucha SOLO en 127.0.0.1 (loopback): no se expone a la
  red. El puerto es configurable con `HITL_WEB_PORT` (default 8765).
"""
import html
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils.call_llm import _setting

HOST = "127.0.0.1"
PUERTO_DEFAULT = 8765
TIMEOUT_DEFAULT = 300

_lock = threading.Lock()          # serializa aprobar(): un pedido a la vez
_evento = None                    # threading.Event del pedido pendiente
_decision = None                  # True/False que dejó el navegador
_pendiente = None                 # (titulo, cuerpo) que se está sirviendo
_servidor = None                  # ThreadingHTTPServer (arranque perezoso)

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
  <button class="aprobar" name="decision" value="aprobar">Aprobar</button>
</form>
<form method="post" action="/decision">
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
        if _pendiente is None:
            self._responder(200, "<p>No hay ningún pedido pendiente.</p>")
            return
        titulo, cuerpo = _pendiente
        self._responder(200, _PAGINA.format(
            titulo=html.escape(titulo), cuerpo=html.escape(cuerpo)))

    def do_POST(self):
        global _decision
        if self.path.split("?")[0] != "/decision":
            self._responder(404, "<p>404</p>")
            return
        largo = int(self.headers.get("Content-Length") or 0)
        datos = self.rfile.read(largo).decode("utf-8", errors="replace")
        # el botón manda decision=aprobar|rechazar (form-urlencoded)
        decision = "rechazar"
        for campo in datos.split("&"):
            clave, _, valor = campo.partition("=")
            if clave == "decision":
                decision = valor
        _decision = (decision == "aprobar")
        if _evento is not None:
            _evento.set()
        self._responder(200, _GRACIAS.format(
            decision="Aprobar" if _decision else "Rechazar"))


def _arrancar():
    """Levanta el servidor una sola vez (perezoso) y devuelve el puerto."""
    global _servidor
    if _servidor is not None:
        return _servidor.server_address[1]
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
    global _pendiente, _evento, _decision
    with _lock:
        try:
            puerto = _arrancar()
        except Exception as e:  # puerto ocupado, inválido, etc.: default seguro
            print(f"[hitl_web] no se pudo levantar el servidor: {e}")
            return False

        _pendiente = (str(titulo), str(cuerpo))
        _decision = None
        _evento = threading.Event()
        print(f"[hitl_web] aprobación pendiente en http://{HOST}:{puerto}")

        try:
            listo = _evento.wait(_timeout())
        except Exception as e:  # nunca colgar al agente por un fallo del HITL
            print(f"[hitl_web] error esperando la decisión: {e}")
            listo = False
        decidido = _decision
        _pendiente = None
        _evento = None
        if not listo:
            print("[hitl_web] timeout sin decisión: se rechaza (default seguro)")
            return False
    return bool(decidido)
