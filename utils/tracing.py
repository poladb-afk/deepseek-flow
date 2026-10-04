"""Tracing: un evento jsonl por nodo ejecutado, en .runs/.

Patch mínimo en BaseNode._run/_run_async (lo único que todos los nodos
atraviesan, sync o async). Cada evento: nodo, acción devuelta, duración.
TRACE=0 lo apaga. Los archivos .runs/ son artefactos, van al .gitignore."""
import json
import time
from datetime import datetime
from pathlib import Path

_activo = False


def activar(ruta_base=None):
    global _activo
    if _activo or __import__("os").environ.get("TRACE", "1") == "0":
        return
    _activo = True

    import pocketflow

    directorio = Path(ruta_base or Path(__file__).resolve().parent.parent / ".runs")
    directorio.mkdir(exist_ok=True)
    archivo = directorio / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    salida = open(archivo, "w", encoding="utf-8")

    def evento(nodo, accion, inicio):
        salida.write(
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "nodo": type(nodo).__name__,
                    "accion": str(accion),
                    "seg": round(time.time() - inicio, 3),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        salida.flush()

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
