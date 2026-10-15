# exp/48 — Persistencia/resume de corridas: el thread serializable (factor 6)

Gap nº1 del análisis 12-factor (`salidas/informe_12factor_2026-10-14.md`):
`shared` muere con el proceso — un flujo largo interrumpido pierde todo el
trabajo. Este experimento lo cierra para el CHAT (v1): checkpoints
incrementales a disco y un `resume` que rehidrata. Los factores 5/7/8/12
desbloquean después sobre esta base.

## 1. `utils/thread_store.py` — NUEVO (funciones PURAS, sin LLM)

- `THREADS_DIR` = setting `THREADS_DIR` (default `salidas/threads`).
- `checkpoint(id_thread, nodo, accion, shared, ruta_dir=None)`: appendea a
  `<ruta_dir>/<id_thread>.jsonl` UNA línea
  `{"ts", "evento": "checkpoint", "nodo", "accion", "shared": <shared completo>}`.
  Bookkeeping de la casa: cualquier fallo se traga, nunca rompe el chat.
  Setting `THREAD_PERSIST` (default "1"); "0" apaga TODO (ni crea dir).
- `cargar(id_thread, ruta_dir=None)`: lee la ÚLTIMA LÍNEA COMPLETA del
  archivo (tolerante a cola cortada a mitad por un crash: las líneas
  parciales se descartan — el JSON que no parsea se salta desde el final).
  Devuelve el `shared` (dict) o None si no existe/no hay línea válida.
- `valido(shared)`: el shared cargado pasa `utils.compaccion.validar_historial`
  (los 4 invariantes del modo thinking ya tienen validador y tests).
  Devuelve la lista de violaciones (vacía = válido) — NUNCA levanta.

## 2. `nodes.py` — los puntos seguros (mismos sitios que el trace)

Tres checkpoints por ciclo, pegados a donde ya se instrumenta la traza
(grep `evento`/`evento_tool` en nodes.py para encontrar los sitos exactos):

1. `GetQuestion.post` — después de agregar el mensaje user (la pregunta
   quedó registrada).
2. `ExecuteTools.post` — al final (la ronda de tools quedó registrada).
3. `AgentStep.post` camino "answer" — antes de devolver (la respuesta quedó).

El `id_thread` del proceso: se toma UNA vez por corrida (mismo stem que el
trace de `.runs` si el tracing ya lo expone — mirar utils/tracing; si no,
`f"{datetime:%Y%m%d_%H%M%S}_{pid}"`). Un módulo-level `thread_id()` en
utils/tracing o thread_store (idempotente por proceso).

## 3. `main.py` — `resume`

- Subcomando `python3 main.py resume <id>`: `shared = cargar(id)`;
  si None → error claro y exit 1; si `valido(shared)` da violaciones →
  aviso y NO arranca (lado seguro: un thread inválido no se rehidrata,
  el modo thinking rompería a la primera llamada). Arranca el MISMO flujo
  del chat con ese shared (los faltantes se completan con setdefault como
  hace hoy main al sembrarlo) — el historial restaurado viaja entero y el
  usuario continúa conversando (el protocolo de continuación existe: un
  mensaje nuevo reinicia presupuesto).
- El banner de resume imprime: id, nº de mensajes restaurados, rondas de
  tools del estado, y "[thread] rehidratado OK · validador: 0 violaciones".

## 4. Tests (`tests/test_thread_store.py` NUEVO, sin LLM)

1. Roundtrip: checkpoint×2 (shared con messages, tool_rounds, no_progress)
   → cargar devuelve el ÚLTIMO (segundo), igualdad canónica.
2. Cola cortada: archivo con última línea a medias (sin \n final o JSON
   roto) → cargar devuelve el anterior completo, sin excepción.
3. `THREAD_PERSIST=0` → checkpoint no escribe (ni crea el directorio).
4. `cargar` de id inexistente → None. Fallo de escritura (dir de solo
   lectura) → no levanta (bookkeeping).
5. `valido`: un shared con historial agéntico válido → 0 violaciones; uno
   con assistant sin sus tools → violación detectada (el validador ya
   existe: reuso, no reimplementación).
6. Los tres puntos seguros: con fakes, GetQuestion.post / ExecuteTools.post
   / AgentStep.post(answer) escriben checkpoint (contador de líneas).

## 5. `.env.example`

Bloque: THREAD_PERSIST (default 1; 0 apaga), THREADS_DIR (default
salidas/threads, gitignored). Dos líneas de qué es: el thread completo en
disco por corrida — privacy igual que preguntas.jsonl/routing.jsonl
(contenido de conversación, no se sube al repo).

## Fuera de scope (no hacer)

- Otros flows (supervisor, juez…): solo el chat en v1.
- Pausa ENTRE selección e invocación (factor 8 completo): eso es exp/49.
- Compresión/rotación de threads viejos.

## Candado final

`python3 -m pytest tests/ -q` verde (hoy 348) y ruff. El E2E real
(matar el proceso a mitad y reanudar) lo corre el conductor.
