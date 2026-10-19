"""HITL web: aprobación humana desde el navegador en vez de la terminal.

Cuando el setting `HITL_WEB=1`, las aprobaciones de write_file,
edit_file y run_command (módulos `escritura` y `coding`) no preguntan
`s/n` por stdin: la función `aprobar(titulo, cuerpo)` levanta (perezoso,
una sola vez por proceso) un servidor HTTP local en 127.0.0.1:8765 que
sirve una página con TODOS los pedidos pendientes. Cada pedido lleva su
propio Event y su propio token; los forms Aprobar / Rechazar postean a
`/decision?token=…`.

Contrato y contención:

- Solo stdlib (`http.server` + `threading`). Sin dependencias nuevas.
- PENDIENTES MÚLTIPLES: el server mantiene un dict `token → _Pedido`. Dos
  `aprobar()` (en hilos distintos del mismo proceso) conviven: cada uno
  espera SOLO su propio Event y un POST solo resuelve el pedido de SU
  token. Un POST de un pedido anterior (o de otra pestaña) no puede
  resolver el vigente.
- Defensa anti-CSRF / DNS-rebinding: el POST a `/decision` solo se acepta
  si el header Host es de loopback y, si viene Origin, también es loopback.
  Una página ajena puede auto-postear, pero su Origin la delata y se
  ignora sin decidir (loopback solo NO alcanzaba como contención).
- `aprobar()` espera el Event con timeout (`HITL_WEB_TIMEOUT`, 300s de
  default) y devuelve True o False. Timeout o error => False: el mismo
  default seguro que el CLI (un rechazo nunca bloquea al agente).
- PUERTO ELÁSTICO: si el puerto base (`HITL_WEB_PORT`, default 8765) está
  ocupado por otro proceso, se prueban los siguientes hasta base+5. Si
  ninguno queda libre, se degrada a False (default seguro): nunca romper
  la acción. La URL efectiva se imprime UNA vez por server.
- El servidor escucha SOLO en 127.0.0.1 (loopback): no se expone a la red.
"""
import html
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from utils.call_llm import _setting

HOST = "127.0.0.1"
PUERTO_DEFAULT = 8765
PUERTO_RANGO = 5          # base, base+1, ..., base+5
TIMEOUT_DEFAULT = 300

_lock = threading.Lock()           # serializa el registro de pendientes
_pendientes = {}                   # token -> _Pedido (cross-hilo, mismo proceso)
_servidor = None                   # ThreadingHTTPServer (arranque perezoso)
_url_impresa = False               # la URL efectiva se imprime UNA vez por server


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
    except (OSError, ValueError):
        puerto = _setting("HITL_WEB_PORT", str(PUERTO_DEFAULT))
    nombres = {"127.0.0.1", "localhost", "[::1]", "::1"}
    return {f"{n}:{puerto}" for n in nombres} | nombres


def _origen_valido(handler):
    """True si la petición viene de un contexto legítimo de la propia página:
    Host de loopback y, si viene Origin, que sea loopback (bloquea CSRF:
    una página ajena puede auto-postear, pero su Origin no es loopback)."""
    host = (handler.headers.get("Host") or "").strip()
    if host and host not in _hosts_validos():
        return False
    origin = (handler.headers.get("Origin") or "").strip()
    if origin:
        try:
            puerto = _arrancar()
        except (OSError, ValueError):
            return False
        permitidos = {f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}"}
        if origin not in permitidos:
            return False
    return True

_PAGINA = """<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>HITL — aprobaciones pendientes</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 60rem; }}
.pedido {{ border: 1px solid #ddd; border-radius: .4rem; padding: 1rem;
           margin-bottom: 1.5rem; }}
pre {{ background: #f6f6f6; border: 1px solid #ddd; padding: 1rem;
       overflow: auto; white-space: pre-wrap; }}
form {{ display: inline-block; margin-right: .5rem; }}
button {{ font-size: 1rem; padding: .6rem 1.4rem; cursor: pointer; }}
.aprobar {{ background: #2e7d32; color: #fff; border: 0; }}
.rechazar {{ background: #b71c1c; color: #fff; border: 0; }}
</style></head>
<body>
<h1>HITL — {cuantos} pedido(s) pendiente(s)</h1>
{pedidos}
</body></html>
"""

_PEDIDO_HTML = """<div class="pedido" id="{token}">
<h2>{titulo}</h2>
<pre>{cuerpo}</pre>
<form method="post" action="/decision?token={token}&amp;respuesta=s">
  <button class="aprobar">Aprobar</button>
</form>
<form method="post" action="/decision?token={token}&amp;respuesta=n">
  <button class="rechazar">Rechazar</button>
</form>
</div>
"""

_SIN_PENDIENTES = "<p>No hay ningún pedido pendiente.</p>"

_GRACIAS = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>HITL</title></head>
<body><p>Decisión registrada: <b>{decision}</b>. Podés cerrar esta pestaña.</p></body></html>
"""


def _pagina():
    """HTML con TODOS los pendientes (cada uno con su título, cuerpo y forms)."""
    with _lock:
        pedidos = list(_pendientes.values())
    if not pedidos:
        return _SIN_PENDIENTES
    bloques = [
        _PEDIDO_HTML.format(
            token=html.escape(p.token),
            titulo=html.escape(p.titulo),
            cuerpo=html.escape(p.cuerpo))
        for p in pedidos
    ]
    return _PAGINA.format(cuantos=len(pedidos), pedidos="\n".join(bloques))


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
        if self.path.split("?")[0] not in ("/", "/index.html"):
            self._responder(404, "<p>404</p>")
            return
        # mismo corte que do_POST: un GET de página ajena (DNS-rebinding) no
        # puede leer los pedidos pendientes ni sus tokens (hallazgo de auditoría)
        if not _origen_valido(self):
            self._responder(403, "<p>Origen no permitido.</p>")
            return
        self._responder(200, _pagina())

    def do_POST(self):
        if self.path.split("?")[0] != "/decision":
            self._responder(404, "<p>404</p>")
            return
        # Contención del gate: un POST de una página ajena (CSRF) o con Host
        # ajeno (DNS-rebinding) se ignora SIN decidir ni revelar el pedido.
        if not _origen_valido(self):
            self._responder(403, "<p>Origen no permitido.</p>")
            return

        consulta = parse_qs(urlsplit(self.path).query)
        token = (consulta.get("token") or [""])[0]
        respuesta = (consulta.get("respuesta") or [""])[0]

        # Compatibilidad con el form viejo (decision=aprobar|rechazar en el
        # cuerpo) y con el nuevo contrato del spec (respuesta=s|n).
        largo = int(self.headers.get("Content-Length") or 0)
        if largo:
            datos = self.rfile.read(largo).decode("utf-8", errors="replace")
            for campo in datos.split("&"):
                clave, _, valor = campo.partition("=")
                if clave == "token" and not token:
                    token = valor
                elif clave == "respuesta" and not respuesta:
                    respuesta = valor
                elif clave == "decision":
                    # aprobar -> s ; cualquier otra cosa -> n
                    respuesta = "s" if valor == "aprobar" else "n"

        with _lock:
            pedido = _pendientes.get(token)
        # token desconocido o ya resuelto/expirado: 404 claro, sin decidir nada
        if pedido is None:
            self._responder(404, "<p>Pedido desconocido o expirado.</p>")
            return
        pedido.decision = respuesta == "s"
        pedido.evento.set()
        self._responder(200, _GRACIAS.format(
            decision="Aprobar" if pedido.decision else "Rechazar"))


def _arrancar():
    """Levanta el servidor una sola vez (perezoso) y devuelve el puerto.

    Puerto elástico: si el base está ocupado, prueba base+1..base+PUERTO_RANGO.
    Si ninguno queda libre, deja la excepción subir (aprobar() la atrapa y
    devuelve False: default seguro, la acción del agente nunca se rompe).
    """
    global _servidor, _url_impresa
    if _servidor is not None:
        return _servidor.server_address[1]
    # OJO: acá el valor inválido DEBE fallar (lo atrapa aprobar() y devuelve
    # False al instante). Endurecerlo con _entero arrancaría el servidor en el
    # puerto default y la aprobación esperaría los 300 s del timeout.
    base = int(_setting("HITL_WEB_PORT", str(PUERTO_DEFAULT)))
    ultimo_error = None
    for puerto in range(base, base + PUERTO_RANGO + 1):
        try:
            _servidor = ThreadingHTTPServer((HOST, puerto), _Handler)
            break
        except OSError as e:  # puerto ocupado: probar el siguiente
            ultimo_error = e
    else:
        raise ultimo_error if ultimo_error is not None else OSError("sin puerto libre")
    threading.Thread(target=_servidor.serve_forever, daemon=True).start()
    efectivo = _servidor.server_address[1]
    if not _url_impresa:
        print(f"[hitl_web] escuchando en http://{HOST}:{efectivo}")
        _url_impresa = True
    return efectivo


def _timeout():
    """Timeout del pedido en segundos; cualquier valor inválido usa el default."""
    try:
        return float(_setting("HITL_WEB_TIMEOUT", str(TIMEOUT_DEFAULT)))
    except (TypeError, ValueError):
        return float(TIMEOUT_DEFAULT)


def aprobar(titulo, cuerpo):
    """Registra el pedido, lo sirve en la página y espera SU decisión.

    Cada llamada crea su token y su Event y espera SOLO el suyo: dos
    aprobaciones en hilos distintos del proceso conviven sin bloquearse.
    Devuelve True si el navegador aprobó dentro del timeout, False en
    cualquier otro caso (rechazo, timeout o error): el default seguro.
    """
    try:
        puerto = _arrancar()
    except (OSError, ValueError) as e:
        print(f"[hitl_web] no se pudo levantar el servidor: {e}")
        return False

    token = secrets.token_urlsafe(24)
    pedido = _Pedido(str(titulo), str(cuerpo), token)
    with _lock:
        _pendientes[token] = pedido
    print(f"[hitl_web] aprobación pendiente en http://{HOST}:{puerto}/?token={token}")

    try:
        listo = pedido.evento.wait(_timeout())
    except Exception as e:  # nunca colgar al agente por un fallo del HITL  # noqa: BLE001 (defensa del wait: el HITL no debe colgar al agente)
        print(f"[hitl_web] error esperando la decisión: {e}")
        listo = False
    finally:
        with _lock:
            _pendientes.pop(token, None)  # deja de listarse al resolverse/expirar
    decidido = pedido.decision
    if not listo:
        print("[hitl_web] timeout sin decisión: se rechaza (default seguro)")
        return False
    return bool(decidido)
