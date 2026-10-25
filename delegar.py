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

from banco.banco import RAIZ, RE_TU, Chat, decision_hitl, limpiar

RE_SN = re.compile(r"\(s/n\):?\s*$")
RE_DOBLE = re.compile(r"\((?:1/2|2/2)\):?\s*$")
MAX_RESUMES = 2
LINEA_RESUME = ("La sesión se cortó a mitad del pedido. Retomá donde quedó y "
                "completalo; después respondé con el resultado.")


def env_delegar(dir_threads, extras=None):
    """El entorno del chat conducido (función PURA).

    SIN `BANCO` — y se saca del entorno heredado si estaba: la corrida DEBE
    contar como origen `terminal` (exp/44), es su razón de ser. Tampoco se
    toca MEMORIA/MEMORIA_DIR: esto es tráfico orgánico, la biblioteca y los
    resúmenes son los de producción (el aislamiento de X41/X43 es promesa
    del BANCO, no de acá). THREADS_DIR propio: el checkpoint de la corrida
    vive junto a su transcript, y un resume lo encuentra sin adivinar."""
    env = dict(os.environ, PYTHONUNBUFFERED="1", TERM="dumb",
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


def tipo_prompt(ultima_linea):
    """Qué prompt HITL está pendiente en la última línea: "sn", "doble" o None.

    Los formatos son contrato del chat (test_banco/test_delegar los fijan con
    líneas reales). La doble confirmación es el nivel destructivo de la
    policy — el conductor la trata con su propia regla."""
    if RE_DOBLE.search(ultima_linea):
        return "doble"
    if RE_SN.search(ultima_linea):
        return "sn"
    return None


def plan_respuesta(ultima_linea, ventana, permitir, permitir_comandos):
    """La línea exacta a mandarle al prompt pendiente (función PURA).

    El rechazo viaja CON MOTIVO (exp/98): `n fuera-de-scope` parsea en
    pedir_aprobacion como Decision(False, "fuera-de-scope") y llega al
    modelo — no tiene que adivinar por qué le dijeron que no."""
    if tipo_prompt(ultima_linea) == "doble":
        # La policy ya clasificó el comando como destructivo: SOLO un
        # prefijo EXPLÍCITO de --permitir-comandos lo autoriza. Sin modo
        # compat (permitir_comandos=None aprueba todo lo no-denylist en los
        # prompts comunes): acá el default es no. La ventana va SIN su
        # última línea: la extracción de decision_hitl saltea el prompt
        # "(s/n)" pendiente, pero no conoce "(1/2)" — sin recortarla, el
        # "comando" extraído sería el propio prompt.
        sin_prompt = "\n".join(ventana.splitlines()[:-1])
        d = decision_hitl("¿Ejecutar? (s/n)", sin_prompt)
        objetivo = d["objetivo"]
        if (objetivo and permitir_comandos and d["motivo"] != "denylist"
                and any(objetivo.startswith(p) for p in permitir_comandos)):
            return {"respuesta": "s", "tipo": "doble",
                    "objetivo": objetivo, "motivo": "ok"}
        motivo = "denylist" if d["motivo"] == "denylist" else "confirmacion-doble"
        return {"respuesta": f"n {motivo}", "tipo": "doble",
                "objetivo": objetivo, "motivo": motivo}
    d = decision_hitl(ultima_linea, ventana, permitir, permitir_comandos)
    if d["dentro"]:
        return {"respuesta": "s", **d}
    return {"respuesta": f"n {d['motivo']}", **d}


def _clasificar_evento(respuesta, motivo):
    if respuesta == "s":
        return "hitl"
    if motivo == "tope":
        return "hitl-tope"
    return "hitl-fuera"


def _turno(chat, permitir, permitir_comandos, max_hitl, deadline, evento):
    """Corre UN turno de la tarea: responde los HITL por scope hasta que el
    prompt `Tú:` vuelva (ok), el chat muera (muerto) o venza el plazo global.

    Devuelve (estado, hitl, rechazos, ventana). La ventana acumula la salida
    del turno entero: la extracción del comando mira varias líneas atrás del
    prompt, no solo el último chunk."""
    ventana = ""
    hitl = 0
    rechazos = 0
    while time.time() < deadline:
        chat.leer()
        if not chat.vivo:
            return "muerto", hitl, rechazos, ventana + chat.nuevo
        lineas = [ln for ln in limpiar(chat.nuevo).splitlines() if ln.strip()]
        if not lineas:
            time.sleep(0.2)
            continue
        ultima = lineas[-1]
        if RE_TU.search(ultima):
            return "ok", hitl, rechazos, ventana + chat.nuevo
        if not tipo_prompt(ultima):
            time.sleep(0.2)
            continue
        if hitl >= max_hitl:
            plan = {"respuesta": "n tope-de-aprobaciones", "tipo": tipo_prompt(ultima),
                    "objetivo": None, "motivo": "tope"}
        else:
            plan = plan_respuesta(ultima, limpiar(ventana + chat.nuevo),
                                  permitir, permitir_comandos)
        time.sleep(0.5)
        chat.enviar(plan["respuesta"])
        hitl += 1
        rechazos += plan["respuesta"] != "s"
        evento(_clasificar_evento(plan["respuesta"], plan["motivo"]),
               {"respuesta": plan["respuesta"], "tipo": plan["tipo"],
                "objetivo": plan["objetivo"], "motivo": plan["motivo"]})
        ventana += chat.nuevo
        chat.nuevo = ""
    return "timeout", hitl, rechazos, ventana + chat.nuevo


def _esperar_muerte(chat, segundos=20):
    """Espera a que el chat termine de cerrar (salida limpia: el reporte
    [tokens] y el resumen de sesión viajan al final del transcript)."""
    fin = time.time() + segundos
    while time.time() < fin and chat.vivo:
        chat.leer()
        time.sleep(0.1)
    return not chat.vivo


def _escribir_resumen(run, pedido, estado, hitl, rechazos, resumes, segundos):
    texto = (
        f"# Delegar — {run.name}\n\n"
        f"- pedido: {pedido}\n"
        f"- estado: {estado}\n"
        f"- duración: {segundos} s\n"
        f"- HITL respondidos: {hitl} ({rechazos} rechazados con motivo)\n"
        f"- reanudaciones: {resumes}\n\n"
        f"Transcript: `transcript.log` · eventos: `eventos.jsonl`\n"
    )
    (run / "resumen.md").write_text(texto, encoding="utf-8")


def conducir(pedido, dir_salida, permitir=None, permitir_comandos=None,
             timeout_min=30, max_hitl=12, extras=None, lanzar=None):
    """Delega el pedido y devuelve el exit code (0 = tarea completada).

    `lanzar` es inyectable para los tests (la máquina de estados sin PTY);
    en producción es el Chat real del banco."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run = Path(dir_salida) / stamp
    (run / "threads").mkdir(parents=True, exist_ok=True)
    # el pid hace consultable el estado de la corrida desde afuera (el
    # arranque del chat reporta "en curso" vs "murió sin resumen")
    (run / "conductor.pid").write_text(str(os.getpid()), encoding="utf-8")
    env = env_delegar(run / "threads", extras)
    crudo = run / "transcript.log"
    lanzador = lanzar or (lambda env, argv: Chat(env=env, argv=argv))
    t0 = time.time()
    total_hitl = total_rechazos = resumes = 0
    with (run / "eventos.jsonl").open("a", encoding="utf-8") as eventos:

        def evento(tipo, detalle=None):
            eventos.write(json.dumps({"ts": round(time.time(), 3), "tipo": tipo,
                                      "detalle": detalle}, ensure_ascii=False) + "\n")
            eventos.flush()

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
                evento("fin", {"estado": "sin-prompt"})
                chat.matar()
                _escribir_resumen(run, pedido, "sin-prompt", total_hitl,
                                  total_rechazos, resumes, round(time.time() - t0))
                return 1
            chat.nuevo = ""
            chat.enviar(linea)
            estado, hitl, rechazos, _ = _turno(chat, permitir, permitir_comandos,
                                               max_hitl, deadline, evento)
            total_hitl += hitl
            total_rechazos += rechazos
            if estado == "ok":
                chat.enviar("salir")
                _esperar_muerte(chat)
                evento("fin", {"estado": "ok"})
                chat.matar()
                _escribir_resumen(run, pedido, "ok", total_hitl, total_rechazos,
                                  resumes, round(time.time() - t0))
                return 0
            if estado != "muerto":  # timeout: interrupción limpia y fin
                chat.ctrl_c()
                _esperar_muerte(chat, 15)
                evento("fin", {"estado": "timeout"})
                chat.matar()
                _escribir_resumen(run, pedido, "timeout", total_hitl,
                                  total_rechazos, resumes, round(time.time() - t0))
                return 1
            chat.matar()
            id_thread = thread_reciente(run / "threads")
            if id_thread is None or resumes >= MAX_RESUMES:
                evento("fin", {"estado": "muerto-sin-resume", "id": id_thread})
                _escribir_resumen(run, pedido, "muerto-sin-resume", total_hitl,
                                  total_rechazos, resumes, round(time.time() - t0))
                return 1
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
                        help="prefijo de comandos aprobables (repetible; también habilita dobles)")
    parser.add_argument("--timeout-min", type=int, default=30, metavar="MIN",
                        help="plazo global en minutos, reanudaciones incluidas (default 30)")
    parser.add_argument("--max-hitl", type=int, default=12, metavar="N",
                        help="tope de aprobaciones por tarea (default 12)")
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
