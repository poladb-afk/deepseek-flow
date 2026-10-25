# Comparativa: los siete subsistemas del paper vs. este harness

**Fecha:** 2026-10-22 (taxonomía verificada contra el paper el mismo día) · **Contra qué se compara:** [arXiv:2609.00006](https://arxiv.org/abs/2609.00006) — *"Harness Engineering: Anatomy, Architecture, and Evolution of Coding Agents — A Source-Code Study of Eleven Systems"* (Barbaste, Darrigol, Vu, Wiltberger; 15-jul-2026), según la síntesis en [salidas/research_harness_engineering.md](../../salidas/research_harness_engineering.md).
**Contra qué se compara el harness:** la documentación del repo verificada línea
a línea (`docs/design.md` 1–499, `docs/informes/capacidades_harness_y_pruebas.md`
1–147), no el código.

Veredicto por subsistema con el vocabulario del issue #636 del paper:
**coincide** · **difiere a propósito** · **brecha**.

## 0. Sobre la fuente y la taxonomía

Los **siete subsistemas canónicos del paper** (verificados contra el HTML de
arXiv el 2026-10-22, no ya contra la formulación secundaria del research) son:
**Agent loop · LLM integration · Tools & actions · Memory & context · Safety &
permissions · Orchestration · Extensibility**. Las secciones 1.1–1.7 siguen
ese orden.

El material de research sigue siendo **sin cifras** de coste por tarea,
contexto, loop budget ni ablaciones A/B (`research_harness_engineering.md:93-100`).
Donde el paper no tiene número, acá tampoco se inventa uno.

## 1. Tabla comparativa

### 1.1 Agent loop (bucle agente-herramienta)

- **Harness**: `GetQuestion → AgentStep → ExecuteTools → AgentStep`, con tool
  calling nativo de DeepSeek en vez de YAML (`design.md:20-34`). `AgentStep` con
  `max_retries=3, wait=5` (`design.md:126-127`); `ExecuteTools` suma
  `tool_rounds` y vuelve al `default` (`design.md:128`).
- **Paper**: núcleo de la Figura 1; en DeepSeek Harness bucle, herramientas e
  interfaz son plugins (`research_harness_engineering.md:78`).
- **Veredicto: COINCIDE**, y con una pieza que el material no cubre: la
  recuperación de `tool_calls` que llegan como texto en vez de estructura.
- **Riesgo propio**: el retry del Node repite la llamada ante un fallo
  transitorio, pero el presupuesto de rondas es por pregunta, no por reintento.
  No está documentado si un retry consume ronda. **No verificado en código** —
  queda como pregunta abierta, no como defecto.

### 1.2 LLM integration

- **Harness**: un solo cliente (`utils/call_llm.py`) contra la API de DeepSeek
  (modelo y base URL por settings); el **modo thinking pegajoso** es contrato
  compartido por las tres variantes (clásica, agente, streaming): todo tráfico
  agéntico viaja con thinking desactivado porque el cliente descarta
  `reasoning_content` (`design.md:137-146`).
- **Paper**: el subsistema existe porque la integración es una superficie con
  contrato propio; la implementación maximal del material es `pi-ai`, la API
  unificada multi-proveedor de Pi (OpenAI, Anthropic, Google —
  `research_harness_engineering.md` y [pi.dev](https://pi.dev/)).
- **Veredicto: COINCIDE en contrato, DIFIERE a propósito en amplitud.** Un
  proveedor configurado vs. multi-proveedor con cambio de modelo en caliente.
  El harness es DeepSeek-first por decisión (el router, el juez de riesgo y las
  sondas están calibrados para ese modelo); cambiar de proveedor acá no es
  plug-and-play ni se pretende que lo sea.

### 1.3 Tools & actions (ejecución de herramientas)

- **Harness**: contención de rutas por `Path.resolve` contra
  `AGENT_ALLOWED_DIRS` (`design.md:181`); hooks pre/post con veto posible;
  salida truncada y timeout configurable por comando.
- **Paper**: en DeepSeek Harness bucle, herramientas e interfaz son plugins
  (`research_harness_engineering.md:79`).
- **Veredicto: COINCIDE** — tools con esquema declarado (TOOLS/IMPL por
  módulo), despacho central (`run_tool_call`) y error-como-feedback.

### 1.4 Memory & context (gestión de contexto y compactación)

- **Harness**: `[compacción]` con zona fría respaldada en `memoria/`; huella
  `_compaccion_huella` evita re-compactar la misma ronda y `_respaldo_huella`
  evita reescribir el respaldo de la misma zona fría (`design.md:105-106`, exp/70).
  Marcador con ruta vigente. Límite por lectura: `READ_MAX_CHARS`
  (`design.md:186`). Memoria entre sesiones como biblioteca consultable (no
  auto-inyectada).
- **Paper**: Codex compacta automáticamente al acercarse al límite
  (`research_harness_engineering.md:67`). **Sin umbrales ni cifras.**
- **Veredicto: COINCIDE**, con más instrumentación que la documentada en la
  fuente: el harness tiene umbral configurable (`COMPACTION_CHARS`),
  deduplicación de respaldo y evento en traza (`capacidades_harness_y_pruebas.md:31`).
- **Divergencia útil**: acá la compactación **no descarta**, respalda en memoria
  recuperable con `memory_search`. La fuente no menciona si Codex conserva nada.

### 1.5 Safety & permissions (permisos, HITL y modos restringidos)

- **Harness**: política graduada auto/pregunta/doble en `utils/policy.py`
  (`capacidades_harness_y_pruebas.md:81`); hooks con denylist dura que vetúa
  antes del HITL (`capacidades_harness_y_pruebas.md:82`); HITL en tres niveles
  (`:51`), HITL web loopback con token en tiempo constante y default seguro
  ante timeout (`design.md:250-268`), `/aprobaciones` (`:53`). Lo más cercano a
  un modo restringido: skills declarativos que recortan la lista de tools
  anunciada (`design.md:271-278`) — **guía, no sandbox** (el action space sigue
  completo).
- **Paper**: OpenCode tiene "Mode: primary" restringido para planificación, con
  sistema de permisos (`research_harness_engineering.md:80`); DeepSeek Harness
  viene con sandbox (`:79`). **Sin métricas.**
- **Veredicto: COINCIDE en política, BRECHA declarada en dos frentes.**
  (a) Aislamiento: "no es un sandbox de sistema operativo"
  (`capacidades_harness_y_pruebas.md:145`) — el perímetro es best-effort y la
  contención es de **rutas, no de efectos**: un `run_command` aprobado por HITL
  puede tocar lo que quiera dentro del usuario del proceso. Decisión, no olvido.
  (b) **Plan mode**: no hay un modo donde el harness no pueda escribir,
  garantizado por el runtime. Lo mínimo para cerrarlo: un skill/estado que
  además de recortar `tools` fuerce el HITL de escritura a "doble" o niegue
  `write_file`/`edit_file`/mutantes en policy. **No implementado; no lo pide
  este pedido.**

### 1.6 Orchestration (multi-agente)

- **Harness**: `debate` (proponente vs crítico por `asyncio.Queue`,
  `design.md:445-455`), `supervisor` (bucle reactivo con Choose local, mayoría
  2-de-3, self-healing, `design.md:478-534`), `juez_lote` sobre
  `AsyncParallelBatchFlow` (`design.md:277`), `a2a_tarea`/`agentes_remotos`
  (`capacidades_harness_y_pruebas.md:78`).
- **Paper**: OpenCode define "Mode: subagent" de solo lectura para explorar
  (`research_harness_engineering.md:69`); 66 configuraciones modelo–harness.
  **Sin ablación cuantitativa.**
- **Veredicto: DIFIERE A PROPÓSITO.** La orquestación acá es **por pipeline
  declarativo** (cada pieza es un grafo con forma fija), no por delegación
  interactiva del agente principal a un subagente. Lo que el paper describe como
  subagente exploratorio, acá lo resuelve el `pre-fetch` declarativo
  (`capacidades_harness_y_pruebas.md:30`) y las tools de lectura del mismo bucle.
- **Costo de la decisión**: no hay aislamiento de contexto por subagente, que es
  justamente lo que un subagente de solo lectura aporta. Es el precio de tener un
  solo historial.

### 1.7 Extensibility (extensiones y skills)

- **Harness**: `modules/*.py` con `TOOLS` + `IMPL`, descubiertos al arrancar
  (`design.md:283-311`); el action space del chat **es** el registro de módulos;
  agregar = dejar un archivo, quitar = borrarlo. Skills YAML con condición regex,
  instrucciones y subset de tools (`design.md:271-278`).
- **Paper**: en DeepSeek Harness, bucle/herramientas/interfaz son plugins
  (`research_harness_engineering.md:81`); **11 de 11** agentes de producción
  revisados no usaban framework (`research_harness_engineering.md:60`).
- **Veredicto: COINCIDE**, y es el punto donde la evidencia del paper respalda
  la decisión de arquitectura del repo. El harness usa PocketFlow como librería
  mínima y todo lo demás es propio, que es exactamente el patrón de los 11
  agentes auditados.

### 1.8 Evaluación — fuera de la taxonomía del paper

Los siete subsistemas del paper **no incluyen evaluación**; esta sección va
aparte por eso. El harness: gate `calidad.sh` (ruff + C901 ≤ 12 + suite,
`capacidades_harness_y_pruebas.md:110`), inventario de tests (`:111`), bench del
juez con baseline y backup (`:139-147`), `evals` / `replay` / `effective_n`
(`:104`), juez adversarial de trabajo terminado con compuerta de hechos
(`design.md:326-380`). El paper: "own your evals" aparece de forma implícita,
**no como framework formal** (`research_harness_engineering.md:72`, `:91`).

- **Veredicto: COINCIDE y EXCEDE.** El paper y las fuentes derivadas **no tienen
  coste por tarea medido** (`:93`) ni ablaciones A/B de HITL/compactación/skills
  (`:99`). El harness sí tiene ablaciones propias —exp/52-B negativo con default
  cambiado por la medición (`design.md:190`), exp/70, exp/81-83— y un instrumento
  cuyo grading evolucionó por evidencia y no por conveniencia
  (`capacidades_harness_y_pruebas.md:139-147`).
- **Único faltante real del lado propio**: **coste/tokens por tarea**. Sin eso,
  la ventaja "own your evals" es de rigor, no de la métrica que el paper señala
  como eje diferencial (`research_harness_engineering.md:88`).

## 2. Síntesis

| Subsistema (paper) | Veredicto | Lo que el paper respalda | Lo que falta del lado propio |
|---|---|---|---|
| Agent loop | coincide | núcleo del runtime | — |
| LLM integration | coincide en contrato, difiere a propósito | integración como superficie con contrato | multi-proveedor (deliberado: DeepSeek-first) |
| Tools & actions | coincide | herramientas como plugins | — |
| Memory & context | coincide | compactar es estándar | umbral en traza, ya existe |
| Safety & permissions | coincide en política, **brecha** en plan mode y sandbox | permisos que el runtime garantiza | modo sin escritura en policy; sandbox OS (declarado fuera) |
| Orchestration | difiere a propósito | subagente de solo lectura | aislamiento de contexto |
| Extensibility | coincide | 11/11 sin framework | — |
| (Evaluación, fuera de taxonomía) | coincide y excede | own your evals | **coste por tarea medido** |

**Lectura de conjunto.** El harness no está atrás en construcción: está atrás en
**una** capacidad (plan mode con enforcement) y en **una** medición (coste por
tarea). Todo lo demás es divergencia deliberada y documentada, que es el veredicto
que el propio paper considera normal entre harnesses
(`research_harness_engineering.md:89`).

Lo más citable de esta comparación, en orden:

1. Los **11/11 sin framework** validan la arquitectura de módulos y el PocketFlow
   mínimo. No hace falta defenderla más: hay evidencia externa.
2. La **saturación de SWE-bench (5 pp entre los 10 mejores)** con
   **brecha de eficiencia 10x** significa que el próximo experimento con retorno
   real no es una capability más, es **instrumentar tokens por pregunta**. El
   harness ya emite `.runs/*.jsonl`; falta la contabilidad de uso por llamada.
3. El caso de **reintentos infinitos con 429** (`:70`) es la justificación
   externa del `presupuesto()` por pregunta y del corte por no-progreso
   (`design.md:183-185`). Esas dos leyes no son over-engineering defensivo: son
   el defecto que otros harnesses midieron en producción.

## 3. Límites de esta comparativa

- Compara **documentación contra documentación**, no código contra código. Si
  `docs/design.md` derivó del código, esta tabla hereda la deriva. Las secciones
  de `design.md` posteriores a la línea 499 (juez, fable, auditoría, RAG, debate,
  research, supervisor) se leyeron **hasta 534**; el resto se citó por rango
  desde `capacidades_harness_y_pruebas.md`, **no verificado línea a línea**.
- La **taxonomía de los siete subsistemas sí está verificada** contra el HTML de
  arXiv (2026-10-22); el resto del contenido del paper llega por el research
  propio (segunda mano, con sus búsquedas falladas declaradas). Un veredicto
  "coincide" significa "coincide con esa formulación".
- **No hay coste ni latencia medidos** de ningún lado. La comparación de
  eficiencia queda pendiente por falta de datos en ambas columnas.
- Un solo harness evaluado. No se compara contra Claude Code, Codex CLI, OpenCode
  ni Pi por falta de cifras en el material — sólo contra lo que el paper
  sistematiza.
