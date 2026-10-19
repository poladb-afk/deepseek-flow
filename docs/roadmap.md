> Los ítems ya cumplidos y la sección "Hechos" viven en [bitacora.md](bitacora.md) (movidos el 2026-10-16): acá queda solo lo que falta.

# Próximos pasos (roadmap)

Priorizado por valor/costo, decidido al cierre de la etapa 2026-10-04.
Cada ítem indica qué pieza lo apoya y qué falta.

## Estado del tablero (2026-10-13, tras la revisión + la jornada Laya)

**Corriendo solo (procesos, no ítems):**
- **exp/43 — la flywheel**: router en shadow, cada pregunta deja par
  decisión↔resultado unido por id; `etiquetar_ambiental.py` produce la
  calibración. Veredicto pre-registrado (exp/45): con ≥100 decisiones, base
  rate de "directo" <10% → apagar el router; si no → alpha de la curva
  propia y enforce con calibración ambiental.
- **exp/44 — juez de riesgo en observación**: tres preguntas de una
  dimensión sobre (comando, último mensaje) en las bandas humanas; el s/n
  del humano es la etiqueta. Primeros datos: el checkpoint base es débil →
  fine-tune cuando el log acumule (siguiente de esta línea).

**Cola priorizada:**
1. ~~**exp/48** — persistencia/resume de corridas~~ **✅ hecho (2026-10-14)**:
   `utils/thread_store.py` + 3 puntos seguros + `main.py resume <id>`;
   E2E con kill -9 y continuidad verificados (design.md). Los otros flows
   (supervisor, juez) heredan la base cuando duela.
2. ~~**exp/49** — HITL como arista del grafo~~ **✅ hecho (2026-10-14, vía
   PocketFlow-simple)**: checkpoint de SELECCIÓN (la pausa del factor 8) +
   `reparar_pendientes` al rehidratar + `request_human_input` (el humano
   como tool call). Corte demostrado E2E: aprobar con el proceso
   reiniciado (design.md). **Fase B (exp/49b)**: arista formal
   approved/rejected e hitl_web multi-pendiente (dos HITL en paralelo).
3. ~~**exp/50** — pre-fetch como política declarativa (nodo `PreFetch`,
   apéndice 13)~~ **✅ hecho (2026-10-14; cerrado 2026-10-19)**: A/B ON/OFF
   medido — las preguntas sobre archivos bajan de **2 rondas a 0**, 5/5
   turnos OK y 0 errores en ambos brazos (detalle en
   [bitacora.md](bitacora.md)).
4. **exp/45** — veredicto del router con datos propios (pre-registrado,
   arriba; ~24/100 pares acumulados). Decide la suerte del router del chat.
5. **Fine-tune del juez de riesgo** — con el log de exp/44 (dataset gratis
   de las aprobaciones); umbrales del log propio, enforcement recién
   después.
6. **Mesa 3 (restos, re-priorizados)**: gate del juez (después del 5),
   presupuesto dinámico/convergencia de loops (empezar DETERMINISTA con las
   features de exp/9, Laya solo si no alcanza), Laya vía MCP como producto.
7. **Mesa 1 (pendiente)**: bench de decisiones del voto como dataset —
   ahora a medio camino: `calibrar_voto.py` (subproducto de exp/43) ya
   genera la mitad.
8. **Mesas 4/5/7/8** (agentes fractales, async, skills, web UX): sin
   cambios de prioridad por la evidencia nueva.
9. **Paydown del ratchet (2026-10-19)**: el baseline de `helpers_duplicados`
   quedó en 20 ocurrencias (8 nombres; los peores son `_git_sha` y `_fmt_pct`
   con 4 copias). Unificar cada uno en `utils/` baja el número y el gate
   reescribe el baseline solo: empezar por los benches (`evals.py`,
   `bench_juez.py`, `replay.py`, `minar_errores.py`, `triaje_trazas.py`)
   cuando se toquen. Las reglas blandas de `AGENTS.md` se gradúan a gate
   cuando duela.
10. ~~**Paydown del ruido (2026-10-19)**: 55 `except` amplios (39% de los
    `try`; la referencia humana tiene 1,6%)~~ **✅ primera pasada (2026-10-19)**:
    7 acotados a su excepción real y 23 justificados con motivo visible; gate
    nuevo (`# noqa: BLE001 (motivo)` obligatorio); ratchet **55 → 48**. Los
    otros tell no deterministas (comentario narrador, código muerto "por si
    acaso", test slop) quedan como review de `AGENTS.md` R9.
11. ~~**A/B de la directiva de forma**~~ **✅ exp/51 (2026-10-19)**: A/B
    pre-registrado con `banco/probes/forma_codigo.py`, n=4 por brazo y tarea,
    deepseek-flash: SLOC 193 → 44 (−77%), tokens −81%, docstrings 0,487 → 0,
    `try` −71% (detalle en la bitácora). Criterio cumplido.
12. **Repetir exp/51 con más n y otro modelo (2026-10-19)**: el efecto es
    grande pero n=4, un modelo y una corrida. Correr
    `python3 banco/probes/forma_codigo.py --runs 8`, comparar con otro modelo
    y medir también el efecto en el chat real (banco), no solo one-shot.

**Descartado hoy por evidencia:** Choose a escala (~2.400 casos — el bench
lo volvió innecesario), round de "hechos actuales" (regla dura lo cierra),
y el menú congelado de 18 se jubiló con el supervisor v2.

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

## Menú de desarrollo (registrado 2026-10-05)

Siete mesas más una de UX, decididas al cierre del día. Orden aceptado como
secuencia oficial (matiz del consejo, 2026-10-05: es el orden por
defecto, no un waterfall — los cortes ligeros y reversibles de otras
mesas pueden avanzar en paralelo con evidencia propia): (1) Replay-evals, (2) HITL graduado + hooks, (3) Laya en
el voto del router.

**Mesa 1 — Evals (el harness juzgándose, 12-factor #8) — ✅ MVP hecho (2026-10-05):** evals.py (bench del router con baseline git-sha: 93.3%/ECE 0.0658, reproduce los históricos; linter de invariantes sobre 114 trazas — detectó el ciego histórico de evento_tool; costo por sesión). Matiz del consejo en la primera corrida: es instrumento de SEÑAL, no gate — antes de bloquear cualquier CI hay que medir sensibilidad/especificidad contra los P0/P1 históricos (¿cuáles habría bloqueado?) y la tasa de falsos bloqueos. ~~Pendiente de la mesa: replay de trazas de .runs contra código actual (regresión de comportamiento, no de unidades)~~ — **✅ replay hecho (exp/41, 2026-10-13):** `replay.py` valida las caminatas reales de .runs contra los grafos VIVOS (emisibilidad, adyacencia del chat, registro de tools, política del router sobre routing.jsonl). Primera corrida 214 trazas: 0/0/0/2/0 (los 2: artefactos de tests viejos), baseline fijado. Limitación documentada: la traza no guarda contenido — la regresión SEMÁNTICA sigue siendo de los benches con contenido. Sigue pendiente de la mesa: bench
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
  (hasta el 2026-10-15 recortaba a los primeros N: corregido en la consolidación)
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
  caso tab-vs-espacios. Línea de base: 27 errores históricos. Primera
  corroboración de campo: 0 errores en 25 llamadas post-fix (vs 9% pre).
- **exp/12 ✅ mergeada** — bypass DSML del presupuesto cerrado: la
  recuperación no re-arma tools retiradas por el tope (markup cortado +
  mensaje honesto + aviso en terminal). Re-medición del escenario que
  by-paseaba: cero ejecución tras el retiro, continuación limpia.
- **exp/3 ✅ mergeada** — hook py_compile visible: `[hook] ⚠ SINTAXIS
  devuelta al modelo` en terminal (el veto ya imprimía; el hook no).
- **exp/5 ✅ mergeada** — search_files con conteo exacto: "N archivos"
  con N real calculado antes del tope + sugerencia de find (auto desde
  exp/1). Fin del "50+" del test exhaustivo.
- **exp/2 ✅ mergeada** — evals como tool del chat (estilo run_informe:
  informe a disco + ruta). Corrección de fondo del conductor: la tool
  compara pero NO guarda el baseline (`actualizar_baseline=False`).
  Medido: tool nativa, 25 s, baseline intacto.
- **exp/13 ✅ mergeada** — router_prefiltro entrenado e integrado:
  530 casos (anti-fuga aplicado), test 54%→79% ECE 0.33→0.09, banda
  confiable no vacía. A/B del pre-filtro: poda 18→2 (89%) por consulta,
- **exp/14 ✅ mergeada** — ranking del pre-filtro en lote (predict_batch):
  3.2× en el camino real (377 ms/bloque warm vs 1211 secuencial),
  decisiones idénticas. Mitiga el único costo medido del prefiltro.
- **exp/15 ✅ mergeada (descarte)** — pre-rank de tools matado por el
  KV-cache: los esquemas ya son ~gratis (miss 215/4311 por llamada);
  variar la lista ahorraría nada y arriesga el action space. Sonda
  re-ejecutable en banco/probes/cache_tools.py.
- **exp/16 ✅ mergeada** — triaje_trazas.py: selección determinista
  (linter + outliers) 37/139 → 73.4% de ahorro de la auditoría nocturna,
  sin checkpoint. Tercer "Laya no acá" por evidencia. Cableado como tarea
  del heartbeat (exp/17, tipo=triaje: 0 llamadas LLM, 0.1 s verificados).
- **exp/19 ✅ mergeada** — auditoría dirigida de modules/: método por
  tandas con anotación incremental (la compacción se comía las primeras
  tandas: 9/16 → 16/16). 6 hallazgos (1 alto: descripción de ver_pdf
  mentía el mecanismo; 1 medio: default de salida de run_auditoria),
  confirmados y corregidos.
  menos churn de búsqueda, costo de ranking local. El claim "~80%" de la
  wild queda reemplazado por la medición propia. Sección en design.md.
