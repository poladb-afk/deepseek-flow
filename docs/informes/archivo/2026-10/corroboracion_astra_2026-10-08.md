# Corroboración de la auditoría externa (Astra) — 2026-10-08

**Qué es esto.** El informe `informe_correcciones_deepseek_flow.md` (22 correcciones,
C01–C22) se escribió sobre un **ZIP anterior** (`deepseek-flow-main.zip`, Python
3.12, PocketFlow 0.0.3). Este documento lo corrobora **contra el repo vivo**
(Python 3.14, PocketFlow local de 99 líneas), con reproducción cuando el claim
era barato de probar y refutación explícita cuando no.

**Método.** Cuatro auditores adversariales en paralelo (uno por bloque), con la
consigna de no creerle al informe; más sondas propias sobre los P0. Nada de red,
nada de checkpoints de Laya, ningún archivo modificado durante la verificación.
Las líneas citadas por el informe (`nodes.py:86-104`, `laya.py:29-48`,
`supervisor.py:74-80`…) corresponden al ZIP y **no** al repo: cada veredicto
lleva la ubicación real.

## 1. Veredictos

| ID | Veredicto | Evidencia en el repo vivo | Rama |
|---|---|---|---|
| C01 | **CONFIRMADO (P0)** | `informe.py:181`, `auditoria.py:100`, `research.py:127`, `supervisor.py:330` (+ `effective_n.py:253/341`, `juez_lote.py:216`): `Path.write_text()` con `salida` elegida por el modelo, sin `_resolve`. Sonda: `write_file` RECHAZA la ruta externa y los flujos la escribían igual | exp/26 |
| C02 | **CONFIRMADO en HEAD → ya corregido** | `read_file` rechazaba el enlace; `search_files` devolvía su contenido (sonda con `tmp_path` + symlink). Corregido con `sin_enlaces` en `fs_tools`, `informe` y `rag` | exp/22 |
| C03 | **CONFIRMADO con matiz** | `_SEMAFORO` de módulo (`informe.py:36`): la 2ª corrida async del proceso falla con *bound to a different event loop*; en el flujo NO crashea (el retry la salva) pero cuesta **5,03 s vs 0,04 s** | deuda |
| C04 | **YA CORREGIDO** | `flow.py:23` ya es `directo - "answer" >> ask` desde el 2026-10-05; test vigilante `test_smoke.py:685-694` | — |
| C05 | **YA CORREGIDO** | import perezoso en `modules/supervisor.py:28`; 5 procesos nuevos con `import supervisor/modules.supervisor/nodes` → rc=0 | — |
| C06a | **CONFIRMADO en parte** | asserts validan entrada externa (`estructura.py:29`, `supervisor.py:165/272`, `research.py:49/110/112`, `debate.py:121-122`). Con `-O`: `queries` como str se itera carácter a carácter (17 búsquedas). **El claim de los 6 pasos del supervisor NO reproduce** (es un `if len(hechos) >= MAX_PASOS`, inmune a `-O`) | exp/28 |
| C06b | **YA CORREGIDO** | `juez.py:112` normaliza `problems`; `verdict: retry` sin problems no explota | — |
| C06c | **PARCIAL** | el juez ya reintenta citando el crudo inválido; research/supervisor/debate repiten el mismo prompt (retry de PocketFlow) | deuda |
| C07 | **CONFIRMADO** | `Judge.prep` verifica las citas y solo se lo CUENTA al LLM (`juez.py:117-128`); con `verdict: ok` entregaba un borrador citando `/ruta/falsa.md:99`. El refinamiento no recibía el borrador previo | exp/29 |
| C08 | **PARCIAL** | informe/auditoría/research devuelven solo la ruta; `run_effective_n` sí devuelve datos; el supervisor ya pasa el resultado del paso N al N+1 | deuda |
| C09 | **PARCIAL** | literales ya corregidos (`_sin_literales`, tanda de deuda); **falta** el tope efectivo (`LIMIT 100` → 100 filas) y `mode=ro`. Medido: `SELECT * … LIMIT 100` = 29.281 chars al contexto vs 12.694 con 50 | deuda |
| C10 | **CONFIRMADO** | `_indice_cache` no se invalidaba al reindexar: la búsqueda de la sesión devolvía el índice viejo | exp/23 |
| C11 | **CONFIRMADO** | `[]`, `null` y `{"answers": null}` → `AttributeError` en `stats_de` y en el cargador | exp/24 |
| C12 | **CONFIRMADO (pérdida real)** | `collect_files` tope 30 heredado por `carga_trazas`; y el `DROP TABLE` fuera de transacción: una carga fallida dejaba la tabla anterior **vacía** (reproducido) | exp/24 |
| C13 | **CONFIRMADO** | 20 queries aceptadas (el prompt pide 3); `MAX_ROUNDS=2` = 3 ciclos; sin presupuesto global | exp/28 (parcial) |
| C14 | **CONFIRMADO** | `LayaRouter.exec` sin try: la excepción de inferencia **escapaba del Flow** (sonda); etiqueta fuera de contrato → chat cerrado en silencio | exp/25 |
| C15 | **PARCIAL** | el router ve 1000 chars del último mensaje (`nodes.py:423`); el corpus es de 30 casos (no 5) y no mide falsos directos por historial | deuda |
| C16 | **PARCIAL** | `setdefault(HF_HUB_OFFLINE)` afecta al proceso: fastembed lo lee y `rag_index` degrada a BM25 sin descargar | deuda |
| C17 | **CONFIRMADO, pero ruido** | extractos de 300 chars (`websearch.py:24`) deliberados; el prompt final ya dice "usando SOLO este material". Falta declararlo, no cambiarlo | deuda |
| C18 | **CONFIRMADO** | parche de `_run`/`_run_async` sin `finally` (nodo que lanza = 0 eventos); nombre por segundo (dos procesos se truncan); sink sin cerrar | exp/27 |
| C19 | **PARCIAL** | comparten `shared` y `transcript` (no hay aislamiento por colas); `call_llm` sync bloquea el loop, declarado y de impacto acotado (sin timeout/cancelación) | deuda |
| C20 | **PARCIAL / ruido** | `mcp_server` expone `rag_index` por default, pero escribe solo dentro de `rag_index/`; el cliente MCP sin política es real y pide diseño, no parche | deuda |
| C21 | **PARCIAL** | el fallo de portabilidad real no es la ruta de bmo (está en `evals.py`, con degradación) sino el `AGENT_ALLOWED_DIRS` fijo: con otra raíz fallan 2 tests | deuda |
| C22 | **REFUTADO en parte** | `juez --rondas` **sí se usa** (`juez.py:263-269` → `max_rounds`; sonda: rondas=1 → 2 llamadas). Sí es cierto que el README documenta `python3 main.py carga_trazas.py`, que no existe como subcomando | deuda |

**Resumen**: 14 confirmados (2 de ellos P0), 4 ya corregidos, 2 refutados en todo o
en parte, 2 confirmados pero declarados ruido. La auditoría encontró cosas reales
—el P0 de escritura y el P0 de enlaces valen por todo el informe— y a la vez
arrastra el sesgo del ZIP: afirma defectos que ya no existen y cita líneas que
hoy son otra cosa.

## 2. Ramas experimentales (todas con gate verde)

| Rama | Qué cambia | Tests |
|---|---|---|
| `exp/22-contencion-enlaces` | `sin_enlaces()` único: ningún recorrido sigue enlaces (search, list, informe, rag) | 222 |
| `exp/23-cache-del-indice` | `SaveIndex.post` invalida `_indice_cache`: reindexar se ve sin reiniciar | 222 |
| `exp/24-lector-tolerante` | `leer_registro()` compartido (json/forma) + carga completa sin el tope 30 + recarga atómica | 224 |
| `exp/25-laya-router-blindado` | `LayaRouter.exec` como frontera: excepción, etiqueta o confianza inválida → lado seguro | 223 |
| `exp/26-escritura-contenida` | `escribir_salida()` único en 7 sedes: se acabó el bypass de `AGENT_ALLOWED_DIRS` | 222 |
| `exp/27-traza-sin-perdidas` | la traza registra el nodo que falla, nombre con pid, sink cerrado con `atexit` | 222 |
| `exp/28-research-con-presupuesto` | `MAX_QUERIES=3` aplicado por código + tipos validados (sin `assert`) | 222 |
| `exp/29-citas-objetivas` | cita rota con `verdict: ok` → retry forzado; el refinamiento recibe su borrador | 224 |

Cada una sale de `main`, se mergea con `--no-ff` solo si gana, y lleva su test
determinista (sin red, sin LLM, sin checkpoint).

## 3. Por qué esto respeta el marco

- **PocketFlow intacto**: ningún cambio toca el framework; el ruteo por acciones y
  el retry (solo de `exec`) se usan como están. Los fixes de validación
  (`ValueError` en `exec`) se apoyan en el retry existente para re-preguntar.
- **Fractalidad**: cada arreglo es **un helper compartido** que reemplaza N copias
  —`escribir_salida` (7 sedes), `sin_enlaces` (4 recorridos), `leer_registro`
  (informe + cargador), `_cita_rota` (una definición, dos modos)—. Ninguno agrega
  nodos ni flujos nuevos.
- **Ley L8**: los topes los aplica el código, no la obediencia del modelo
  (`MAX_QUERIES`, la compuerta de citas, el corte por no-progreso).
- **Degradación por default**: toda frontera nueva cae al lado seguro
  (herramientas, ERROR como texto, retry), nunca levanta el proceso.
- **Cero dependencias nuevas**: ni Pydantic, ni OpenTelemetry, ni manifiestos.

## 4. Descartes razonados (el consejo los evaluó y los tumbó)

| Propuesta del informe | Veredicto | Versión que sí |
|---|---|---|
| Servicio único de escritura con Pydantic | no | 20 líneas de `escribir_salida` reusando `_resolve` (exp/26) |
| Presupuesto global con `deadline`/`max_depth`/`max_output_bytes` | no | los topes locales que ya existen + `queries[:3]` + `fetchmany` |
| Manifiesto de versión del índice | no | la recarga atómica de exp/24 cubre el daño medido |
| `set_progress_handler` para SQL | no | el tope de filas es el 90% del valor (la hinchazón medida) |
| Descargar páginas web + anti-SSRF en research | no ahora | declarar el alcance (extractos) y medir antes |
| HITL obligatorio en los flujos | **no** | rompe el cron: `input()` sin TTY → EOFError → rechazo; contención sí, fricción no |
| `exigir()` en los 8 asserts | sí, pero después | el daño medido es research; el resto es deuda cosmética |
| Contract `run_id`/`step_id` en la traza | no | pid + `finally` resuelven el daño real (exp/27) |

## 5. Deuda declarada (documentada, no arreglada)

C03 (semáforo por ejecución, ~5 líneas), C06c, C08, C09 (tope de filas + `mode=ro`,
3 líneas), C13 (presupuesto global de llamadas internas), C15, C16, C17 (declarar
el alcance), C19, C20 (política MCP), C21 (fixture de raíces), C22 (el README
miente con un subcomando), más los residuales del informe de Laya
(`revision_laya_2026-10-08.md`).

**Regla de la casa**: nada de esto se toca sin una medición que lo pida. Los
P0 ya están; lo demás espera su número.
