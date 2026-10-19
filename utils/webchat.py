"""Chat web MVP (Mesa 8, exp/59): SSE con stdlib, CERO dependencias nuevas.

Cada sesión de navegador corre el chat REAL en un SUBPROCESO aislado
(`python3 -u main.py`): hereda grafo, streaming y HITL tal cual, sin tocar el
CORE (ni `input()`, ni threading global, ni estado compartido entre sesiones).
El server de `utils/hitl_web.py` expone, con `WEBCHAT=1`:

    GET  /chat                      página mínima (textarea + log)
    POST /chat/sesion               crea sesión → {sesion, token}
    POST /chat/mensaje {sesion,token,texto} → escribe la pregunta al hijo
    GET  /chat/stream?sesion&token  SSE con stdout/stderr del hijo
    POST /chat/cerrar {sesion,token}

Seguridad (mismo nivel que el webhook): solo loopback (Host/Origin del HITL),
token aleatorio por sesión comparado en TIEMPO CONSTANTE, tope de sesiones
(`WEBCHAT_MAX_SESIONES`, 3) y TTL sin actividad (`WEBCHAT_TTL`, 900 s). El
texto que escribe el navegador NO se persiste: el hijo corre con
`PREGUNTAS_LOG=0`, `NO_COLOR=1` (la página no interpreta ANSI) y `TRACE=0`
(no ensucia `.runs` con cada pregunta web).
"""
import contextlib
import json
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MAX_SESIONES_DEFAULT = 3
TTL_DEFAULT = 900
COMANDO_CHAT = [sys.executable, "-u", "main.py"]

_limite = threading.Lock()
_gestor = None


def _ttl():
    from utils.call_llm import _entero

    return max(30, _entero("WEBCHAT_TTL", TTL_DEFAULT))


def _max_sesiones():
    from utils.call_llm import _entero

    return max(1, _entero("WEBCHAT_MAX_SESIONES", MAX_SESIONES_DEFAULT))


class Sesion:
    """Un chat vivo en un subproceso. Aislado: su stdin/stdout/cola son propios."""

    def __init__(self, comando=None):
        self.id = secrets.token_urlsafe(8)
        self.token = secrets.token_urlsafe(24)
        self._cola = queue.Queue()
        self._viva = True
        self._ultimo = time.monotonic()
        entorno = os.environ.copy()
        entorno.update({
            "HITL_WEB": "1",        # las aprobaciones salen por la página HITL
            "CHAT_STREAM": "1",     # el texto llega en vivo para el SSE
            "PREGUNTAS_LOG": "0",   # el texto del navegador no se persiste
            "NO_COLOR": "1",        # la página no interpreta ANSI
            "TRACE": "0",           # no ensucia .runs con cada pregunta web
        })
        self._proceso = subprocess.Popen(
            comando or COMANDO_CHAT, cwd=RAIZ, env=entorno,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        threading.Thread(target=self._leer, daemon=True).start()

    def _leer(self):
        """Un char por vez: el streaming del chat no respeta líneas."""
        try:
            while self._viva:
                trozo = self._proceso.stdout.read(1)
                if trozo == "":
                    break
                self._ultimo = time.monotonic()
                self._cola.put(trozo)
        finally:
            self._cola.put(None)

    def enviar(self, texto):
        if not self._viva:
            raise RuntimeError("sesión cerrada")
        self._proceso.stdin.write(texto.rstrip("\n") + "\n")
        self._proceso.stdin.flush()
        self._ultimo = time.monotonic()

    def eventos(self):
        """Trozos de salida del chat. Termina con EOF del hijo o TTL.

        Sin parámetro de timeout: el deadline real es el TTL de inactividad y
        el corte por techo de rondas lo hace el chat. (Antes había un `if`
        cuyo único efecto era un `continue` en ambas ramas: muerto.)"""
        while self._viva:
            if time.monotonic() - self._ultimo > _ttl():
                yield "\n[webchat] sesión sin actividad: cerrando\n"
                return
            try:
                trozo = self._cola.get(timeout=1.0)
            except queue.Empty:
                continue
            if trozo is None:
                return
            yield trozo

    def cerrar(self):
        self._viva = False
        with contextlib.suppress(OSError, ValueError):
            self._proceso.stdin.close()
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            self._proceso.terminate()
            self._proceso.wait(timeout=3)
        with contextlib.suppress(OSError):
            self._proceso.kill()


class Gestor:
    """Sesiones vivas por proceso, con tope y limpieza por TTL/muerte."""

    def __init__(self):
        self._sesiones = {}

    def crear(self):
        with _limite:
            self._limpiar()
            if len(self._sesiones) >= _max_sesiones():
                raise RuntimeError(
                    f"tope de sesiones ({_max_sesiones()}): cerrá una pestaña")
            sesion = Sesion()
            self._sesiones[sesion.id] = sesion
            return sesion

    def obtener(self, id_sesion, token):
        sesion = self._sesiones.get(id_sesion or "")
        if sesion is None or not secrets.compare_digest(str(token or ""), sesion.token):
            return None
        return sesion

    def cerrar(self, id_sesion, token):
        sesion = self.obtener(id_sesion, token)
        if sesion is None:
            return False
        with _limite:
            self._sesiones.pop(sesion.id, None)
        sesion.cerrar()
        return True

    def _limpiar(self):
        for id_sesion, sesion in list(self._sesiones.items()):
            if (not sesion._viva
                    or time.monotonic() - sesion._ultimo > _ttl()):
                self._sesiones.pop(id_sesion, None)
                sesion.cerrar()


def gestor():
    """El gestor único del proceso (perezoso: los tests lo reemplazan)."""
    global _gestor
    if _gestor is None:
        _gestor = Gestor()
    return _gestor


def habilitado():
    from utils.call_llm import _setting

    return _setting("WEBCHAT", "0") == "1"


def evento_sse(trozo):
    """Un evento SSE (JSON: preserva saltos de línea y no rompe el framing)."""
    return f"data: {json.dumps({'t': trozo}, ensure_ascii=False)}\n\n"


def pagina():
    """Página mínima: sin CDN ni build. Una pestaña = una sesión."""
    return """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>deepseek-flow — chat</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;background:#111;color:#ddd}
main{max-width:860px;margin:0 auto;padding:16px}
#log{white-space:pre-wrap;background:#1b1b1b;border-radius:8px;padding:12px;
height:60vh;overflow:auto;font-size:14px;line-height:1.35}
#fila{display:flex;gap:8px;margin-top:10px}
#texto{flex:1;padding:10px;border-radius:8px;border:1px solid #444;background:#1b1b1b;color:#eee}
button{padding:10px 16px;border-radius:8px;border:0;background:#26f;color:#fff;cursor:pointer}
#estado{color:#888;font-size:12px;margin-top:6px}
</style></head><body><main>
<h3>deepseek-flow — chat web (SSE)</h3>
<div id="log"></div>
<div id="fila"><input id="texto" placeholder="Preguntá algo y Enter…" autofocus>
<button id="enviar">Enviar</button></div>
<div id="estado">creando sesión…</div>
<script>
let sesion=null, token=null;
const log=document.getElementById('log'), estado=document.getElementById('estado');
function pintar(t){ log.textContent += t; log.scrollTop = log.scrollHeight; }
function crear(){
  fetch('/chat/sesion',{method:'POST'}).then(r=>r.json()).then(d=>{
    sesion=d.sesion; token=d.token; estado.textContent='sesión '+sesion.slice(0,8)+'…';
    const es=new EventSource('/chat/stream?sesion='+encodeURIComponent(sesion)+'&token='+encodeURIComponent(token));
    es.onmessage=e=>{ try{ pintar(JSON.parse(e.data).t); }catch(_){ } };
    es.onerror=()=>{ estado.textContent='stream cerrado'; es.close(); };
    window._es=es;
  }).catch(e=>estado.textContent='error creando sesión: '+e);
}
function enviar(){
  const t=document.getElementById('texto'); const v=t.value.trim(); if(!v||!sesion) return;
  t.value=''; pintar('\\nTú: '+v+'\\n');
  fetch('/chat/mensaje',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({sesion,token,texto:v})}).catch(e=>pintar('[error] '+e));
}
document.getElementById('enviar').onclick=enviar;
document.getElementById('texto').addEventListener('keydown',e=>{if(e.key==='Enter')enviar()});
window.addEventListener('beforeunload',()=>{
  if(sesion) fetch('/chat/cerrar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({sesion,token}),keepalive:true});
});
crear();
</script></main></body></html>
"""
