"""Juez en lote: verificación EN PARALELO de varias preguntas con citas.

Patrón parallel del cookbook de PocketFlow (AsyncParallelBatchFlow): el
fan-out del WORKFLOW, distinto del fan-out de un solo nodo. Cada pregunta
corre el flujo del juez EXISTENTE (juez.create_juez_flow) — no se duplica la
lógica Draft→Judge→retry.

Por qué async y no un BatchNode paralelo: la carga es I/O-bound (llamadas
LLM), donde el paralelismo SÍ aporta. La sincronía del flujo del juez no se
puede esperar dentro de un bucle de eventos ya corriendo (deadlock), así que
se cruza el puente con asyncio.to_thread (el shim mínimo): cada corrida pasa
la mayor parte del tiempo esperando la red y las corridas se solapan. Cada
tarea lleva su ÍNDICE, de modo que el informe queda en el orden del archivo
(no en orden de terminación, que con concurrencia es indeterminado).

Medición (patrón parallel del cookbook): cada corrida registra su duración;
la suma de los tiempos individuales representa el costo secuencial y se
compara con el reloj de pared total → speedup medido.

Estructura: UN AsyncParallelBatchFlow explícito
- prep_async devuelve la lista de trabajos (una pregunta cada uno);
- CorrerJuez (AsyncNode) es la rama que corre el flujo sync del juez;
- post_async (AsyncFlow) recolecta y escribe el informe UNO SOLO con la
  medición al pie — el BatchFlow ES el flujo, no un pipeline de nodos aparte
  (con AsyncParallelBatchFlow no hay reduce como nodo separado).

Uso:
    python3 main.py juez_lote preguntas.txt [--salida salidas/juez_lote.md]
"""
import argparse
import asyncio
import time
from datetime import date
from pathlib import Path

from pocketflow import AsyncNode, AsyncParallelBatchFlow

from juez import create_juez_flow
from utils.call_llm import _setting
from utils.fs_tools import _resolve

DEFAULT_SALIDA = "salidas/juez_lote.md"
# Semáforo anti-429 entre preguntas (mismo criterio que informe.py): no
# limita el paralelismo de las corridas, solo cuántas llamadas LLM se solapan.
JUEZ_LOTE_CONCURRENCIA = int(_setting("JUEZ_LOTE_CONCURRENCIA", "8"))


def leer_preguntas(path):
    """Una pregunta por línea no vacía (se recorta espacios; se saltan las
    líneas que arrancan con '#' para poder comentar un lote)."""
    lineas = Path(path).read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lineas if ln.strip() and not ln.strip().startswith("#")]


def resolver_archivo(raw):
    """Resuelve la ruta del archivo de preguntas dentro de las raíces
    permitidas. Devuelve (Path, error); el error es texto para el modelo."""
    resolved, err = _resolve(raw)
    if err:
        return None, err
    if not resolved.is_file():
        return None, f"no existe el archivo de preguntas: {resolved}"
    return resolved, None


class CorrerJuez(AsyncNode):
    """Rama del BatchFlow: una pregunta → el flujo sync del juez, sin duplicarlo.

    El shim mínimo es asyncio.to_thread: el flujo del juez es síncrono (bloquea
    en call_llm) y no se puede esperar dentro del bucle de eventos ya corriendo;
    en un hilo no bloquea y N preguntas se verifican de verdad en paralelo.
    Devuelve un dict de tipos simples (nada de shared compartido entre ramas)."""

    def __init__(self, semaforo, **kw):
        super().__init__(**kw)
        self.semaforo = semaforo

    async def prep_async(self, shared):
        # bp (el dict del job) llega por params, no por shared: cada rama
        # recibe {**self.params, **bp} — acá está la pregunta.
        return self.params.get("pregunta", "")

    async def exec_async(self, pregunta):
        async with self.semaforo:

            def _correr():
                shared = {"question": pregunta}
                t0 = time.perf_counter()
                try:
                    create_juez_flow().run(shared)
                except Exception as e:  # noqa: BLE001  (medido en vivo: el fallo
                    # persistente de UNA pregunta —p. ej. verdict inválido tras
                    # los retries del juez— no puede matar el lote y perder el
                    # trabajo ya ganado de las demás)
                    return {
                        "pregunta": pregunta,
                        "error": f"{type(e).__name__}: {e}",
                        "rounds": shared.get("rounds", 0),
                        "segundos": time.perf_counter() - t0,
                    }
                return {
                    "pregunta": pregunta,
                    "respuesta": shared.get("draft"),
                    "advertencia": shared.get("advertencia"),
                    "rounds": shared.get("rounds", 0),
                    "segundos": time.perf_counter() - t0,
                }

            return await asyncio.to_thread(_correr)

    async def post_async(self, shared, prep_res, exec_res):
        exec_res["indice"] = self.params.get("indice", 0)
        shared["resultados"].append(exec_res)
        marca = "✗" if exec_res.get("error") else "✓"
        print(f"  {marca} P{exec_res['indice'] + 1} ({exec_res['segundos']:.2f}s, "
              f"{exec_res['rounds']} rondas)")


class JuezLoteFlow(AsyncParallelBatchFlow):
    """AsyncParallelBatchFlow: un job por pregunta, ramas en asyncio.gather,
    y el informe se escribe en el post del propio batch flow."""

    def __init__(self, salida=DEFAULT_SALIDA, semaforo=None):
        super().__init__(start=CorrerJuez(semaforo or asyncio.Semaphore(JUEZ_LOTE_CONCURRENCIA)))
        self.salida = Path(salida)
        # t0 lo pone prep_async (una vez, antes del fan-out): así _seg_par es
        # el reloj de pared real de TODO el lote.
        self._t0 = None
        self._seg_par = 0.0

    async def prep_async(self, shared):
        self._t0 = time.perf_counter()
        return [
            {"pregunta": q, "indice": i}
            for i, q in enumerate(shared["preguntas"])
        ]

    def _markdown(self, shared):
        resultados = shared.get("resultados", [])
        pasos = sorted(resultados, key=lambda r: r.get("indice", 0))
        n = len(pasos)
        # suma de tiempos individuales = costo si se hubieran verificado en
        # serie; el reloj de pared real = costo paralelo. Speedup medido.
        suma = sum(r["segundos"] for r in pasos)
        speedup = (suma / self._seg_par) if self._seg_par > 0 else float("inf")

        secciones = []
        fallidas = 0
        for i, r in enumerate(pasos):
            if r.get("error"):
                fallidas += 1
                secciones.append(f"""## P{i + 1}. {r.get('pregunta', '')}

**❌ Falló** (el juez no la pudo verificar):

> {r['error']}

- Rondas: {r.get('rounds', 0)} · Duración: {r.get('segundos', 0.0):.2f}s
""")
                continue
            adv = (
                f"\n\n> ⚠️  {r['advertencia']}"
                if r.get("advertencia") else ""
            )
            secciones.append(f"""## P{i + 1}. {r.get('pregunta', '')}

**Respuesta:**

{r.get('respuesta') or '_(sin respuesta)_'}{adv}

- Rondas: {r.get('rounds', 0)} · Duración: {r.get('segundos', 0.0):.2f}s
""")
        aviso_lote = (f"\n\n> ⚠️  {fallidas} de {n} preguntas fallaron y quedaron "
                      "sin verificar (el resto del lote se conserva)." if fallidas else "")

        tabla = "\n".join(
            f"| P{i + 1} | {r.get('rounds', 0)} | {r['segundos']:.2f}s |"
            for i, r in enumerate(pasos)
        ) or "| — | — | — |"

        return f"""# Juez en lote — {date.today().isoformat()}

{date.today().isoformat()} · {n} preguntas verificadas en paralelo
(AsyncParallelBatchFlow){aviso_lote}

## Medición

| Métrica | Valor |
|---|---|
| Preguntas | {n} |
| Suma de tiempos individuales (secuencial) | {suma:.2f}s |
| Tiempo de pared (paralelo) | {self._seg_par:.2f}s |
| **Speedup medido** | **{speedup:.2f}×** |

La suma de los tiempos individuales es el costo si cada pregunta se hubiera
verificado en serie (una tras otra); el tiempo de pared es el reloj total del
lote paralelo. `speedup = suma / pared` (>1 acelera; con una sola pregunta es
~1, porque no hay nada que solapar).

## Detalle por pregunta

| Pregunta | Rondas | Duración |
|---|---|---|
{tabla}

## Resultados

{chr(10).join(secciones)}
"""

    async def post_async(self, shared, prep_res, exec_res):
        self._seg_par = time.perf_counter() - self._t0
        path = self.salida
        path.parent.mkdir(parents=True, exist_ok=True)
        texto = self._markdown(shared)
        path.write_text(texto, encoding="utf-8")
        resultados = shared.get("resultados", [])
        n = len(resultados)
        fallidas = sum(1 for r in resultados if r.get("error"))
        suma = sum(r["segundos"] for r in resultados)
        shared["informe"] = str(path.resolve())
        shared["metricas"] = {"n": n, "fallidas": fallidas,
                              "seg_secuencial": suma, "seg_paralelo": self._seg_par}
        print(f"\nInforme: {path.resolve()} ({n} preguntas, "
              f"{suma:.2f}s secuencial → {self._seg_par:.2f}s paralelo)")
        return exec_res


def create_juez_lote_flow(salida=DEFAULT_SALIDA, semaforo=None):
    return JuezLoteFlow(salida=salida, semaforo=semaforo)


def run_juez_lote(ruta_preguntas, salida=DEFAULT_SALIDA):
    """Corre el lote y devuelve un resumen de texto (para el chat)."""
    preguntas = leer_preguntas(ruta_preguntas)
    if not preguntas:
        return f"ERROR: el archivo no tiene preguntas: {ruta_preguntas}"
    shared = {"preguntas": preguntas, "resultados": []}
    asyncio.run(create_juez_lote_flow(salida=salida).run_async(shared))
    m = shared["metricas"]
    detalle = f", {m['fallidas']} fallidas" if m.get("fallidas") else ""
    return (
        f"Juez en lote: {m['n']} preguntas verificadas en paralelo{detalle} "
        f"({m['seg_secuencial']:.2f}s secuencial → {m['seg_paralelo']:.2f}s "
        f"paralelo). Informe: {shared['informe']}"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="juez_lote",
        description="Verificación en paralelo de varias preguntas con el juez existente",
    )
    parser.add_argument("preguntas", help="archivo con una pregunta por línea no vacía")
    parser.add_argument("--salida", default=DEFAULT_SALIDA, help="markdown de salida (default: %(default)s)")
    args = parser.parse_args(argv)

    ruta, err = resolver_archivo(args.preguntas)
    if err:
        raise SystemExit(f"ERROR: {err}")
    print(run_juez_lote(ruta, args.salida))


if __name__ == "__main__":
    main()