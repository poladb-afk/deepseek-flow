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

# Los marcadores que el banco cuenta por turno: la señal medible del chat.
MARCADORES = {
    "laya": r"\[laya\]",
    "voto": r"\[voto\]",
    "hitl_prompt": r"\(s/n\)",
    "compaccion": r"\[compacción\]",
    "sintaxis": r"⚠ SINTAXIS",
    "veto_l8": r"\[laya\] \S+ está vetada|\[L8\] \S+ vetada",
    "veto_denylist": r"\[denylist\]",
    "recuperacion": r"\[recuperación\]",
    "dsml_ignorado": r"\[DSML\] tool calls como texto: IGNORADOS",
    "sanitizado": r"\[sanitizado\]",
    "ronda": r"⚙ ronda \d+",
    "auto_lectura": r"run_command \[auto",
    "interrumpido": r"\[interrumpido\]",
    "etiqueta_ambiental": r"\[router\] etiqueta ambiental: (directo|herramientas) \(\d+ rondas\)",
    "riesgo": r"\[riesgo\] observa:",
    "prefetch": r"\[pre-fetch\]",
}


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


def _env_del_chat(extras=None):
    """Entorno del chat bajo banco: procedencia + memoria fuera de la curada.

    BANCO=1 marca las decisiones HITL como sintéticas (exp/44). Y la memoria
    va SIEMPRE a `salidas/banco/memoria`: una corrida de banco no puede tocar
    la biblioteca del usuario (exp/71 — con MEMORIA=0 el respaldo de compacción
    igual escribía `memoria/`; los escenarios con `memoria: true` también
    escriben ahí). El `env:` del escenario es el ÚNICO override: heredar
    `MEMORIA_DIR` del operador alcanzaba para devolver la biblioteca a
    producción (review de exp/71)."""
    env = dict(
        os.environ,
        PYTHONUNBUFFERED="1",
        TERM="dumb",
        BANCO="1",
        MEMORIA="0",
        MEMORIA_DIR=str(RAIZ / "salidas" / "banco" / "memoria"),
    )
    env.update(extras or {})
    return env


class Chat:
    """El proceso `main.py` bajo PTY: echo off, ISIG intacto (Ctrl+C real).

    La ventana `nuevo` se TRUNCA al enviar cada línea: la detección de
    prompt/HITL trabaja solo sobre la salida NUEVA, nunca sobre prompts
    viejos que quedaron en el buffer (el bug del driver original: los
    rótulos de turno quedaban desplazados una posición).
    """

    def __init__(self, env_extra=None, argv=None, env=None):
        """`env` explícito es el del conductor (exp/99): NO pasa por
        _env_del_chat — sin BANCO=1 (origen terminal) y sin tocar MEMORIA.
        Sin `env`, el comportamiento del banco queda intacto."""
        self.pid, self.master = pty.fork()
        if self.pid == 0:
            import termios

            attrs = termios.tcgetattr(0)
            attrs[3] &= ~termios.ECHO
            termios.tcsetattr(0, termios.TCSANOW, attrs)
            os.chdir(RAIZ)
            os.execvpe(sys.executable, [sys.executable, *(argv or ["main.py"])],
                       env if env is not None else _env_del_chat(env_extra))
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

    ruta_scope = escribir_scope(dir_salida / f"{escenario['id']}_{stamp}_scope.json", aprobar=False)
    env["HITL_SCOPE"] = str(ruta_scope)
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

    resultados = []
    for i, turno in enumerate(escenario["turnos"], 1):
        tid = turno.get("id", f"t{i}")
        timeout = int(turno.get("timeout", 120))
        decisiones = dir_salida / f"{escenario['id']}_{stamp}_{tid}_hitl.jsonl"
        escribir_scope(ruta_scope, escenario.get("permitir"), escenario.get("permitir_comandos"),
                       turno.get("max_hitl", MAX_HITL_POR_TURNO), decisiones,
                       aprobar=turno.get("hitl", "none") == "s")
        evento("turno-inicio", {"n": i, "id": tid})
        t0 = time.time()

        # la ventana de DETECCIÓN se trunca al enviar (fix del desfase del
        # driver original); la de MEDICIÓN (ventana) acumula todo el turno.
        chat.nuevo = ""
        ventana = ""
        chat.enviar(turno["linea"])

        if turno.get("ctrl_c_segundos"):
            if chat.esperar(RE_DEEPSEEK, timeout):
                time.sleep(turno["ctrl_c_segundos"])
                chat.ctrl_c()
            estado = "ok" if turno_finalizo(chat) or chat.esperar(RE_TU, 30) else "timeout"
        else:
            estado = "timeout"
            inicio = time.time()
            while time.time() - inicio < timeout:
                chat.leer()
                if not chat.vivo:
                    # un turno de salida: morir es el final ESPERADO (el
                    # "¡Chao!" distingue salida limpia de crash a mitad)
                    estado = "ok" if "¡Chao" in limpiar(ventana + chat.nuevo) else "proceso-muerto"
                    break
                if hitl_pendiente(chat):
                    # un (s/n) que no pasó por pedir_aprobacion: sin dato, no
                    chat.enviar("n")
                    evento("hitl-sin-dato", {"n": i, "id": tid})
                    ventana += chat.nuevo
                    chat.nuevo = ""
                    continue
                if turno_finalizo(chat):
                    estado = "ok"
                    break
                time.sleep(0.2)
        filas = leer_decisiones(decisiones)
        for fila in filas:
            evento("hitl", {"n": i, "id": tid, "respuesta": "s" if fila["ok"] else "n"})
            if fila["motivo"] in ("fuera-de-scope", "denylist", "tipo-desconocido"):
                evento("hitl-fuera-de-alcance", {"objetivo": fila["objetivo"],
                                                 "motivo": fila["motivo"], "turno": i})
        hitl = len(filas)
        hitl_topes = sum(1 for f in filas if f["motivo"] == "tope")
        # el conteo de marcadores es la MEDIDA del turno
        marcadores = contar_marcadores(limpiar(ventana + chat.nuevo))
        fallas = verificar_turno(turno.get("verificar"), limpiar(ventana + chat.nuevo)) if estado == "ok" else []
        if fallas:
            estado = "no-hecha"  # el prompt volvió pero la tarea no se cumplió
            evento("no-hecha", {"n": i, "id": tid, "fallas": fallas})
        duracion = round(time.time() - t0)
        evento("turno-fin", {"n": i, "id": tid, "estado": estado, "seg": duracion,
                             "hitl": locals().get("hitl", 0),
                             "hitl_tope": locals().get("hitl_topes", 0), "marcadores": marcadores})
        resultados.append({"id": tid, "estado": estado, "seg": duracion,
                           "hitl": locals().get("hitl", 0), "marcadores": marcadores})
        if estado in ("proceso-muerto", "timeout"):
            evento("corte", {"motivo": estado, "en_turno": tid})
            break

    evento("fin", {"ok": sum(1 for r in resultados if r["estado"] == "ok"),
                   "total": len(resultados)})
    eventos.close()

    ok = sum(1 for r in resultados if r["estado"] == "ok")
    con_criterio = sum(1 for t in escenario["turnos"] if t.get("verificar"))
    with resumen.open("w", encoding="utf-8") as f:
        f.write(f"# Banco — {escenario['id']} — {datetime.now().isoformat()}\n\n")
        # "OK" en un turno con `verificar:` es TAREA HECHA; sin él, solo que el
        # prompt volvió. El resumen dice cuántos turnos miden de verdad.
        f.write(f"{ok}/{len(escenario['turnos'])} turnos OK "
                f"({con_criterio} con criterio de tarea hecha) · "
                f"HITL pedidos: {sum(r['hitl'] for r in resultados)}\n\n")
        f.write("| turno | estado | seg | hitl | marcadores |\n|---|---|---|---|---|\n")
        for r in resultados:
            marca = ", ".join(f"{k}×{v}" for k, v in sorted(r["marcadores"].items())) or "—"
            f.write(f"| {r['id']} | {r['estado']} | {r['seg']} | {r['hitl']} | {marca} |\n")
        f.write(f"\nTranscript: `{crudo.name}` · eventos: `{eventos_f.name}`\n")

    for path in escenario.get("scratch", []):
        objetivo = objetivo_scratch(path)
        if objetivo is None:
            print(f"  [scratch] fuera del proyecto, no se toca: {RAIZ / path}")
            continue
        if objetivo.is_dir():
            shutil.rmtree(objetivo, ignore_errors=True)
        elif objetivo.exists():
            objetivo.unlink()

    chat.matar()
    print(f"Banco {escenario['id']}: {ok}/{len(escenario['turnos'])} OK → {resumen}")
    return 0 if ok == len(escenario["turnos"]) else 1


def objetivo_scratch(path):
    """El destino a borrar del scratch, o None si cae FUERA del proyecto.

    X3: RAIZ / '/abs' da '/abs' y '..' se escapa — sin esta contención un
    escenario podía borrar cualquier ruta del disco. Función pura para
    testearla sin correr el banco."""
    objetivo = (RAIZ / path).resolve()
    if objetivo == RAIZ or RAIZ not in objetivo.parents:
        return None
    return objetivo


def sustituir_placeholders(texto):
    """Reemplaza los marcadores RAIZ y HOME entre llaves en los escenarios.

    Las rutas de la máquina del autor no viajan en el repo (PR 5 del plan de
    orden): los YAML traen '{RAIZ}/salidas/...' y acá se expanden."""
    return texto.replace("{RAIZ}", str(RAIZ)).replace("{HOME}", str(Path.home()))


# Criterio de TAREA HECHA por turno (`verificar:`): sin él, "ok" solo decía
# que el prompt `Tú:` volvió, y un turno que no hizo nada pasaba igual
# (auditoría de H1: el modelo rehusó exp2-docs y el banco dio 2/2 OK). Cada
# chequeo es determinista y corre al cerrar el turno, contra el disco y el
# transcript del turno. Rutas relativas a la raíz del proyecto.
#
# `salida` es el chequeo de las tareas de LECTURA: el comando calcula la
# respuesta correcta contra el repo VIVO (el YAML no guarda números que
# envejezcan) y el modelo tiene que haberla dado como `RESPUESTA: <x>`.
CHEQUEOS = ("existe", "no_existe", "contiene", "transcript", "comando", "salida")
# Los que un turno vacío NO cumple: todo `verificar:` necesita uno. `no_existe`
# y `comando: pytest` pasan sin que el modelo toque nada (así banco-1 y
# banco-3 daban OK con fixes que ya estaban aplicados).
CHEQUEOS_DE_TRABAJO = ("existe", "contiene", "transcript", "salida")


def _respuesta_esperada(comando):
    """La salida del comando (la respuesta correcta), o None si no corre."""
    import subprocess

    r = subprocess.run(comando, shell=True, cwd=RAIZ, capture_output=True, text=True, timeout=300)
    salida = (r.stdout or "").strip()
    return salida if r.returncode == 0 and salida else None


def dio_la_respuesta(esperada, transcript):
    """`RESPUESTA: <esperada>` en el transcript (tolera negrita y backticks)."""
    patron = rf"(?i)RESPUESTA:\s*[*`]*{re.escape(esperada)}[*`]*(?![\w.])"
    return re.search(patron, transcript) is not None


def verificar_turno(chequeos, transcript):
    """Los chequeos que FALLAN (lista vacía = tarea hecha). PURA salvo la
    lectura del disco y `comando`, que corre con timeout en la raíz."""
    import subprocess

    fallas = []
    for chequeo in chequeos or ():
        (tipo, valor), = chequeo.items()
        if tipo == "existe" and not (RAIZ / valor).exists():
            fallas.append(f"no existe {valor}")
        elif tipo == "no_existe" and (RAIZ / valor).exists():
            fallas.append(f"existe {valor}")
        elif tipo == "contiene":
            ruta = RAIZ / valor["ruta"]
            if not ruta.is_file() or valor["texto"] not in ruta.read_text(encoding="utf-8", errors="replace"):
                fallas.append(f"{valor['ruta']} no contiene {valor['texto']!r}")
        elif tipo == "transcript" and not re.search(valor, transcript):
            fallas.append(f"el transcript no matchea {valor!r}")
        elif tipo == "comando":
            r = subprocess.run(valor, shell=True, cwd=RAIZ, capture_output=True, timeout=300)
            if r.returncode:
                fallas.append(f"`{valor}` salió {r.returncode}")
        elif tipo == "salida":
            if "RESPUESTA:" not in transcript.upper():
                fallas.append("el modelo no dio `RESPUESTA:`")
                continue
            esperada = _respuesta_esperada(valor)
            if esperada is None:
                fallas.append(f"`{valor}` no produjo la respuesta esperada")
            elif not dio_la_respuesta(esperada, transcript):
                fallas.append(f"falta `RESPUESTA: {esperada}`")
    return fallas


def _validar_chequeos(ruta, turno):
    chequeos = turno.get("verificar") or ()
    for chequeo in chequeos:
        if not (isinstance(chequeo, dict) and len(chequeo) == 1 and next(iter(chequeo)) in CHEQUEOS):
            raise ValueError(f"verificar inválido en {ruta}: {chequeo!r} (uno de {CHEQUEOS})")
    if chequeos and not any(next(iter(c)) in CHEQUEOS_DE_TRABAJO for c in chequeos):
        raise ValueError(f"verificar en {ruta} turno {turno.get('id')!r} se cumple sin hacer nada: "
                         f"sumá uno de {CHEQUEOS_DE_TRABAJO}")


def cargar_escenario(ruta):
    esc = yaml.safe_load(sustituir_placeholders(Path(ruta).read_text(encoding="utf-8")))
    if not esc.get("id") or "turnos" not in esc:
        raise ValueError(f"escenario inválido: {ruta}")
    ids = [t.get("id") for t in esc["turnos"]]
    if len(ids) != len(set(ids)):
        raise ValueError(f"ids de turno duplicados en {ruta}")
    for turno in esc["turnos"]:
        # knob declarativo por turno: default = MAX_HITL_POR_TURNO; si
        # viene debe ser un int >= 1 (nunca un tope 0 que colgaría el turno).
        tope = turno.get("max_hitl", MAX_HITL_POR_TURNO)
        if not isinstance(tope, int) or isinstance(tope, bool) or tope < 1:
            raise ValueError(f"max_hitl inválido en {ruta}: {tope!r} (int >= 1)")
        _validar_chequeos(ruta, turno)
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
