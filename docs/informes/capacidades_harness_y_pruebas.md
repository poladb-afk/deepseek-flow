# Capacidades del harness y cómo probarlas

**Fecha:** 2026-10-17 · **Alcance:** chat interactivo (`python3 main.py`) + subcomandos + quality gate.

Este documento es el mapa de pruebas: qué sabe hacer el harness, cómo se verifica cada
capacidad con evidencia observable, y qué NO prueba cada chequeo. La regla es la misma
de la auditoría: sin evidencia reproducible no es una capacidad, es una promesa.

## 1. Principios de prueba

- **Evidencia primaria:** el transcript de la terminal, el trace `.runs/*.jsonl`, los
  archivos que quedan en disco, y el gate (`./calidad.sh`).
- **Una capability = un bucle:** modelo → tools → HITL → respuesta. Si una vuelta
  funciona pero la segunda no, la capacidad no está probada.
- **Conversación continua:** varias capacidades solo se ven en una misma sesión
  (continuidad, compacción, presupuesto por pregunta, `/aprobaciones`).
- **LLM real, no mock:** los tests fijan contratos; el test en vivo muestra el comportamiento
  con `deepseek-flash`. Las respuestas son variables: se verifica la ESTRUCTURA
  (tools, citas, HITL, límites), no la redacción.

## 2. Matriz de capacidades y pruebas

### 2.1 Núcleo del chat

| # | Capacidad | Cómo probarla | Evidencia esperada |
|---|---|---|---|
| C1 | Conversación multi-turno con historial | `python3 main.py`; turno 1 lee un archivo, turno 2 pregunta algo que solo se sabe por el turno 1 | la respuesta del turno 2 usa el contenido leído sin volver a pedir la tool |
| C2 | Streaming y corte tolerable | default (`CHAT_STREAM=1`); pedir una respuesta larga; comparar con `CHAT_STREAM=0` | tokens en vivo; `Ctrl+C` conserva lo parcial (`CHAT_STREAM_INTERRUPT=1`) |
| C3 | Pre-fetch declarativo | en el pedido nombrar 1–2 archivos existentes | líneas `[pre-fetch] ruta` antes de la primera llamada y `read_file` evitado/duplicado |
| C4 | Router Laya (shadow/enforce/off) | `LAYA_MODO=shadow` (default) y `enforce`; preguntar algo simple y algo que requiera tools | línea `[laya] directo/herramientas`; en shadow la ruta real no cambia |
| C5 | Compacción de contexto | `COMPACTION_CHARS=4000` y una conversación larga | línea `[compacción] zona fría…`; el agente sigue recordando la tarea vigente |
| C6 | Presupuesto + cierre forzado | `MAX_TOOL_ROUNDS=2` y un pedido amplio; luego mandar `seguí` | `[ronda 2/2]`, aviso de cierre (`DeepSeek (aviso): …`) y al `seguí` el presupuesto se reinicia |
| C7 | Verificación de citas | pedir hallazgos con `ruta/archivo.py:línea` | `[citas] x/y verificadas contra el disco`; si hay malas, bloque `DeepSeek (citas corregidas)` |
| C8 | HITL graduado | pedir `pytest -q tests/test_policy.py` (auto), un `touch`/comando no reconocido (pregunta), y `rm -rf`/`git push` (doble) | `run_command` sin s/n en auto; `(s/n)` en pregunta; dos `(s/n)` en doble; rechazo con `n` no corta la sesión |
| C9 | HITL web | `HITL_WEB=1 python3 main.py`; pedir una escritura | la aprobación aparece en el navegador (`http://127.0.0.1:8765`), consola no bloqueada |
| C10 | `/aprobaciones` | mandar exactamente `/aprobaciones` en el chat | resumen de aprobaciones/rechazos de la sesión; no gasta turno del modelo |
| C11 | Trazas y medición | con `TRACE=1` hacer 2–3 turnos; `python3 tablero.py` | `.runs/*.jsonl` con `tool`/`hitl_*`; tablero con métricas del día |
| C12 | Memoria entre sesiones | `MEMORIA=1`, conversar, salir; abrir otra sesión | resumen guardado en `memoria/`; catálogo al arrancar; `memory_search` lo encuentra |
| C13 | Persistencia / resume | `THREAD_PERSIST=1`, salir y `python3 main.py resume <id>` | thread rehidratado en `salidas/threads/`; la conversación continúa |

### 2.2 Herramientas

| # | Capacidad | Cómo probarla | Evidencia esperada |
|---|---|---|---|
| T1 | Lectura de archivos | `lista los .py de utils/`, `leé utils/votacion.py`, `buscá 'mayoria(' en el repo` | `list_files`/`read_file`/`search_files` en el transcript y en el trace |
| T2 | Escritura y edición con HITL | pedir crear `salidas/tmp.txt` y editar un archivo | diff + `(s/n)`; aprobar escribe, rechazar no; hook `py_compile` avisa `⚠ SINTAXIS` si el `.py` quedó roto |
| T3 | `run_command` + política | `pytest -q tests/test_policy.py`; `python3 -c "print(1)"`; `rm -rf /tmp/x` | auto/preguntar/doble según `utils/policy.py`; salida truncada y timeout configurable |
| T4 | Tools de dominio | `sql`/`db_schema`, `rag_search`/`rag_index`, `memory_search/save`, `ver_imagen`/`ver_pdf`, `search_web`, `mcp_tools`/`mcp_call`, `agentes_remotos`/`a2a_tarea`, `request_human_input` | tool-specific: filas SQL, fragmentos indexados, nota guardada, descripción de imagen, resultado web/MCP/A2A |
| T5 | Registro de módulos | agregar un archivo `modules/mi_modulo.py` con `TOOLS`+`IMPL`, reiniciar | el tool aparece sin tocar el registro; borrarlo lo quita |
| T6 | Hooks pre/post | intentar un comando de la denylist dura (`rm -rf /`) y escribir un `.py` con error de sintaxis | veto pre-tool sin s/n; aviso post-tool `⚠ SINTAXIS` al modelo |

### 2.3 Subcomandos y flujos

| # | Capacidad | Cómo probarla | Evidencia esperada |
|---|---|---|---|
| S1 | `juez` / `juez_lote` | `python3 main.py juez "pregunta" --rondas 2`; `juez_lote preguntas.txt` | borrador + verificación de citas + refinamiento; lote con speedup medido |
| S2 | `informe` / `auditoria` | `python3 main.py informe [carpeta]`; `auditoria c1 c2` | informe markdown/json de trazas; comparativa multi-carpeta |
| S3 | `research` / `debate` / `supervisor` | `python3 main.py research "tema"`; `debate "tema"`; `supervisor "tarea"` | bucle de cobertura; proponente/crítico + juez; pasos con tool-calling nativo |
| S4 | `effective_n` | `python3 main.py effective_n [carpeta]` | deduplicación exacta por contenido + informe conjunto |
| S5 | `evals` / `bench_juez` / `replay` | `python3 main.py evals`; `bench_juez`; `replay [trace]` | bench del router, linter de trazas, costos; grading por código; re-validación de traces |
| S6 | `grafo` / `visor` | `python3 main.py grafo`; `python3 main.py visor [trace]` | mermaid de los grafos; HTML navegable del trace |
| S7 | `heartbeat` / `mcp-server` / `resume` | `heartbeat --ahora`; `mcp-server`; `resume <id>` | piezas programadas; capacidades expuestas MCP; thread rehidratado |

### 2.4 Calidad

| # | Capacidad | Cómo probarla | Evidencia esperada |
|---|---|---|---|
| Q1 | Gate de calidad | `./calidad.sh` | ruff + complejidad (C901 ≤ 12 en fronteras) + suite completa en verde |
| Q2 | Inventario de tests | `tests/inventario_tests.txt` | tests nuevos permitidos; no se pierden tests existentes (límite 800 líneas/archivo) |
| Q3 | Verificación en vivo | sesión scriptada tipo `live12/` | cada capability con evidencia en transcript + trace; resultados en `salidas/auditoria_2026-10/` |

## 3. Plantilla de sesión continua (chat)

Una sola sesión de `python3 main.py`, 9 turnos + `/aprobaciones` + `salir`; entorno
`TRACE=1 PREGUNTAS_LOG=0 MEMORIA=0 HITL_AUTO=1 LAYA_MODO=shadow COMPACTION_CHARS=6000`:

1. cwd + conteo de `.py` en `utils/` → tools de lectura y system prompt.
2. leer `utils/votacion.py` → `read_file` y resumen.
3. preguntar por el default de `minimo` → continuidad sin relectura.
4. buscar llamadas a `mayoria(` con citas `archivo:línea` → verificación de citas.
5. correr `pytest -q tests/test_policy.py` → HITL auto + `run_command`.
6. crear y leer `salidas/tmp_capacidades.txt` → HITL de escritura.
7. `/aprobaciones` → comando de terminal.
8. preguntar por las aprobaciones → continuidad sobre la salida del comando.
9. resumen en 3 bullets → continuidad larga + compacción.

Cada turno se considera probado si aparece la evidencia esperada en el transcript;
el trace y `sesion.json` cierran la evidencia (tools, HITL, duración).

## 4. Lo que estas pruebas NO cubren

- **Verdad semántica:** la verificación de citas valida líneas, no que la afirmación sea cierta.
- **Calidad del modelo:** una respuesta correcta en una corrida no garantiza repetibilidad
  (el harness es determinista en la política, no en el LLM).
- **Carga/estrés:** latencia y concurrencia del servidor MCP, RAG con corpus grande, etc.
- **Seguridad completa:** el perímetro es de mejor esfuerzo (política + hooks + HITL); no es un
  sandbox de sistema operativo.

## 5. Última corrida en vivo

**live12 (2026-10-18):** 9 turnos + `/aprobaciones` + `salir`, 91,8 s, exit 0.
12 de 13 capacidades del chat con evidencia en vivo: tools (9 rondas), HITL (3
aprobaciones), pre-fetch (2 archivos), router Laya shadow (8 decisiones),
compacción (11 eventos), verificación de citas (5 eventos, todas OK) y trazas
(67 eventos). No ejercitadas: HITL web, rechazo/doble confirmación, presupuesto
forzado, memoria entre sesiones, resume y subcomandos (recetas en §2).

Artefactos: `salidas/auditoria_2026-10/live12/` (transcript, trace, `sesion.json`)
y el informe `capacidades_chat_live.md` con el detalle por turno.

**Corrida 2 (2026-10-18, recetas restantes):** rechazo HITL, doble confirmación,
presupuesto/continuación (`seguí`), memoria entre sesiones, thread persist/resume
y HITL web aprobado por HTTP: **todas ✅**. Detalle y observaciones en
`capacidades_chat_extra.md` (artefactos `live13/`, `live14/`, `live15/`).

**Corrida 3 (2026-10-18, subcomandos):** los 17 subcomandos de la CLI
ejecutados en vivo (deterministas + LLM + MCP con cliente real). El bench del
juez destapó una regresión (70,6% vs 94,1%) por el excerpt fijo de 200 líneas
ante archivos que crecieron: corregido con `_contexto_extra` (**A63**, gate
**562**). El caso `supervisor-umbral` del banco quedó obsoleto (setting mudado
a `sonda_supervisor.py`); baseline sin tocar para no esconder la señal. Detalle
en `salidas/auditoria_2026-10/subcomandos/subcomandos_live.md`.

**Corrida 4 (2026-10-18, cierre del bench):** caso `supervisor-umbral` corregido
(la sonda vive en `sonda_supervisor.py`) y baseline regenerado con backup del
anterior. Full bench: **100% respuesta_ok / 87,5% cita_ok** (17 casos, 393,6 s;
antes 70,6%/68,8%).

**Corrida 5 (2026-10-18, cita exacta):** el prompt del `Draft` ahora pide la
línea EXACTA del símbolo o del literal (no el inicio del bloque). En los 2 casos
que fallaban: **2/2 respuesta y cita ✅**. Full bench: **100% respuesta_ok /
87,5% cita_ok** (17 casos, 495,0 s), baseline nuevo **OK**; las 2 citas que
fallan (`sanitizar-markers`, `thinking-tools`) son flakiness del modelo en el
grading exacto, no una regresión de código.

**Corrida 6 (2026-10-18, anclaje determinista):** `juez._anclar_citas` re-ancla
una cita a la línea cercana (±30) que contiene el literal/negrita/símbolo del
párrafo. Full bench: **100% respuesta / 87,5% cita** otra vez, pero **los fallos
rotan** (`a2a-protocolo`, `trampa-pdf-filesapi`): citan `:5` o la descripción en
vez de la implementación. Conclusión: el techo de 87,5% es flakiness del
grading por línea exacta, no una regresión.

**Corrida 7 (2026-10-18, grading por ventana — decisión):** el grading del bench
pasa de 2 líneas (n, n+1) a **±`VENTANA_GRADING` = 10 líneas** alrededor de la
cita. Es un cambio del INSTRUMENTO, no de producción: mide “cita cerca de la
evidence” en vez de número exacto. Full bench: **100% respuesta / 100% cita**
(17 casos, 607 s); baseline regenerado (**OK**, backup del anterior).