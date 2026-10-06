"""Heartbeat: las piezas corriendo solas de noche, la salida lista a la
mañana.

Pieza standalone (como carga_trazas): lee `heartbeat.jsonl` (una tarea
por línea), corre las que tienen el vencimiento cumplido con el supervisor
reactivo completo (Choose de Laya + self-healing) y deja:

- la salida de cada tarea donde la línea diga (`salida`),
- el estado de vencimientos en `.heartbeat/estado.json`,
- una línea por corrida en `.heartbeat/log.jsonl` (auditoría).

El reloj lo pone el cron del sistema — esta pieza solo decide qué toca:

    0 * * * * cd /ruta/a/deepseek-flow && timeout 3600 python3 heartbeat.py >> .heartbeat/cron.log 2>&1

Formato de heartbeat.jsonl (una línea por tarea):

    {"tarea": "auditá las trazas nuevas de ~/datos", "salida": "heartbeat/auditoria.md", "cada_horas": 24}

Leyes: cada corrida es un supervisor entero (MAX_PASOS=5, veto tras dos
fallos); `--ahora` fuerza todas (para probar); `--seco` solo lista qué
correría. Sin tareas vencidas no gasta una sola llamada.
"""
import argparse
import json
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ESTADO = RAIZ / ".heartbeat" / "estado.json"
LOG = RAIZ / ".heartbeat" / "log.jsonl"
MAX_TAREAS_POR_CORRIDA = 10  # L8: aunque el jsonl crezca, la noche es finita


def cargar_estado():
    if ESTADO.is_file():
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    return {}


def guardar_estado(estado):
    ESTADO.parent.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")


def vencidas(tareas, estado, ahora=None):
    ahora = ahora or time.time()
    out = []
    for t in tareas:
        clave = f"{t['salida']}"
        ultima = estado.get(clave, 0)
        if ahora - ultima >= t.get("cada_horas", 24) * 3600:
            out.append(t)
    return out[:MAX_TAREAS_POR_CORRIDA]


def correr(tarea):
    from supervisor import supervisar

    destino = RAIZ / tarea["salida"]
    destino.parent.mkdir(parents=True, exist_ok=True)  # Sintetizar escribe directo
    inicio = time.time()
    try:
        informe = supervisar(tarea["tarea"], str(destino))
        return {"ok": True, "informe": informe, "seg": round(time.time() - inicio, 1)}
    except Exception as e:  # noqa: BLE001  (la corrida nocturna no muere por una tarea)
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "seg": round(time.time() - inicio, 1)}


def registrar(tarea, resultado):
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(
            {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tarea": tarea["tarea"], **resultado},
            ensure_ascii=False,
        ) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="heartbeat", description="Piezas programadas, listas a la mañana")
    parser.add_argument("--config", default=str(RAIZ / "heartbeat.jsonl"))
    parser.add_argument("--ahora", action="store_true", help="correr todas sin esperar vencimiento")
    parser.add_argument("--seco", action="store_true", help="solo listar qué correría")
    args = parser.parse_args(argv)

    from utils.tracing import activar

    activar()
    tareas = [json.loads(linea) for linea in Path(args.config).read_text(encoding="utf-8").splitlines() if linea.strip()]
    estado = cargar_estado()
    pendientes = tareas if args.ahora else vencidas(tareas, estado)
    if args.seco or not pendientes:
        proxima = "todo ya corrió dentro de su ventana" if not args.seco else ""
        print(f"{len(pendientes) or 0} tareas para correr. {proxima}")
        for t in pendientes:
            print(f"  · [{t.get('cada_horas', 24)}h] {t['tarea'][:70]} → {t['salida']}")
        return
    print(f"{len(pendientes)} tareas vencidas:")
    for t in pendientes:
        print(f"▶ {t['tarea'][:70]}")
        resultado = correr(t)
        registrar(t, resultado)
        print(f"  {'✅' if resultado['ok'] else '✗'} {resultado['seg']}s · {resultado.get('informe') or resultado.get('error')}")
        if resultado["ok"]:
            estado[t["salida"]] = time.time()
            guardar_estado(estado)


if __name__ == "__main__":
    main()
