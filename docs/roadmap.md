# Próximos pasos (roadmap)

Priorizado por valor/costo, decidido al cierre de la etapa 2026-10-04.
Cada ítem indica qué pieza lo apoya y qué falta.

## 1. Datos: Effective N y `pasos` en los rounds — ✅ hecho (2026-10-04)

Pieza `effective_n.py` (código puro, informe markdown) + módulo
`run_effective_n`. Los hallazgos, medidos y en design.md:

- **Effective N = 6.717 de 15.595** (56,9% duplicación), 0 contradicciones
  de etiqueta. La "duplicación round3↔verified" era exacta:
  `round3/harness_choose_verified.jsonl` es **copia byte a byte** del
  choose (la verificación no filtró nada).
- round3 es acumulativo (contiene el 89,6% de round2): round2 aporta solo
  275 casos nuevos. Subconjunto entrenable máximo: raíz_verified +
  round1_verified + round3 = **6.141**.
- Rounds 1-3 sin `steps` (usan `observation`); producción y raíz usan
  `steps`. `relabelled` vacío por volcado nunca poblado.

Decisión tomada: el volcado de rounds no está versionado y dejó los tres
defectos; antes de re-entrenar hay que regenerar los rounds con el
generador versionado de bmo (`train/generate_targeted.py`, que emite
`steps`). Entretanto: entrenar con el subconjunto de 6.141 y tratar
round3/verified como choose. El fine-tune (ítem 2) sigue condicionado a
esa regeneración.

## 2. Fine-tune de Laya para routing — ✅ hecho (2026-10-04)

Hecho, con la stack de bmo tal cual (task `router_flow` en
`bmo/train/kaggle-router/`): 840 casos generados con DeepSeek sobre 12
contextos de tráfico → juez ciego (821 verificados) → Kaggle T4 →
checkpoint `.modelos/router_flow-1k`.

| checkpoint | crudo | ECE | con compuerta |
|---|---|---|---|
| base multilingual | 13/24 | 0.379 | 12/24 |
| router_flow-1k | 20/24 | 0.077 | **22/24** |

`USE_LAYA_ROUTER=1` es ahora el default (flow.py). El supervisor pasó a
bucle reactivo con Choose local (task supervisor_dispatch, 18 opciones):
r1 8/24 → r2 **11/24 · ECE 0.222** (hallazgos: head truncado a 256 tokens,
87% del dataset con hechos de herramientas inventadas, dosis 60/opción);
r3 (15/24, 13 despachos 9 correctos) y round dirigido r4 sobre los
pares confusos (3.283 casos): **14/24 crudo con 8/8 despachos locales
correctos** — integrado y activo. El crudo tiene techo (~15) porque parte
del matiz es convención; la calibración quedó perfecta para el sistema:
lo que despacha local no falla. El contrato
entrenamiento≡producción (pregunta y estado byte a byte) es el que
cuenta — documentado en design.md. Pendiente dentro de esta línea:
promover el patrón a **Choose del supervisor** (falta la task de despacho
con su catálogo) y un round dirigido de "hechos actuales" para el único
falso-directo que resiste (mundial, 0.83).

## Hechos

### 4 (viejo). Self-healing + heartbeat — ✅ (2026-10-05)

- Self-healing en el supervisor reactivo: el fallo de un paso es un
  hecho con ERROR; el reintento recibe el error como feedback en el
  prompt de args; dos fallos y la herramienta se veta (L8), y las
  herramientas sin-args no se repiten. El informe final lleva la sección
  "Pasos" (auditoría). Verificado con LLM real: fallo → reintento
  corregido → éxito.
- `heartbeat.py`: tareas programadas (heartbeat.jsonl) con el supervisor
  completo, estado + log de auditoría, línea de cron sugerida. Probado
  con dos tareas reales nocturnas (trazas + effective_n de bmo/data).

## 3. Visor del trace — ✅ hecho (2026-10-05)

`visor.py` (python3 main.py visor): HTML autocontenido offline con
recorrido, resumen por nodo y cronología con barras. Testeado con traces
reales del supervisor y del heartbeat.

## 4. Majority vote — ✅ hecho (2026-10-05, primera etapa)

`utils/votacion.py` (mayoría genérica) + integración en el despacho
dudoso del supervisor: 2-de-3 (DeepSeek directo, DeepSeek por
eliminación, Laya crudo). Medido con LLM real: sistema 16/24 → **17/24**,
corrigiendo los pares confusos; hallazgo: los dos votos DeepSeek
correlacionan — la independencia la pone Laya. Siguientes aplicaciones
cuando duelan: el falso-directo del router (mundial) y las respuestas
verificables del chat.

## 5. Coding agent — ✅ hecho (2026-10-05)

`run_command` y `edit_file` con HITL (`modules/coding.py`), verificados en
vivo (loop write→run→edit→run); la memoria del ciclo vive en la biblioteca
de `modules/memoria.py`.

## 6. Streaming + memoria entre sesiones

- **Streaming implementado (2026-10-05)**: `call_llm_agent_stream` en
  `utils/call_llm.py` (mismo contrato de modo thinking pegajoso y filtro
  de `reasoning_content`, con `stream=True`) imprime en vivo cada delta de
  CONTENT (flush, sin saltos extra) y descarta los de reasoning; reconstruye
  `.content` y `.tool_calls` desde los fragmentos (id/name en el primer
  fragmento, arguments por concatenación). `AgentStep.exec` (y por herencia
  `DirectAnswer`) elige stream con `CHAT_STREAM` (default 1), clásica con 0.
  Si el sanitizado corta, tras el aviso se imprime la versión limpia; y con
  stream `post()` NO reimprime la respuesta (la respuesta ya salió en vivo:
  solo cierra la línea).
- **Interrupción del usuario (2026-10-05)**: Ctrl+C durante la generación
  corta el stream y conserva lo parcial (el chat sigue); `CHAT_STREAM_INTERRUPT`
  (default 1) la activa, `0` propaga el Ctrl+C como salida.
- **Memoria entre sesiones implementada (2026-10-05)**: como
  **biblioteca consultable, NO contexto auto-inyectado**. Cada chat arranca
  con la memoria vacía (nada se inyecta al inicio; el system prompt no se
  toca) y el agente la consulta por tools cuando el pedido lo justifica.
  `modules/memoria.py` expone `memory_search` (busca texto en los markdown
  de `memoria/` y lista la biblioteca; código puro) y `memory_save`
  (escribe `memoria/nota_FECHA_slug.md` con el título como primera línea:
  sin HITL —es la libreta del agente— pero con contención dura, solo dentro
  de `memoria/`, slug del título sin rutas ni `..`). Al salir del chat, con
  `MEMORIA=1` (default) y ≥2 preguntas, UNA llamada a `call_llm` resume la
  conversación en `memoria/sesion_FECHA.md` (bookkeeping, sin HITL; si
  falla, se sale igual). `memoria/` está en `.gitignore`. Descartado por
  ahora: persistir/comprimir `messages` completo (el historial se reenvía
  entero dentro de la sesión — costo creciente); vuelve cuando duela.

## 7. HITL web — ✅ hecho (2026-10-05)

`utils/hitl_web.py` (solo stdlib: `http.server` + `threading`). Con
`HITL_WEB=1`, las aprobaciones de `write_file`, `edit_file` y
`run_command` en vez de preguntar `s/n` en la terminal se responden
desde el navegador: un servidor perezoso en `127.0.0.1:8765` (puerto
`HITL_WEB_PORT`) sirve el título + el cuerpo (diff o comando) dentro de
`<pre>` con botones Aprobar/Rechazar. Un solo pedido a la vez
(`threading.Event`), timeout `HITL_WEB_TIMEOUT` (300s), y timeout o
error ⇒ rechazo (mismo default seguro que el CLI). Falta todavía el
paso siguiente de la línea: subir el HITL a una arista del grafo
(`needs_approval` → AskHuman → `approved/rejected`) y migrar el chat a
FastAPI/Gradio.

## Menú de desarrollo (registrado 2026-10-05)

Siete mesas más una de UX, decididas al cierre del día. Orden aceptado como
secuencia oficial (matiz del consejo, 2026-10-05: es el orden por
defecto, no un waterfall — los cortes ligeros y reversibles de otras
mesas pueden avanzar en paralelo con evidencia propia): (1) Replay-evals, (2) HITL graduado + hooks, (3) Laya en
el voto del router.

**Mesa 1 — Evals (el harness juzgándose, 12-factor #8) — ✅ MVP hecho (2026-10-05):** evals.py (bench del router con baseline git-sha: 93.3%/ECE 0.0658, reproduce los históricos; linter de invariantes sobre 114 trazas — detectó el ciego histórico de evento_tool; costo por sesión). Matiz del consejo en la primera corrida: es instrumento de SEÑAL, no gate — antes de bloquear cualquier CI hay que medir sensibilidad/especificidad contra los P0/P1 históricos (¿cuáles habría bloqueado?) y la tasa de falsos bloqueos. Pendiente de la mesa: replay de trazas de
.runs contra código actual (regresión de comportamiento, no de unidades); bench
de decisiones del voto (los casos donde corrigió a Laya como dataset
permanente); costo por sesión (tokens/latencia) como métrica first-class
derivable de las trazas.

**Mesa 2 — HITL graduado + hooks (12-factor #6) — ✅ MVP hecho (2026-10-05):**
`utils/policy.py` (clasificador determinista sin LLM: `auto`/`preguntar`/`confirmar_doble`)
+ integración en `run_command` (`HITL_AUTO=1` default; `0` = todo pregunta como hoy)
+ hooks post-tool en `run_tool_call` (`HOOKS_POST`; `py_compile` tras edit/write de `.py`
como error-como-feedback). Reglas de composición: `&&`/`|` exigen que TODOS los segmentos
sean auto; redirección/`$()`/backticks/`xargs` ⇒ preguntar; `python3 -c` siempre pregunta;
`git push`/`rm -rf` ⇒ doble confirmación. Residuales pendientes de la mesa: hooks de
denylist ANTES de run_command, pytest tras write de .py (más caro que py_compile),
GET del hitl_web sin validar origen, naming `_pendido`/`_pendiente`.

**Mesa 3 — Laya en más mecanismos:** el voto del router (mejor ROI: dispara en
cada directo-met y hoy paga DeepSeek); gate del juez (clasificar ok/retry, juez
completo solo si duda); presupuesto dinámico de rondas (estimación Laya de
cuántas rondas necesita el pedido); triaje de memoria (¿esta nota merece
biblioteca?). Cada candidato cuesta un round de entrenamiento: el filtro es la
frecuencia de la decisión que reemplaza.

**Mesa 4 — Agentes fractales:** agents/ como modules/ (sub-agentes
especializados: mini-flows con prompt y subset de tools, expuestos como tools;
el supervisor ya lo es de facto); debate con tools (debaters que grep/lean/corren
antes de argumentar — medir win-rate en temas factuales); comité de jueces
(juez_lote + mayoria() = self-consistency 2-de-3); coding loop como sub-flow
(plan→edit→test→revert, presupuesto propio).

**Mesa 5 — Async donde falta:** research de BatchNode a AsyncParallelBatchNode
(mismo patrón medido que juez_lote); comité de debates paralelos (N debates
sobre sub-preguntas + síntesis); supervisor con sub-tareas independientes (salto
reactivo→DAG).

**Mesa 6 — Contexto y loops:** compacción de contexto (12-factor #5 — messages
crece sin techo, sesión de fixes como evidencia; validar contra el modo thinking
pegajoso); telemetría de convergencia (hechos nuevos por ronda: comprar ronda si
converge, cortar si estanca); agentic RAG como flow dedicado (gap del cookbook);
loops fractales con presupuesto heredado (depth máx 2).
- Nuevo de la investigación 2026-10-05: **pre-filtro de contexto** — Laya
  elige qué notas de memoria/ o chunks de RAG entran al prompt ANTES de
  pagar tokens (patrón de la wild con ~80% de costo/tiempo reportado);
  y **¿el trabajo está listo?** — clasificador de convergencia de loops
  (el judgment kernel del agente mu hace exactamente esto: riesgo de
  comando, qué queda en contexto, cuándo terminar).

- Nuevo de la investigación 2026-10-05 (patrones de la wild): **exponer
  Laya vía MCP** como producto del harness (referencia typesafe-mcp /
  mcp-laya: el juicio tipado y calibrado como tool consumible por
  cualquier agente MCP — nosotros ya tenemos mcp_server.py).
**Mesa 7 — Skills y triggers:** skills/ declarativas (paquete prompt+tools+condición
de disparo, a lo ZCode); webhook autenticado sobre el server del HITL web (el
harness como servicio, seguridad primero).

**Mesa 8 — UX (incorporada a pedido):** chat web completo (FastAPI/SSE sobre el
server HITL existente, sesiones en navegador); pulido de terminal (etiqueta
DeepSeek: en streaming —nit pendiente—, colores por tipo de evento, indicador de
progreso en rondas largas); HITL UX (diffs con highlight, explicación corta del
comando antes del s/n, historial de aprobaciones de la sesión); visor --watch
(tail -f de .runs); arranque con listado de la biblioteca de memoria (mostrar el
catálogo, SIN inyectar contexto — el arranque vacío es regla).

## Cola final (considerados, sin fecha)

- **A2A** — solo si sirve para consumir agentes remotos de otros equipos.
- **Vision/PDF** — extracción de datos de PDFs con visión (patrón
  invoice del cookbook).

## Descartes

- **Voz** — no interesa.
