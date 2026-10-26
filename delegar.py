"""Conductor chico: delegarle UNA tarea real al chat, sin nadie al timón.

El meta-loop necesitaba un auditor contestando s/n por tmux (exp/95–98); con
esto el operador delega solo. Es el "banco-lite" de exp/99: el MISMO driver
PTY y el MISMO scope HITL del banco (`banco.banco`), pero con un pedido real
en vez de un escenario guionizado — y SIN `BANCO=1`: las decisiones cuentan
como origen `terminal`, el tráfico orgánico que alimenta la flywheel del
router (X42). Si el chat muere a mitad (el kill de tmux de exp/98), el
conductor rehidrata el thread (exp/48) y re-envía el pedido como continuación.

Uso:
    python3 main.py delegar "pedido" [--permitir ruta]... [--permitir-comandos prefijo]...
        [--timeout-min 30] [--max-hitl 12] [--dir salidas/delegar] [--env K=V]...
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from banco.banco import RAIZ, RE_TU, Chat, escribir_scope, leer_decisiones, limpiar

RE_SN = re.compile(r"\(s/n\):?\s*$")
MAX_RESUMES = 2
LINEA_RESUME = ("La sesión se cortó a mitad del pedido. Retomá donde quedó y "
                "completalo; después respondé con el resultado.")


def env_delegar(dir_threads, extras=None):
    """El entorno del chat conducido (función PURA).

    SIN `BANCO` — y se saca del entorno heredado si estaba: la corrida DEBE
    contar como origen `terminal` para el PAR de routing (exp/44), es su
    razón de ser. `DELEGADO=1` marca la otra procedencia (exp/101): las
    ETIQUETAS del juez de riesgo de una corrida delegada las decide el scope
    del conductor, no un humano — no cuentan como orgánicas para el
    fine-tune. Tampoco se toca MEMORIA/MEMORIA_DIR: esto es tráfico
    orgánico, la biblioteca y los resúmenes son los de producción (el
    aislamiento de X41/X43 es promesa del BANCO, no de acá). THREADS_DIR
    propio: el checkpoint de la corrida vive junto a su transcript, y un
    resume lo encuentra sin adivinar."""
    env = dict(os.environ, PYTHONUNBUFFERED="1", TERM="dumb", DELEGADO="1",
               THREADS_DIR=str(dir_threads))
    env.pop("BANCO", None)
    env.update(extras or {})
    return env


def thread_reciente(dir_threads):
    """El id del checkpoint más nuevo (exp/48), o None si no hay ninguno.

    Tras un resume el proceso hijo genera id nuevo, así que "el más reciente"
    es siempre la punta de la cadena de la corrida."""
    try:
        archivos = sorted(Path(dir_threads).glob("*.jsonl"),
                          key=lambda p: (p.stat().st_mtime, p.name))
    except OSError:
        return None
    return archivos[-1].stem if archivos else None


def _pid_vivo(pid):
    """True si el proceso existe (PermissionError cuenta como vivo: existe,
    aunque sea de otro usuario)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False
    return True


def _leer_pid(run):
    try:
        return int((run / "conductor.pid").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _estado_de_corrida(run):
    """El estado legible de UNA corrida: el de su resumen, o 'en curso' si
    el conductor vive, o 'murió sin resumen' si el pid feneció antes de
    escribirlo (p. ej. un SIGKILL externo)."""
    resumen = run / "resumen.md"
    if resumen.exists():
        for linea in resumen.read_text(encoding="utf-8").splitlines():
            if linea.startswith("- estado:"):
                return linea.split(":", 1)[1].strip()
    pid = _leer_pid(run)
    if pid is not None and _pid_vivo(pid):
        return "en curso"
    return "murió sin resumen"


def _corridas(dir_salidas):
    """Las corridas del conductor, la más reciente primero (el stamp del
    nombre ordena lexicográficamente)."""
    base = Path(dir_salidas)
    try:
        return sorted((d for d in base.iterdir() if d.is_dir()),
                      key=lambda d: d.name, reverse=True)
    except OSError:
        return []


def panorama_delegadas(dir_salidas=None, maximo=3):
    """Las últimas corridas con su estado, para el ARRANQUE del chat
    (exp/100: el operador vive en el chat; si el resultado de lo delegado no
    aparece ahí, es como si no existiera). Best-effort."""
    base = dir_salidas or (RAIZ / "salidas" / "delegar")
    return [f"{d.name}: {_estado_de_corrida(d)}" for d in _corridas(base)[:maximo]]


def corridas_activas(dir_salidas=None):
    """Las delegadas cuyo conductor sigue vivo y no terminó (el aviso al
    CERRAR el chat: la tarea sigue aunque el chat no — el conductor corre
    detached)."""
    base = dir_salidas or (RAIZ / "salidas" / "delegar")
    return [d for d in _corridas(base)
            if not (d / "resumen.md").exists()
            and _leer_pid(d) is not None
            and _pid_vivo(_leer_pid(d))]


def _turno(chat, deadline, evento):
    """Corre UN turno: espera el prompt `Tú:` (ok), la muerte del chat o el
    plazo. Los HITL los decide el propio chat contra el scope (HITL_SCOPE);
    si igual aparece un `(s/n)` —un prompt que no pasó por pedir_aprobacion—
    se rechaza: el conductor no aprueba lo que no puede leer como dato."""
    while time.time() < deadline:
        chat.leer()
        if not chat.vivo:
            return "muerto"
        lineas = [ln for ln in limpiar(chat.nuevo).splitlines() if ln.strip()]
        ultima = lineas[-1] if lineas else ""
        if RE_TU.search(ultima):
            return "ok"
        if RE_SN.search(ultima):
            chat.enviar("n fuera-de-scope")
            evento("hitl-sin-dato", {"prompt": ultima[:200]})
            chat.nuevo = ""
            continue
        time.sleep(0.2)
    return "timeout"


def _esperar_muerte(chat, segundos=20):
    """Espera a que el chat termine de cerrar (salida limpia: el reporte
    [tokens] y el resumen de sesión viajan al final del transcript)."""
    fin = time.time() + segundos
    while time.time() < fin and chat.vivo:
        chat.leer()
        time.sleep(0.1)
    return not chat.vivo


def _escribir_resumen(run, pedido, estado, resumes, segundos):
    filas = leer_decisiones(run / "hitl.jsonl")
    rechazos = sum(1 for f in filas if not f["ok"])
    texto = (
        f"# Delegar — {run.name}\n\n"
        f"- pedido: {pedido}\n"
        f"- estado: {estado}\n"
        f"- duración: {segundos} s\n"
        f"- HITL respondidos: {len(filas)} ({rechazos} rechazados con motivo)\n"
        f"- reanudaciones: {resumes}\n\n"
        f"Transcript: `transcript.log` · eventos: `eventos.jsonl` · decisiones: `hitl.jsonl`\n"
    )
    (run / "resumen.md").write_text(texto, encoding="utf-8")


def conducir(pedido, dir_salida, permitir=None, permitir_comandos=None,
             timeout_min=30, max_hitl=12, extras=None, lanzar=None):
    """Delega el pedido y devuelve el exit code (0 = tarea completada).

    El scope viaja como archivo (HITL_SCOPE) y el chat decide cada pedido en
    su proceso; el conductor solo conduce: arranque, muerte→resume y plazo.
    `lanzar` es inyectable para los tests (sin PTY); en producción es el Chat
    real del banco."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run = Path(dir_salida) / stamp
    (run / "threads").mkdir(parents=True, exist_ok=True)
    # el pid hace consultable el estado de la corrida desde afuera (el
    # arranque del chat reporta "en curso" vs "murió sin resumen")
    (run / "conductor.pid").write_text(str(os.getpid()), encoding="utf-8")
    env = env_delegar(run / "threads", extras)
    # sin --permitir-comandos el conductor NO aprueba ningún comando (lista
    # vacía, no None): nadie al timón no es "todo lo no irreversible". Los de
    # solo-lectura (auto) corren igual: nunca piden aprobación.
    env["HITL_SCOPE"] = str(escribir_scope(run / "scope.json", permitir, permitir_comandos or [],
                                           max_hitl, run / "hitl.jsonl"))
    crudo = run / "transcript.log"
    lanzador = lanzar or (lambda env, argv: Chat(env=env, argv=argv))
    t0 = time.time()
    resumes = 0
    with (run / "eventos.jsonl").open("a", encoding="utf-8") as eventos:

        def evento(tipo, detalle=None):
            eventos.write(json.dumps({"ts": round(time.time(), 3), "tipo": tipo,
                                      "detalle": detalle}, ensure_ascii=False) + "\n")
            eventos.flush()

        def fin(chat, estado, codigo, **detalle):
            evento("fin", {"estado": estado, **detalle})
            chat.matar()
            _escribir_resumen(run, pedido, estado, resumes, round(time.time() - t0))
            return codigo

        evento("inicio", {"pedido": pedido[:200], "permitir": permitir,
                          "permitir_comandos": permitir_comandos,
                          "timeout_min": timeout_min, "max_hitl": max_hitl})
        deadline = time.time() + timeout_min * 60
        argv = ["main.py"]
        linea = pedido
        while True:
            chat = lanzador(env, argv)
            chat.abrir_log(crudo)
            if not chat.esperar(RE_TU, 120):
                return fin(chat, "sin-prompt", 1)
            chat.nuevo = ""
            chat.enviar(linea)
            estado = _turno(chat, deadline, evento)
            if estado == "ok":
                chat.enviar("salir")
                _esperar_muerte(chat)
                return fin(chat, "ok", 0)
            if estado == "timeout":  # interrupción limpia y fin
                chat.ctrl_c()
                _esperar_muerte(chat, 15)
                return fin(chat, "timeout", 1)
            chat.matar()
            id_thread = thread_reciente(run / "threads")
            if id_thread is None or resumes >= MAX_RESUMES:
                return fin(chat, "muerto-sin-resume", 1, id=id_thread)
            resumes += 1
            evento("muerte", {"id": id_thread})
            if chat.raw:
                chat.raw.write(f"\n=== [conductor] el chat murió — resume {id_thread} ===\n")
                chat.raw.flush()
            evento("resume", {"id": id_thread, "n": resumes})
            argv = ["main.py", "resume", id_thread]
            linea = LINEA_RESUME


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="delegar", description="Delega UNA tarea real al chat del harness, sin timón")
    parser.add_argument("pedido", help="la tarea, entre comillas (una sola línea: el chat lee por input())")
    parser.add_argument("--permitir", action="append", default=None, metavar="RUTA",
                        help="prefijo de rutas aprobables para escrituras (repetible)")
    parser.add_argument("--permitir-comandos", action="append", default=None, metavar="PREFIJO",
                        help="prefijo de comandos aprobables (repetible; cada segmento del comando necesita uno)")
    parser.add_argument("--timeout-min", type=int, default=30, metavar="MIN",
                        help="plazo global en minutos, reanudaciones incluidas (default 30)")
    parser.add_argument("--max-hitl", type=int, default=12, metavar="N",
                        help="tope de aprobaciones por corrida, reanudaciones incluidas (default 12)")
    parser.add_argument("--dir", default="salidas/delegar", help="directorio de corridas")
    parser.add_argument("--env", action="append", default=None, metavar="K=V",
                        help="variable de entorno del chat (repetible)")
    args = parser.parse_args(argv)
    if not args.pedido.strip():
        parser.error("el pedido está vacío")
    if "\n" in args.pedido:
        parser.error("el pedido debe ser una sola línea (armalo con puntos y comas)")
    if args.max_hitl < 1 or args.timeout_min < 1:
        parser.error("--max-hitl y --timeout-min exigen enteros >= 1")
    extras = dict(kv.split("=", 1) for kv in args.env or [])
    try:
        return conducir(args.pedido.strip(), RAIZ / args.dir,
                        permitir=args.permitir, permitir_comandos=args.permitir_comandos,
                        timeout_min=args.timeout_min, max_hitl=args.max_hitl, extras=extras)
    except KeyboardInterrupt:
        # el chat hijo muere con el conductor (SIGHUP del PTY al cerrar el master)
        print("\n[conductor] interrumpido — el transcript quedó en salidas/delegar/")
        return 130


if __name__ == "__main__":
    sys.exit(main())
