"""Heartbeat: las piezas corriendo solas de noche, la salida lista a la
mañana.

Pieza standalone (como carga_trazas): lee `heartbeat.jsonl` si existe (una tarea
por línea), corre las que tienen el vencimiento cumplido con el supervisor
reactivo completo (Choose de Laya + self-healing) y deja:

- la salida de cada tarea donde la línea diga (`salida`),
- el estado de vencimientos en `.heartbeat/estado.json`,
- una línea por corrida en `.heartbeat/log.jsonl` (auditoría).

El reloj lo pone el cron del sistema — esta pieza solo decide qué toca:

    0 * * * * cd /ruta/a/deepseek-flow && timeout 3600 python3 heartbeat.py >> .heartbeat/cron.log 2>&1

Si no hay `heartbeat.jsonl` local usa `heartbeat.example.jsonl` (versionado,
sin rutas de una máquina puntual). Formato (una línea por tarea):

    {"tarea": "auditá las trazas nuevas de ~/datos", "salida": "heartbeat/auditoria.md", "cada_horas": 24}

Cada tarea es un supervisor reactivo (LLM). Una tarea con `"tipo"` es un
error de esa tarea, sin gastar llamadas: el único tipo, `triaje`, se fue en
X168 (el triaje de trazas es laboratorio: `python3 triaje_trazas.py`), y una
config vieja no puede caer callada al supervisor.

Leyes: cada corrida es un supervisor entero (MAX_PASOS=5, veto tras dos
fallos); `--ahora` fuerza todas (para probar); `--seco` solo lista qué
correría. Sin tareas vencidas no gasta una sola llamada.
"""
import argparse
import json
import time
from pathlib import Path

import supervisor
from utils.fs_tools import _resolve, escribir_atomico
from utils.tracing import activar

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
    # atómico: una corrida que muere a mitad no deja el estado truncado (el
    # próximo heartbeat leería un JSON roto y perdería los vencimientos)
    escribir_atomico(ESTADO, json.dumps(estado, ensure_ascii=False, indent=1))


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
    inicio = time.time()
    # X161 (C01): la salida pasa por la contención ANTES de tocar el disco
    # (antes un `mkdir` del destino corría primero). Fuera de las raíces es un
    # error de ESA tarea.
    destino, err = _resolve(str(RAIZ / tarea["salida"]))
    if destino is None:
        return {"ok": False, "error": err, "seg": 0.0}
    if "tipo" in tarea:
        return {"ok": False, "error": f"tipo {tarea['tipo']!r} desconocido (X168)", "seg": 0.0}
    try:
        informe = supervisor.supervisar(tarea["tarea"], str(destino))
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
    # config local si existe; si no, el ejemplo versionado (PR 5 del plan de
    # orden: el heartbeat.jsonl del autor no viaja en el repo)
    config = RAIZ / "heartbeat.jsonl"
    parser.add_argument("--config",
                        default=str(config if config.is_file() else RAIZ / "heartbeat.example.jsonl"))
    parser.add_argument("--ahora", action="store_true", help="correr todas sin esperar vencimiento")
    parser.add_argument("--seco", action="store_true", help="solo listar qué correría")
    args = parser.parse_args(argv)

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
