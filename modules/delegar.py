"""Módulo `delegar`: la tool que lanza el conductor desde el chat.

El operador vive en el chat (exp/100): la delegación arranca DURANTE el chat
y su resultado se reporta AL ARRANCAR el próximo. El conductor sigue siendo
un proceso aparte — el que aprueba los HITL de la tarea no puede ser el chat
que los pide — pero la puerta es esta tool: UNA aprobación del operador con
el pedido y el scope a la vista (el operador es el veto del scope que el
modelo propuso), y el resto lo maneja el scope. El import de la pieza es
perezoso (el top-level corre discover() al cargarse)."""
import contextlib
import os
import subprocess
import sys
from pathlib import Path

from utils.aprobaciones import Pedido, pedir_aprobacion

RAIZ = Path(__file__).resolve().parent.parent

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "delegar_tarea",
            "description": (
                "Lanza el conductor: delega una tarea al harness en background "
                "(proceso aparte que sobrevive al cierre del chat) con HITL "
                "resuelto por scope. Usalo cuando el usuario pida dejar una tarea "
                "trabajando sola ('delegá esto', 'hacelo mientras no estoy', "
                "'dejalo corriendo'). Vos proponés el scope; el usuario lo aprueba "
                "o rechaza en el momento del lanzamiento. El resultado queda en el "
                "resumen.md de la corrida (salidas/delegar/) y el próximo arranque "
                "del chat lo reporta. No sirve para tareas interactivas: nadie va a "
                "contestar preguntas durante la corrida, acotá el pedido."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pedido": {
                        "type": "string",
                        "description": "la tarea completa, en una línea (puntos y coma si hace falta)",
                    },
                    "permitir": {
                        "type": "string",
                        "description": "rutas aprobables para escrituras, separadas por coma (ej.: '/repo/docs, /repo/salidas'); vacío = solo la denylist dura",
                    },
                    "permitir_comandos": {
                        "type": "string",
                        "description": "prefijos de comandos aprobables, separados por coma (cada segmento del comando debe empezar con uno); vacío = ningún comando que pida aprobación se aprueba (los de solo-lectura corren igual); git push y rm -rf nunca",
                    },
                    "timeout_min": {
                        "type": "integer",
                        "description": "plazo global en minutos (default 30)",
                    },
                },
                "required": ["pedido"],
            },
        },
    },
]


def _lista(texto):
    """'a, b' → ['a', 'b']; None/vacío → None (conductor en su default)."""
    if not texto or not str(texto).strip():
        return None
    return [parte.strip() for parte in str(texto).split(",") if parte.strip()]


def _minutos_validos(timeout_min):
    try:
        minutos = int(timeout_min)
    except (TypeError, ValueError):
        return None
    return minutos if minutos >= 1 else None


def delegar_tarea(pedido, permitir=None, permitir_comandos=None, timeout_min=30):
    if not pedido or not str(pedido).strip():
        return "ERROR: el pedido está vacío"
    pedido = " ".join(str(pedido).split())  # una sola línea, como el CLI
    minutos = _minutos_validos(timeout_min)
    if minutos is None:
        return "ERROR: timeout_min debe ser un entero de minutos >= 1"
    rutas = _lista(permitir)
    comandos = _lista(permitir_comandos)
    scope = ", ".join(rutas) if rutas else "solo denylist dura"
    scope_cmd = ", ".join(comandos) if comandos else "ninguno (solo los de solo-lectura, que no piden aprobación)"
    # el patrón de run_command: el operador ve TODO antes del s/n (el cuerpo
    # imprime acá para la terminal y viaja entero al HITL web)
    cuerpo = (f"lanzamiento del conductor\n\npedido: {pedido}\n"
              f"escrituras permitidas: {scope}\ncomandos permitidos: {scope_cmd}\n"
              f"plazo: {minutos} min\n\n"
              "El conductor contesta solo los HITL dentro de este scope "
              "(proceso aparte); la tarea sigue aunque cierres el chat.")
    print(f"\n── delegar_tarea ──\n{cuerpo}")
    decision = pedir_aprobacion(Pedido(f"¿Delegar en background? (scope: {scope})",
                                       cuerpo, "delegar", pedido))
    if not decision:
        motivo = getattr(decision, "motivo", "")
        detalle = f' Motivo del usuario: "{motivo}".' if motivo else ""
        return f"RECHAZADO por el usuario:{detalle} La tarea no se lanzó."
    argv = [sys.executable, "main.py", "delegar", pedido]
    for ruta in rutas or []:
        argv += ["--permitir", ruta]
    for prefijo in comandos or []:
        argv += ["--permitir-comandos", prefijo]
    argv += ["--timeout-min", str(minutos)]
    subprocess.Popen(argv, cwd=RAIZ, env=dict(os.environ), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return ("tarea delegada al conductor (proceso aparte: sigue aunque se cierre "
            "el chat). Para ver cómo sigue: listá salidas/delegar/ y leé el "
            "resumen.md de la corrida más nueva (o sus eventos.jsonl); el próximo "
            "arranque del chat lo reporta solo.")


IMPL = {"delegar_tarea": delegar_tarea}


def estado_delegadas(_shared=None):
    """exp/100: el resultado de lo delegado aparece AL ARRANCAR el chat (el
    operador vive acá; si no se reporta, es como si no hubiera pasado).
    Best-effort: sin corridas no imprime nada y un fallo jamás corta el
    arranque. Import perezoso: el conductor arrastra el driver PTY."""
    with contextlib.suppress(Exception):  # noqa: BLE001 (reportar nunca corta el arranque)
        from delegar import panorama_delegadas

        lineas = panorama_delegadas()
        if lineas:
            print(f"\n[delegar] últimas tareas delegadas: {len(lineas)}")
            for linea in lineas:
                print(f"  - {linea}")


def aviso_delegadas_al_cerrar(_shared=None):
    """exp/100: si hay delegadas corriendo, el cierre las nombra — siguen en
    background (el conductor corre detached) y el resultado se reporta al
    próximo arranque. Sin activas, silencio."""
    with contextlib.suppress(Exception):  # noqa: BLE001 (aviso de cierre best-effort)
        from delegar import corridas_activas

        activas = corridas_activas()
        if activas:
            nombres = ", ".join(c.name for c in activas)
            print(f"[delegar] {len(activas)} tarea(s) delegadas siguen corriendo "
                  f"({nombres}) — el resultado se reporta al próximo arranque")


HOOKS = {"al_arrancar": estado_delegadas, "al_salir": aviso_delegadas_al_cerrar}
