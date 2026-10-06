"""Tracing: un evento jsonl por nodo ejecutado, en .runs/.

Patch mínimo en BaseNode._run/_run_async (lo único que todos los nodos
atraviesan, sync o async). Cada evento: nodo, acción devuelta, duración.
TRACE=0 lo apaga. Los archivos .runs/ son artefactos, van al .gitignore."""
import json
import time
from datetime import datetime
from pathlib import Path

_activo = False
_salida = None


def _escribir(dic):
    if _salida is None:
        return
    _salida.write(json.dumps(dic, ensure_ascii=False) + "\n")
    _salida.flush()


def evento_tool(nombre, ok, seg):
    """Evento de tool individual. Las tools que no son flujos (run_command,
    sql, write_file...) no atraviesan nodos: sin esto, un ExecuteTools de
    50s es inatribuible desde .runs (ciego medido en la auditoría)."""
    _escribir(
        {
            "ts": round(time.time(), 3),
            "nodo": nombre,
            "accion": "ok" if ok else "error",
            "seg": round(seg, 3),
        }
    )


def activar(ruta_base=None):
    global _activo, _salida
    if _activo or __import__("os").environ.get("TRACE", "1") == "0":
        return
    _activo = True

    import pocketflow

    directorio = Path(ruta_base or Path(__file__).resolve().parent.parent / ".runs")
    directorio.mkdir(exist_ok=True)
    archivo = directorio / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    # sumidero a vida de proceso: se escribe por evento y se cierra al salir
    _salida = open(archivo, "w", encoding="utf-8")  # noqa: SIM115

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
        accion = _run_original(self, shared)
        evento(self, accion, inicio)
        return accion

    pocketflow.BaseNode._run = _run_trazado

    # AsyncNode define _run_async; BaseNode no
    if hasattr(pocketflow, "AsyncNode"):
        _run_async_original = pocketflow.AsyncNode._run_async

        async def _run_async_trazado(self, shared):
            inicio = time.time()
            accion = await _run_async_original(self, shared)
            evento(self, accion, inicio)
            return accion

        pocketflow.AsyncNode._run_async = _run_async_trazado
    print(f"[trace] {archivo}", file=__import__("sys").stderr)
    return archivo
