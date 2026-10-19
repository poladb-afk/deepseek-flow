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
- WEBHOOK AUTENTICADO (Mesa 7, exp/57): `POST /webhook` recibe eventos de
  otros procesos (`{"tipo": "...", "detalle": ...}`) y los persiste en
  `WEBHOOK_LOG` (JSONL, gitignored) + memoria para `GET /eventos`. Seguridad
  primero: header `X-Webhook-Token` comparado en TIEMPO CONSTANTE contra
  `WEBHOOK_TOKEN` (si el setting está vacío el endpoint da 503, nunca abierto
  por default), Host/Origin de loopback (mismo corte anti DNS-rebinding que
  el HITL), cuerpo máximo (`WEBHOOK_MAX_BYTES`) y rate limit por minuto
  (`WEBHOOK_MAX_POR_MINUTO`). El token NUNCA se loguea ni se devuelve.
"""
import html
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
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

WEBHOOK_RUTA = "/webhook"
RUTAS_CHAT = ("/chat/sesion", "/chat/mensaje", "/chat/cerrar")
EVENTOS_RUTA = "/eventos"
WEBHOOK_LOG_DEFAULT = "salidas/webhooks.jsonl"
WEBHOOK_MAX_BYTES_DEFAULT = 65536
WEBHOOK_MAX_POR_MINUTO_DEFAULT = 60
MAX_EVENTOS_MEMORIA = 200
_eventos = []                      # últimos webhooks de esta sesión (GET /eventos)
_eventos_lock = threading.Lock()
_ventana_webhooks = []             # timestamps de webhooks recibidos (rate limit)
_ventana_lock = threading.Lock()


def _token_webhook():
    """Token esperado del webhook; vacío = endpoint deshabilitado (503)."""
    return (_setting("WEBHOOK_TOKEN", "") or "").strip()


def token_valido(token):
    """Compara en TIEMPO CONSTANTE; sin token configurado SIEMPRE False."""
    esperado = _token_webhook()
    if not esperado:
        return False
    return secrets.compare_digest(str(token or ""), esperado)


def _parsear_evento(datos):
    """Valida el JSON del webhook: objeto con `tipo` corto y `detalle` simple."""
    try:
        evento = json.loads(datos.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError("JSON inválido") from e
    if not isinstance(evento, dict):
        raise ValueError("el evento debe ser un objeto JSON")
    tipo = evento.get("tipo")
    if not isinstance(tipo, str) or not tipo.strip() or len(tipo) > 64:
        raise ValueError("`tipo` requerido (string de 1 a 64 caracteres)")
    detalle = evento.get("detalle", {})
    if detalle is not None and not isinstance(detalle, (dict, list, str, int, float, bool)):
        raise ValueError("`detalle` debe ser JSON simple")
    evento["tipo"] = tipo.strip()
    return evento


def _max_bytes():
    try:
        return max(1, int(_setting("WEBHOOK_MAX_BYTES", str(WEBHOOK_MAX_BYTES_DEFAULT))))
    except (TypeError, ValueError):
        return WEBHOOK_MAX_BYTES_DEFAULT


def _max_por_minuto():
    try:
        return max(1, int(_setting("WEBHOOK_MAX_POR_MINUTO",
                                   str(WEBHOOK_MAX_POR_MINUTO_DEFAULT))))
    except (TypeError, ValueError):
        return WEBHOOK_MAX_POR_MINUTO_DEFAULT


def _permitido_por_limite():
    """Rate limit por proceso: ventana deslizante de 60 s."""
    ahora = time.monotonic()
    with _ventana_lock:
        _ventana_webhooks[:] = [cuando for cuando in _ventana_webhooks
                                if ahora - cuando < 60.0]
        if len(_ventana_webhooks) >= _max_por_minuto():
            return False
        _ventana_webhooks.append(ahora)
        return True


def registrar_evento(evento):
    """Persiste el webhook en `WEBHOOK_LOG` (JSONL) y en memoria. Devuelve
    cuántos eventos lleva la sesión. Un fallo de disco lo maneja el handler."""
    registro = {"ts": round(time.time(), 3), **evento}
    ruta = Path(_setting("WEBHOOK_LOG", WEBHOOK_LOG_DEFAULT))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "a", encoding="utf-8") as archivo:
        archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    with _eventos_lock:
        _eventos.append(registro)
        del _eventos[:-MAX_EVENTOS_MEMORIA]
        recibidos = len(_eventos)
    # observabilidad SIN contenido: tipo e id, jamás el detalle (puede traer secretos)
    print(f"[webhook] {registro['tipo']} recibido (id={registro.get('id', '')})", flush=True)
    return recibidos


def eventos_recientes(n=50):
    """Los últimos n eventos de ESTA sesión (para `GET /eventos`)."""
    with _eventos_lock:
        return list(_eventos[-max(1, int(n)):])




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


def _json(datos):
    """Respuesta JSON compacta (sin contenido extra)."""
    return json.dumps(datos, ensure_ascii=False)


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
        ruta = self.path.split("?")[0]
        if ruta == EVENTOS_RUTA:
            self._get_eventos()
            return
        if ruta == "/chat":
            self._get_chat()
            return
        if ruta == "/chat/stream":
            self._get_stream()
            return
        if ruta not in ("/", "/index.html"):
            self._responder(404, "<p>404</p>")
            return
        # mismo corte que do_POST: un GET de página ajena (DNS-rebinding) no
        # puede leer los pedidos pendientes ni sus tokens (hallazgo de auditoría)
        if not _origen_valido(self):
            self._responder(403, "<p>Origen no permitido.</p>")
            return
        self._responder(200, _pagina())

    def _get_eventos(self):
        """GET /eventos: requiere token (los eventos pueden traer datos) y
        loopback; devuelve los de esta sesión, sin leer el log completo."""
        if not _origen_valido(self):
            self._responder(403, _json({"error": "origen no permitido"}))
            return
        if not _token_webhook():
            self._responder(503, _json({"error": "webhook deshabilitado"}))
            return
        if not token_valido(self.headers.get("X-Webhook-Token", "")):
            self._responder(401, _json({"error": "token inválido"}))
            return
        self._responder(200, _json(eventos_recientes()),
                        tipo="application/json; charset=utf-8")

    def _get_chat(self):
        """GET /chat: página del chat web (WEBCHAT=1), solo loopback."""
        from utils import webchat

        if not webchat.habilitado():
            self._responder(404, "<p>404</p>")
            return
        if not _origen_valido(self):
            self._responder(403, "<p>Origen no permitido.</p>")
            return
        self._responder(200, webchat.pagina())

    def _get_stream(self):
        """GET /chat/stream: SSE con la salida del chat (sesión + token)."""
        from urllib.parse import parse_qs

        from utils import webchat

        if not webchat.habilitado():
            self._responder(404, _json({"error": "webchat apagado (WEBCHAT=0)"}))
            return
        if not _origen_valido(self):
            self._responder(403, _json({"error": "origen no permitido"}))
            return
        consulta = parse_qs(urlsplit(self.path).query)
        sesion = webchat.gestor().obtener(
            (consulta.get("sesion") or [""])[0], (consulta.get("token") or [""])[0])
        if sesion is None:
            self._responder(401, _json({"error": "sesión/token inválido"}))
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            for trozo in sesion.eventos():
                self.wfile.write(webchat.evento_sse(trozo).encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # la pestaña cerró: la sesión sigue viva hasta TTL/cerrar
        finally:
            self.close_connection = True

    def _post_chat(self, ruta):
        """POST /chat/{sesion,mensaje,cerrar} con sesión+token (loopback)."""
        from utils import webchat

        if not webchat.habilitado():
            self._responder(404, _json({"error": "webchat apagado (WEBCHAT=0)"}))
            return
        if not _origen_valido(self):
            self._responder(403, _json({"error": "origen no permitido"}))
            return
        datos = self._cuerpo_json()
        if datos is None:
            return
        try:
            if ruta == "/chat/sesion":
                sesion = webchat.gestor().crear()
                self._responder(200, _json({"sesion": sesion.id, "token": sesion.token}),
                                tipo="application/json; charset=utf-8")
                return
            sesion = webchat.gestor().obtener(datos.get("sesion", ""), datos.get("token", ""))
            if sesion is None:
                self._responder(401, _json({"error": "sesión/token inválido"}))
                return
            if ruta == "/chat/cerrar":
                webchat.gestor().cerrar(datos.get("sesion", ""), datos.get("token", ""))
                self._responder(200, _json({"ok": True}),
                                tipo="application/json; charset=utf-8")
                return
            texto = str(datos.get("texto") or "").strip()
            if not texto or len(texto) > 4000:
                self._responder(400, _json({"error": "texto requerido (1..4000)"}))
                return
            sesion.enviar(texto)
            self._responder(200, _json({"ok": True}), tipo="application/json; charset=utf-8")
        except RuntimeError as e:
            self._responder(429, _json({"error": str(e)}))
        except OSError as e:
            self._responder(503, _json({"error": f"fallo de sesión ({type(e).__name__})"}))

    def _cuerpo_json(self):
        """Lee y parsea el cuerpo JSON; responde 400 y devuelve None si falla."""
        largo = int(self.headers.get("Content-Length") or 0)
        if largo > 16384:
            self._responder(413, _json({"error": "cuerpo demasiado grande"}))
            return None
        datos = self.rfile.read(largo) if largo else b"{}"
        try:
            valor = json.loads(datos.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._responder(400, _json({"error": "JSON inválido"}))
            return None
        if not isinstance(valor, dict):
            self._responder(400, _json({"error": "se esperaba un objeto JSON"}))
            return None
        return valor

    def _post_webhook(self):
        """POST /webhook autenticado (Mesa 7): seguridad primero."""
        if not _origen_valido(self):
            self._responder(403, _json({"error": "origen no permitido"}))
            return
        if not _token_webhook():
            self._responder(503, _json({"error": "webhook deshabilitado (WEBHOOK_TOKEN vacío)"}))
            return
        # headers de HTTP son case-insensitive en el cliente; acá se piden ambos nombres
        enviado = self.headers.get("X-Webhook-Token") or ""
        if not token_valido(enviado):
            self._responder(401, _json({"error": "token inválido"}))
            return
        maximo = _max_bytes()
        largo = int(self.headers.get("Content-Length") or 0)
        if largo > maximo:
            self._responder(413, _json({"error": f"cuerpo mayor a {maximo} bytes"}))
            return
        datos = self.rfile.read(largo) if largo else b""
        try:
            evento = _parsear_evento(datos)
        except ValueError as e:
            self._responder(400, _json({"error": str(e)}))
            return
        if not _permitido_por_limite():
            self._responder(429, _json({"error": "demasiados webhooks por minuto"}))
            return
        try:
            recibidos = registrar_evento(evento)
        except OSError as e:
            self._responder(503, _json({"error": f"no se pudo persistir ({type(e).__name__})"}))
            return
        self._responder(200, _json({"ok": True, "id": evento.get("id", ""),
                                    "recibidos": recibidos}),
                        tipo="application/json; charset=utf-8")

    def do_POST(self):
        ruta = self.path.split("?")[0]
        if ruta == WEBHOOK_RUTA:
            self._post_webhook()
        elif ruta in RUTAS_CHAT:
            self._post_chat(ruta)
        elif ruta == "/decision":
            self._post_decision()
        else:
            self._responder(404, "<p>404</p>")

    def _post_decision(self):
        """POST /decision: la aprobación/rechazo del gate humano (HITL)."""
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
        token, respuesta = self._leer_form_decision(token, respuesta)
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

    def _leer_form_decision(self, token, respuesta):
        """Form viejo en el cuerpo (token/respuesta/decision) a pares."""
        largo = int(self.headers.get("Content-Length") or 0)
        if not largo:
            return token, respuesta
        datos = self.rfile.read(largo).decode("utf-8", errors="replace")
        for campo in datos.split("&"):
            clave, _, valor = campo.partition("=")
            if clave == "token" and not token:
                token = valor
            elif clave == "respuesta" and not respuesta:
                respuesta = valor
            elif clave == "decision":
                respuesta = "s" if valor == "aprobar" else "n"
        return token, respuesta


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


def iniciar():
    """CLI `python3 main.py webhook`: levanta HITL+webhook y bloquea hasta Ctrl+C."""
    try:
        puerto = _arrancar()
    except (OSError, ValueError) as e:
        print(f"[hitl_web] no se pudo levantar el servidor: {e}")
        return 1
    estado = "sí" if _token_webhook() else "NO (WEBHOOK_TOKEN vacío: POST /webhook da 503)"
    print(f"[hitl_web] HITL+webhook en http://{HOST}:{puerto} · webhook habilitado: {estado}")
    print(f"[hitl_web] POST {WEBHOOK_RUTA} con header X-Webhook-Token · "
          f"GET {EVENTOS_RUTA} (mismo token)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


def main(_argv=None):
    """Entrada del subcomando; devuelve el código de salida."""
    return iniciar()
