"""Subcomando `resume <id>`: rehidrata un thread del chat desde su checkpoint.

El gap nº1 del 12-factor (exp/48): `shared` muere con el proceso. Acá se
recupera el último checkpoint de una corrida y se arranca el MISMO flujo del
chat con ese `shared` — el historial restaurado viaja entero y el usuario
continúa conversando (el protocolo de continuación de exp/4: un mensaje nuevo
del usuario reinicia el presupuesto).

Lado seguro: un thread que NO pasa el validador de invariantes (utils.thread_store
→ utils.compaccion.validar_historial) no se rehidrata — el modo thinking pegajoso
rompería a la primera llamada, así que se avisa y se sale sin arrancar."""

import sys

from flow import create_agent_flow
from utils.estado_sesion import restaurar
from utils.thread_store import cargar, cargar_sesion, reparar_pendientes, valido

# Claves sueltas de la pregunta en curso, antes de la caja `turno` (H2 PR 4a):
# un checkpoint viejo las trae así y se migran al rehidratar.
CLAVES_VIEJAS = {"tool_rounds": "rondas", "no_progress": "sin_progreso", "_fp": "huella",
                 "_huellas_vistas": "huellas_vistas", "_racha_sin_novedad": "racha_sin_novedad",
                 "_corte_novedad": "corte_novedad", "_aviso_cierre": "aviso_cierre",
                 "_skill_activo": "skill", "_router_pendiente": "router_pendiente",
                 "_uso_inicio_pregunta": "uso_inicio"}


def migrar(shared):
    """El shared de un checkpoint anterior a la caja `turno`, con su caja.
    PURA sobre el dict; idempotente."""
    from nodes import nuevo_turno

    viejas = {nueva: shared.pop(vieja) for vieja, nueva in CLAVES_VIEJAS.items() if vieja in shared}
    if "turno" not in shared:
        shared["turno"] = {**nuevo_turno(), **viejas}
    return shared


def _banner(id_thread, shared, reparadas=0):
    mensajes = shared.get("messages", [])
    rondas = (shared.get("turno") or {}).get("rondas", 0)
    extra = f" · {reparadas} llamada(s) interrumpida(s) reparadas" if reparadas else ""
    print(
        f"[thread] id {id_thread} · {len(mensajes)} mensajes restaurados · "
        f"{rondas} rondas de tools · rehidratado OK · validador: 0 violaciones"
        f"{extra}"
    )


def main(args):
    if not args:
        print("uso: python3 main.py resume <id>", file=sys.stderr)
        return 1
    id_thread = args[0]
    shared = cargar(id_thread)
    if shared is None:
        print(
            f"[thread] no hay checkpoint legible para '{id_thread}' "
            f"(no existe o no tiene ninguna línea válida). Nada que reanudar.",
            file=sys.stderr,
        )
        return 1
    # exp/49: si el proceso murió entre la SELECCIÓN y la EJECUCIÓN de las
    # tools, el último assistant tiene tool_calls huérfanos. Se reparan ANTES
    # de validar (el mensaje honesto los hace válidos) y el banner lo dice.
    migrar(shared)
    restaurar(cargar_sesion(id_thread))  # costo, aprobaciones e intención (F5)
    reparadas = reparar_pendientes(shared)
    violaciones = valido(shared)
    if violaciones:
        print(
            f"[thread] '{id_thread}' NO se rehidrata: el historial viola "
            f"{len(violaciones)} invariante(s) del modo thinking:",
            file=sys.stderr,
        )
        for v in violaciones:
            print(f"  - {v}", file=sys.stderr)
        return 1
    # Los faltantes se completan con setdefault, igual que main al sembrar el
    # shared: un checkpoint viejo (o parcial) no rompe el arranque.
    from main import system_prompt

    shared.setdefault("messages", [{"role": "system", "content": system_prompt()}])
    _banner(id_thread, shared, reparadas)
    try:
        create_agent_flow().run(shared)
    except KeyboardInterrupt:
        print("\n¡Chao! 👋")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
