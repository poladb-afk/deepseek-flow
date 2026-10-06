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
`git push`/`rm -rf` ⇒ doble confirmación. **Residual del denylist ✅ cerrado (2026-10-05):**
`utils/fs_tools.HOOKS_PRE` (hooks PRE con poder de CANCELAR) + denylist dura de `run_command`
(`rm -rf /`, fork bomb) que veta sin s/n, registrada desde `modules/coding.py`.
Residuales todavía diferidos: pytest tras write de .py (más caro que py_compile),
GET del hitl_web sin validar origen (mitigado por la validación de origen actual),
naming `_pendido`/`_pendiente` (no existe `_pendido` en el código: nada que renombrar).

**Mesa 3 — Laya en más mecanismos — ✅ voto del router promovido (2026-10-05, jornada de fine-tune completa):** task router_voto (contrato PREGUNTA_VOTO, sha1 congelado) → 930 generados/558 verificados por juez ciego en dos rondas (el juez rechazó ~40%: la banda de confusión es cara de etiquetar; corrección de dirección imperativo≠tools) → r1 (288 casos) REPROBADO por la puerta: banda confiable vacía, ahorro 0 (honestidad del instrumento) → r2 (528 casos) PROMOVIDO: 27/30 crudo, 96% en banda confiable, ahorro medido 80% de los turnos-directo (24/30), 0 ecos, 0 errores nuevos, correlación de errores router↔voto limpia. Producción: tres niveles en voto_confirmacion_router (Laya-voto decide acuerdos/desacuerdos confiables; banda incierta la arbitra DeepSeek; sin checkpoint, voto DeepSeek de siempre). Verificado e2e. Nota operativa: medir router+voto en UN proceso dio OOM (2×615MB + 15GB de máquina) — un checkpoint por proceso, dumps en /tmp. Siguientes de la mesa (sin fecha): gate del juez, presupuesto dinámico de rondas, triaje de memoria, exposición MCP. El voto del router (mejor ROI: dispara en
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
pegajoso) — **✅ compacción hecha (2026-10-06):** `utils/compaccion.py` (código
puro, sin LLM) + `AgentStep.prep`: la zona fría se reemplaza por un resumen
`[compacción]` y la ventana caliente (system + últimos 6, con assistant+tools
como unidad indivisible) queda intacta; `COMPACTION_CHARS` (default 60000), una
vez por ronda por huella sha1, `shared['compacciones']` cuenta. Invariantes del
modo thinking clavados por `validar_historial` (sin reasoning_content, dicts
canónicos, sin assistant sin sus tools, primer mensaje system). 124 passed.
Siguientes de la mesa (sin fecha): telemetría de convergencia (hechos nuevos por
ronda: comprar ronda si converge, cortar si estanca); agentic RAG como flow
dedicado (gap del cookbook); loops fractales con presupuesto heredado (depth máx
2).
- Nuevo de la investigación 2026-10-05: **pre-filtro de contexto** — Laya
  elige qué notas de memoria/ o chunks de RAG entran al prompt ANTES de
  pagar tokens (patrón de la wild con ~80% de costo/tiempo reportado) —
  **✅ construido (2026-10-06):** `utils/contexto.py` (helpers puros:
  `unidades_bloques`, `elegir_por_laya`) + ganchos en `rag_search`
  (`RAG_PREFILTRO`/`RAG_PREFILTRO_N`) y `memory_search`
  (`MEMORIA_PREFILTRO`/`MEMORIA_PREFILTRO_N`). Sin checkpoint
  (`LAYA_MODEL_PREFILTRO`) el filtro es no-op: entran todos, como siempre
  (no se pierde recall; cercado por tests con Laya simulado). Siguiente
  real: entrenar el checkpoint `router_prefiltro`.
  Y **¿el trabajo está listo?** — clasificador de convergencia de loops
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

**Pulido de terminal ✅ (2026-10-05):** `utils/terminal.py` — `colorear(texto,
tipo)` con códigos ANSI por tipo de evento (`tool`/`ok`/`error`/`info`/`aviso`/
`respuesta`) y `progreso_ronda(ronda, tope)` (`⚙ ronda 2/8`). Sin tty, o con
`NO_COLOR`/`COLOR=0`, degrada a texto plano (nada cambia en CI, pipes ni logs).
`ExecuteTools` anuncia cada tool ANTES de correrla (`→ read_file`, para que una
espera no parezca colgada) y etiqueta la ronda consumida con su avance. Los
avisos de recuperación DSML y sanitizado van coloreados como `aviso`.

**Visor --watch ✅ (2026-10-06):** `visor.py --watch` re-genera el HTML de
la traza cuando crece (tail -f de `.runs/`), con `--intervalo` configurable.
No re-renderiza sin cambios y un Ctrl+C sale limpio.

**Catálogo de memoria al arranque ✅ (2026-10-06):** `main.catalogo_memoria()`
imprime el listado de notas de la biblioteca al arrancar (nombre + conteo),
SIN inyectar su contenido al contexto — el arranque vacío sigue siendo regla
(la memoria es una biblioteca que el agente consulta con `memory_search`).
Con `MEMORIA=0` o biblioteca vacía, silencio; nunca corta el arranque.

Sigue pendiente de la mesa: el chat web y el HITL UX (diffs con highlight,
explicación antes del s/n, historial de aprobaciones).

## Cola final — ✅ vacía (2026-10-05)

Los dos últimos ítems quedaron construidos y verificados:

- **Vision/PDF** — ✅ `modules/vision.py`: `ver_imagen` (data-URL base64
  en un turno de USER; el type se valida por contenido; 32 MiB/48 MiB
  chequeados antes de llamar) y `ver_pdf` (Files API: `POST /files` con
  `purpose=file-extract` → `file_id` → `POST /chat/completions` con
  `content=[{type:file,file_id},{type:text}]`; sin estado; 64 MiB).
- **A2A** — ✅ `modules/a2a.py`: `agentes_remotos` (agent card con
  degradación a "inaccesible") y `a2a_tarea` (JSON-RPC 2.0
  `message/send`); setting `A2A_AGENTS` (JSON nombre→URL); sin setting,
  mensaje claro.

Tests sin red (mocks de `requests.post` + `http.server` fake), diseño en
la sección "Vision/PDF y A2A" de design.md.

## Descartes

- **Voz** — no interesa.

## Ciclo de experimentos exp/ (2026-10-06)

Workflow: branch exp/N → gate ./calidad.sh verde → medición en el mensaje
del commit → merge --no-ff solo del ganador. El banco (banco/banco.py)
mide: marcadores por turno en conversación real contra DeepSeek.

- **exp/1 ✅ mergeada** — política HITL: `cd` neutro + `sort` whitelist +
  partir por `;` (hueco medido: `ls ; rm -rf /tmp/x` clasificaba auto).
  Los 5 run_command reales de la sesión del test exhaustivo: 2 pasan a
  auto, 0 se relajan peligrosos.
- **exp/6 ✅ mergeada** — banco de conversación: escenarios YAML contra el
  chat real por PTY, conteo de marcadores por turno (laya, voto, hitl,
  compacción, auto...), no contamina memoria, exit 0 = todo OK. Primera
  corrida 7/7 y prueba en vivo de exp/1 (run-auto sin s/n).
- **exp/7 ✅ mergeada** — sonda_laya.py: evidencia de Laya con vara propia
  (ECE, curva de compuerta, latencia CPU ~0.2 s, RSS 2.86 GiB/proceso).
  La compuerta 0.9 del supervisor = rodilla precisión=100% de su curva.
  Sección "Laya: estado de la evidencia" en design.md.
- **exp/8 ✅ mergeada** — compuerta del router 0.7→0.85 por datos + split
  LAYA_UNSURE_HIGH_VOTO (el veto conserva 0.7). El veto confirmaba el
  falso-directo "mundial" (0.78 met): error correlacionado medido; la
  compuerta nueva lo bloquea antes. Ensamble 25/30 → 26/30. Sección en
  design.md.
- **exp/9 ✅ mergeada** — minar_errores.py: 43 errores en 108 sesiones,
  tasa de autocorrección 67% (94% entre los reintentados) — el lazo
  error-como-feedback ya ES el triaje. **Triaje con Laya descartado por
  evidencia**; único candidato residual: reintento determinista para los
  4 timeouts por firma de duración. Sección en design.md.
- **exp/11 ✅ mergeada** — scope de aprobación por path en el banco:
  el driver del banco parsea el objetivo de cada HITL y solo aprueba
  dentro del scope del escenario; denylist dura del conductor (.env,
  .git/, memoria/, git push, rm -rf). Auto-prueba en vivo: el ataque al
  .env se rechazó solo (evento hitl-fuera-de-alcance), el permitido
  corrió. Sección en design.md.
- **exp/4 ✅ mergeada** — presupuesto visible: la nota de la anteúltima
  ronda viaja en el resultado de la tool (el modelo ya ve su tope),
  protocolo de continuación documentado ("seguí" reinicia) y env por
  escenario en el banco (MAX_TOOL_ROUNDS=40 para aplicar). HALLAZGO:
  la recuperación DSML by-pasea el retiro de tools — candidato a fix.
- **exp/10 ✅ mergeada** — edit_file con feedback rico: diagnóstico de
  indentación (incluye old_strings de 1 línea), candidatos con línea y
  ocurrencias listadas. Medido: reintento único y cero relecturas en el
  caso tab-vs-espacios. Línea de base: 27 errores históricos.
- **exp/12 ✅ mergeada** — bypass DSML del presupuesto cerrado: la
  recuperación no re-arma tools retiradas por el tope (markup cortado +
  mensaje honesto + aviso en terminal). Re-medición del escenario que
  by-paseaba: cero ejecución tras el retiro, continuación limpia.
