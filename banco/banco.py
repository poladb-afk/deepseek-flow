"""Banco de conversación: escenarios reproducibles contra el chat REAL.

Corre un escenario (YAML) por un PTY — HITL s/n respondido según política,
turnos con timeout propio — y deja por corrida: transcript crudo, eventos
jsonl y resumen markdown con el CONTEO DE MARCADORES por turno (compacción,
votos, auto, sintaxis, vetos…). Ese conteo es la medición: mismo escenario
antes y después de un cambio = A/B con números, no impresiones.

Decisiones de banco (para que una corrida no contamine):
- MEMORIA=0 default (el resumen de sesión NO pisa memoria/; configurable
  por escenario con `memoria: true` cuando el experimento ES la memoria).
- Los paths de `scratch:` se borran al terminar (fixtures desechables).
- Exit 0 solo si todos los turnos terminaron OK: usable como gate.

Uso:
    python3 banco/banco.py banco/escenarios/smoke.yaml [--dir salidas/banco]
"""
import argparse
import contextlib
import json
import os
import pty
import re
import select
import shutil
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
RE_HITL = re.compile(r"\(s/n\):?\s*$")
RE_TU = re.compile(r"Tú:\s*$")
RE_DEEPSEEK = re.compile(r"DeepSeek: ?$")
MAX_HITL_POR_TURNO = 6

# Scope HITL (exp/11): el driver deja de aprobar a ciegas. Parsea el objetivo
# del prompt y solo aprueba si cae DENTRO del alcance del escenario; la
# denylist dura del conductor manda por encima de cualquier scope.
RE_HITL_ESCRITURA = re.compile(r"→ (\S+) \(s/n\)")
RE_HITL_COMANDO = re.compile(r"¿Ejecutar\? \(s/n\)")
DENYLIST_DURA = {
    "rutas": (".env", ".git/", "memoria/"),
    "comandos": ("git push", "rm -rf", "rm -fr"),
}


def decision_hitl(prompt, buffer_reciente, permitir=None, permitir_comandos=None):
    """Decide si un prompt HITL cae dentro del alcance (función PURA).

    Devuelve {tipo, objetivo, dentro, motivo}. `tipo` ∈ escritura/comando/
    desconocido. Sin `permitir`/`permitir_comandos` (None) todo está
    permitido SALVO la denylist dura: compatibilidad con los escenarios
    viejos que no declaran scope.
    """
    objetivo = None
    tipo = "desconocido"

    m = RE_HITL_ESCRITURA.search(prompt)
    if m:
        tipo = "escritura"
        objetivo = m.group(1)
        if any(fragmento in objetivo for fragmento in DENYLIST_DURA["rutas"]):
            return {"tipo": tipo, "objetivo": objetivo, "dentro": False, "motivo": "denylist"}
        if permitir is not None and not any(objetivo.startswith(p) for p in permitir):
            return {"tipo": tipo, "objetivo": objetivo, "dentro": False, "motivo": "fuera-de-scope"}
        return {"tipo": tipo, "objetivo": objetivo, "dentro": True, "motivo": "ok"}
    elif RE_HITL_COMANDO.search(prompt):
        tipo = "comando"
        lineas = [linea for linea in buffer_reciente.splitlines() if linea.strip()]
        for linea in reversed(lineas):
            limpia = linea.strip()
            # el propio prompt HITL y su banner no son el comando (la
            # ventana integrada incluye la línea "(s/n)" pendiente)
            if "(s/n)" in limpia or limpia.startswith("── run_command") or limpia.startswith("↳ "):
                continue
            objetivo = limpia
            break
        if objetivo is not None:
            if any(objetivo.startswith(c) for c in DENYLIST_DURA["comandos"]):
                return {"tipo": tipo, "objetivo": objetivo, "dentro": False, "motivo": "denylist"}
            if permitir_comandos is not None and not any(
                    objetivo.startswith(p) for p in permitir_comandos):
                return {"tipo": tipo, "objetivo": objetivo, "dentro": False, "motivo": "fuera-de-scope"}
        return {"tipo": tipo, "objetivo": objetivo, "dentro": True, "motivo": "ok"}

    # prompt nuevo o formato desconocido: dejamos seguir el flujo y que la
    # política decida, pero queda registrado para revisar.
    return {"tipo": "desconocido", "objetivo": None, "dentro": True, "motivo": "no-parseable"}

# Los marcadores que el banco cuenta por turno: la señal medible del chat.
MARCADORES = {
    "laya": r"\[laya\]",
    "voto": r"\[voto\]",
    "hitl_prompt": r"\(s/n\)",
    "compaccion": r"\[compacción\]",
    "sintaxis": r"⚠ SINTAXIS",
    "veto": r"PROHIBID|[Vv]etad",
    "recuperacion": r"\[recuperación\]",
    "dsml_ignorado": r"\[DSML\] tool calls como texto: IGNORADOS",
    "sanitizado": r"\[sanitizado\]",
    "ronda": r"⚙ ronda \d+",
    "auto_lectura": r"run_command \[auto",
    "interrumpido": r"\[interrumpido\]",
}


def limpiar(texto):
    return ANSI.sub("", texto.replace("\r\n", "\n").replace("\r", "\n"))


class Chat:
    """El proceso `main.py` bajo PTY: echo off, ISIG intacto (Ctrl+C real).

    La ventana `nuevo` se TRUNCA al enviar cada línea: la detección de
    prompt/HITL trabaja solo sobre la salida NUEVA, nunca sobre prompts
    viejos que quedaron en el buffer (el bug del driver original: los
    rótulos de turno quedaban desplazados una posición).
    """

    def __init__(self, env_extra=None):
        self.pid, self.master = pty.fork()
        if self.pid == 0:
            import termios

            attrs = termios.tcgetattr(0)
            attrs[3] &= ~termios.ECHO
            termios.tcsetattr(0, termios.TCSANOW, attrs)
            os.chdir(RAIZ)
            env = dict(os.environ, PYTHONUNBUFFERED="1", TERM="dumb",
                       MEMORIA=os.environ.get("MEMORIA", "0"))
            env.update(env_extra or {})
            os.execvpe(sys.executable, [sys.executable, "main.py"], env)
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


def contar_marcadores(texto):
    conteo = {}
    for nombre, patron in MARCADORES.items():
        n = len(re.findall(patron, texto))
        if n:
            conteo[nombre] = n
    return conteo


def turno_finalizo(chat):
    """True cuando el prompt `Tú:` volvió a aparecer en la salida NUEVA."""
    lineas = [linea for linea in limpiar(chat.nuevo).splitlines() if linea.strip()]
    return bool(lineas) and bool(RE_TU.search(lineas[-1]))


def hitl_pendiente(chat):
    """La última línea con contenido es un prompt (s/n) sin responder."""
    lineas = [linea for linea in limpiar(chat.nuevo).splitlines() if linea.strip()]
    return bool(lineas) and bool(RE_HITL.search(lineas[-1]))


def correr(escenario, dir_salida):
    dir_salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    crudo = dir_salida / f"{escenario['id']}_{stamp}.log"
    eventos_f = dir_salida / f"{escenario['id']}_{stamp}.jsonl"
    resumen = dir_salida / f"{escenario['id']}_{stamp}.md"

    # env del escenario: cada escenario puede fijar variables del chat
    # (p. ej. MAX_TOOL_ROUNDS=3 para forzar la nota de presupuesto en pocas
    # rondas). MEMORIA=0 default salvo `memoria: true`.
    env = dict(escenario.get("env") or {})
    env.setdefault("MEMORIA", "1" if escenario.get("memoria") else "0")

    chat = Chat(env_extra=env)
    chat.abrir_log(crudo)
    eventos = eventos_f.open("a", encoding="utf-8")

    def evento(tipo, detalle=None):
        eventos.write(json.dumps({"ts": round(time.time(), 3), "tipo": tipo,
                                  "detalle": detalle}, ensure_ascii=False) + "\n")
        eventos.flush()

    evento("inicio", {"escenario": escenario["id"], "turnos": len(escenario["turnos"])})
    if not chat.esperar(RE_TU, 120):
        evento("fallo", "nunca apareció el primer prompt")
        chat.matar()
        return 1

    permitir = escenario.get("permitir")
    permitir_comandos = escenario.get("permitir_comandos")
    resultados = []
    for i, turno in enumerate(escenario["turnos"], 1):
        tid = turno.get("id", f"t{i}")
        politica = turno.get("hitl", "none")
        timeout = int(turno.get("timeout", 120))
        evento("turno-inicio", {"n": i, "id": tid})
        t0 = time.time()

        # la ventana de DETECCIÓN se trunca al enviar (fix del desfase del
        # driver original); la de MEDICIÓN (ventana) acumula todo el turno
        # para no perder marcadores al responder un HITL a mitad de turno.
        chat.nuevo = ""
        ventana = ""
        chat.enviar(turno["linea"])

        if turno.get("ctrl_c_segundos"):
            if chat.esperar(RE_DEEPSEEK, timeout):
                time.sleep(turno["ctrl_c_segundos"])
                chat.ctrl_c()
            estado = "ok" if turno_finalizo(chat) or chat.esperar(RE_TU, 30) else "timeout"
        else:
            estado = "corriendo"
            inicio = time.time()
            hitl_dados = 0
            while time.time() - inicio < timeout:
                chat.leer()
                if not chat.vivo:
                    # un turno de salida: morir es el final ESPERADO (el
                    # "¡Chao!" distingue salida limpia de crash a mitad)
                    estado = "ok" if "¡Chao" in limpiar(ventana + chat.nuevo) else "proceso-muerto"
                    break
                if hitl_pendiente(chat) and hitl_dados < MAX_HITL_POR_TURNO:
                    # el HITL ya no se aprueba a ciegas: se mira el objetivo
                    ventana_completa = limpiar(ventana + chat.nuevo)
                    lineas_con_texto = [ln for ln in ventana_completa.splitlines() if ln.strip()]
                    ultima_linea = lineas_con_texto[-1] if lineas_con_texto else ""
                    decision = decision_hitl(ultima_linea, ventana_completa,
                                             permitir, permitir_comandos)
                    if decision["dentro"]:
                        respuesta = "s" if politica == "s" else "n"
                    else:
                        respuesta = "n"
                        evento("hitl-fuera-de-alcance",
                               {"objetivo": decision["objetivo"], "motivo": decision["motivo"],
                                "turno": i})
                    time.sleep(0.5)
                    chat.enviar(respuesta)
                    hitl_dados += 1
                    evento("hitl", {"n": i, "id": tid, "respuesta": respuesta})
                    ventana += chat.nuevo
                    chat.nuevo = ""
                    continue
                if turno_finalizo(chat):
                    estado = "ok"
                    break
                time.sleep(0.2)
            else:
                estado = "timeout"
            hitl = hitl_dados
        # el conteo de marcadores es la MEDIDA del turno
        marcadores = contar_marcadores(limpiar(ventana + chat.nuevo))
        duracion = round(time.time() - t0)
        evento("turno-fin", {"n": i, "id": tid, "estado": estado, "seg": duracion,
                             "hitl": locals().get("hitl", 0), "marcadores": marcadores})
        resultados.append({"id": tid, "estado": estado, "seg": duracion,
                           "hitl": locals().get("hitl", 0), "marcadores": marcadores})
        if estado in ("proceso-muerto", "timeout"):
            evento("corte", {"motivo": estado, "en_turno": tid})
            break

    evento("fin", {"ok": sum(1 for r in resultados if r["estado"] == "ok"),
                   "total": len(resultados)})
    eventos.close()

    ok = sum(1 for r in resultados if r["estado"] == "ok")
    with resumen.open("w", encoding="utf-8") as f:
        f.write(f"# Banco — {escenario['id']} — {datetime.now().isoformat()}\n\n")
        f.write(f"{ok}/{len(escenario['turnos'])} turnos OK\n\n")
        f.write("| turno | estado | seg | hitl | marcadores |\n|---|---|---|---|---|\n")
        for r in resultados:
            marca = ", ".join(f"{k}×{v}" for k, v in sorted(r["marcadores"].items())) or "—"
            f.write(f"| {r['id']} | {r['estado']} | {r['seg']} | {r['hitl']} | {marca} |\n")
        f.write(f"\nTranscript: `{crudo.name}` · eventos: `{eventos_f.name}`\n")

    for path in escenario.get("scratch", []):
        objetivo = RAIZ / path
        if objetivo.is_dir():
            shutil.rmtree(objetivo, ignore_errors=True)
        elif objetivo.exists():
            objetivo.unlink()

    chat.matar()
    print(f"Banco {escenario['id']}: {ok}/{len(escenario['turnos'])} OK → {resumen}")
    return 0 if ok == len(escenario["turnos"]) else 1


def cargar_escenario(ruta):
    esc = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
    if not esc.get("id") or "turnos" not in esc:
        raise ValueError(f"escenario inválido: {ruta}")
    ids = [t.get("id") for t in esc["turnos"]]
    if len(ids) != len(set(ids)):
        raise ValueError(f"ids de turno duplicados en {ruta}")
    return esc


def main(argv=None):
    parser = argparse.ArgumentParser(prog="banco", description="Escenarios reproducibles contra el chat real")
    parser.add_argument("escenario", help="path del YAML del escenario")
    parser.add_argument("--dir", default="salidas/banco", help="directorio de salida (default: %(default)s)")
    args = parser.parse_args(argv)
    esc = cargar_escenario(args.escenario)
    return correr(esc, RAIZ / args.dir)


if __name__ == "__main__":
    sys.exit(main())
