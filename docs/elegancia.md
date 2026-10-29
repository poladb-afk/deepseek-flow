# Elegancia — la definición que gobierna el refactor

Este documento es el contrato de forma del harness. Cada propiedad tiene una
prueba que se puede correr; las que ya se pueden contar tienen un ratchet
(`ratchet.py`) y no pueden empeorar. El refactor (fases 1–5, abajo) consiste en
bajar esos números **borrando**, no agregando.

> **Regla madre: un arreglo es elegante si borra un caso en vez de agregarlo.**
> Si el fix suma una palabra a una lista, una regex o una frase al prompt, no
> fue a la raíz.

## Elegancia funcional

El comportamiento sale de pocos mecanismos generales, cada decisión la toma
quien tiene la información para tomarla, y el grafo muestra todo el control.

| # | Propiedad | Prueba | Gate |
|---|---|---|---|
| F1 | **Generalidad**: ningún mecanismo conoce casos particulares | ¿Si cambio idioma, redacción o dominio del pedido, la decisión sigue andando? | `vocabulario_hardcodeado` |
| F2 | **Decisión en su lugar**: lo exacto lo cuenta el código, lo semántico lo juzga un modelo, lo irreversible lo decide un humano | ¿Hay una regex juzgando significado? | `vocabulario_hardcodeado` |
| F3 | **El grafo dice la verdad**: el control vive en las aristas | ¿Se explica un turno leyendo `python3 main.py grafo`? | `nodos_largos`, `test_el_diagrama_del_readme_es_el_grafo_del_chat` |
| F4 | **Fractal**: una primitiva a toda escala (chat = sub-agente = supervisor) | ¿Una política nueva llega gratis a los sub-agentes? | fase 2 (un solo loop) |
| F5 | **Dependencias hacia adentro**: los módulos dependen del CORE; el CORE no los conoce | ¿Borrar cualquier archivo de `modules/` deja el chat andando? | `core_importa_modulos` |
| F6 | **Errores reversibles**: el smart-if decide perillas cuyo error se autocorrige, nunca le quita capacidades al agente | ¿Si Laya se equivoca, el siguiente paso lo corrige solo? | fase 3 (`producto_router.py`) |
| F7 | **Producto ≠ laboratorio**: el producto no sabe que existe el banco | ¿Aparecen `banco`, `BANCO`, `DELEGADO` o `GROUND-TRUTH` en producción? | `producto_conoce_lab` |

## Elegancia de código

Cada concepto vive en un solo lugar, con el menor código que lo expresa,
funciones puras en el centro y efectos en los bordes.

| # | Propiedad | Prueba | Gate |
|---|---|---|---|
| C1 | **Un concepto, un lugar** | ¿Dos loops, dos cierres, tres presupuestos? | `helpers_duplicados`, `cuerpos_duplicados` |
| C2 | **Núcleo puro, efectos en el borde** | ¿La decisión se testea sin I/O ni mocks? | review |
| C3 | **Configuración mínima**: cada setting es contrato del operador, no un A/B abierto | ¿Cuántos settings son brazos de experimentos cerrados? | `settings_leidos` |
| C4 | **Imports honestos**: sin imports perezosos que esquiven ciclos | ¿Cuántos `import` viven dentro de funciones? | `imports_perezosos` |
| C5 | **El código dice el porqué actual**; la historia va a la bitácora | ¿El comentario sigue siendo verdad sin su `exp/N`? | review |
| C6 | **Tamaño ∝ responsabilidad**: un nodo, una cosa (≤ 40 líneas) | ¿Algún nodo hace varias? | `nodos_largos` |
| C7 | **El prompt describe el formato, no corrige conductas** | ¿Una frase del prompt tapa algo que una tool o un gate debería hacer? | `texto_de_prompt` |

## Fuentes

PocketFlow (grafo + shared store, sin módulos de proveedor); 12-Factor Agents
(factores 8 y 10); Anthropic, *Building effective agents* (simple y componible)
y *Effective context engineering* (prompts a la altitud correcta, sin if-else
rígido; tools mínimas; compaction); Manus, *Context engineering* (no agregar ni
quitar tools en caliente); Agent Skills (divulgación progresiva por
descripción); la bitter lesson aplicada a harnesses (las capas que tapan
debilidades del modelo envejecen); mini-swe-agent (~100 líneas de clase de
agente); SWE-agent (el linter en la edición como guardrail medido). Detalle y
citas en la auditoría del 2026-10-27 (`docs/bitacora.md`, X91).

## Línea de base (fase 0, 2026-10-27)

| Ratchet | Baseline | Meta del refactor |
|---|---|---|
| `core_importa_modulos` | 3 → **0** (X92) | 0 ✅ |
| `producto_conoce_lab` | 10 → **0** (X93) | 0 ✅ |
| `vocabulario_hardcodeado` | 8 → 7 (X104) | ≤ 2 (fases 3–4; quedan los sí/no del HITL) |
| `settings_leidos` | 89 → 84 (X93) → 78 (X101) → 79 (X103, temporal) → 78 (X105) | ≤ 45 (fases 1–5, ver inventario) |
| `imports_perezosos` | 137 → 126 (X92) | ≤ 40 |
| `nodos_largos` | 15 → 14 (X96) | ≤ 3 |
| `texto_de_prompt` | 2748 chars | ≤ 800 |

## Plan

| Fase | Cambio | ¿Cambia conducta? | Gate de salida |
|---|---|---|---|
| 0 | Estos ratchets + el diagrama del README generado + este documento | No | `./calidad.sh` verde |
| 1 | ✅ 1a (X92): hooks de ciclo de vida en los módulos (S4). ✅ 1b (X93): el producto deja de leer `BANCO`/`DELEGADO`/`GROUND-TRUTH` (S5); el driver PTY sale de `banco/` | No | `test_caracterizacion_chat.py` idéntico |
| 2 | ✅ 2a (X94): el kernel con el shared solo de datos. ✅ 2b-1 (X95): `Contexto` (compacción) como nodo. ✅ 2b-2 (X96): `Observar` y `Cierre` (el presupuesto como arista). Falta: el chat es `kernel.loop` + políticas como nodos (S9); esquema de tools fijo y cierre por arista (S3) | Mínimo | `replay`, `test_grafos_sin_calles_muertas.py`, fable s17–s20 |
| 3 | (2d no entró, X99.) Gate previo PASA (X102). 3a NO PASA (X105, cableado borrado). 3b por la opción (b): el router sale del chat, pre-registro en `banco/specs/fase3b_4a.md`. `reasoning_content` preservado en rondas de tools (S1); todo camino ofrece tools y Laya elige el modo (S2) | **Sí** | `producto_router.py` con 0 falsos directos; s17–s20 calidad ≥ y costo ≤ |
| 4 | ✅ 4b-mín (X104): sin la regex de palabras. Falta 4a: se borran reglas y voto con la 3b; directivas en la 5b (S6–S8) | Sí | mismo banco; `settings_leidos` ≤ 60 |
| 5 | Política de comandos como datos (S10); skills por descripción; Laya 0.4.x | Mínimo | `test_policy_bypass.py` idéntico |
| 6 | Limpieza de piezas sueltas (`juez`, `effective_n`, `juez_lote`, `research`, `informe`, `fable_judge`): nodos largos e imports perezosos (decisión del operador, X103) | No | `nodos_largos` ≤ 3, `imports_perezosos` ≤ 40 |

## Inventario de settings (78 tras X105: 42 contrato · 19 revisar · 17 borrar)

`contrato` = decisión del operador que se queda; `revisar` = se decide en la
fase indicada; `borrar` = se va con su rama en esa fase.

| Setting | Veredicto | Fase | Motivo | Lo lee |
|---|---|---|---|---|
| `BMO_TASKS_DIR` | borrar | 1 | S5: dependencia de otro proyecto (bmo) | `utils/rutas.py` |
| `LEER_BMO_ENV` | borrar | 1 | S5: dependencia de otro proyecto (bmo) | `utils/call_llm.py` |
| `LAYA_ALPHA_VOTO` | borrar | 3 | S2: el voto existe para tapar el directo sin tools | `utils/laya_routing.py` |
| `LAYA_CALIBRACION_VOTO` | borrar | 3 | S2: el voto existe para tapar el directo sin tools | `utils/laya_routing.py` |
| `LAYA_MODEL_VOTO` | borrar | 3 | S2: el voto existe para tapar el directo sin tools | `nodes.py` |
| `LAYA_MODO` | borrar | 3 | S2: el router deja de quitar tools | `utils/laya_routing.py` |
| `LAYA_UNSURE_HIGH` | borrar | 3 | S2: el router deja de quitar tools | `utils/laya.py`, `utils/laya_routing.py` |
| `LAYA_UNSURE_HIGH_VOTO` | borrar | 3 | S2: el voto existe para tapar el directo sin tools | `utils/laya_routing.py` |
| `LAYA_UNSURE_LOW` | borrar | 3 | S2: el router deja de quitar tools | `utils/laya.py` |
| `USE_LAYA_ROUTER` | borrar | 3 | S2: el router deja de quitar tools | `flow.py`, `replay.py` |
| `USE_VOTACION` | borrar | 3 | S2: el voto existe para tapar el directo sin tools | `nodes.py` |
| `CORTE_NOVEDAD` | borrar | 4 | S6: presupuesto por perfil/texto → Ledger por novedad | `nodes.py` |
| `CORTE_NOVEDAD_MIN` | borrar | 4 | S6: presupuesto por perfil/texto → Ledger por novedad | `nodes.py` |
| `MAX_TOOL_ROUNDS_AMPLIO` | borrar | 4 | S6: presupuesto por perfil/texto → Ledger por novedad | `nodes.py` |
| `PROMPT_AUDITORIA` | borrar | 4 | S7/S8: brazos de A/B cerrados → skills | `main.py` |
| `PROMPT_FABLE` | borrar | 4 | S7/S8: brazos de A/B cerrados → skills | `main.py` |
| `UMBRAL_SIN_PROGRESO` | borrar | 4 | S6: presupuesto por perfil/texto → Ledger por novedad | `nodes.py` |
| `HITL_SCOPE` | revisar | 1 | S5: entrada headless legítima, hoy nombrada como del banco | `utils/aprobaciones.py` |
| `HUMANO_RESPUESTA` | revisar | 1 | S5: entrada headless legítima, hoy nombrada como del banco | `modules/humano.py` |
| `LAYA_MODEL_SUPERVISOR` | revisar | 1 | sondas: van a banco/, no al producto | `sonda_supervisor.py` |
| `LAYA_UNSURE_HIGH_SUPERVISOR` | revisar | 1 | sondas: van a banco/, no al producto | `sonda_supervisor.py` |
| `SONDA_LAYA_CKPT` | revisar | 1 | sondas: van a banco/, no al producto | `sonda_laya.py` |
| `CHAT_STREAM_INTERRUPT` | revisar | 2 | S9: citas e interrupción siempre activas | `utils/call_llm.py` |
| `CITAS_VERIFICAR` | revisar | 2 | S9: citas e interrupción siempre activas | `nodes.py` |
| `PREFETCH` | revisar | 2 | S9: prefetch como nodo; topes como constantes | `utils/prefetch.py` |
| `LAYA_ALPHA` | revisar | 3 | S1/S2: la calibración conformal se queda si Laya elige el modo | `utils/laya_routing.py` |
| `LAYA_CALIBRACION_ROUTER` | revisar | 3 | S1/S2: la calibración conformal se queda si Laya elige el modo | `utils/laya_routing.py` |
| `LAYA_MODEL_RIESGO` | revisar | 3 | S1: el juez de riesgo observa sin decidir: decidir o borrar | `utils/riesgo.py` |
| `PROMPT_FORMA` | revisar | 4 | S8: se queda solo si un A/B del modelo actual lo sostiene | `main.py` |
| `SKILLS` | revisar | 4 | S7: skills por descripción; el apagador global quizá sobra | `nodes.py` |
| `INFORME_CARPETA` | revisar | 5 | concurrencia: una constante del kernel | `informe.py` |
| `LAYA_BATCH_SIZE` | contrato | — | no es un tunable: `0` = el lote no se parte (un solo forward), N = lotes de N; elige el pico de memoria del prefiltro (X101) | `utils/laya.py` |
| `LAYA_MODEL_PREFILTRO` | revisar | 5 | prefiltros: un mecanismo, un setting | `modules/memoria.py` |
| `MEMORIA_PREFILTRO` | revisar | 5 | prefiltros: un mecanismo, un setting | `modules/memoria.py` |
| `MEMORIA_PREFILTRO_N` | revisar | 5 | prefiltros: un mecanismo, un setting | `modules/memoria.py` |
| `RAG_PREFILTRO` | revisar | 5 | prefiltros: un mecanismo, un setting | `modules/rag.py` |
| `RAG_PREFILTRO_N` | revisar | 5 | prefiltros: un mecanismo, un setting | `modules/rag.py` |
| `COMPACTION_CHARS` | contrato | 2 | tamaño de contexto | `nodes.py` |
| `MAX_TOOL_ROUNDS` | contrato | 2 | el techo duro del Ledger (único presupuesto) | `utils/fs_tools.py` |
| `READ_MAX_CHARS` | contrato | 2 | tamaño de contexto | `utils/fs_tools.py` |
| `LAYA_MODEL` | contrato | 3 | el checkpoint del smart-if | `utils/laya.py` |
| `A2A_AGENTS` | contrato | — | superficies opcionales (web, MCP, A2A, búsqueda) | `modules/a2a.py` |
| `AGENT_ALLOWED_DIRS` | contrato | — | credenciales y proveedor | `utils/fs_tools.py` |
| `CHAT_STREAM` | contrato | — | presentación y costos | `nodes.py` |
| `COLOR` | contrato | — | presentación y costos | `utils/terminal.py` |
| `DB_PATH` | contrato | — | presentación y costos | `modules/db.py` |
| `DEEPSEEK_API_KEY` | contrato | — | credenciales y proveedor | `utils/call_llm.py` |
| `HITL_AUTO` | contrato | — | seguridad y HITL: decisión del operador | `modules/coding.py` |
| `HITL_WEB` | contrato | — | seguridad y HITL: decisión del operador | `utils/aprobaciones.py`, `utils/riesgo.py` |
| `HITL_WEB_PORT` | contrato | — | seguridad y HITL: decisión del operador | `utils/hitl_web.py` |
| `HITL_WEB_TIMEOUT` | contrato | — | seguridad y HITL: decisión del operador | `utils/hitl_web.py` |
| `LAYA_LOG_ARCHIVO` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `utils/laya_routing.py` |
| `LAYA_LOG_DECISIONES` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `nodes.py`, `utils/laya_routing.py` |
| `LAYA_LOG_PREGUNTA` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `utils/laya_routing.py` |
| `LLM_API_KEY` | contrato | — | credenciales y proveedor | `utils/call_llm.py` |
| `LLM_BASE_URL` | contrato | — | credenciales y proveedor | `modules/vision.py`, `utils/call_llm.py` |
| `LLM_MODEL` | contrato | — | credenciales y proveedor | `modules/vision.py`, `utils/call_llm.py` |
| `MCP_EXPOSE` | contrato | — | superficies opcionales (web, MCP, A2A, búsqueda) | `mcp_server.py` |
| `MCP_SERVERS` | contrato | — | superficies opcionales (web, MCP, A2A, búsqueda) | `utils/mcp_client.py` |
| `MEMORIA` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `main.py`, `nodes.py` |
| `MEMORIA_DIR` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `modules/memoria.py` |
| `NO_COLOR` | contrato | — | presentación y costos | `utils/terminal.py` |
| `PRECIO_TOKENS` | contrato | — | presentación y costos | `main.py` |
| `PREGUNTAS_ARCHIVO` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `nodes.py` |
| `PREGUNTAS_LOG` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `nodes.py` |
| `RIESGO_ARCHIVO` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `utils/riesgo.py` |
| `RIESGO_LOG` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `utils/riesgo.py` |
| `SEARCH_PROVIDER` | contrato | — | superficies opcionales (web, MCP, A2A, búsqueda) | `utils/websearch.py` |
| `THREADS_DIR` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `utils/thread_store.py` |
| `THREAD_PERSIST` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `utils/thread_store.py` |
| `TRACE` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `utils/tracing.py` |
| `WEBCHAT` | contrato | — | superficies opcionales (web, MCP, A2A, búsqueda) | `utils/webchat.py` |
| `WEBCHAT_MAX_SESIONES` | contrato | — | superficies opcionales (web, MCP, A2A, búsqueda) | `utils/webchat.py` |
| `WEBCHAT_TTL` | contrato | — | superficies opcionales (web, MCP, A2A, búsqueda) | `utils/webchat.py` |
| `WEBHOOK_LOG` | contrato | — | seguridad y HITL: decisión del operador | `utils/hitl_web.py` |
| `WEBHOOK_MAX_BYTES` | contrato | — | seguridad y HITL: decisión del operador | `utils/hitl_web.py` |
| `WEBHOOK_MAX_POR_MINUTO` | contrato | — | seguridad y HITL: decisión del operador | `utils/hitl_web.py` |
| `WEBHOOK_TOKEN` | contrato | — | seguridad y HITL: decisión del operador | `utils/hitl_web.py` |

