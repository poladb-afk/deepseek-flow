"""El driver del chat real bajo PTY, compartido por quien lo conduce.

Lo usan el banco (escenarios guionizados, `banco/banco.py`) y el conductor de
tareas delegadas (`delegar.py`). Vivía en `banco/banco.py` y `delegar.py` lo
importaba de ahí: el producto dependía del laboratorio (X93). Acá solo está
lo mecánico — lanzar, leer, escribir, el scope HITL como archivo y su
registro de decisiones —; el entorno y la política los pone cada conductor.
"""
import contextlib
import json
import os
import pty
import re
import select
import signal
import sys
import termios
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
RE_TU = re.compile(r"Tú:\s*$")


def escribir_scope(ruta, rutas=None, comandos=None, maximo=12, eventos=None, aprobar=True):
    """El scope HITL como archivo (HITL_SCOPE): el chat decide cada Pedido
    contra él en SU proceso (utils.aprobaciones.por_scope) y deja la decisión
    en `eventos`. Antes el driver releía la pantalla y reconstruía el pedido
    con regex: el conductor aprobaba `git push` (auditoría 2026-10-26, S1/S2)."""
    ruta = Path(ruta)
    ruta.write_text(json.dumps({"rutas": rutas, "comandos": comandos, "max": maximo,
                                "eventos": str(eventos) if eventos else None,
                                "aprobar": aprobar}, ensure_ascii=False), encoding="utf-8")
    return ruta



def leer_decisiones(ruta):
    """Las decisiones que dejó por_scope (una por pedido), o [] si no hubo."""
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    return [json.loads(ln) for ln in ruta.read_text(encoding="utf-8").splitlines() if ln.strip()]



def limpiar(texto):
    return ANSI.sub("", texto.replace("\r\n", "\n").replace("\r", "\n"))



class Chat:
    """El proceso `main.py` bajo PTY: echo off, ISIG intacto (Ctrl+C real).

    La ventana `nuevo` se TRUNCA al enviar cada línea: la detección de
    prompt/HITL trabaja solo sobre la salida NUEVA, nunca sobre prompts
    viejos que quedaron en el buffer (el bug del driver original: los
    rótulos de turno quedaban desplazados una posición).
    """

    def __init__(self, env, argv=None):
        """`env` es el entorno COMPLETO del chat: cada conductor (el banco,
        `delegar`) arma el suyo; el driver no decide procedencia ni memoria."""
        self.pid, self.master = pty.fork()
        if self.pid == 0:
            attrs = termios.tcgetattr(0)
            attrs[3] &= ~termios.ECHO
            termios.tcsetattr(0, termios.TCSANOW, attrs)
            os.chdir(RAIZ)
            os.execvpe(sys.executable, [sys.executable, *(argv or ["main.py"])],
                       env)
        self.nuevo = ""
        self.raw = None
        self.vivo = True

    def abrir_log(self, destino):
        self.raw = destino.open("a", encoding="utf-8")
        return self.raw

    def leer(self, timeout=0.3):
        """Acorre la salida al buffer `nuevo` (y al log crudo)."""
        fin = time.time() + timeout
        while time.time() < fin:
            r, _, _ = select.select([self.master], [], [], 0.1)
            if not r:
                continue
            try:
                datos = os.read(self.master, 65536)
            except OSError:
                self.vivo = False
                return
            if not datos:
                self.vivo = False
                return
            texto = datos.decode("utf-8", errors="replace")
            if self.raw:
                self.raw.write(texto)
                self.raw.flush()
            self.nuevo += texto

    def enviar(self, linea):
        os.write(self.master, (linea + "\r").encode("utf-8"))

    def ctrl_c(self):
        os.write(self.master, b"\x03")

    def esperar(self, patron, timeout):
        inicio = time.time()
        while time.time() - inicio < timeout:
            self.leer()
            if not self.vivo:
                return False
            if patron.search(limpiar(self.nuevo)):
                return True
        return False

    def matar(self):
        with contextlib.suppress(ProcessLookupError):
            os.kill(self.pid, signal.SIGKILL)
