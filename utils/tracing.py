"""Tracing: un evento jsonl por nodo ejecutado, en .runs/.

Patch mínimo en BaseNode._run/_run_async (lo único que todos los nodos
atraviesan, sync o async). Cada evento: nodo, acción devuelta, duración.
TRACE=0 lo apaga. Los archivos .runs/ son artefactos, van al .gitignore."""
import atexit
import json
import os
import time
from datetime import datetime
from pathlib import Path

_activo = False
_salida = None
_ruta_salida = None  # archivo planeado: se abre recién al primer evento
_id_thread = None


def _escribir(dic):
    global _salida
    if _salida is None:
        if not (_activo and _ruta_salida):
            return
        # apertura PEREZOSA: una corrida sin eventos (CLI que termina, tests)
        # no deja un .jsonl vacío (F4: 41/255 trazas vacías).
        _salida = open(_ruta_salida, "w", encoding="utf-8")  # noqa: SIM115
        atexit.register(_salida.close)
        print(f"[trace] {_ruta_salida}", file=__import__("sys").stderr)
    _salida.write(json.dumps(dic, ensure_ascii=False) + "\n")
    _salida.flush()


def evento_tool(nombre, ok, seg, codigo=None):
    """Evento de tool individual. Las tools que no son flujos (run_command,
    sql, write_file...) no atraviesan nodos: sin esto, un ExecuteTools de
    50s es inatribuible desde .runs (ciego medido en la auditoría).

    `codigo` es un discriminador CORTO y sin contenido (p. ej. `ERROR:TypeError`,
    `RECHAZADO`, `exit_1`): permite agrupar causas sin guardar texto del error
    (F4: la traza no podía atribuir causas). CONTRATO SOCIAL: lo arma el
    llamador; tracing NO valida que sea corto ni que no traiga contenido."""
    evento = {
        "ts": round(time.time(), 3),
        "nodo": nombre,
        "accion": "ok" if ok else "error",
        "seg": round(seg, 3),
    }
    if codigo:
        evento["codigo"] = codigo
    _escribir(evento)


def evento_hitl(tipo, nivel, decision, seg=0.0):
    """Decisión HITL compacta (SIN contenido): tipo, nivel y decisión.
    `seg` es opcional y hoy el chat pasa 0 (no mide latencia HITL): el campo
    existe por compatibilidad con el esquema de traza, NO como medición.
    Da tasa de fricción/rechazo medible sin persistir lo que se aprobó (F4)."""
    _escribir(
        {
            "ts": round(time.time(), 3),
            "nodo": f"hitl_{tipo}",
            "accion": "aprobado" if decision else "rechazado",
            "seg": round(seg, 3),
            "nivel": str(nivel),
        }
    )


def evento_politica(nombre, detalle=""):
    """Evento de POLÍTICA del loop (no es una tool ejecutada): accion propia
    para que el tablero/minería no lo cuenten como un éxito de tool. Medido en
    vivo: el corte por no-progreso se registraba como ok y sumaba un éxito
    fantasma (auditoría de sesión real). Nota de esquema: `nodo` es la clave
    genérica de la traza (acá lleva el nombre de la política) y `seg=0` porque
    no hay duración de tool que medir."""
    _escribir(
        {
            "ts": round(time.time(), 3),
            "nodo": str(nombre),
            "accion": "politica",
            "seg": 0.0,
            **({"detalle": str(detalle)} if detalle else {}),
        }
    )


def thread_id():
    """El id del thread del proceso (exp/48): idempotente — se resuelve UNA vez.

    Si el tracing ya está activo, reusa el MISMO stem del archivo de `.runs`
    (el thread y su trace quedan correlacionados por nombre). Si no, cae al
    MISMO FORMATO `f"{datetime:%Y%m%d_%H%M%S}_{pid}"` que usa `activar`, pero
    NO al mismo valor: el timestamp se toma en esta llamada y `activar()`
    resetea el id al planificar su archivo. Llamá `activar()` antes si
    necesitás que thread_id coincida con el stem del trace."""
    global _id_thread
    if _id_thread is not None:
        return _id_thread
    if _salida is not None and getattr(_salida, "name", None):
        _id_thread = Path(_salida.name).stem
    elif _ruta_salida is not None:
        _id_thread = Path(_ruta_salida).stem
    else:
        _id_thread = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    return _id_thread


def activar(ruta_base=None):
    global _activo, _ruta_salida, _id_thread
    if _activo or __import__("os").environ.get("TRACE", "1") == "0":
        return
    _activo = True
    _id_thread = None  # el stem se resuelve del archivo PLANEADO

    import pocketflow

    directorio = Path(ruta_base or Path(__file__).resolve().parent.parent / ".runs")
    directorio.mkdir(exist_ok=True)
    # el pid evita la colisión medida: dos procesos en el mismo segundo
    # abrían el MISMO archivo con "w" y se truncaban entre sí
    archivo = directorio / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}.jsonl"
    # NO se abre todavía: _escribir lo hace al primer evento (evita vacías).
    _ruta_salida = archivo

    def evento(nodo, accion, inicio):
        _escribir(
            {
                "ts": round(time.time(), 3),
                "nodo": type(nodo).__name__,
                "accion": str(accion),
                "seg": round(time.time() - inicio, 3),
            }
        )

    _run_original = pocketflow.BaseNode._run

    def _run_trazado(self, shared):
        inicio = time.time()
        try:
            accion = _run_original(self, shared)
        except BaseException as e:
            # Un nodo que lanza TAMBIÉN deja evento: sin esto la traza miente
            # por omisión (medido: 0 eventos del nodo fallido) y ningún "cero
            # excepciones" posterior es falsable. La excepción se propaga.
            evento(self, f"error:{type(e).__name__}", inicio)
            raise
        evento(self, accion, inicio)
        return accion

    pocketflow.BaseNode._run = _run_trazado

    # AsyncNode define _run_async; BaseNode no
    if hasattr(pocketflow, "AsyncNode"):
        _run_async_original = pocketflow.AsyncNode._run_async

        async def _run_async_trazado(self, shared):
            inicio = time.time()
            try:
                accion = await _run_async_original(self, shared)
            except BaseException as e:
                evento(self, f"error:{type(e).__name__}", inicio)
                raise
            evento(self, accion, inicio)
            return accion

        pocketflow.AsyncNode._run_async = _run_async_trazado
    return archivo
