# Elegancia — la definición que gobierna el refactor

Este documento es el contrato de forma del harness. Cada propiedad tiene una
prueba que se puede correr; las que ya se pueden contar tienen un ratchet
(`ratchet.py`) y no pueden empeorar. El refactor (fases 1–5, abajo) consiste en
bajar esos números **borrando**, no agregando.

> **Regla madre: un arreglo es elegante si borra un caso en vez de agregarlo.**
> Si el fix suma una palabra a una lista, una regex o una frase al prompt, no
> fue a la raíz.

## Definición (X116)

> **Funcional:** el comportamiento sale de una primitiva que se contiene a sí
> misma (agente = Flow = Node = Tool), con las decisiones como datos tipados,
> tomadas aparte de los efectos y sobre un solo estado serializable.
>
> **De código:** las variaciones salen de componer y de datos, no de casos;
> cada cambio borra algo, falla hacia lo seguro y declara sus límites.

La definición es lo que las tres fuentes de diseño (PocketFlow, 12-Factor
Agents y Laya) tienen en común: los nueve **principios de elegancia EL1–EL9**,
que desde X144 viven en `docs/principios.md` (antes estaban acá como
"P1–P9" y chocaban con los P de diseño). Este archivo guarda sus pruebas
(F1–F7, C1–C7), el plan del refactor y el inventario de settings.

Tres de las prohibiciones del operador (N1–N3; N4 es C1), como prueba que se puede correr:

| Prohibido | Prueba | Lo legítimo |
|---|---|---|
| Parche | ¿El diff borra un caso o lo agrega? ¿Con otro modelo, seguiría haciendo falta? | Nada: si la medición obliga a dejarlo, es deuda medida con su A/B de salida |
| Hardcodeo | ¿Hay un literal que sirve para un caso particular (palabra, extensión, pista)? | En el borde, como datos y con dueño (`utils/politica_comandos.json`, `utils/proveedor.py`) |
| Arreglo por system prompt | Borrá la frase: ¿un mecanismo (tool, política, nodo, gate) sostiene la conducta? | El prompt describe entorno y formato |

## Elegancia funcional

El comportamiento sale de pocos mecanismos generales, cada decisión la toma
quien tiene la información para tomarla, y el grafo muestra todo el control.

| # | Propiedad | Prueba | Gate |
|---|---|---|---|
| F1 | **Generalidad**: ningún mecanismo conoce casos particulares | ¿Si cambio idioma, redacción o dominio del pedido, la decisión sigue andando? | `vocabulario_hardcodeado` |
| F2 | **Decisión en su lugar**: lo exacto lo cuenta el código, lo semántico lo juzga un modelo, lo irreversible lo decide un humano | ¿Hay una regex juzgando significado? | `vocabulario_hardcodeado` |
| F3 | **El grafo dice la verdad**: el control vive en las aristas | ¿Se explica un turno leyendo `python3 main.py grafo`? | `nodos_largos`, `test_el_diagrama_del_readme_es_el_grafo_del_chat` |
| F4 | **Fractal**: una definición del loop, N instancias (chat = sub-agente = supervisor = copia de sí mismo); difieren solo en datos y la recursión tiene tres frenos: profundidad, saldo y efecto | ¿Una política nueva llega gratis a los sub-agentes? ¿Anidar el loop en sí mismo necesita código nuevo? | `test_un_agente_que_se_llama_a_si_mismo_reparte_y_suma`; el chat, con S9b; `test_un_rechazo_del_humano_llega_igual_al_chat_al_supervisor_y_a_una_copia`, `test_sin_saldo_ningun_nivel_ejecuta_y_la_ultima_llamada_va_sin_tools` y `test_la_compactacion_es_una_politica_del_loop_y_corre_igual_en_una_copia` (el gate fractal, X138) |
| F5 | **Dependencias hacia adentro**: los módulos dependen del CORE; el CORE no los conoce | ¿Borrar cualquier archivo de `modules/` deja el chat andando? | `core_importa_modulos` |
| F6 | **Errores reversibles**: el smart-if decide perillas cuyo error se autocorrige, nunca le quita capacidades al agente | ¿Si Laya se equivoca, el siguiente paso lo corrige solo? | fase 3 (`banco/specs/fase3b_4a.md`) |
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
| C6 | **Tamaño ∝ responsabilidad**: un nodo, una cosa (≤ 40 líneas de código) | ¿Algún nodo hace varias? | `nodos_largos` |
| C7 | **El prompt describe el formato, no corrige conductas** | ¿Una frase del prompt tapa algo que una tool o un gate debería hacer? | `texto_de_prompt` |

## Fuentes

PocketFlow (grafo + shared store, sin módulos de proveedor); 12-Factor Agents
(factores 8 y 10); Anthropic, *Building effective agents* (simple y componible)
y *Effective context engineering* (prompts a la altitud correcta, sin if-else
rígido; tools mínimas; compaction); Manus, *Context engineering* (no agregar ni
quitar tools en caliente); Agent Skills (divulgación progresiva por
descripción); la bitter lesson aplicada a harnesses (las capas que tapan
debilidades del modelo envejecen); mini-swe-agent (~100 líneas de clase de
agente); SWE-agent (el linter en la edición como guardrail medido). El
fractal (X116): RAO, RAH y RLM a favor de un loop que se replica; en contra,
los estudios de escala de 2026 con el presupuesto igualado (el A/B que lo
decide para este harness: `banco/specs/exp103_fractal.md`). Detalle y
citas en la auditoría del 2026-10-27 (`docs/bitacora/2026-10.md`, X91). Con URL y la capa a la que fundamenta cada una: `docs/principios.md`.

## Línea de base (fase 0, 2026-10-27)

| Ratchet | Baseline | Meta del refactor |
|---|---|---|
| `core_importa_modulos` | 3 → **0** (X92) | 0 ✅ |
| `producto_conoce_lab` | 10 → **0** (X93) | 0 ✅ |
| `vocabulario_hardcodeado` | 8 → 7 (X104) → 3 (X106) → 5 (X112: el instrumento ahora lee la `condicion` de `skills/*.yaml`, que el AST no veía) → 4 (S9a/X133: la continuación salió de `GetQuestion`) → **3** (X135: salió `TOOL_CONTEXTO_RE` del juez; quedan las 2 regex de `skills/*.yaml` y el `YES` del HITL) | **piso honesto 3** (S7 cerrado sin remedio para este modelo: las 2 regex de los skills quedan como deuda medida; el `YES` del HITL es el s/n). La meta ≤2 se re-expresa en X136 (era inalcanzable con las dos de los skills) |
| `settings_leidos` | 89 → 84 (X93) → 78 (X101) → 79 (X103, temporal) → 78 (X105) → 64 (X106) → 58 (X109) → 56 (X112) → **52 (S6/X132)** | ≤ 45 (fases 1–5, ver inventario) |
| `imports_perezosos` | 137 → 126 (X92) → 90 (X106) → 81 (X109) → 80 (X112) | **≤ 40** (X112 deja sin efecto el ~60 del 2026-10-30: la clasificación de los 81 muestra 12 de stdlib y 2 de dependencias obligatorias sin motivo, y 59 internos que en su mayoría no esquivan ningún ciclo; paso propio de imports, con motivo visible para los que se quedan) |
| `nodos_largos` | 15 (físicas) → 14 (X96) → 13 (X106) → 12 (S9b A′/X126) → **4** (X134: el escáner ahora cuenta líneas de **código**, no físicas; el 12 físico queda como diagnóstico no gateado) → **3** (X137/I4: el render del informe del lote salió del nodo) | ≤ 3 ✅ (definición de X134: más de 40 líneas de código; quedan `juez.Judge` 72, `effective_n.WriteReport` 50 y `effective_n.HashFile` 47, que esperan la recomposición de P4) |
| `lineas_del_producto` | **7.693** (X142: arranque; 74 archivos de código — núcleo + capacidades + utils/ + modules/) | **solo baja** (el límite producto/laboratorio es explícito en `ratchet.py`: `PRODUCTO_RAIZ`/`LABORATORIO_RAIZ`; el laboratorio mide y no engorda al producto; el texto impreso no cuenta, definición de X134) |
| `texto_de_prompt` | 2748 → 1542 (X112: sin la prosa de fable) | **1542** (decisión del operador, X112: lo fijo + la forma de exp/51 + el checklist de exp/78 como opción; ≤ 800 pedía borrar una directiva con efecto medido) ✅ |

## Plan

| Fase | Cambio | ¿Cambia conducta? | Gate de salida |
|---|---|---|---|
| 0 | Estos ratchets + el diagrama del README generado + este documento | No | `./calidad.sh` verde |
| 1 | ✅ 1a (X92): hooks de ciclo de vida en los módulos (S4). ✅ 1b (X93): el producto deja de leer `BANCO`/`DELEGADO`/`GROUND-TRUTH` (S5); el driver PTY sale de `banco/`. ✅ deuda (X109): sin el `.env` ni las tareas de bmo; las sondas de Laya a `banco/probes/`. **Queda**: `HITL_SCOPE` y `HUMANO_RESPUESTA` (revisar) | No | `test_caracterizacion_chat.py` idéntico |
| 2 | ✅ 2a (X94): el kernel con el shared solo de datos. ✅ 2b-1 (X95): `Contexto` (compacción) como nodo. ✅ 2b-2 (X96): `Observar` y `Cierre` (el presupuesto como arista). ✅ S9b A′ (X126): **el chat corre sobre `kernel.loop`** con `Observar`/`Contexto` como políticas y `PasoChat`/`ActuarChat`/`CierreChat` como nodos del chat; se borraron `AgentStep`/`ExecuteTools`/`Cierre`. ✅ S9a (X133): la continuación se decide por el estado del thread (la pregunta anterior abierta por el techo), no por la lista de palabras de `GetQuestion`. ✅ I2 (X135): el juez sin la regex de contexto (el inventario va al prompt y la membresía la hace el código). **Queda**: S3 (esquema de tools fijo y cierre por arista) | Mínimo | `replay`, `test_grafos_sin_calles_muertas.py`, fable s17–s20 |
| 3 | (2d no entró, X99.) Gate previo PASA (X102). 3a NO PASA (X105, cableado borrado). ✅ 3b PASA (X106, `banco/specs/fase3b_4a.md`): el router salió del chat. **Cerradas con veredicto negativo** (decisión del operador): S2 —Laya elige el modo— la rechazó el A/B de la 3a; S1 —`reasoning_content` en rondas de tools— no aplica sin thinking con tools. ✅ X109: el juez de riesgo que solo observaba se borró; el log de la decisión humana queda | **Sí** | los criterios de `banco/specs/fase3b_4a.md` |
| 4 | ✅ 4b-mín (X104): sin la regex de palabras. ✅ 4a (X106): reglas y voto borrados con la 3b. ✅ S6 (X132): un solo techo de 16 por pregunta con saldo en `turno`; `CORTE_NOVEDAD`, `CORTE_NOVEDAD_MIN`, `MAX_TOOL_ROUNDS_AMPLIO` y `UMBRAL_SIN_PROGRESO` salen con su código y sus tests. **El A/B pre-registrado PASA** (52 corridas: calidad +0,167 con margen −0,25, costo 0,958×, descarrilos 6 → 4, 0 deploys, US$0,2307) | Sí | banco + fable: USD y descarrilos ≤ base ✅; `settings_leidos` 56 → 52 ✅ |
| 5 | ✅ 5a (X108): política de comandos como datos (S10) en `utils/politica_comandos.json`, 0 diferencias sobre la foto real de 445. **5b medida y revertida** (X111): el A/B no pasó (disparo 1/2/2 de 4, ruido 1,29×, s18 sin +1,0 ni R1/R3, trampas s3/s9 abajo); `git revert 3273a84` y la regex no vuelve (`banco/specs/fase5b.md`). 5c (paso 4) Laya 0.4.x y los prefiltros como un mecanismo con un setting | Mínimo / Sí (5b) | 5b: NO PASA (X111); 5c: su pre-registro |
| 6 | Limpieza de piezas sueltas (`juez`, `effective_n`, `juez_lote`, `research`, `informe`, `fable_judge`): nodos largos (decisión del operador, X103). Los imports perezosos van en su paso propio (X112) | No | `nodos_largos` ≤ 3 **sobre líneas de código** (X134 corrigió el instrumento: el conteo físico daba 12 y contaba el texto impreso; el arranque con la definición nueva es 4). ✅ I1 (X134a): `effective_n.WriteReport` partido en `Cruzar` → `WriteReport` (73 → 50 de código). ✅ I2 (X135): el juez sin regex de contexto. ✅ I4 (X137): `informe_lote` como función de módulo — `nodos_largos` **4 → 3**, meta cumplida; `Judge`/`WriteReport`/`HashFile` quedan por la recomposición de P4, no por un corte forzado |

**Orden de lo que queda** (X112, aprobado por el operador): 1 ✅ deuda de la
fase 1 → 2 ❌ 5b (revertida) → ✅ X112 (docs, prosa de fable, forma fija,
ratchet sobre los YAML) → 3 imports perezosos → 4 S6 → 5 5c-a / 5c-b → 6
S9a ✅ / S9b ✅ / S3 (bloqueado) → 7 fase 6 ✅. Primero lo que no cambia
conducta; lo que la cambia, con su A/B pre-registrado.

## Inventario de settings (52 tras S6/X132: 39 contrato · 12 revisar · 1 borrar)

`contrato` = decisión del operador que se queda; `revisar` = se decide en la
fase indicada; `borrar` = se va con su rama en esa fase.

| Setting | Veredicto | Fase | Motivo | Lo lee |
|---|---|---|---|---|
| `PROMPT_AUDITORIA` | borrar | 4 | S7/S8: brazos de A/B cerrados → skills | `main.py` |
| `HITL_SCOPE` | revisar | 1 | S5: entrada headless legítima, hoy nombrada como del banco | `utils/aprobaciones.py`, `utils/riesgo.py` |
| `HUMANO_RESPUESTA` | revisar | 1 | S5: entrada headless legítima, hoy nombrada como del banco | `modules/humano.py` |
| `CHAT_STREAM_INTERRUPT` | revisar | 2 | S9: citas e interrupción siempre activas | `utils/call_llm.py` |
| `CITAS_VERIFICAR` | revisar | 2 | S9: citas e interrupción siempre activas | `nodes.py` |
| `PREFETCH` | revisar | 2 | S9: prefetch como nodo; topes como constantes | `utils/prefetch.py` |
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
| `LLM_API_KEY` | contrato | — | credenciales y proveedor | `utils/call_llm.py` |
| `LLM_BASE_URL` | contrato | — | credenciales y proveedor | `modules/vision.py`, `utils/call_llm.py` |
| `LLM_MODEL` | contrato | — | credenciales y proveedor | `modules/vision.py`, `utils/call_llm.py` |
| `MCP_EXPOSE` | contrato | — | superficies opcionales (web, MCP, A2A, búsqueda) | `mcp_server.py` |
| `MCP_SERVERS` | contrato | — | superficies opcionales (web, MCP, A2A, búsqueda) | `utils/mcp_client.py` |
| `MEMORIA` | contrato | — | privacidad: cada sink de datos tiene su apagador (README) | `modules/memoria.py` |
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

