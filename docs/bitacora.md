# Bitácora — deepseek-flow

El registro de lo que se midió y cuándo: cada experimento exp/N con su evidencia, las jornadas de trabajo y los fixes de auditoría. Se separó de [design.md](design.md) el 2026-10-16 (PR 2 del plan de orden): design.md documenta lo vigente y esto, cómo se llegó ahí.

---

## El historial canónico y el modo thinking pegajoso (2026-10-05)

Tres crashes medidos en producción, todos `400: The reasoning_content in
the thinking mode must be passed back to the API`, dos de ellos con el
fix anterior puesto — lo que forzó a instrumentar el cliente y capturar
el historial exacto de la request fallida (dump en fallo, hoy retirado).

**El historial rechazado era estructuralmente perfecto** (dicts
canónicos, sin reasoning, sin extras) — el veneno no era la forma de los
mensajes sino el FLIP de modo thinking dentro de la conversación:

- ON→OFF: vuelta directa (thinking) seguida de vuelta con tools (crash
  del usuario, turno 3).
- OFF→ON: 8 rondas de tools y la llamada del tope reactiva thinking
  porque `tools=None` (crash en la sesión de fixes, reproducido dos
  veces; la traza .runs muestra las 8 rondas y el dump confirma 8
  assistants con tool_calls).

Respuesta en capas:

1. **`historiar()` en `nodes.py`**: el mensaje del asistente entra al
   historial como dict canónico `{role, content, tool_calls}` — sin
   `reasoning_content`, sin campos nulos del objeto pydantic.
   `ExecuteTools.prep` y `run_tool_call` usan la forma dict.
2. **Modo pegajoso en `call_llm_agent`**: si hay tráfico de tools en el
   historial (cualquier `role:tool` o `tool_calls`), thinking va
   desactivado aunque la llamada no traiga tools — cubre la llamada del
   tope de rondas Y las vueltas directas posteriores a una agéntica.
   Conversación limpia y sin tools: thinking normal (el modo disabled
   midió descarrilos). El filtro de `reasoning_content` queda como
   segunda barrera.
3. **`extraer_yaml`**, recovery DSML y sanitizar conviven con esto: los
   dos últimos viven en `exec()` (reintento real de PocketFlow), no en
   `post()`.

Validación: matriz de probes (4 combinaciones ±reasoning ±tools en
aislamiento: todas OK — el validador solo estalla con el flip real en
sesión larga) + E2E con `MAX_TOOL_ROUNDS=1` reproduciendo el escenario
exacto del crash (ronda de tools → llamada sin tools sobre historial
agéntico → vuelta directa): responde completo, sin 400.

Nota de límites: la regla del validador dejó de ser opaca — los docs
oficiales (verificados 2026-10-13) la documentan: con `tools` en el
request, el `reasoning_content` debe devolverse COMPLETO en todas las
requests subsecuentes; sin tools se ignora. Los tres crashes eran esa
regla rompiéndose (había tráfico agéntico + reasoning ausente tras el
flip de modo), y la sonda de exp/38 confirmó que el flip SOLO ya no
rechaza. El modo pegajoso se mantiene por decisión (este cliente descarta
el reasoning): la alternativa documentada —preservarlo en el historial—
habilitaría thinking en las rondas de tools al costo de reenviarlo en
cada vuelta.

### Sanitizado: el episodio del system prompt ajeno

(Detalle de la capa 2 de la sección «Sanitizado de respuestas descarriladas
y thinking selectivo», arriba.) Medido en producción (2026-10-05): una respuesta se cortó a mitad del
saludo y el modelo siguió emitiendo un system prompt AJENO (un "file
exploration agent" genérico — texto de entrenamiento, no inyección de
nadie: episodio estocástico de decodificación, no reproducible en 3
intentos). `AgentStep.post` ahora corta el contenido en el primer marker
de rol (`<system>`, `[INST]`, `<|im_start|>`…): el chat muestra y el
historial guarda solo lo que lo precede; si no queda nada, el reintento
del nodo re-pregunta. Test con el transcript real.

### Laya: estado de la evidencia (exp/7, 2026-10-06)

| checkpoint | crudo | ECE | p50 CPU | carga fría | RSS pico |
|---|---|---|---|---|---|
| router_flow-1k | 27/30 | 0.066 | 190 ms | 9.7 s | 2.86 GiB |
| router_voto | 27/30 | 0.119 | 232 ms | 9.7 s | 2.86 GiB |
| supervisor_dispatch-1k | 14/24 | 0.209 | 500 ms | 10.1 s | 2.86 GiB |
| base multilingual | 16/30 | 0.300 | 203 ms | 9.9 s | 2.86 GiB |

- La sonda reproduce los artefactos previos: router 27/30 · ECE 0.066 =
  results.json del checkpoint y bench_router.json; supervisor 14/24 = r4;
  base 16/30 = results base. La cadena de evidencia cierra en CPU local.
- El "~0 s" heredado es en realidad ~0.2 s en CPU (supervisor ~0.5 s con
  18 opciones): órdenes de magnitud más barato que una llamada remota,
  pero ni gratis ni instantáneo.
- RSS por proceso 2.86 GiB (no los 615 MB del archivo): la ley "un
  checkpoint por proceso" ahora tiene número — dos procesos ya suman
  5.7 GiB.
- La compuerta 0.9 del supervisor es EXACTAMENTE la rodilla precisión=100%
  de la curva propia (8/24 locales, 8/8 correctos); debajo de 0.85 la
  precisión cae a 0.818. El umbral heredado de las leyes de bmo coincide
  con el punto óptimo medido.
- Router a 0.7: cobertura 0.90 / precisión 0.963; a 0.85: 0.833 / 1.000
  (mata el falso-directo "mundial", conf 0.831). La banda 0.7–0.85 es la
  sobrecargada (gap −0.32). La decisión de umbral es exp/8.
- Semántica verificada en el código del paquete: answer_confidence =
  max(p) post-temperatura (la calibrada); confidence = entropía
  normalizada (NO calibrada). Clamp de temperaturas [0.5, 5.0]: el router
  trae choice=0.5 exacto (el mínimo del clamp); el sesgo del clamp es
  conservador. Decisión: NO re-ajustar temperaturas con 54 casos.

## Cómo crecer desde aquí

- Escribir archivos → herramienta write_file con confirmación humana
  previa (HITL).
- Memoria entre sesiones → ✅ hecha como **biblioteca consultable** (ver
  abajo), NO como contexto inyectado: persistir/comprimir `messages`
  (cookbook `chat-memory`) quedó descartado por costo creciente.
- Muchos documentos y preguntas repetidas → indexar offline (RAG).
- Streaming de respuestas y memoria entre sesiones (persistir/comprimir
  `messages`).
- Choose del supervisor a escala: recargar saldo DeepSeek, generar
  ~2.400 casos con hechos del menú real (prompt ya corregido), verify
  y un run más — la dosis por opción es la palanca que falta (60 → 120+).
- Datar el punto débil restante del router (mundial): un round dirigido
  de "hechos actuales" con `generate_targeted` (arreglar su
  `contexts_path` roto primero).
- La aprobación HITL vive hoy dentro del tool (`input()`, o el navegador
  con `HITL_WEB=1` vía `utils/hitl_web.py`); el paso siguiente, si el
  chat migra a web (FastAPI/Gradio), es subirla a una arista del grafo
  (`needs_approval` → AskHuman → `approved/rejected`).
- Self-healing batch (pasos fallidos re-encolados con feedback) y
  heartbeat (piezas corriendo solas de noche).
- Un visor del trace (.runs/*.jsonl ya registra nodo/acción/duración).

### exp/8 — la compuerta del router, decidida por datos (2026-10-06)

La curva con semántica de producción (solo el lado "directo" se computa;
herramientas dudoso cae al lado seguro sin compuerta) y la medición del
ensamble completo (router_flow-1k + router_voto sobre las mismas 30
preguntas, `sonda_laya.py voto_en_router`) dieron el veredicto:

- **El veto CONFIRMA el falso-directo "mundial"**: responde "directo" con
  conf 0.78 (met) — las dos capas fallan juntas, el caso de eco que la
  Mesa 3 advertía como riesgo, ahora medido en un caso real del test.
- **Compuerta del router 0.7 → 0.85**: bloquea mundial ANTES de consultar
  al voto. En la banda 0.7–0.85 no hay ningún directo-correcto que lo
  pierda (t20-historia, 0.62, ya estaba bloqueado en todos los umbrales)
  — el kill es gratis. El ensamble pasa de 25/30 a 26/30 con los mismos 3
  arbitrajes.
- **El voto conserva su umbral propio** (LAYA_UNSURE_HIGH_VOTO=0.7): su
  curva da 96% de precisión con 83% de cobertura local a 0.7; heredar la
  subida del router le cortaría la cobertura a 53% sin ganar nada.
- El supervisor no se toca: 0.9 ya es exactamente la rodilla de su curva
  (exp/7).
- Caveat honesto: n=30. La curva es consistente con todo lo medido antes
  (mundial 0.83 documentado desde la curaduría), pero la banda 0.7–0.85
  tiene pocos casos; el round dirigido de "hechos actuales" del roadmap
  sigue siendo el refuerzo natural si aparecen más falsos-directos.
- Descubrimiento de activación: `_setting` lee en cascada nuestro .env y
  el de bmo (BMO_ENV) — bmo/.env trae LAYA_UNSURE_HIGH=0.7 heredado, que
  enmascara el default del código. La compuerta 0.85 se activa fijando
  LAYA_UNSURE_HIGH=0.85 en el .env del proyecto (documentado en
  .env.example).

### exp/9 — minería de errores: el triaje con Laya, descartado con el número a la vista (2026-10-06)

`minar_errores.py` minó las 108 trazas de `.runs/` (SIN torch, JSON puro;
reusa el parseo de evals). Límite honesto: la traza no guarda el texto del
error (solo tool + ok/error + segundos) — la causa es imposibilidad, no
omisión; lo medible es frecuencia, firma de duración y destino del
reintento.

- 43 errores de tools en 108 sesiones (18 sesiones con errores): frecuencia
  baja, ~0,4 por sesión.
- **Tasa de autocorrección 67,4%** (29/43): de los errores que la misma
  sesión reintentó (35), **33 terminaron bien (94%)** — el lazo
  error-como-feedback ES el triaje, y es gratis.
- edit_file concentra 27/43 (old_string que no matchea → el modelo corrige
  y reintenta, delta mediano 4 s); run_command 4/4 recuperados.
- Los 8 abandonos son mayormente timeouts de flujos largos (juez_lote,
  deep_research) donde el reintento no es decisión del modelo de todos modos.
- 4 timeouts con firma de duración ~100 s: si algo se automatiza, es un
  REINTENTO DETERMINISTA por firma (regla de código, no un modelo).

**Veredicto: el triaje con noul de Laya queda DESCARTADO por evidencia** —
a esta frecuencia y con esta autocorrección, una capa de decisión no agrega
valor; su costo (checkpoint, umbral, fallback) no se paga. Revisar si la
frecuencia de errores crece o si aparecen errores caros que el modelo no
puede autodiagnosticar.

### exp/11 — scope de aprobación por path en el banco (2026-10-06)

Riesgo operacional medido: en la sesión exp8-aplicar el harness propuso
editar el `.env` real fuera de spec y solo el timing lo frenó — el driver
del banco aprobaba TODO el HITL del turno sin mirar el objetivo.

El driver ahora parsea el objetivo de cada prompt HITL y responde con la
política solo si está dentro del alcance declarado por el escenario
(`permitir:` prefijos de rutas, `permitir_comandos:` prefijos de
comandos). Fuera de alcance → "n" automático + evento
`hitl-fuera-de-alcance` con el objetivo. Una DENYLIST DURA del conductor
aplica por encima de cualquier scope: `.env`, `.git/`, `memoria/`,
`git push`, `rm -rf` — jamás aprobables por el driver. Sin claves de
scope, todo está permitido salvo la denylist (compatibilidad).

Auto-prueba en vivo (escenario exp11-autoprueba): escribir un archivo
dentro del scope → aprobado y creado; intentar agregar un comentario a
`.env` vía edit_file → el driver rechazó solo (evento con motivo
"denylist"), el modelo reportó el rechazo como dato, y el hash del
`.env` quedó intacto. 3/3 turnos OK.

### exp/4 — presupuesto visible + protocolo de continuación (2026-10-06)

Medición que cambió el diagnóstico: el problema nunca fue "llamadas por
ronda" (87% de las rondas tiene 1-2; el outlier de 17 read_file fue UNA
ronda) sino RONDAS para la clase editar→probar→editar — 42 preguntas
históricas sobre 8 (máx. 242) y tres sesiones de aplicación muertas por
el corte. Y el hallazgo de diseño: el modelo NO veía su presupuesto (el
⚙ iba a la terminal, nunca a la conversación).

- `nota_presupuesto`: en la anteúltima ronda, la nota viaja en el
  resultado de la última tool ("la próxima es tu ÚLTIMA con tools...
  cerrá el estado y pedí continuación — un mensaje nuevo reinicia el
  presupuesto"). El reset ya existía (cada mensaje nuevo pone
  tool_rounds en 0): lo que faltaba era el aviso.
- El default 8 queda: mediana 2 rondas/pregunta; 19 min colgados en una
  pregunta es mala UX de chat — la solución es el aviso + la mano amiga,
  no un tope enorme.
- `env:` por escenario en el banco: las sesiones de aplicación pesadas
  corren con MAX_TOOL_ROUNDS=40 (así se aplicó exp/11).

Demostración (exp4-protocolo, tope 2, tarea de 3 rondas dependientes):
protocolo verificado — el presupuesto se reinicia con el mensaje nuevo.
Y UN HALLAZGO: al retirarse las tools, el modelo emitió el write_file
como TEXTO DSML y la recuperación lo ejecutó igual (recuperacion×1) —
la recuperación DSML by-pasea el presupuesto de tools: la ley L8 no es
tope duro por ese camino. Benigno acá (la tarea se completó), pero es
una interacción conocida: candidato a fix — que la recuperación
respete el retiro de tools o consuma ronda.

Las corridas de control (exp4-bajo/amplio, presupuesto 4 vs 40 con la
misma tarea) no muestran daño en defaults: 2 rondas, sin nota, sin
diferencia.

### exp/10 — edit_file con feedback rico (2026-10-06)

edit_file generaba el 63% de los errores del harness (27/43, minería
exp/9) con un feedback ciego: "old_string no aparece... releé el
archivo" — el modelo relee entero y reintenta a ciegas.

El error ahora diagnostica: (a) si el texto matchea normalizado
whitespace (tabs→4, sin trailing), NOTA explícita de indentación — la
causa clásica, incluso para old_strings de una línea; (b) top-3 de
candidatos con número de línea (difflib sobre el texto unido — sobre
listas de líneas compararía líneas enteras y toda casi-igual daría
ratio 0); (c) en ocurrencias múltiples, las líneas exactas para apuntar
con contexto.

Medición (exp10-reintento, indentación tab-vs-espacios): 2 intentos de
edit, CERO relecturas del archivo, diff correcto aprobado y verificado
— el reintento único hipotetizado. minar_errores queda como línea de
base (27 errores) para vigilar la tasa a futuro.

Primera corroboración de campo (2026-10-06, corte en el merge de exp/10):
pre-fix 116 llamadas / 11 errores (9%); post-fix 25 llamadas / 0 (0%).
Direccional — muestra chica y sesiones más simples que las de código;
el heartbeat acumulará la serie.

### exp/13 — router_prefiltro: el checkpoint del pre-filtro de contexto (2026-10-06)

La infra era no-op desde la Mesa 6 (contexto.py + settings); faltaba el
checkpoint. Fine-tune con la receta de router_voto en bmo (task yaml con
el estado de DOS campos consulta+bloque como producción, contrato
congelado por sha1):

- Datos: 1033 generados → juez ciego 530 verificados (51%) con top-up
  dirigido de la clase "no" (balance final 299/231). **Filtro anti-fuga
  aplicado** (lección de router_voto r2, donde el test entrenó dentro de
  los verificados): 0 ids del test en el entrenamiento.
- Sesgo juez=generador acotado por primera vez: releabel manual del
  conductor sobre 30 casos → acuerdo 77% (7 corregidos: trampas bien
  construidas mal etiquetadas — tema compartido, dato ausente, fecha
  equivocada). Informe en bmo/data/router_prefiltro_relabel_informe.md.
- Resultados (results.json del kernel T4x2, minutos): test 15/28 →
  **22/28** (54% → 79%), ECE 0.326 → **0.091**; banda confiable NO vacía
  (13 casos en [0.5,0.7) con 69% — la lección de voto r1 no se repite).
- **El A/B que reemplaza el claim externo "~80%"** (biblioteca de 18
  notas, max 2): poda 18→2 archivos por consulta (89%), el modelo hizo
  menos búsquedas (3 vs 6 del control) y trabajó desde lo podado; costo
  ~7 s por consulta de inferencia local (0 API). El ahorro real es de
  CONTEXTO (2 bloques vs 18 entran al prompt), no de reloj.

### exp/14 — el ranking del pre-filtro, en lote (2026-10-06)

`_puntuar` llamaba a Laya una vez por bloque (secuencial: ~1.2 s/bloque
medido con bloques largos reales). `preguntar_lote` (Agent.predict_batch,
forward compartido) lo baja a UNA llamada: micro-benchmark — secuencial
1211 ms/bloque vs lote 421 ms/bloque (~2.9×), y el camino completo
`elegir_por_laya` medido WARM: 377 ms/bloque (3.2×), decisiones idénticas
14/14 en el solapamiento. La carga en frío (~11 s) sigue siendo costo
fijo por proceso. El turno del banco NO es instrumento acá (la latencia
de DeepSeek domina con ±50% de ruido; en una corrida el modelo ni
siquiera hizo búsquedas anchas). La ley de degradación no cambia:
cualquier fallo del lote → default seguro (entran todos).

### exp/15 — pre-rank de tools: descartado por el KV-cache (2026-10-06)

La idea del brainstorm: 27 esquemas viajan en cada ronda de tools; Laya
elegiría la familia y DeepSeek vería un top-k. La sonda
`banco/probes/cache_tools.py` (API real) lo mató antes de construirlo:
los esquemas viven en el PREFIJO CACHEADO — llamada idéntica 4096/4311
tokens cacheados (miss 215 ≈ el propio mensaje del usuario), y un subset
variado en orden canónico pegó miss 161. Ahorrar tokens que cuestan
~nada a cambio de (a) arriesgar sacar la tool correcta del action space
y (b) bustear el cache si el orden varía: pérdida neta. Segundo descarte
por evidencia (con el triaje de exp/9): la sonda queda como artefacto
re-ejecutable.

### exp/16 — triaje de trazas para la auditoría nocturna (2026-10-06)

La pregunta: auditar TODAS las trazas cuesta N llamadas LLM que crece
sin techo (177 hoy). El triaje DETERMINISTA (invariantes del linter +
outliers de duración >120 s) selecciona **37/139 legibles → 73.4% de
ahorro** de la auditoría nocturna — sin checkpoint nuevo: tercera
decisión por evidencia donde Laya no corresponde (con el triaje de
errores y el pre-rank de tools). Límite honesto en el informe: el triaje
ve lo estructural; lo semántico (decisión mala sin violación) requiere
lectura LLM. `triaje_trazas.py` standalone; la integración como tarea
del heartbeat queda para cuando se quiera cablear.

Nota de proceso: la sesión del harness que lo aplicó agotó presupuesto y
emitió el segundo edit como texto DSML — y el fix de exp/12 lo IGNORÓ en
producción por primera vez (antes by-paseaba el tope): la ley sostuvo
mientras el triaje se estaba construyendo. El test a medias que dejó se
completó con la intención del edit ignorado (aserción en mixed-case
contra un haystack con .upper()).

### exp/17 — el triaje, cableado al heartbeat (2026-10-06)

El heartbeat acepta `"tipo"` en sus tareas: default = supervisor
reactivo (LLM, la noche es finita); `"tipo": "triaje"` = el script
determinista directo, **cero llamadas LLM**. Verificación en vivo con
config de una sola tarea: ✅ 0.1 s (los supervisores tardan minutos),
informe `salidas/heartbeat/triaje_trazas_<fecha>.md` escrito y logueada.
38/140 seleccionadas en la corrida real (72.9% de ahorro) — la auditoría
profunda queda disponible para la selección cuando haga falta.

### exp/19 — auditoría dirigida de modules/ y hallazgos (2026-10-06)

El harness auditó los 16 módulos dirigido por scenario (scope, inventario
y método regalados; MAX_TOOL_ROUNDS=40). Dos corridas — la primera enseñó
el hallazgo metodológico: con 19 lecturas (~130 KB) la COMPACCIÓN se
comió los módulos de las primeras tandas (informe final: 9/16); el
método corregido anota hallazgos POR TANDA antes de avanzar (inmune a la
compacción: cero en la segunda corrida, 6 rondas). La sospecha de
websearch (TOOLS `search_web` vs función `run_search_web`) se
AUTO-VERIFICÓ contra el mecanismo de despacho y se declaró "falsa alarma
mía" — la calibración de confianza del auditor mejoró de 0/2 (auditoría
1) a hallazgos verificados.

Veredicto: 6 hallazgos (1 alto, 1 medio, 4 cosméticos), los dos
sustantivos CONFIRMADOS y corregidos:
- ALTO `modules/vision.py`: la descripción de `ver_pdf` decía "vía la
  Files API" — falso desde el fix de poppler (la Files API rechaza PDFs,
  HTTP 400). El modelo leía esa mentira en cada llamada. Descripción y
  comentario de PDF_MAX_BYTES corregidos (la IMPL ya documentaba bien).
- MEDIO `modules/auditoria.py`: el default de `salida` del tool era
  `auditoria.md` mientras descripción y CLI prometen `salidas/auditoria.md`
  — alineado. (Los 4 cosméticos: naming de websearch, `rondas=None` vs
  "default 2" efectivo, comentario de PDF_MAX_BYTES, tope de páginas no
  declarado — quedan como están, documentados acá.)

- Kaggle, dos lecciones de operación: el CLI de datasets subió solo los
  archivos de primer nivel (la v1/v2 del kernel falló por eso — subida
  plana y versión nueva lo arreglaron) y el notebook copiado hereda
  referencias por nombre que hay que renombrar TODAS (contexts_router
  sobrevivió al primer reemplazo).

### exp/12 — el bypass DSML del presupuesto, cerrado (2026-10-06)

Hallazgo de exp/4: al retirarse las tools por el tope, el modelo emitía
la llamada como TEXTO DSML y la recuperación la ejecutaba igual — la ley
"todo bucle tiene presupuesto" no era tope duro por el canal de texto.

`dsml_con_presupuesto_agotado`: con tools ofrecidas, la recuperación de
siempre; con tools retiradas, el markup se corta (lo previo sobrevive) y
si no queda nada, el contenido pasa a ser el mensaje honesto "(sin
texto: emitiste tool-calls con el presupuesto agotado — decí 'seguí'
para reiniciarlo)". Terminal: "[DSML] tool calls como texto: IGNORADOS".

Re-medición del escenario que by-paseaba (exp4-protocolo, tope 2):
antes — el write_file corría tras el retiro (recuperacion×1); ahora —
dsml_ignorado×1, cero ejecución en el turno 1, y el turno de
continuación completa con su HITL. La ley vuelve a sostenerse.

### exp/3 — el hook de sintaxis, visible (2026-10-06)

Asimetría medida en el test exhaustivo: el veto imprime en terminal pero
el `⚠ SINTAXIS` del hook py_compile viajaba solo al modelo — el usuario
no veía que el hook actuó. Ahora el hook imprime `[hook] ⚠ SINTAXIS
devuelta al modelo: <última línea del detalle>` (coloreado, flush como
los demás avisos). El flujo del modelo no cambia: la observabilidad
completa sin tocar el contrato.

### exp/5 — search_files con conteo exacto (2026-10-06)

Patología medida (test exhaustivo): el conteo de ".py" quedaba "50+" y
el modelo no sabía cuántos eran; su find para cerrar el número cayó en
preguntar (hasta exp/1). Ahora el conteo EXACTO se calcula antes de
truncar la muestra: "N archivos coinciden" con N real, y al cortar el
tope agrega "... y M más (mostrando 50 de TOT; para el listado completo:
run_command 'find ...' ya es solo-lectura auto)" — la sugerencia apunta
al camino que exp/1 volvió automático.

### exp/2 — evals como tool del chat (2026-10-06)

Medido en el test exhaustivo: el modelo QUISO correr evals en vivo, no
existía la tool, su run_command fue rechazado y degradó a leer la
corrida del día anterior del disco. La spec pedía dos tools (rápida +
pesada); el harness prefirió UNA `evals` estilo run_informe (informe a
disco + ruta) — consistente con el patrón del código, y la revisión del
conductor aceptó el diseño con UNA corrección de fondo: `generar` ganó
`actualizar_baseline` (default True = CLI intacto) y la tool pasa False
— el ancla de medición no se pisa desde una conversación.

Medición (exp2-medicion): tool nativa usada (cero run_command), informe
leído y resumido en 25 s, y el baseline verificado INTACTO tras la
corrida (filecmp).

### exp/35 — la política del router, separada de la clasificación (2026-10-08)

El informe externo señaló lo que faltaba: una decisión probabilística no debe
mezclarse con la política que la aplica. Ahora Laya **estima** (opción +
probabilidades) y Python **decide** (qué ruta se ejecuta), en
`utils/laya_routing.py`:

- `decide(respuesta, config)` es **pura**: sin probabilidades usables, con
  etiqueta fuera de contrato, NaN/infinito, `bool`, texto o suma distinta de 1
  → **abstención** (herramientas). Nunca "directo" por defecto. Se EXIGEN las
  dos probabilidades: `answer_confidence` es max(p) y `confidence` es entropía
  normalizada — el wrapper viejo las mezclaba en cascada.
- Con calibración, la ruta directa exige que el **conjunto conformal colapse**
  con las probabilidades reales de cada etiqueta (exp/30/31); sin calibración,
  el umbral fijo de siempre.
- `LAYA_MODO`: `off` (no ejecuta Laya), `shadow` (registra la propuesta y
  **conserva herramientas**: mide sin cambiar la conducta y sin gastar el voto
  de DeepSeek) y `enforce` (default: aplica la propuesta). El modo sombra es la
  forma de juntar evidencia antes de apretar nada.
- Cada decisión deja una línea en `salidas/routing.jsonl` (propuesta, ruta
  aplicada, causa, p(directo), q, umbral, versión de laya). El trace no la
  tenía: registraba el nodo y la acción, no el porqué.
- `LayaRouter.exec` absorbe la guarda de exp/25 (una excepción de inferencia se
  lee como abstención) y `preguntar_detalle` conserva la respuesta completa.
- **Los dos registros se unen**: con `LAYA_LOG_PREGUNTA=1` el evento de routing
  agrega los primeros 200 caracteres de la pregunta (default 0: no guarda texto
  del usuario), así que una corrida en modo sombra deja el set completo
  (pregunta + propuesta + p(directo) + ruta aplicada) y
  `banco/probes/etiquetar_router.py --extra salidas/routing.jsonl` lo etiqueta
  para elegir alpha. Ese es el circuito para pasar de `shadow` a `enforce` con
  evidencia propia.

Costo: 0 llamadas nuevas (el modo sombra ahorra el voto); tests puros de la
política en `tests/test_laya_routing.py` (sin modelo ni red).

### exp/40 — drift de spec hallado al corroborar con fuentes oficiales (2026-10-13)

Corroboración completa de la evidencia del harness contra las fuentes
oficiales (docs de DeepSeek, spec de A2A, repo de PocketFlow, el paper de
Conformal Cascade). La mayoría confirmada al detalle (vision: imágenes
solo en user con 400 medido y documentado, límites 32/48 MiB, magic
bytes, 1024 tokens/imagen, PDFs fuera de la Files API; PocketFlow 100
líneas cero deps; el paper de conformal fiel a lo citado). Dos drifts
encontrados y cerrados:

- **A2A habla el wire format viejo**: la spec actual sirve el agent card
  en `/.well-known/agent-card.json` (el módulo usaba el legado
  `agent.json`) y exige `messageId` en el message. Fix: el cliente prueba
  el path nuevo primero y cae al legado SOLO ante 404 (un agente caído no
  merece segundo intento: doblaría el timeout de detección); el payload
  suma `messageId` (UUID) — los servers viejos lo ignoran como campo
  extra. Los `parts` siguen con `type` (legado): la spec actual usa oneOf
  sin discriminador, pero un campo extra es más seguro de tolerar que un
  part sin `type` para un server viejo. Tests: card solo-nuevo,
  solo-legado (fallback) y messageId presente.
- **La anotación A1 describía el síntoma, no la regla**: los docs
  oficiales documentan que tools+thinking SÍ son compatibles; la regla
  real es que, con `tools` en el request, el `reasoning_content` debe
  devolverse COMPLETO en todas las requests subsecuentes. Los tres
  crashes históricos eran esa regla rompiéndose (razonamiento ausente +
  tráfico agéntico tras el flip de modo) — consistente con la sonda de
  exp/38, donde el flip SOLO ya no reproducía el 400. El modo pegajoso NO
  cambia (decisión: este cliente descarta el reasoning; preservarlo
  habilitaría thinking en las rondas de tools al costo de reenviarlo en
  cada vuelta — candidato a exp futuro si el costo duele). Solo se
  corrigen las anotaciones (call_llm.py y esta doc) para que el contrato
  documentado sea el real.

## exp/41 — replay de trazas: la Mesa 1 cierra su pendiente original (2026-10-13)

`replay.py` (`python3 main.py replay`): las caminatas REALES de `.runs/`
validadas contra los grafos VIVOS del código actual. La pregunta de la
Mesa 1 desde el origen — cuando el código cambia, ¿el harness de hoy
todavía ejecuta lo que ejecutó en producción? — respondida con evidencia
de disco, no con la lista congelada del linter (que admite historia por
diseño y por eso no puede detectar drift).

**Límite honesto** (arriba en cada informe): la traza guarda la caminata
(nodo/acción/duración), no el contenido. Este replay detecta regresión
ESTRUCTURAL; la semántica (misma caminata, peor respuesta) es de los
benches con contenido. Instrumento de señal, no gate.

Cuatro niveles, funciones puras testeables sin disco:

- **A — emisibilidad**: cada (nodo, accion) histórico tiene que ser
  emisible por el código de HOY (clase viva + acción cableada). Es el
  guard de calles muertas (exp/39) generalizado a caminatas reales.
  Incluye la recursión DENTRO de los Flow/BatchFlow anidados: el flujo
  interno de auditoría (CarpetaScan/Seccion) vive en `start_node`, no en
  successors — sin recursión quedaba "desconocido" (16 falsos medidos);
  el propio guard de exp/39 tiene ese punto ciego.
- **B — adyacencia del chat**: los runs de nodos del CHAT tienen que
  seguir siendo aristas del chat actual (unión ±router). La primera
  corrida marcó 246 "rotas" — todas falsas, y el por qué es un hallazgo
  del propio instrumento: el chat despacha supervisor/debate/juez por
  tools y SUS eventos quedan en el mismo archivo (corridas de otros
  grafos intercaladas en la traza del chat). El nivel juzga solo los runs
  de nodos del chat; el resto es de nivel A.
- **C — registro de tools**: eventos de tool contra el action space VIVO
  (importado de nodes, no lista de mantenimiento).
- **D — política del router sobre tráfico real**: las decisiones de
  `salidas/routing.jsonl` (exp/35) re-evaluadas con la compuerta de HOY
  (umbral/q de config_router): apretó (un directo aprobado que hoy no
  pasaría) o aflojó (uno bloqueado que hoy pasaría). n=13 hoy; crece solo
  con el tráfico.

**Primera corrida (214 trazas, 8.827 eventos, 139 del chat)**: A=0,
A′=0, B=0, D=0, C=2 — los dos `grep` con error son artefactos de tests
del 6/10 (0.0 s). Baseline fijado (`salidas/evals/replay_baseline.json`,
patrón evals: comparar sin pisar; `--actualizar-baseline` guarda). 16
tests nuevos. El pendiente restante de la Mesa 1 (bench de decisiones
del voto como dataset permanente) sigue abierto.

## exp/42 — el residual de la trampa-delete-file, cerrado POR el harness (2026-10-13)

Primera pieza del harness aplicada por el propio harness (conductor GLM
dirigiendo por banco, 5 sesiones reales con DeepSeek). El residual:
`trampa-delete-file` (hallazgo 2 de exp/20) fallaba 3/3 — el Draft
alucinaba la tool inexistente y el Judge no podía notarlo porque nunca
vio el inventario real.

**El mecanismo** (diseño del harness, fiel a los patrones de la casa):
`_tools_alucinadas(draft, inventario)` contrasta los nombres que el
borrador menciona COMO herramienta contra el action space real
(`_inventario_tools()`, import perezoso de nodes — el ciclo de
modules/juez.py lo prohíbe a nivel de módulo). El inventario lo aporta
el CÓDIGO en `Judge.exec` (la tupla prep→exec quedó en sus 4 campos:
los tests existentes son candados y no se reescriben para acomodar un
detalle interno); la `_compuerta` existente se extendió — verdict ok +
tool inventada → retry, el mismo patrón que la cita rota.

**El ciclo medir→corregir→remedir, con el bench como vara:**
- Corrida 1: la trampa PASA (117 s: el gate fuerza el retry y el borrador
  converge a "no existe"), pero el bench marca REGRESIÓN (76,5% vs
  94,1%) — dos clases de FALSO POSITIVO medidas: segmentos de ruta
  (`fs_tools` extraído de `utils/fs_tools.py`) y funciones internas
  mencionadas como "la función X" (`call_llm_agent`, `reasoning_content`)
  porque el contexto incluía "función".
- Sesión 4 (feedback medido al harness): el contexto perdió "función", y
  las rutas/citas (`[\w./-]+\.[\w]{2,4}`) se quitan de la línea ANTES de
  matchear candidatos. Candados de regresión con los DOS casos medidos.
- Corrida 2: la trampa sigue pasando y MÁS RÁPIDA (63,6 s);
  memoria-slug y trampa-pdf-filesapi (degradados por el gate) se
  recuperan; el detector queda limpio sobre los borradores que fallan.

**Lo que NO es del fix (hallazgos nuevos, medidos):**
1. **Drift del modelo**: deepseek-flash hoy REHÚSA responder fuera del
   contexto verificado ("solo líneas 1–200 de 548; no voy a inventar") —
   compaction-chars, search-vacio y sanitizar-markers fallan por la
   ventana de 200 líneas que arma `Draft.prep` (read_file limit=200), no
   por el gate (borradores limpios). Candidato a exp: ventana más ancha
   o paginación a pedido del Draft.
2. **El caso thinking-tools envejeció con exp/40**: exigía el token
   "rechaza" que la corrección de la anotación A1 reescribió; el
   borrador citaba las líneas nuevas y explicaba la regla real. El caso
   se actualizó al ground truth vigente (["thinking",
   "reasoning_content"]).
3. Residual conocido del detector: "tool" como subcadena auto-activa el
   contexto ("tool_calls" se flaggea a sí mismo al mencionarse) — solo
   visible en borradores que discuten el tema tools; documentado, sin
   acción.

**Desempeño del harness como aplicador** (5 sesiones, 336 eventos,
~1.092 s de reloj de nodos, 120 llamadas a tools, **0 errores de tools**):
diseñó con los patrones de la casa sin que se los diera; dejó NOTA DE
MEMORIA al frenarse por presupuesto y las sesiones siguientes ARRANCARON
con memory_search (la biblioteca como handoff, funcionando tal como fue
diseñada); autodiagnosticó su propio test mal escrito ("llamador" dispara
el verbo de contexto). Dos fricciones medidas del LADO del conductor: el
tope de HITL por turno (6→12→20: dos sesiones clippeadas) y que cuando
disiente del conductor DEBATE en vez de aplicar (sesión 2: contrapropuso
reescribir los tests, que era lo que el conductor había vetado).

316 tests verdes + ruff limpio (verificado por el conductor, no por
auto-reporte). Escenarios de las 5 sesiones en `banco/escenarios/exp42-aplicar*.yaml`.

## exp/43 — la etiqueta ambiental del router: la flywheel (2026-10-13)

La revisión del harness contra el ecosistema 2026 (System One/Jev, el paper
de agentic routing) destapó la asimetría: el router produce "herramientas" en
el 100% del tráfico registrado y la calibración existente (85 casos) era todo
banco, todo "herramientas" — la clase "directo" no tenía datos propios. El
mismo hallazgo lo hizo el propio harness en la sesión 3 de aplicación (midió
44 decisiones, todas inválidas o herramientas). La pieza que faltaba no era
otro round de fine-tune: era la ETIQUETA.

**La insight**: en modo shadow la ruta aplicada es SIEMPRE herramientas, así
que DeepSeek corre con tools — y si responde SIN llamar ninguna, la pregunta
era "directo" EN LA PRÁCTICA. Esa es la etiqueta ambiental: gratis, en la
distribución exacta de producción, y crece sola con el uso. Es además la
definición OPERATIVA del objetivo del router (predecir si el bucle de tools
va a arrancar), no una opinión de oráculo. Límite honesto (declarado en el
código): mide lo que DeepSeek HIZO, no lo que la pregunta NECESITABA — un
modelo que responde de memoria una pregunta de archivos etiqueta "directo";
ruido que el volumen compensa.

**La mecánica** (4 sesiones del banco, conductor GLM): cada decisión con
probabilidades gana un `id` (`uuid4().hex[:8]`, dentro del evento de
`registrar_decision`); en shadow con `p_directo` utilizable,
`LayaRouter.post` deja `shared["_router_pendiente"]`; `AgentStep.post` al
devolver "answer" lo consume y registra la línea `{"evento": "resultado",
"id", "uso_tools", "rondas"}` en el MISMO routing log (enforce no etiqueta:
directo retira las tools y mediría la política; `GetQuestion.post` limpia
huérfanos; bookkeeping que nunca corta el chat). Terminal:
`[router] etiqueta ambiental: directo (0 rondas)` — marcador contable por el
banco. `banco/probes/etiquetar_ambiental.py` (código puro, join PURO
testeable) une decisión↔resultado por id y emite el JSONL de calibración
{conf, correcto} drop-in para `utils/conformal` — con `LAYA_LOG_PREGUNTA=1`
la fila lleva la pregunta.

**Verificado en vivo** (escenario exp43-demo, shadow, log propio): "¿cuántos
.py en utils/?" → Laya herramientas 0.0016 → 1 ronda → etiqueta herramientas
(Laya correcta, conf 0.998); "¿por qué el cielo es azul?" → Laya directo
0.998 → 0 rondas → etiqueta directo (correcta, conf 0.998). Las DOS clases
ocurren naturalmente con preguntas reales — la flywheel ya no depende del
sesgo del banco. El etiquetador emitió ambas filas sin una llamada LLM.

**El .env quedó en `LAYA_MODO=shadow` + `LAYA_LOG_PREGUNTA=1`**: el tráfico
real acumula etiquetas desde ahora. El circuito de vuelta a enforce: muestra
suficiente + balance de clases → `etiquetar_ambiental.py` → calibración →
`LAYA_CALIBRACION_ROUTER` + alpha elegido de la curva propia.

**Fricciones medidas del aplicador (4 sesiones, la saga completa en
`banco/escenarios/exp43-*.yaml`)**: (1) el tope HITL por turno volvió a
clippear una sesión (6 aprobadas, 2 rechazadas — receta conocida de exp/42:
max_hitl 20); (2) una sesión DISINTIÓ de la spec y construyó en cambio la
compuerta conformal del VOTO (`config_voto`/`decide_voto`,
`banco/probes/calibrar_voto.py`, `tests/test_voto_router.py`) — trabajo
verde, neutro por defecto (umbral 0.7 sin calibración) y coherente con la
dirección de la casa, así que QUEDA como subproducto documentado, no pedido;
(3) una sesión perdió la acción puntual por la COMPACTACIÓN (prompt largo +
5 compactaciones → el modelo investigó bien pero no editó) — la lección
operativa: specs largas VAN A DISCO y el prompt del turno queda en una
línea; (4) la cuarta sesión, con spec mecánica en disco (código literal,
precedente exp/12) y prompt corto, cerró completo. 316 → **333 tests** +
ruff limpio, verificados por el conductor en cada corte.

**La caza dirigida (exp43-caza, patrón exp/19 con hitl n — solo lee)**: el
harness auditó su propio diff nuevo con zonas de caza regaloneadas (DSML,
huérfanos, gates, unir límite, marcadores). Resultado: 2 bugs VERIFICADOS y
cerrados en sesión exp43-fix (spec `banco/specs/exp43_fix_caza.md`), 1
hallazgo refutado con honestidad (el archivo mezclado viejo/nuevo se maneja
bien — traza pública en el transcript):

- **H1 (medio)**: con `LAYA_LOG_DECISIONES=0` el pendiente se seteaba igual
  y el print corría — el banco contaba `etiqueta_ambiental×1` sin ninguna
  línea escrita (el patrón del Fix 10: medir el print, no el registro). Fix:
  el gate entra en la condición del pendiente; candado
  `test_shadow_con_log_apagado_no_deja_pendiente_ni_escribe`.
- **H2 (medio)**: el marcador matcheaba prosa ecoada — el literal vive en el
  f-string de nodes.py que las auditorías mandan leer. Fix: el patrón exige
  la forma real con dígitos `(directo|herramientas) \(\d+ rondas\)` (el
  template `{etiqueta}`/`{rondas}` no matchea) + fixture negativo en
  test_banco (lección Fix 10 aplicada de entrada esta vez).

Regresión final: demo re-corrida post-fix — 2/2 pares decisión↔resultado y
marcador exacto 1/turno. **334 tests** + ruff limpio. De paso, la caza misma
dejó 2 pares etiquetados en `salidas/routing.jsonl`: cada sesión del banco
es ahora tráfico calibrable.

## exp/44 — el juez de riesgo de acciones, en observación (2026-10-13)

El uso nº1 de la familia Jev/Laya en la wild (LangChain AutoMode): juzgar
cada ACCIÓN antes de ejecutarla. Este harness ya tenía las reglas duras
(`policy.py` auto/preguntar/confirmar_doble + denylist) — el hueco semántico
era la banda que decide SOLO un humano. exp/44 la instrumenta **sin cambiar
ninguna conducta**: en las bandas humanas (preguntar/confirmar_doble),
`run_command` consulta a Laya tres preguntas de UNA dimensión cada una
(`modifica_estado`, `danio_irreversible`, `requiere_revision` — contrato
`utils/riesgo.py`, congelado por sha1) sobre el estado `(comando, último
mensaje del usuario)` — evidencia de intención, nunca el razonamiento del
propio agente (lección del manual de Jev: se auto-aprueba) — imprime
`[riesgo] observa:` y al conocerse el s/n registra
`{"comando", "mensaje", "juicios", "aprobado"}` en `salidas/riesgo.jsonl`.
La respuesta del humano ES la etiqueta (misma jugada ambiental que exp/43).
Sin `LAYA_MODEL_RIESGO` todo es no-op. `utils/estado_sesion.py` es el
plumbing del último mensaje (lo siembra `GetQuestion.post`).

**Primera observación en vivo** (exp44-observa, checkpoint BASE sin
fine-tune): 3 comandos juzgados + etiquetados. Lecciones: el base es débil
— dijo "no requiere revisión" (0.58) para un `pip install` que el humano
RECHAZÓ, y "modifica estado" para un `python3 -c print(40+2)`; y `mkdir`
bien juzgado. La dirección es clara: el pipeline funciona, el checkpoint
necesita el fine-tune cuando el log acumule (los pares ya caen solos con el
uso del chat y del banco). Nota: el `rm -rf` del escenario nunca llegó al
gate — deepseek-flash se negó solo a ejecutarlo y ofreció alternativa
segura.

## El bench del supervisor — el veredicto medido (2026-10-13)

`banco/bench_supervisor.py` (grading dinámico en código puro: la verdad se
calcula al momento, 6 tareas reales): el supervisor reactivo (Laya elige +
mayoría 2-de-3 + args por DeepSeek) contra un agente DeepSeek PLANO con
tool-calling nativo sobre el MISMO action space y presupuesto:

| vía | calidad | llamadas remotas | reloj |
|---|---|---|---|
| supervisor | 6/6 | **65** | 358 s |
| agente plano | 6/6 | **14** | 26 s |

**4,6× llamadas y 14× tiempo por CERO ganancia de calidad** en esta clase de
tareas de búsqueda/lectura. El veredicto del bench: el despacho se
simplifica — el valor del supervisor nunca estuvo en el Choose, está en los
vetos/self-healing/presupuesto (código, no Laya). El ítem del roadmap
"Choose a escala (~2.400 casos)" queda DESCARTADO por evidencia: no hay
brecha de calidad que cerrar comprimiendo llamadas del despacho. Límite
honesto: n=6, tareas homogéneas de lookup; tareas reactivas multi-paso más
complejas podrían favorecer al bucle reactivo — si se conserva, que sea por
esa clase de trabajo, no por ahorro. Dos bugs del propio instrumento
medidos y cerrados por el conductor: el contador no veía las llamadas del
supervisor (binding: `from utils.call_llm import call_llm` directo — se
envuelve también la referencia del módulo supervisor; primera corrida
reportó 0 llamadas, imposible) y `cargar_tareas` recibía lista donde esperaba
ruta.

## exp/46 — la regla temporal: el "mundial" cerrado por regla dura (2026-10-13)

El falso-directo resistente ("¿quién ganó el último mundial?", conf 0.83
que pasa la compuerta) era un límite de FAMILIA, no de entrenamiento: estos
modelos no juzgan fechas ni recencia (manual de Jev: "no dates — extract
parts in code"). Rounds dirigidos no lo curan. La salida del runbook (regla
dura ANTES que modelo): `regla_temporal(pregunta)` en
`utils/laya_routing.py` — regex generosa (último/actual/hoy/2026/latest,
es/en, con y sin tilde; falso-herramientas es barato: el modelo con tools
responde directo si puede). En **enforce** corta antes de llamar a Laya
(centinela `regla:temporal`, decisión registrada con su causa, sin gasto);
en **shadow** NO corta — Laya corre igual para que la flywheel junte las
etiquetas de exactamente esta clase y valide la regla contra realidad.
Candados: 4 grupos de tests (la sesión cableó pero no los escribió; los
escribió el conductor — el reporte de sesión decía otra cosa, verificación
de conductor no opcional).

## Fix: el caché de errores de Laya vence (2026-10-13)

Medido en la revisión: 31/37 decisiones de producción salieron "sin detalle
de Laya" y el fallo de carga quedaba cacheado PARA SIEMPRE en el proceso —
un OOM transitorio degradaba la sesión entera sin reintento. Ahora
`_errores` guarda `(ts, msg)` y el error VENCE: pasado
`LAYA_ERROR_COOLDOWN` (default 60 s) se reintenta la carga; el acierto
limpia el residual; dentro del cooldown el raise cacheado es rápido (un
checkpoint roto permanente cuesta un reintento por minuto, aceptable). La
ley de degradación no cambia. Tests con módulo laya falso
(`tests/test_laya_cache_reintento.py`).

**Estado del turn (verificación final del conductor): 350 tests + ruff
limpio.** La sesión exp46-aplicar también dejó una lección operativa: corrió
con `USE_LAYA_ROUTER=0` y `LAYA_MODEL_RIESGO=""` por escenario — las
sesiones de ESCRITURA no cargan checkpoints (2×2.86 GiB de RAM que no
aportan); la primera corrida sin eso saturó la RAM de la máquina y mató el
banco.

## Supervisor v2 — el despacho simplificado, el bench aplicado (2026-10-13)

Decisión del dueño tras el veredicto del bench. El bucle reactivo queda; el
Choose se jubila. **Un paso = UNA llamada** que elige herramienta Y args
juntos (`call_llm_agent` con tool-calling nativo sobre `_TODAS`), y las
leyes L8 viven como GUARDAS PURAS del ejecutor (`guarda_vetada`,
`guarda_repetida` — cache de idénticas, veto sin-args, veto tras dos
fallos; testeables sin LLM). El historial VIAJA COMPLETO entre pasos (fin
de los hechos recortados a 160 chars: el modelo ve los resultados reales —
la ganancia medida del agente plano). `Sintetizar` y la sección "Pasos" del
informe se conservan; anti-recursión (L1) intacta; `supervisar`/`REGISTRO`/
`_TODAS`/`create_supervisor_flow` intactos para heartbeat, módulo y bench.
`PREGUNTA_DESPACHO` y `elegir_con_deepseek` se mudaron a
`sonda_supervisor.py` (el checkpoint jubilado se sigue midiendo como
evidencia, por args). `LAYA_MODEL_SUPERVISOR` comentado en `.env` — **los
procesos del supervisor y del heartbeat dejan de cargar 2.86 GiB**.

**Bench post-v2 (mismas 6 tareas, grading dinámico):**

| vía | calidad | llamadas | reloj |
|---|---|---|---|
| supervisor v1 (Laya+mayoría+args) | 6/6 | 65 | 358 s |
| **supervisor v2** | 6/6 | **20** | **50 s** |
| agente plano | 6/6 | 14 | 23 s |

**−69% llamadas y −86% reloj** con la calidad sostenida; el residual contra
el plano (1.4×) es la síntesis final y algo más de uso de tools — el precio
del informe auditable. E2E real verificado (respuesta honesta incluida:
declaró que MAX_PASOS llegó por evidencia indirecta cuando el truncado de
search_files no le mostró la línea). Fix de conductor en el cierre: el
caché de idénticas no veía DENTRO de una tanda (el snapshot de prep es
previo a la ronda y los modelos sí duplican llamadas en una misma ronda) —
estado vivo local en `Ejecutar.exec`.

**Saga de aplicación (3 sesiones + conductor)**: la reescritura murió a
mitad por **saturación de RAM del host** (no de la sesión: corría sin
checkpoints; fue el acumulado del ambiente — la sesión de tests posterior,
con la RAM ya liberada, cerró sin incidente y con la RAM plana). Lección
operativa consolidada: las sesiones de escritura van SIN checkpoints y el
conductor verifica `free -g` antes de lanzar. La sesión de tests jubiló
(con nombre en su reporte): votación 2-de-3 en el despacho,
reintento-con-feedback del prompt de args, umbral del supervisor —
mecánica que ya no existe; el contrato sha1 del despacho quedó congelado
donde vive ahora (la sonda). Un `_diag_replay.py` rastrero de una sesión
anterior se borró en la limpieza. **348 tests + ruff limpio.**

## exp/47 — 12 factor agents: el gap analysis (2026-10-14)

El material oficial de humanlayer/12-factor-agents quedó versionado local
(`banco/material/12factor/`, 13 archivos) y una sesión del banco (patrón
exp/19) auditó el harness factor por factor, con evidencia citada y
verificada por el conductor. **Informe completo:
`salidas/informe_12factor_2026-10-14.md`.** Resumen del tablero: 6 factores
cubiertos con evidencia (1, 2, 3, 4, 9, 10), 6 parciales (5, 7, 8, 11, 12,
apéndice 13) y 1 ausente (6). Las divergencias informadas — lo que el
material recomienda y la casa RECHAZÓ con evidencia propia — son parte del
resultado: pre-rank de tools (exp/15, KV-cache), triaje LLM de errores
(exp/9, autocorrección 67%), errorCounter por tool (reemplazado por
no-progress), persistir messages como memoria (descartado por costo).

**La tesis "PocketFlow envuelve la metodología" se sostiene por el factor
8 con sus propias palabras** ("the number one feature request... interrupt
a working agent and resume later, ESPECIALLY between tool selection and
invocation", factor-08 L73-74): el harness ya ejerce el control flow propio
sin framework pesado; lo que le falta al factor 8 es justo el
break-and-resume — y encaja como un nodo y una arista más, no como un
framework. Los tres gaps derivados, ya en el roadmap como exp/48-50:

| exp | pieza | factor | métrica de corte |
|---|---|---|---|
| exp/48 | persistencia/resume de corridas (thread serializable) | 6 | rehidratar sin violar invariantes; ≥50% rondas ahorradas en ≥20 rondas |
| exp/49 | HITL como arista (`AskHuman` + approved/rejected) | 7/8 | aprobar con el proceso reiniciado; 2 HITL paralelos sin bloqueo |
| exp/50 | pre-fetch como política declarativa (nodo `PreFetch`) | ap. 13 | A/B ON/OFF: ≥1 ronda menos sin subir errores |

## exp/48 — el thread serializable: persistencia/resume del chat (2026-10-14)

Aplicado por el harness (sesión exp48-aplicar) con el conductor auditando el
diff completo. **La pieza**: `utils/thread_store.py` (puro) — `checkpoint()`
appendea el `shared` COMPLETO por línea a `salidas/threads/<id>.jsonl`
(bookkeeping que jamás corta el chat; `THREAD_PERSIST=0` apaga todo),
`cargar()` lee la última línea COMPLETA tolerando cola cortada por crash, y
`valido()` reusa `validar_historial` (los 4 invariantes del modo thinking).
Tres **puntos seguros** en el grafo (mismos sitios que el trace):
GetQuestion.post (pregunta registrada), ExecuteTools.post (ronda
registrada), AgentStep.post answer (respuesta registrada — DirectAnswer
persiste con su nombre de clase real). Subcomando `python3 main.py resume
<id>`: rehidrata, completa faltantes con setdefault, y un thread con
violaciones NO arranca (lado seguro — el modo thinking rompería a la
primera llamada). 368 tests (+20, `tests/test_thread_store.py`) · ruff
limpio.

**E2E del conductor, dos casos reales:**
- **Continuidad**: thread de una corrida completa (13 mensajes, 3 rondas)
  → resume → pregunta de memoria ("¿qué números te di?") respondida SIN
  tools — etiqueta ambiental "directo (0 rondas)": el historial restaurado
  es memoria utilizable (y de paso alimentó la flywheel).
- **kill -9 a mitad**: tarea multi-carpeta asesinada durante la ronda 1
  (último checkpoint: ExecuteTools, rondas=1, 6 mensajes, 0 violaciones) →
  resume con continuación → cierra limpio SIN re-ejecutar la ronda ya hecha
  (el resultado restaurado viaja en el historial). Ahorro total de la ronda
  realizada; la métrica formal (≥50% en tareas ≥20 rondas) queda para el
  tráfico real, n=1 hoy.

**Límites v1 (documentados)**: solo el chat (otros flows después); el
resume abre un LINAJE NUEVO de thread (el id es por proceso — la
continuidad es del contenido, no del id); sin pausa entre selección e
invocación (eso es exp/49, que reusa esta base). Nota operativa del
conductor: `pkill -f "main.py"` mata también al wrapper del conductor si su
línea de comando contiene el patrón — matar por PID exacto.

## exp/49 — la aprobación durable: el HITL sobrevive al proceso (2026-10-14)

Corte pre-registrado en exp/47 ("aprobar con el proceso reiniciado"),
resuelto por la vía PocketFlow-simple (decisión del conductor documentada):
sin reestructurar el flujo con aristas approved/rejected todavía — la base
de exp/48 + dos piezas. Aplicado por el harness, auditado por el conductor.

- **Punto seguro 4 — la SELECCIÓN** (`AgentStep.post`, camino "tool"): el
  checkpoint en el momento EXACTO que el factor 8 pide ("between tool
  selection and tool invocation"). Dos checkpoints por ronda: selección y
  cierre.
- **`reparar_pendientes(shared)`** (PURA, `utils/thread_store.py`): un
  proceso muerto entre selección y ejecución deja el último assistant con
  `tool_calls` huérfanos — viola el invariante de la API y el resume lo
  rechazaría. La reparación appendea, por cada huérfano, un mensaje tool
  HONESTO ("no llegó a registrarse ejecutada — puede haber corrido a
  medias; verificá el efecto antes de repetirla"). Acotada al final (pares
  viejos rotos en el medio son corrupción, los caza el validador),
  idempotente. `resume` la aplica y el banner informa cuántas.
- **`modules/humano.py`** — `request_human_input(pregunta)`: el humano como
  TOOL CALL (factor 7 literal): el modelo puede pedir aclaración antes de
  asumir; una línea por `input()`, EOF/excepción → "(sin respuesta del
  humano: …)" — dato, no crash; sin HITL (preguntar no es un efecto).

**E2E del conductor (el corte, demostrado)**: chat con pedido de escritura,
stdin abierto en silencio por fifo, `kill -9` mientras el `(s/n)` espera →
último checkpoint `AgentStep tool` con la violación esperada ("assistant
con tool_calls sin sus tools"); `resume` → banner "1 llamada interrumpida
reparada" · 0 violaciones → el modelo re-propone el `write_file` →
aprobación `s` → **archivo escrito** ("exp49 ok") y cierre limpio. La
aprobación sobrevivió al proceso que la pidió.

**Hallazgo de la auditoría (no previsto, valioso)**: con stdin por pipe, el
EOF alcanza la aprobación y cuenta como RECHAZO (default seguro) — la ronda
cierra sola y el modelo responde con elegancia. El escenario "muerte con
aprobación PENDIENTE" solo existe con stdin abierto (terminal real o
hitl_web); el fifo lo reprodujo fielmente. Límites v1 documentados:
`request_human_input` es solo terminal (la vía web es 49b con el server
multi-pendiente); la reparación es at-most-once honesto, no exactly-once
(verificá efectos antes de repetir — el mensaje se lo dice al modelo).

**378 tests (+10) · ruff limpio.**

## exp/50 — pre-fetch como política declarativa (2026-10-14)

Corte pre-registrado en exp/47 (fila exp/50 de la tabla de arriba): "A/B
ON/OFF: ≥1 ronda menos sin subir errores". Aplicado por el harness (sesión
exp50-aplicar2) y cerrado por el conductor — tests, `.env.example` y A/B
(la sesión entregó código sin sus tests: tercera vez del patrón exp/44).
Nota operativa: el primer intento (exp50-aplicar) se colgó 30 min en 7
HITL; el reintento aplicó en 220 s (3/3 turnos OK) cuando el conductor le
respondió la pregunta abierta (los 4 fallos de `test_replay.py` eran un
artefacto de `USE_LAYA_ROUTER=0` heredado por el pytest hijo).

**La pieza** — `utils/prefetch.py` (PURO en su lógica de matching, sin LLM):

- `decidir(pregunta)` — regex de rutas `[\w./-]+\.[A-Za-z]{1,4}` sobre la
  pregunta; se queda con las que EXISTEN dentro del perímetro
  (`AGENT_ALLOWED_DIRS`, reusando el resolvedor de contención de
  `fs_tools` — NO se reimplementa), hasta `PREFETCH_MAX_ARCHIVOS=2`, y las
  lee hasta `PREFETCH_MAX_LINEAS=80`. Nunca lanza: error de lectura → esa
  ruta se salta.
- `mensaje(prefetches)` — un solo mensaje user con prefijo FIJO
  `[pre-fetch]` (patrón compacción) y el formato `[pre-fetch] {path}
  (primeras {n} líneas):\n{contenido}`; `None` sin matches (ley de
  ausencia: sin match la pieza es no-op).
- `nodes.PreFetch` corre entre GetQuestion y el router/paso: appendea el
  mensaje user-tras-user (legal para la API; `validar_historial` verde
  antes y después) y siempre devuelve "continue". `PREFETCH=0` apaga todo.
- **El router lee la PREGUNTA, no el prefetch**: `LayaRouter.prep` (y el
  prep del propio nodo) recorre hacia atrás y saltea los user que empiezan
  con el prefijo — sin eso el router tomaba el mensaje sintético como
  pregunta. `replay._grafos_vivos` agrega las aristas TRANSITIVAS de
  `PreFetch` (A -accion-> PreFetch -accion-> X ⇒ A -accion-> X) para que
  las caminatas históricas sigan siendo válidas: cambió la FORMA del grafo,
  no el fondo.
- Nota de `tests/test_replay.py`: los 4 tests que dependían del entorno
  quedaron herméticos (fixture de módulo que pina `USE_LAYA_ROUTER=1` con
  save/restore).

**Tests** — `tests/test_prefetch.py` (11): matching / inexistente / fuera
del perímetro (contención: `/etc/passwd` → vacío) / tope / apagado; forma
del mensaje y `None`; el nodo appendea sin romper `validar_historial` y es
no-op sin match; el prep saltea prefetches viejos; `LayaRouter.prep`
devuelve la pregunta; marcador del banco con fixture NEGATIVO (el template
del código no matchea — lección H2/Fix 10). `.env.example` documenta los
tres settings. **Gate del cierre (2026-10-19): 569 tests verdes · ruff
limpio.**

**El A/B** — escenarios versionados `banco/escenarios/exp50-ab-on.yaml` /
`exp50-ab-off.yaml`: misma batería de 5 turnos, mismo `.env`, solo cambia
`PREFETCH=1|0` (corrida: `python3 banco/banco.py
banco/escenarios/exp50-ab-on.yaml`).

| brazo | preguntas de archivo (3) | turnos | HITL | pared |
|---|---|---|---|---|
| ON (`PREFETCH=1`) | **0 rondas** (prefetch) | 5/5 OK | 0 | 25 s |
| OFF (`PREFETCH=0`) | **2 rondas** c/u (search_files → read_file) | 5/5 OK | 0 | 34 s |

- **Criterio pre-registrado: ✅ cumplido** — 6 rondas menos en 3 preguntas
  (≥1) sin subir errores (0 errores de turno en ambos brazos).
- Las tres respuestas son correctas en ambos brazos (verificadas a mano en
  el transcript); la 4.ª pregunta (prefijo textual) no mide el pre-fetch:
  la responden directo los dos.
- **Límites**: n=3 preguntas medidas, un escenario, una corrida por brazo
  (LLM estocástico); el banco mide turno OK (cierre sin error/HITL), no
  corrección semántica. Artefactos: `salidas/banco/exp50-ab-on_130600.*` y
  `exp50-ab-off_130627.*` — `salidas/` no se versiona.

## Jornada 2026-10-19 — tres repos de reglas, un ratchet y un contrato (mejoras al harness)

Pedido del operador: mirar qué hacen `monk-eee/git-agent-ratchet`,
`Emmanuel-Bamidele/AI-Agent-Coding-Rules` y `kernullist/ruleward`, y usarlos
para mejorar el harness. Investigación, fuentes y descartes en
[informes/ratchets_y_reglas_agente_2026-10-19.md](informes/ratchets_y_reglas_agente_2026-10-19.md).

**Diagnóstico (medido, no estimado):** el harness ya tenía gate fuerte
(`calidad.sh`), inventario de tests y test de deriva de docs. Lo que faltaba
era (a) un contrato de agente versionado, (b) un linter de ese contrato y (c)
métricas estructurales con baseline. Medición del árbol: 8 nombres de helpers
privados bifurcados (20 ocurrencias; `_git_sha` y `_fmt_pct` con 4 copias
cada uno), 0 marcadores `TODO`/`FIXME`/`HACK` reales (el ratchet G del repo
original acá sería una sinecura), los 30 tests citados en `estado.md`
existen, y de 36 paths citados solo 4 son ejemplos de prosa (no deriva).

**Lo construido:**

- **`ratchet.py` + `ratchets/baseline.json`** — mecanismo de
  git-agent-ratchet adaptado: `helpers_duplicados` (deuda, menor mejor) y
  `tests_definidos` (cobertura, mayor mejor) contra un baseline versionado;
  auto-baja al mejorar; guardia anti-bypass (baseline editado a mano vs
  `HEAD`/`HEAD~1`, clave `HUMAN_RATCHET_BYPASS_KEY` para el operador);
  `--actualizar` humano y `--no-escribir` diagnóstico. Palanca 3 de
  `calidad.sh`, `python3 main.py ratchet`, CI con `fetch-depth: 2`.
  Siembra: 20 helpers · 491 tests; tras los tests nuevos: 516. 18 tests
  propios. **El ratchet se detectó a sí mismo**: la primera corrida encontró
  `_resumen` repetido entre `ratchet.py` y `utils/compaccion.py`; se renombró
  en vez de sembrar 22. La lección es el mecanismo: el ratchet es un
  instrumento que corre sobre el árbol real, no un adorno.
- **`AGENTS.md`** (92 líneas, presupuesto 160) — estructura de
  AI-Agent-Coding-Rules adaptada al repo: qué leer primero, 8 reglas no
  negociables **cada una con su gate**, blandas declaradas, bypasses
  prohibidos por nombre y definición de terminado. El patrón "regla → gate"
  es de git-agent-ratchet. El contrato ya está activo: esta misma sesión lo
  recibió al aparecer.
- **`tests/test_deriva_reglas.py`** (7 tests) — ruleward determinista:
  presupuesto de AGENTS.md, rutas y tests citados que existen, tabla de
  enforcement válida y cada test que `estado.md` dice que cubre un hallazgo
  existe (la regla del tablero deja de ser honor system).

**Descartado con motivo:** los otros seis ratchets del original (print,
chatter, PowerShell, temporales, imports privados y max-file-lines: no
aplican, hay 0 marcadores reales, o contradicen la decisión medida de
funciones largas), el NLI semántico y SARIF de ruleward (dependencia y ruido
sin consumidor), y copiar los 22 archivos de reglas de Bamidele (bloat de
contexto: un archivo alcanza). Detalle en el informe.

**Verificación:** `./calidad.sh` verde con 4 palancas; **594 tests**
recolectados, ruff limpio, complejidad de fronteras limpia.

**Límites:** el ratchet congela deuda, no la paga (el paydown quedó en el
roadmap: unificar `_git_sha`/`_fmt_pct`); no hay pre-commit, el gate es
`calidad.sh`/CI; el anti-bypass es disuasión auditable, no un sandbox.

## Jornada 2026-10-19 (2) — código de IA vs humano: evidencia, medición y gates de forma

Segunda parte del pedido del operador (la primera fue ratchets y contrato):
el objetivo real es **bajar la lógica de código de IA** —funciona, pero deja
ruido— y acercarla a la forma humana, más prolija y minimalista. La
investigación debía traer evidencia online (papers, docs oficiales,
comunidad) e identificar repos que asimilen el código a forma humana.
Investigación completa, tablas y fuentes en
[informes/codigo_ia_vs_humano_2026-10-19.md](informes/codigo_ia_vs_humano_2026-10-19.md).

**Respuesta a "¿Matt Pollock tiene algo así?"**: el nombre correcto es
**Matt Pocock** y sí: [`mattpocock/skills`](https://github.com/mattpocock/skills)
(296k estrellas) — no es un humanizer, es disciplina de ingeniería (lenguaje
compartido/glosario, diseño de módulos profundos, TDD, code-review con
baseline de smells). El ruido baja como efecto de la disciplina, no de
reescribir texto.

**Evidencia que decidió el diseño** (resumen; detalle en el informe):

- *Show and Tell* (arXiv 2511.13972): directivas explícitas de concisión
  bajan el código 56–70% y persisten en el turno siguiente; los ejemplos
  solos no; un pedido genérico de "mejorar legibilidad" infla todo.
- *Debt Behind the AI Boom* (arXiv 2603.28592): 304k commits de IA en 6.275
  repos; el smell #1 es **broad exception handling** (41.723 casos) y el
  24,2% de los issues sobrevive al HEAD.
- *SlopCodeBench* (arXiv 2603.24755): la degradación es iterativa —erosión
  sube en 80% de las trayectorias, verbosidad en 89,8%—; el prompt mejora el
  inicio pero no frena la caída. ⇒ hacen falta gates, no solo prosa.
- *AI-Generated Smells* (arXiv 2605.02741): Long Method/God Class/"Modular
  Mirage"; "Volume-Quality Inverse Law"; few-shot no mitiga.
- GitClear 2026 (623M cambios): refactoring −70%, duplicación de bloques
  +81%, error-masking +47%. DORA 2024: la IA mejora la productividad
  individual pero castiga estabilidad/throughput. METR 2025: 19% más lentos
  con IA aunque la percepción diga +20%.
- Docs oficiales: Claude Code ("CLAUDE.md corto y humano; uno inflado se
  ignora"; un review que busca gaps de más genera sobre-ingeniería) y
  Anthropic (contexto = conjunto mínimo de tokens de alta señal; tools
  mínimos).
- Comunidad: Ponytail (167k ★, pirámide YAGNI "lazy, not negligent"),
  code-humanizer (16 patrones + reglas de hierro), slop-scan (benchmark
  6,91× vs OSS maduro), anti-slop.

**Medición propia** (69 archivos del harness vs 18 de `requests` como
referencia humana): `except` amplios **55 (39,0% de los try) vs 1 (1,6%)**;
`except: pass` 9 vs 6; banners **61 vs 8**; try-import 14 vs 11; docstrings
0,52 vs 0,68; ratio defensivo 0,0256 vs 0,0358; erosión estructural
(SCBench, masa CC>10) **0,204 vs 0,390**; comentarios/SLOC 8,1% vs 10,4%.
Lectura: el ruido **no** es "demasiados comentarios" ni funciones gigantes
—el repo comenta en proporción similar al humano y está menos erosionado—;
el ruido es **excepción amplia (smell #1), decoración y duplicación**.

**Lo construido:**

- `ratchet.py` gana `excepts_amplios` (deuda, menor mejor): siembra 55; un
  `except Exception` nuevo frena el gate. No se prohíben (hay best-effort
  legítimos): no crecen sin decisión humana.
- `tests/test_estilo_humano.py`: banners decorativos = 0 (**61 → 0**),
  docstrings de relleno = 0, wrappers vacíos sin justificar = 0, y el
  `system_prompt` debe pedir el mínimo código sin pasar 1.400 chars.
- Directiva en `main.system_prompt` ("el mínimo que funciona… sin defensas
  ni docstrings que el pedido no exija… validación, seguridad y
  accesibilidad no se recortan"): la palanca de forma que midió Show & Tell,
  aplicada al producto.
- `AGENTS.md` R9 + sección "forma humana" (pirámide de Ponytail, tell de
  reimplementar, defensas solo en la frontera, docstrings para el porqué,
  nada de banners ni `_v2` en paralelo).
- Informe con evidencia primaria, tabla de repos, catálogo de 11 patrones
  (determinista vs review) y límites.

**Descartado con motivo:** deslop automático masivo (las reglas de hierro de
code-humanizer exigen preservación de comportamiento y tests; acotar 55
`except` es cambio semántico → paydown medido en el roadmap); herramientas
JS/TS (otro stack); NLI semántico (ruido).

**Verificación:** `./calidad.sh` verde (4 palancas); suite con los tests
nuevos; baseline del ratchet: 20 helpers · tests definidos actualizados · 55
except amplios. Límites: los gates cubren el subconjunto determinista; la
comparación `requests` es de otro dominio (ubica magnitud, no fija ideal); la
evidencia de industria tiene intereses comerciales declarados.

## Paydown de except amplios y exp/51 — la directiva de forma, medida (2026-10-19)

Continuación de la jornada, cerrando los dos ítems que el roadmap dejó
abiertos.

**Paydown del smell #1.** De los 55 handlers amplios que siembra el ratchet,
**34 no tenían motivo visible** (30 sin `noqa` y 4 con `noqa` pero sin
motivo). Se acotaron 7 a la excepción real que
esperan manejar (logs JSONL → `OSError`; `_arrancar()` del HITL →
`(OSError, ValueError)`; `git rev-parse` de la sonda →
`(OSError, subprocess.SubprocessError)`) y los 23 restantes son fronteras
best-effort legítimas (Laya opcional, hooks, bookkeeping, trazas,
integraciones externas): quedaron con `# noqa: BLE001 (motivo)`.
`tests/test_estilo_humano.py` gana el gate: **todo `except` amplio necesita
motivo visible** — de 34 sin motivo a 0. Ratchet: **55 → 48** (las
acotaciones bajan el número solas, como debe ser).

**exp/51 — la directiva de forma.** Corte **pre-registrado antes de correr**
(está en el docstring de `banco/probes/forma_codigo.py`): la directiva es
éxito si baja la mediana de SLOC y la densidad de docstrings sin subir los
errores de sintaxis; diferencia <10% en SLOC = no concluyente. Método: A/B
del `system_prompt` con la única diferencia de `DIRECTIVA_FORMA`, 2 tareas de
escritura de código (CSV-stats y config-loader), n=4 por brazo y tarea = 16
llamadas, deepseek-flash, 212 s. Artefacto crudo:
`salidas/probes/forma_codigo_20261019_092456.json` (salidas/ no se versiona;
la sonda es reproducible).

| métrica (mediana de las 8 salidas por brazo) | sin directiva | con directiva | delta |
|---|---|---|---|
| SLOC | 193 | **44** | −77% |
| tokens estimados (chars/4) | 2.064 | **383** | −81% |
| funciones | 11 | 2 | −82% |
| densidad de docstrings | 0,487 | **0** | −100% |
| `try` | 3,5 | 1 | −71% |
| chequeos de `None` | 1,5 | 0 | −100% |
| comentarios | 55 | 12 | −78% |

El efecto se sostiene por tarea: csv_stats 162,5 → 47 SLOC; config_loader 266
→ 35. **Veredicto: criterio cumplido** en forma y docstrings; el código
extraído no tuvo errores de sintaxis en ningún brazo (0/15), aunque en
`con_forma` una de 8 respuestas vino sin bloque de código (1/16 del total):
con n=4 no alcanza para decir que la directiva aumente los fallos de formato.
**Límites:** n chico, un modelo, una corrida; el efecto es tan grande que
vale repetirlo con n mayor y otro modelo antes de generalizar (roadmap).

**Réplica (n=8, dos modelos, tokens reales).** Con `--runs 8` y el usage de
la API en vez de chars/4: deepseek-flash SLOC 201 → 41,5 (−79%), completion
tokens 6.080 → 1.486 (−76%), tokens totales (prompt+completion) 6.367 → 1.858
(−71%); deepseek-chat SLOC 152 → 50 (−67%), completion 1.486 → 510 (−66%),
totales 1.747 → 840 (−52%). Docstrings 0,56/0,63 → 0 en ambos. El prompt
cuesta +26/30% de entrada (la directiva) pero la ganancia neta es grande; por
tarea también se sostiene. Caveat: 2/16 respuestas de flash con directiva
vinieron sin bloque de código (código extraído: 0 errores de sintaxis; en
chat 0/16). Artefactos: `forma_codigo_20261019_093809.json` (flash) y
`..._094021.json` (chat), en salidas/probes/.

**Chat real (tools + HITL).** `banco/probes/forma_chat.py` + escenarios
`exp51-chat-on/off.yaml` (escribir un módulo con `write_file` y editarlo con
`edit_file`; HITL aprobado por scope; único cambio: `PROMPT_FORMA=1|0`), n=2
por brazo: SLOC 133,5 → 32 (−76%), funciones 5,5 → 2,5, docstrings 1,00 →
0,33, `try` 3 → 0,5, None-checks 2,5 → 1,5, comentarios 41 → 12. Las
sesiones además fueron ~15% más rápidas (33/29 s vs 26/25 s). 4/4 OK.
Artefacto: `salidas/probes/forma_chat_20261019_095012.json`. Límite: n=2,
mismo modelo.

**Paydown de duplicación (misma jornada).** El "signature tell" #1 de
code-humanizer seguía en el harness: **4 copias de `_git_sha`** (dos
semánticas distintas: sha largo con motivo vs. corto vacío), **4 de
`_fmt_pct`** (una de ellas formateaba un valor que YA venía en porcentaje) y
`_leer_eventos` en evals con wrapper en replay e imports privados en
triaje/minar. Se extrajo a `utils/git.py` (`sha_corto`/`sha_largo`/
`sha_o_motivo`), `utils/formato.py` (`pct`) y `utils/trazas.py`
(`leer_eventos`); `triaje` conserva `_pct_directo` con su unidad documentada.
Se van también los `from evals import _git_sha` (bench_juez,
banco/bench_supervisor) y los `from evals import _leer_eventos` (replay,
triaje, minar). **Ratchet de helpers: 20 → 10**; `excepts_amplios` bajó a 44
por los `_git_sha` que se fueron. Tests: `tests/test_utils_compartidos.py`
(7), incluido el best-effort cuando git no está.

## Sesión de prueba completa (2026-10-05): 19 turnos, las 18 capacidades

Una sola sesión continua de chat ejerciendo todo el harness. Resultado
por capacidad: router directo ✓, list/read/search ✓, write_file con HITL
(crea y sobrescribe) ✓, answer_verified con citas ✓, sql ✓, mcp_tools +
mcp_call (1847×293=541171, correcto) ✓, search_web (honesto: los snippets
no traían el tag de versión) ✓, rag_index + rag_search (35 fragmentos,
dedup en design.md al top) ✓, run_effective_n ✓, run_informe (22
archivos, 33.974 registros — creció con los datasets nuevos) ✓,
run_auditoria (round1 vs round3) ✓, run_supervisor (42 .py, el más
grande correcto, notó hasta el path truncado en los hechos) ✓,
debate/research ✗ (ver hallazgo 1).

Hallazgos y sus fixes:

1. **El separador DSML es DOBLE barra** (`<｜｜DSML｜｜`): la primera
   versión de la recuperación usaba una sola (copiada de un transcript
   pegado a mano que la colapsaba) y NUNCA disparó — el debate y el
   research de la sesión se perdieron. Fix: regex flexible `[｜|]{1,2}`,
   verificada contra los tres bloques reales del log (los tres parsean)
   y con test de ambos formatos. El patrón de fondo: el DSML aparece
   cuando el modelo va SIN tools (camino directo del router) pero quiere
   llamar igual — tres de los falso-directo del router terminaron en
   DSML; con la recuperación andando, ese error del router se
   auto-corrige.
2. **Repetición idéntica con args en el supervisor**: search_files con
   el mismo glob corrió 4 veces (el veto solo cubría sin-args). Fix:
   firma canónica herramienta+args → cache (la idéntica no re-ejecuta,
   reutiliza el resultado) + veto a la segunda firma repetida.
3. Ruido cosmético: httpx/asyncio "Event loop is closed" al cerrar los
   clientes async (×6 por sesión) — sin impacto, pendiente de silenciar.
   Warning de fastembed (mean pooling) — informativo, sin acción.
4. El falso-directo del router se confirmó en vivo dos veces más
   (MCP 0.82, debate 0.78) — candidato al ensamble 2-de-3 cuando toque.

## Vision/PDF y A2A: la cola final, dos capacidades (2026-10-05)

Últimos dos ítems del roadmap. Dos módulos nuevos (`modules/vision.py`,
`modules/a2a.py`), sin dependencias nuevas (`requests` ya estaba), con
`TOOLS`+`IMPL` como el resto. Nunca tocan el historial del chat: la
imagen/el archivo viaja en un turno de usuario aislado y lo que vuelve es
solo el texto de la respuesta.

### Vision/PDF — `modules/vision.py`

Dos caminos distintos, cada uno por una razón medida:

- **`ver_imagen(path, pregunta)`** — la imagen va como **data-URL base64**
  dentro de un message de **USER** con `content=[{type:text},
  {type:image_url}]`. El mensaje system/assistant NO puede llevar
  imágenes: la API responde **400** (medido) — por eso la imagen viaja en
  un turno de usuario propio y no se inyecta al historial. La llamada es
  `call_llm` (contenido como array), **SIN** el `extra_body` de thinking:
  `call_llm_agent` agrega thinking+tools y eso no aplica acá.
- **`ver_pdf(path, pregunta)`** — los PDF NO van por base64: van por la
  **Files API**. `POST /files` multipart (`file` + `purpose=file-extract`)
  → `file_id`; luego `POST /chat/completions` con
  `content=[{type:file,file_id},{type:text}]` → el texto llega en
  `message.content`. **Sin estado**: cada `ver_pdf` sube, consulta y listo
  (no se guarda el `file_id`). El tope lo impone la Files API (64 MiB).

**El tipo se valida por CONTENIDO, no por nombre** (magic bytes): `\xff\xd8\xff`
JPEG, `\x89PNG\r\n\x1a\n` PNG, `GIF87a/GIF89a`, `RIFF....WEBP`; un PDF
empieza con `%PDF`. Un `.png` que en realidad es JPEG se acepta como JPEG;
un `.png` de texto se rechaza. **Límites chequeados ANTES de llamar**:
imagen 32 MiB y body 48 MiB (base64 crece ~4/3); superarlos devuelve un
`ERROR` legible sin tocar la red. API key/base de los settings existentes
(`LLM_API_KEY`/`LLM_BASE_URL`).

### A2A — `modules/a2a.py`

El eje de `mcp` pero del lado de los AGENTES: en vez de tools dentro de un
servidor, hablamos con agentes remotos que exponen el protocolo
**agent2agent**. Setting `A2A_AGENTS` en `.env`: JSON
`{"nombre": "http://host:puerto"}`.

- **`agentes_remotos()`** — lista los agentes del setting con su agent card
  (`GET {base}/.well-known/agent.json`, timeout 5s). Card inaccesible ⇒
  `inaccesible` **y el resto sigue** (degradación, no crash).
- **`a2a_tarea(nombre, mensaje)`** — `POST {base}/` JSON-RPC 2.0
  `method=message/send`, `params={message:{role:"user",parts:[{type:"text",
  text:mensaje}]}}`, `id` incrementado por proceso. Devuelve el `result`
  (serializado) o el error del JSON-RPC como texto. Timeout 60s.

Sin setting (o vacío, o JSON roto ⇒ se trata como vacío) las tools
devuelven "no hay agentes configurados" sin tocar la red.

Tests sin red (`tests/test_smoke.py`): la imagen y el PDF se validan
mockeando `requests.post` (forma del data-URL, `purpose`, `file_id` dentro
del `content`, y que >límite/tipo inválido devuelven ERROR *sin* llamar);
A2A corre contra un `http.server` fake (card + JSON-RPC), con un agente
caído verificado como `inaccesible`.

## El coding agent: run_command y edit_file (2026-10-05)

El agente de archivos se volvió agente de código con un módulo nuevo
(`modules/coding.py`, el patrón TOOLS+IMPL — el CORE no cambió una línea)
y dos herramientas bajo el mismo contrato HITL que `write_file`:

- **`run_command`**: shell con aprobación `(s/n)`, preview del comando.
  Rieles mecánicos: timeout de 120s, salida truncada a 4k chars (viaja
  al historial y al costo), stdin cerrado (nada espera input
  interactivo), CWD del proceso. Diseño explícito: para shell la
  aprobación humana ES la contención — un comando llega a donde las
  raíces permitidas de las tools de archivos no llegan. El rechazo
  vuelve al modelo como texto (información para corregir, no error).
- **`edit_file`**: reemplazo exacto y único de `old_string` por
  `new_string` con diff unificado y aprobación. Falla ruidosamente si
  el texto no aparece, aparece N veces, o es idéntico al reemplazo —
  obliga al modelo a volver al archivo en vez de reescribirlo de
  memoria. Es la lección medida del clobber de `fs_tools.py`
  (write_file de archivo entero lo dejó en 16 líneas).

El supervisor NO suma estas tools: su contrato de 18 opciones está
congelado con el checkpoint de Laya (agregarlas exige re-entrenar el
dispatch). Chat-first; supervisor recién si medimos necesidad.

Verificación en vivo (sesión completa por el flujo real del chat, con
aprobaciones HITL reales vía driver pty):

- crear `demo.py` con `write_file` usando un path RELATIVO
  (`salidas/tmp_coding/demo.py`) — resolvió por el candidato CWD del
  fix de `_resolve` (el issue 6 de la caza, funcionando en producción);
- verificar con `run_command` (`python3 -c "...print(suma(2,3))"` →
  exit 0, salida `5`);
- corregir con `edit_file`: diff de UNA línea (`a + b` → `a - b`),
  aplicado y re-verificado con `cd ... && python -c`;
- precisión de instrucciones: el agente notó que el docstring quedó
  desactualizado ("Devuelve la suma") y NO lo tocó porque el pedido era
  solo el retorno.

31/31 tests (HITL sí/no, timeout, truncado, y las tres fallas
ruidosas del edit).

## HITL graduado + hooks (mesa 2, 2026-10-05)

El contrato binario del HITL (todo `run_command` paga un `s/n` — 272 en
una sola sesión) encuentra su gradación sin aflojar la contención, en dos
piezas nuevas.

**`utils/policy.py` — clasificador determinista, sin LLM.** Mismo comando
⇒ misma clasificación, siempre. Tres niveles de fricción:

- **`auto`**: solo-lectura verificado. Whitelist conservadora de prefijos
  exactos de primeros tokens (`pytest`, `python3 -m pytest`, `grep`, `ls`,
  `cat`, `head`, `tail`, `wc`, `find`, `file`, `echo` sin redirección,
  `git status/log/diff/show/blame`). Se ejecuta directo.
- **`preguntar`**: el flujo de hoy (un `s/n`). **Default de todo lo no
  reconocido** — la política solo RELAJA lo que reconoce.
- **`confirmar_doble`**: `git push` y `rm -rf` piden dos `s/n` seguidos.

Reglas de composición (la parte crítica):

- El comando se parte por `&&` y `|`. **Todos** los segmentos deben ser
  `auto` para que el compuesto sea `auto` — basta uno sospechoso
  (`ls && rm -rf /`) para que todo pregunte.
- Cualquier redirección (`>` `<` `>>`), sustitución `$(...)`, backticks o
  `xargs` degrada a `preguntar`: escriben o ejecutan cosas que no se
  pueden clasificar por prefijo.
- `python3 -c` pregunta SIEMPRE: es código arbitrario disfrazado de
  comando de una línea (aunque hoy lo usemos para repros).

Orden: whitelist primero, negra después, default `preguntar`.

**Integración en `run_command` (`modules/coding.py`).** Con `HITL_AUTO=1`
(default) se clasifica ANTES del preview: `auto` ejecuta imprimiendo una
línea visible `── run_command [auto: solo-lectura] ──` + el comando (el
usuario lo ve igual — transparencia); `preguntar` es el flujo de hoy;
`confirmar_doble` hace dos `(s/n)` y cualquiera que sea no aborta. Con
`HITL_AUTO=0` todo vuelve al `s/n` clásico (compatibilidad).

**Hooks post-tool (`utils/fs_tools.run_tool_call`).** Mecanismo genérico
`HOOKS_POST = {nombre_tool: [fn]}` donde `fn(tool_call_dict, resultado_str)
-> str` puede enriquecer el resultado antes de que viaje al modelo. Se
registra UNO: tras `edit_file`/`write_file` sobre un `.py`, corre
`python3 -m py_compile` (subprocess, timeout 15s) y si falla agrega
`⚠ SINTAXIS: <error>` al resultado. Es el patrón **error-como-feedback**:
el modelo ve el problema y se autocorrige en la vuelta siguiente —
habría pescado el clobber de `fs_tools.py` al instante. Contrato de
hierro: un hook NUNCA rompe la ejecución (si py_compile no existe, el
archivo no es `.py`, o cualquier cosa falla raro, el resultado queda
intacto).

**Hooks pre-tool (`utils/fs_tools.HOOKS_PRE`).** El complemento que
faltaba: `HOOKS_PRE = {nombre_tool: [fn]}` donde `fn(tool_call_dict) -> str|None`.
Si el hook devuelve texto, **CANCELA** la ejecución (ese texto es el
resultado); si devuelve `None`, no opina. **Fail-closed** (consolidación
2026-10-15): un hook PRE que lanza VETA — es una guarda y "no pude
decidir" no puede significar "adelante"; el veto vuelve como texto de tool
y el chat sigue. Los hooks POST conservan el contrato fail-open. Corre ANTES de la
implementación porque hay guardas que un hook post ya llega tarde a
evaluar (un comando que ya corrió). El primer uso es el residual de la
mesa 2:

- **Denylist dura de `run_command`** (`modules/coding.py`): los comandos
  de daño irreversible en el host — `rm -rf /` y la fork bomb
  `:(){ :|:& };:` — se vetan **sin s/n** (no hay aprobación que los
  salve) y el veto vuelve al modelo como `ERROR` para que reformule. La
  lista es corta a propósito: la política graduada ya cubre el resto con
  fricción; acá solo va lo que nunca debería ejecutarse desde un chat
  automático. El hook se registra desde el propio módulo
  (`_registrar_hooks()` al importar), así la política viaja con su
  módulo, no con el CORE.

81→88→92 tests: los tres niveles de `clasificar()`, TODAS las reglas de
composición, `run_command` con HITL_AUTO=1 seguro sin input (monkeypatch
que explota si se llama) y no-seguro pidiendo, doble confirmación
abortando, y el hook tras edit/write de `.py` roto vs. bueno.

## Pulido de terminal (mesa 8, 2026-10-05)

`utils/terminal.py` (stdlib, sin dependencias) da las dos piezas que
faltaban del pulido de terminal, ambas degradando a texto plano cuando la
salida no es una terminal:

- **`colorear(texto, tipo)`** — códigos ANSI por TIPO de evento (`tool`
  cian, `ok` verde, `error` rojo, `info` gris, `aviso` amarillo,
  `respuesta` negrita). Solo pinta si `sys.stdout.isatty()` y no hay
  `NO_COLOR` (el estándar) ni `COLOR=0` (escape hatch propio). Sin tty —
  tests, pipes, logs — devuelve el texto intacto: nada cambia en CI.
- **`progreso_ronda(ronda, tope)`** — etiqueta `⚙ ronda 2/8` (o `⚙ ronda
  2` sin tope) para las rondas de herramientas.

Integración en `nodes.ExecuteTools`: cada tool se **anuncia ANTES de
correrla** (`→ read_file`, para que una espera de varios segundos no
parezca colgada) y, en `post()`, la ronda consumida se etiqueta con su
avance sobre `MAX_TOOL_ROUNDS`. Los avisos de recuperación DSML y de
sanitizado pasan por `aviso` (amarillo). Los hooks y el resto del flujo no
se tocan.

5 tests: color con/sin tty, `NO_COLOR`/`COLOR=0`, tipo desconocido, el
formato de `progreso_ronda`, y que `ExecuteTools` anuncie cada tool y
etiquete la ronda (forzando `isatty=False` para ver el texto plano).

## Candados de contrato y fixes de la auditoría de sesión (2026-10-05)

Auditoría de una sesión real del usuario (revisión de consistencia
semántica, informe en `salidas/revision_consistencia_2026-10-05.md`).
Sus mediciones se verificaron independientemente — el sha1
prod≡sonda del router (`01bf4478f15c…`) era exacto — y su lote de
"candados, no refactors" se aplicó completo:

1. **`sonda_router.py` importa `PREGUNTA_ROUTER` de `nodes`** — una sola
   fuente; la copia local podía derivar sin que ningún test lo notara
   (drift medido como 0 hoy, riesgo latente alto).
2. **`test_contratos_laya_congelados_sha1`** — congela el CONTENIDO
   completo (sha1 canónico) de ambos contratos; el test de claves no
   alcanzaba (cambiaba una palabra de instructions y nada fallaba).
3. **Fix de `search_files` con `path` a archivo**: `os.walk` sobre un
   archivo no visita nada → falso negativo silencioso ("Ningún archivo
   contiene X" sobre un archivo que sí lo contiene). El informe lo
   midió pero lo atribuyó a "strings cortos"; repro y root-cause
   nuestros: es el path-a-archivo (ahora se trata como único habitante
   de su directorio padre).
4. **`evento_tool` en la traza**: las tools que no son flujos
   (run_command, sql, write_file) no atravesaban nodos — una ronda de
   50s era inatribuible desde `.runs/` (ciego medido en esta
   auditoría). ExecuteTools registra ahora nombre + ok/error + duración
   por llamada.
5. **design.md**: default de informe corregido (decía `bmo/data`; el
   código usa `.` con `INFORME_CARPETA` en .env).

No aplicado (correctamente diferido por el informe): unificar
vocabulario de `shared`/actions — 7/9 claves compartidas son benignas,
los archivos fríos no justifican el refactor (churn medido), y las 2
colisiones reales (`analisis`, `feedback`) se documentan, no se tocan.

**Cierre (2026-10-05, candados ejecutados):** los tres "hacer ya" de la
recomendación quedaron aplicados, y las 2 colisiones quedaron
**documentadas en el código** (no solo en este registro):

1. `sonda_router.py` ya importa `PREGUNTA_ROUTER` de `nodes` (drift
   imposible); se sumó `sonda_supervisor` a la misma garantía con test
   (`PREGUNTA_DESPACHO is supervisor.PREGUNTA_DESPACHO`).
2. Los contratos de Laya están congelados por sha1 (router, despacho, voto):
   cambiar una palabra rompe el test.
3. Comentarios de contrato en `informe.py`/`effective_n.py` (`analisis`) y
   `juez.py`/`research.py` (`feedback`) declaran la forma esperada y la
   colisión consciente — barato, sin refactor.
4. Lo diferido (idioma de claves, `rounds`→`ronda`, vocabulario de actions)
   sigue **sin hacerse por falta de evidencia** (7/9 claves compartidas son
   benignas; los flujos fríos no justifican el churn).

## Sesión integral 2026-10-05 (post-coding agent): 18 turnos, todo verde

Prueba completa por el chat real (driver pty, aprobaciones HITL
automáticas): 26 llamadas a tools, 16 herramientas distintas, 0 errores.
Cobertura: tools CORE, coding (write→run→edit→run con verificación de
doble(4)==8 → triple(4)==12), sql+db_schema, answer_verified con cita
verificada (`tests/test_smoke.py:613`), debate (async, 2 rondas + juez),
informe map-reduce async-paralelo, web, RAG (index+search), supervisor
sub-agente, effective_n, MCP real (servidor `matematica`, 4 tools),
inglés espejado en el turno 1. La traza nueva con `evento_tool` dejó
cada llamada nominada en `.runs/`.

Tres hallazgos en vivo:

1. **El falso-directo atacó y el voto lo mató**: "debatí en 2 rondas…"
   → Laya `directo conf 0.99` (la debilidad conocida del checkpoint con
   imperativos) → voto 2-de-2 → `herramientas` → el debate corrió. La
   defensa de mayoría trabajando en producción, no en la sonda.
2. **El supervisor heredó las coding tools por el lado DeepSeek**: su
   `catalogo()` deriva del action space dinámico, así que `run_command`
   fue electable (y electo, con HITL aprobándose DENTRO del sub-agente).
   La congelación aplica al contrato de Laya (18 opciones), no al
   catálogo. Decisión implícita que queda documentada acá: se acepta —
   el self-healing del supervisor (feedback, vetos) y el HITL protegen;
   re-entrenar el dispatch para sumarlas es costo sin necesidad medida.
3. **El guard del ZeroDivision se ejercitó solo**: los 3 .jsonl más
   chicos de .runs tienen 0 registros → `effective_n` con total==0
   produjo su informe en vez de crashear (el fix de esa mañana,
   validado sin buscarlo).

Y el modo thinking pegajoso sobrevivió la sesión entera: turnos
directos intercalados en un historial agéntico pesado, sin un solo 400.

Contraste con el cookbook de PocketFlow (revisado mismo día): cubrimos
Chat, Structured Output, Workflow, Agent, RAG, Map-Reduce, Multi-Agent,
Supervisor, Parallel, Thinking (selectivo+pegajoso), MCP (client y
server), Tracing (nodos+tools+visor), Judge, Debate, Heartbeat, Deep
Research, Coding Agent y HITL web. Faltan — y ya estaban en el roadmap:
streaming, memoria de largo plazo, A2A, vision/PDF. Voice,
descartado.

## Memoria entre sesiones: biblioteca consultable (2026-10-05)

Tercer ítem construido por el propio harness (6 turnos, 36 aprobaciones,
2 commits). Filosofía pedida por el usuario, respetada al pie de la
letra: la memoria es una BIBLIOTECA, no contexto auto-inyectado — todo
chat arranca vacío y el system prompt quedó intacto (estabilidad
byte-a-byte preservada). Piezas (`modules/memoria.py` + `main.py`):

- `memory_search(query)`: código puro, busca en `memoria/*.md` y lista
  la biblioteca. Verificado en vivo: ante "¿qué hay en memoria?", el
  agente la consultó y contestó con el contenido real.
- `memory_save(titulo, contenido)`: escribe `memoria/nota_FECHA_slug.md`
  sin HITL (la libreta del agente) con contención dura: slug sin rutas
  ni `..`, solo dentro de `memoria/`.
- Resumen automático al salir: una sola llamada resume la sesión a
  `memoria/sesion_FECHA.md` (bookkeeping, sin HITL; MEMORIA=0 apaga;
  <2 preguntas no resume).

Anomalía registrada honestamente: la sesión de construcción misma NO
dejó resumen al salir (salida limpia, sin print alguno), pero cuatro
repros (pipe simple, pty, tools, transcript grande) funcionan y el
episodio no se reprodujo. Consecuencia: **ninguna ruta del
exit-summary vuelve a ser muda** — desactivada, sesión corta, OSError y
éxito ahora imprimen su veredicto, con test que clava las cuatro rutas.
Si reincide, el print dirá exactamente cuál fue.

Nota: `sesion_FECHA.md` comparte nombre por día — sesiones repetidas el
mismo día se sobrescriben (aceptado por ahora; cada sesión que importa
suele tener además sus salidas/ nominativas).

**Catálogo al arranque (mesa 8, 2026-10-06):** `main.catalogo_memoria()`
imprime, apenas arranca el chat, la lista de notas de la biblioteca (nombre
+ conteo) — el agente sabé QUÉ hay sin que su contenido entre al contexto.
La regla del arranque vacío se respeta al pie: se muestra el catálogo, no se
inyecta nada al system prompt ni al historial. Con `MEMORIA=0` o biblioteca
vacía, silencio; la función es best-effort (nunca corta el arranque).

## Pre-filtro de contexto por Laya (Mesa 6, investigación 2026-10-05)

Los dos caminos de contexto del harness tienen un techo duro en caracteres
y no elegían QUE entra al prompt. El patrón de la wild (reportado con
~80% de costo/tiempo) es dejar que un juicio barato y local elija antes
de pagar tokens: **regla de hierro: si no hay juicio disponible, entran
TODOS los chunks — un retriever no debe perder recall por un modelo
ausente.**

Dos filtros, mismos helpers, default seguro:

- **`utils/contexto.py`** (código puro): `unidades_bloques(texto)` corta un
  markdown/texto en bloques atómicos (una línea en blanco o directiva
  `# ` los separa) sin partir ninguno; `elegir_por_laya(query, unidades,
  setting_prompt, setting_modelo, max_unidades)` puntúa cada bloque con
  el Laya correspondiente (0-1) y devuelve los de mayor puntaje **en orden
  original** (la relevancia decide QUE entra, no el orden). Sin modelo
  (`disponible()` False) o ante cualquier excepción, devuelve las
  `max_unidades` primeras: nunca pierde recall por un fallo.
- **`rag_search`** (modules/rag.py) filtra sus chunks por relevancia
  antes de devolverlos (`RAG_PREFILTRO=1`, `RAG_PREFILTRO_N`).
- **`memory_search`** (modules/memoria.py) filtra los .md de la
  biblioteca cuando hay query (`MEMORIA_PREFILTRO=1`, `MEMORIA_PREFILTRO_N`).
  Sin query, listado completo de siempre.

El contrato del prompt/modelo de Laya va declarado (como los del router) y
se lee de settings (`PREGUNTA_PREFILTRO` es la constante; `LAYA_MODEL_PREFILTRO`
el checkpoint). No hay checkpoint entrenado todavía: en la ausencia de
modelo, los filtros son no-op y el comportamiento es idéntico al de hoy
(cercado por tests: sin modelo, entra todo).

## Compacción de contexto (Mesa 6, 12-factor #5) — 2026-10-06

### El problema, medido

`shared['messages']` crece sin techo y **cada vuelta reenvía TODO el
historial** a la API. Evidencia: la sesión de construcción de la cola
final disparó **115 llamadas a tools**; cada turno pagó tokens por todo
lo anterior aunque lo viejo ya no aportara. El KV-cache amortigua el
precio unitario, pero el contexto sigue creciendo linealmente y cada
turno vuelve a mandarlo entero — el problema es de tamaño, no solo de
plata. Y el modo thinking *pegajoso* (ver `utils/call_llm.py`) vuelve
delicado tocar el historial: cualquier reescritura puede romper los
invariantes y disparar el 400 medido.

### La pieza: `utils/compaccion.py` (código puro, sin LLM)

`compactar(messages, max_chars, ventana=6)`:

- **(a) Ventana caliente intacta.** Siempre conserva el system (índice 0)
  y los últimos `N` mensajes (default 6), contando **assistant con
  `tool_calls` + sus tools como UNIDAD indivisible** — nunca se separan.
- **(b) Zona fría → un resumen.** El medio se reemplaza por **UN mensaje
  de user** con prefijo fijo `[compacción]`, el conteo de mensajes
  omitidos y un placeholder instructivo. El resumen REAL lo escribe el
  agente a sí mismo en un segundo paso; acá no hay LLM: mismo input →
  mismo output (determinista y pura).
- **(c) Invariante de la API.** Nunca deja un assistant con `tool_calls`
  sin sus tools. Si el corte por ventana cae en medio de una unidad, la
  unidad entra completa (la ventana puede quedar en más de N mensajes: la
  unidad manda).
- **(d) No-op documentado.** Si el historial ya entra en `max_chars` o
  tiene menos de `ventana + 2` mensajes, se devuelve intacto.

### Integración (`nodes.py`, `AgentStep.prep`)

ANTES de llamar al modelo: si el historial serializado supera
`COMPACTION_CHARS` (setting, default 60000), `compactar` corre y se
guarda `shared['compacciones'] += 1` con el print
`[compacción] zona fría: X mensajes → resumen; ventana caliente: Y`.

**El costo se paga UNA vez por ronda**: `shared['_compaccion_huella']`
guarda el sha1 del historial ya compactado y no se re-procesa si coincide
(una segunda llamada con el mismo historial es un no-op).

El resumen-instrucción es deliberadamente sobrio: dice que las vueltas
anteriores fueron compactadas y que los hechos durables están en
`memoria/` si hicieran falta (el agente la consulta con `memory_search`).
No inventa memoria ni pide escribir nada.

### Invariantes de seguridad (tests que los clavan)

`validar_historial(messages)` devuelve las violaciones (vacío = válido) y
NUNCA levanta. Clava los cuatro invariantes que el modo thinking pegajoso
exige:

1. Sin `reasoning_content` en ningún mensaje.
2. Dicts canónicos por rol (role/content/tool_calls/tool_call_id).
3. Ningún assistant con `tool_calls` sin sus tools inmediatas después
   (comparación por `tool_call_id`: caza tanto la tool faltante como la
   tool huérfana).
4. Primer mensaje = system.

`test_compaccion_invariantes_antes_y_despues` corre `validar_historial`
ANTES y DESPUÉS de compactar sobre un historial sintético de 201 mensajes
con mezcla de tools, y además verifica que el validador SÍ detecta cada
rotura (no es un chequeo vacuo).

### Tests

`tests/test_smoke.py`: no-op corto, no-op si entra en `max_chars`,
conservación de system + ventana caliente, unidad indivisible (sin tool
huérfana ni assistant sin tools), no-partir-unidad al recortar,
determinismo (dos llamadas), invariantes antes/después, e integración
(`COMPACTION_CHARS` chico por monkeypatch → `AgentStep.prep` devuelve el
historial compactado y cuenta en `shared['compacciones']`, sin
re-compactar la misma ronda). Suite: **124 passed**.

## Cierre de jornada 2026-10-05/06 — tablero verde

Secuencia oficial completa y cola final vacía. Lo construido por el
harness con auditoría independiente + E2E real en cada pieza:

- **Mesas 1-2-3** (evals, HITL graduado+hooks, Laya-voto): el voto r2
  promovido con 80% de turnos-directo sin DeepSeek (0 ecos, 0 errores
  nuevos; r1 reprobado honestamente por la puerta).
- **Mesa 6** (compacción): 89% de reducción con los 4 invariantes del
  modo thinking intactos; E2E real final — la API acepta el historial
  compactado, las tools siguen corriendo después, y el modelo explica
  qué se compactó reteniendo la ventana caliente. Pre-filtro de contexto
  y catálogo de memoria al arranque también adentro.
- **Cola final** (A2A + vision/PDF): ver_imagen/ver_pdf contra la API
  real (la Files API no acepta PDFs — medido — ruta por rasterización
  poppler, multi-página verificado: 3 páginas, clave exacta de la p.2);
  A2A verificado contra server fake del protocolo.
- Bonus de sesiones: denylist PRE, historial de aprobaciones de sesión,
  export en .env, stream sin enmascarar errores, pulido de terminal.

24 capacidades · 141 tests · OOM aprendido: un checkpoint por proceso.
Pendientes del menú: Mesa 4 (agentes fractales), 5 (async), 7 (skills),
8 (chat web — ya empezada).

## Deuda menor y bugs latentes (2026-10-07)

Nueve correcciones de la spec verificada `banco/specs/deuda_2026-10-07.md`
(revisión completa del harness, cada punto verificado en el código). Una
línea por fix, lo que el diff muestra:

- **Fix 1 — `utils/embeddings.py`**: el prefijo `query:`/`passage:` se
  decide DESPUÉS de cargar el modelo (sobre `_nombre_modelo` efectivo), no
  antes: la primera llamada con la familia e5 ya prefija bien.
- **Fix 2 — `minar_errores.py`**: el emparejado error→reintento usa la
  posición del evento (no `eventos.index(ev)` por igualdad de dict), así
  dos errores idénticos no colapsan ambos al primero.
- **Fix 3 — `carga_trazas.py`**: `_texto()` serializa a JSON los campos
  `criteria`/`task`/`modulo` no-string, para que un `criteria` lista/dict
  no reviente el INSERT con `InterfaceError`.
- **Fix 4 — `utils/websearch.py`**: `search_web` captura la excepción de
  `DDGS().text` y devuelve `"ERROR: ..."` como texto (degrada, no tumba el
  flujo de research, que era el único punto sin degradar del harness).
- **Fix 5 — `utils/compaccion.py`**: eliminado `_recortar_cola` (era la
  identidad, código muerto); el call site asigna directo
  `cola = unidades[-ventana:]`. Cero cambio de comportamiento.
- **Fix 6 — `modules/memoria.py`**: `guardar_resumen_sesion` sufija la
  hora si `sesion_FECHA.md` ya existe, así dos sesiones del mismo día no
  se pisan (la primera conserva el nombre clásico).
- **Fix 7 — `modules/db.py`**: `_sin_literales()` vacía el contenido de los
  literales `'...'`/`"..."` para los chequeos de PROHIBIDOS y LIMIT: una
  consulta con la palabra 'delete'/'limit' en un string ya no da falso
  positivo ni se salta el LIMIT forzado.
- **Fix 8 — sondas** (`sonda_laya.py`, `sonda_router.py`,
  `sonda_supervisor.py`): el directorio de tests se resuelve por el setting
  `BMO_TASKS_DIR` (default idéntico al path anterior), portable a otra
  máquina sin editar código.
- **Fix 9 — `docs/roadmap.md`**: la sección "Cola final" describe `ver_pdf`
  con su mecanismo real (pdftoppm/poppler → PNG por página → imágenes al
  modelo, tope 8 páginas), no la Files API muerta (HTTP 400 con PDFs).
  Coherencia documental; el ítem sigue marcado como hecho.

**Falsa alarma descartada**: el `write_file` del supervisor reportado como
no ejecutable NO era un bug — ya era electable y ejecutable vía
`**_MODULE_IMPLS`. Se confirmó primera-mano y se descartó sin tocar código.

## Robustez del banco (2026-10-07, segunda tanda)

Segunda tanda de la spec `banco/specs/banco_robusto_2026-10-07.md`: tres
fixes anclados a contratos existentes (la línea que el código imprime, el
YAML del escenario, la semántica del shell), cada uno con su candado de
test contra líneas REALES. Los números que siguen son los medidos.

- **Fix 10 — marcadores de veto anclados a líneas reales**: el marcador
  `"veto": r"PROHIBID|[Vv]etad"` fallaba en ambas direcciones — 6 falsos
  positivos medidos en los transcripts del día (`PROHIBIDOS`, la constante
  de `modules/db.py`, dentro de diffs preview de `edit_file`; y "vetado" en
  prosa ecoada de instrucciones) y, a la vez, el veto de SEGURIDAD nunca se
  contaba: el texto de la denylist iba solo al modelo como resultado de tool
  y no se imprimía. Ahora `veto_l8`/`veto_denylist` se anclan a las líneas
  reales (`\[laya\] … vetada`/`\[L8\] … vetada` y `[denylist]`) y el hook de
  la denylist imprime `[denylist]` en terminal (paridad con `[hook]`).
  Verificación offline: 0 falsos positivos en los 5 transcripts de
  producción y 3/3 en las líneas reales.
- **Fix 11 — tope HITL: agotamiento elegante + knob por turno**: al agotar
  los 6 HITL el driver enmudecía, el turno colgaba hasta 20 min y el
  `timeout` truncaba el escenario sin registrar la causa (2 turnos colgados
  hoy; 5 turnos "aplicar" históricos terminando exactamente en 6/6). Ahora
  hay knob `max_hitl` por turno y agotamiento elegante con el evento
  `hitl-tope` (causa registrada, no timeout mudo). Smoke E2E con
  `max_hitl=1`: turno ok en 16 s, primera escritura aprobada, segunda
  rechazada y reportada por el modelo.
- **Fix 12 — policy: `2>&1` es lectura, no escritura**: el regex
  `_PELIGRO_SHELL` cazaba el `>` de `2>&1`, degradando a `preguntar` formas
  de verificación solo-lectura. Ahora el token `2>&1` se quita antes del
  escaneo y ninguna redirección real se oculta (`> f`, `2> f`, `2>&1 > f`,
  `> f 2>&1` sobreviven). Matriz de 8 casos.

## exp/20 — bench del juez: la vara que le faltaba (2026-10-07)

El **problema**: `answer_verified` no tenía banco de pruebas propio. Cada
cambio a la ronda de juez (prompt, regex de citas, criterio de refuerzo) se
evaluaba "a ojo": sin casos, sin baseline y sin números, cualquier ajuste
parecía mejorar y nunca se podía comparar contra la versión anterior; peor
aún, un cambio que empeoraba el grading podía pasar desapercibido.

La **pieza** que cierra ese hueco:

- **`banco/juez_preguntas.jsonl`** — 17 casos: 15 de hecho + 2 trampas
  deliberadas (una pregunta que exige una herramienta inexistente y otra con
  una premisa falsa sobre la Files API). Las etiquetas quedaron **verificadas
  mecánicamente contra el repo por la auditoría**, no escritas a mano.
- **`bench_juez.py`** — con **grading en CÓDIGO PURO**: `respuesta_ok` y
  `cita_ok` leen la línea citada del disco con el `CITA_RE` **importado de
  `juez.py`**, el mismo regex de producción. No confiamos en el juez para
  calificar al juez: la verificación es determinista y ajena al LLM. La
  corrida es **secuencial y determinista**, y el baseline
  `salidas/evals/bench_juez.json` sigue el patrón de `evals.py`: **comparar
  sin pisar** (la corrida nueva se contrasta contra el baseline guardado, que
  no se sobrescribe).
- **Subcomando `main.py bench_juez`** para dispararlo desde la CLI.
- **5 tests** con `responder` *fake* inyectable, de modo que se ejercita el
  grading **sin LLM**.

La corrida baseline con LLM real la hace la **auditoría después** (no forma
parte de este cierre documental).

### Resultados del baseline (2 corridas, LLM real)

- **Corrida 1** (instrumento pre-calibración): `respuesta_ok` 64.7% (11/17),
  `cita_ok` 81.8% (9/11).
- **Corrida 2** (instrumento calibrado, baseline vigente): `respuesta_ok`
  76.5% (13/17), `cita_ok` 76.9% (10/13).

Hallazgos medidos:

1. **'verdict inválido' ESTOCÁSTICO del Judge** — 5/17 y 3/17 casos en cada
   corrida, SIEMPRE casos distintos, ~60s quemados por caso en 3 retries: el
   contrato YAML del verdict falla al azar en ~1 de cada 4-5 preguntas.
2. **trampa-delete-file falló 2/2 corridas** — el Draft alucina la herramienta
   inexistente y el Judge no contrasta contra el inventario real de tools.
3. **citas desviadas pasan el juez** — las 3 citas fallidas de la corrida 2 son
   near-misses que el Judge dejó pasar (línea 191 vs 195 real; 119/129 vs def
   real en 128; rutas falsas tipo `/fs_tools.py:64` que `read_file` no
   resuelve).
4. **la trampa de premisa falsa (Files API) la corrigió bien en la corrida 1**
   (pdftoppm con cita verificada).

Sobre el instrumento mismo: **contención por caso** (un caso que explota no
tira el bench — aprendido en la primera corrida real) y **calibración de
`cita_ok` a la ventana de 2 líneas de `Judge.prep`** (el bench no debe ser más
estricto que el contrato que mide).

## exp/21 — el verdict estocástico del juez: sondeado, endurecido, degradado (2026-10-07)

**La sonda** (`banco/probes/verdict_juez.py`, 9 respuestas del Judge con LLM
real sobre las 8 víctimas de exp/20) capturó la forma real del verdict
inválido: el sinónimo **`needs_changes`** — YAML perfectamente parseable,
falla **SEMÁNTICA**. Resultado: 8 ok válidas, 1 `needs_changes`.

**El fix en `juez.py` en tres capas**:

1. **Prompt endurecido** — el verdict SOLO `ok` o `retry`, literal.
2. **Normalización** `str`/`strip`/`lower` + `_ALIAS_VERDICT` con SOLO el
   sinónimo medido (`needs_changes`): el contrato se aprieta, no se afloja.
   *(Superado por la fase B2, abajo: el alias se eliminó — el verdict se
   repara con feedback; la canonicalización quedó.)*
3. **Degradación terminal en `responder_con_juez`** — flujo roto tras los
   retries con draft presente → se entrega el borrador con advertencia
   (patrón L8); sin draft se re-raise. `main.py juez` y `juez_lote` heredan.

**Re-medición del bench (fase C)**: `respuesta_ok` 76.5% → **94.1%**
(+17.6pp) y `cita_ok` 76.9% → **93.8%** (+16.8pp) en la corrida de
comparación; **CERO excepciones** (antes 3-5 por corrida). La corrida de
actualización del baseline reprodujo 94.1% (baseline vigente: `respuesta_ok`
94.1%, `cita_ok` 87.5%; dos corridas post-fix estables en 94.1).

**Residuales medidos que NO eran de este exp**: ~~trampa-delete-file sigue
fallando (3/3 corridas — la alucinación de tool inexistente, hallazgo 2 de
exp/20)~~ — **✅ cerrado en exp/42** (el Judge contrasta contra el
inventario real; ver la sección de exp/42). Quedan los near-miss de citas
(hallazgo 3) y, nuevo de exp/42, la ventana de 200 líneas del Draft frente
al modelo que hoy rehúsa fuera de lo verificado.

### Fase B2 — de parche a patrón (la crítica del dueño)

La fase B puso dos parches (la línea de prompt enumerando sinónimos
prohibidos y `_ALIAS_VERDICT` clavado al único sinónimo medido) que
perseguían el token observado: un sinónimo nuevo los atravesaba, y la
degradación sola convertía el crash en entrega sin juzgar. La crítica del
dueño del harness los tumbó. El reemplazo es el patrón propio del harness
(error-como-feedback, como el supervisor con args): un loop de reparación
que cita la respuesta inválida VERBATIM, más el motivo y el contrato
(marcador observable `[juez] verdict ilegible → reintento con feedback`),
con fallback semántico al lado seguro del contrato binario (retry con el
crudo citado, acotado por `max_rounds` L8) y canonicalización
`str`/`strip`/`lower` (ruido de codificación, no semántica). El test que
refuta el parche por existencia: `needs_changes` resuelto SIN alias, por el
feedback. Re-medición: `respuesta_ok` 94.1% sostenido sin parches (delta
0.0000), `cita_ok` 93.8% y en la corrida de actualización 16/16 (100%); el
marcador disparó 0 veces en ambas corridas — la línea honesta de contrato
bastó y el loop queda como armadura probada por tests. Baseline vigente:
94.1 / 100 sobre el sha del patrón. Residual único de respuesta:
trampa-delete-file (hallazgo 2 de exp/20).


---

## Roadmap — ítems cumplidos

Movidos desde [roadmap.md](roadmap.md) el 2026-10-16 (PR 2 del plan de orden): el roadmap queda solo hacia adelante.

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
cuenta — documentado en design.md. ~~Pendiente dentro de esta línea:
promover el patrón a **Choose del supervisor** y un round dirigido de
"hechos actuales" (mundial)~~ — **cerrado el 2026-10-13 por evidencia**:
el bench del supervisor midió el Choose 65 llamadas vs 14 del agente plano
a calidad igual (6/6) → supervisor v2 sin Choose (design.md); y el mundial
cerró por REGLA DURA, no por round (exp/46: la familia no juzga recencia).

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

## Cola final — ✅ vacía (2026-10-05)

Los dos últimos ítems quedaron construidos y verificados:

- **Vision/PDF** — ✅ `modules/vision.py`: `ver_imagen` (data-URL base64
  en un turno de USER; el type se valida por contenido; 32 MiB/48 MiB
  chequeados antes de llamar) y `ver_pdf` (rasteriza con pdftoppm/poppler
  → PNG por página → cada página va como imagen al modelo; la Files API
  NO acepta PDFs — HTTP 400 'unsupported file' — por eso el camino es el
  rasterizado; tope de 8 páginas, ~1024 tokens c/u; sin estado: rasteriza
  en /tmp y borra; 64 MiB de PDF fuente).
- **A2A** — ✅ `modules/a2a.py`: `agentes_remotos` (agent card con
  degradación a "inaccesible") y `a2a_tarea` (JSON-RPC 2.0
  `message/send`); setting `A2A_AGENTS` (JSON nombre→URL); sin setting,
  mensaje claro.

Tests sin red (mocks de `requests.post` + `http.server` fake), diseño en
la sección "Vision/PDF y A2A" de design.md.

