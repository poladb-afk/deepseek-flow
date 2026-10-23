# Estado del arte para los tres experimentos candidatos (explorador aislado · plan mode · loops que convergen)

**Fecha:** 2026-10-23 · **Contexto local:** `docs/informes/fractal_agent_mapeo_2026-10-23.md` y `docs/informes/fractal_spawn_evidencia_2026-10-23.md` (leídos; no se re-busca lo que ya está ahí) · **Método:** 8 consultas web acotadas. Todo lo de producción es **superficie web**: no leí ningún repositorio de terceros clonado; los repos se citan por lo que dice su página/README en los resultados de búsqueda.

> **Alcance y cautela.** Se afirma sólo lo que una fuente dice. Lo que no apareció se marca **no consta** y significa "no lo encontré en estas búsquedas", no que no exista. Tipos de fuente: **doc oficial** (primaria del vendor), **paper** (arXiv), **repo** (código del autor), **blog** (secundario; puede citar primarios sin enlazarlos). Lo que ya estaba en el informe de spawn (aislamiento de Claude Code, sub-agentes de OpenCode, `max_iter` de CrewAI, `recursion_limit` de LangGraph, la tabla comparativa de profundidad/presupuesto) **no se repite**: se usa como base y se agrega sólo lo nuevo.

## Contexto del harness (verificado en esta pasada)

- El supervisor despacha **secuencial**: un nodo `UnPaso` elige tool+args, un nodo `Ejecutar` corre las tool_calls de esa ronda y devuelve el resultado como `role=tool` (`supervisor.py:204`, `supervisor.py:233`). El tope es una constante: `MAX_PASOS = 5` (`supervisor.py:53`) y las tools se retiran al llegar (`supervisor.py:206-208`).
- La mecánica de fan-out ya existe y está medida: `JuezLoteFlow(AsyncParallelBatchFlow)` con semáforo `JUEZ_LOTE_CONCURRENCIA=8` (`juez_lote.py:46`, `juez_lote.py:125`), `asyncio.to_thread` como puente al flujo sync (`juez_lote.py:64`), resultados ordenados por **índice** (`juez_lote.py:112-114`) y speedup medido contra la suma secuencial (`juez_lote.py:151-153`).
- El HITL existe y pausa de verdad: `pedir_aprobacion` va por navegador con `HITL_WEB=1` o por terminal (`utils/aprobaciones.py:74-90`).
- No hay plan persistido, ni sub-agente con contexto fresco, ni condición de parada por convergencia de texto: el corte de todo loop es una constante.

---

## 1. EXPLORADOR AISLADO — sub-agente de sólo lectura con contexto fresco que devuelve un resumen

### (A) Estado del arte

- **OpenCode** es el caso más nítido de "read-only como permiso, no como convención": en plan mode las tools `write` y `edit` están **deshabilitadas por defecto**, con la excepción de archivos bajo `.opencode/plans/*.md` para escribir el plan mismo ([doc oficial de modos](https://open-code.ai/en/docs/modes)). Es decir: el explorador aislado y el que planea son **el mismo agente restringido**, no dos piezas distintas.
- **OpenCode** clasifica los agentes en `primary` (a los que el usuario les habla) y subagentes (invocados por el primario o con `@`); el agente de planificación se declara `mode: primary` y su descripción es "analiza código, sugiere cambios o crea planes **sin hacer modificaciones**" ([doc oficial de agents](https://opencode.ai/docs/agents/)).
- **Codex CLI** resuelve el mismo eje con **sandbox + modos de aprobación** (`--suggest`, `--auto-edit`, `--full-auto`): el modo bajo el que corre un rol es configurable por invocación, y la ejecución va en sandbox por defecto ([blog secundario que enumera los modos](https://www.blott.com/blog/post/openai-codex-cli-build-faster-code-right-from-your-terminal), [deepstation](https://deepstation.ai/en-au/blog/what-is-openai-codex-cli-the-guide-to-ai-powered-coding-2026)). El primario de los modos (`developers.openai.com/codex/...`) no apareció en mis resultados → **no leí la doc oficial de Codex en esta pasada**.
- **Claude Code**: ya documentado en el informe de spawn (ventana propia, devuelve resumen, profundidad 5, subset de tools por agente en `.claude/agents/*.md`). Lo nuevo de esta pasada confirma el **mecanismo de "read-only"**: es un toolset recortado, igual que OpenCode; no hay un "modo de lectura" del filesystem.
- **Lo que NO consta** en ninguna de las fuentes de esta pasada: cuántos tokens recibe/hereda un sub-agente explorador, ni si se le aplica un tope de tiempo. Confirma lo del informe de spawn: nadie entrega presupuesto heredado por sub-agente.
- **Riesgo de seguridad con nombre en el estándar**: OWASP Top 10 for LLM Applications **LLM06:2025 — Excessive Agency** define el fallo como "capacidad, permisos o autonomía mayores que los necesarios" ([listado OWASP GenAI](https://genai.owasp.org/llm-top-10/), [desglose secundario](https://www.linkedin.com/pulse/owasp-llm-top-10-countdown-6-excessive-agency-ash-fahim-nfbde)). Un explorador con **toolset recortado a lectura** es la mitigación canónica de ese ítem. La versión "Top 10 for Agentic AI" aparece en blogs secundarios ([akto](https://www.akto.io/blog/owasp-top-10-for-agentic-ai-security)); **no verifiqué** que sea publicación oficial distinta de la de LLM.

### (B) GITHUBS inspiracionales

- **[anomalyco/opencode](https://github.com/anomalyco/opencode)** (fuente: [doc oficial de modos](https://open-code.ai/en/docs/modes), [issue #1293](https://github.com/anomalyco/opencode/issues/1293) que ya citaba el informe de spawn). **Mecanismo que nos sirve:** el modo de un agente es un **mapa de permisos por tool** (`write: false`, `edit: false` salvo una ruta permitida). Copiable literal como dict `{tool: "permitir"|"negar"}` sobre el catálogo que ya arma `discover()` en `supervisor.py:58`.
- **[cline/cline](https://github.com/cline/cline)** (fuente: [README del CLI](https://github.com/cline/cline/blob/main/apps/cli/README.md), [discusión #2311](https://github.com/cline/cline/discussions/2311)). **Mecanismo que nos sirve:** auto-aprobación **por tool y por tarea** — el usuario pre-aprueba las tools de lectura al pasar a modo Act, y en modo Plan el modelo no escribe. Es la política de permisos como tabla, no como rama del código.
- **[AgentScope](https://github.com/agentscope-ai/agentscope)** (`as_tool()`: sub-agente con conversación fresca que devuelve su resultado **como resultado de tool**) — ya citado en el informe de spawn con su [doc](https://java.agentscope.io/en/multi-agent/agent-as-tool.html); sirve como **forma del contrato de retorno**, no como dependencia.
- **Para "explorador que resume"** no encontré un repo que implemente específicamente "contexto fresco + resumen al padre" fuera de estos harness: **no consta** un repo canónico separado.

### (C) Diseño mínimo para el harness

Una tool `explorar` en el catálogo del supervisor, implementada como **mini-flow síncrono** con su propio `shared` y toolset de sólo lectura:

- **Toolset = `TOOLS` filtrado por nombre** desde `utils/fs_tools.py` (`read_file`, `list_files`, `search_files`; `run_command` **fuera**, por ser el que puede escribir). El filtro es una lista blanca de nombres, no un `if` dentro de cada tool.
- **Contexto fresco**: su `shared` es `{"messages": [system_explorador, user_pregunta]}`; el padre sólo recibe `{"resumen": texto, "citas": [...], "left": rondas_restantes}` — el mismo contrato de devolución del prototipo (`fractal_agent__1_.py:468`, ya citado en el mapeo).
- **Presupuesto**: el hijo arranca con `MAX_PASOS_EXPLORADOR` propio (3 es suficiente para leer/grep/cerrar) y **devuelve lo no usado** al padre, que es el esquema de `Spawn` del prototipo pero con un contador entero en vez de un objeto `Budget`. Si el padre está en su última ronda, no se permite `explorar` (evita el cierre con la tool colgada).
- **Sin paralelismo en la v1**: una exploración por ronda y secuencial; el fan-out queda para cuando haya demanda medida, con `JuezLoteFlow` como precedente copiable (`juez_lote.py:125`).
- **Verificación medible**: mismo bench del supervisor, comparando `llamadas` y `ok` con y sin la tool; la métrica honesta es **llamadas por respuesta correcta**, no latencia.

---

## 2. PLAN MODE ESTRUCTURADO — plan persistido + aprobación + ejecución contra el plan

### (A) Estado del arte

- **OpenCode**: plan es un **estado de permisos** (sin `write`/`edit` salvo `.opencode/plans/*.md`) y se cambia con **Tab** entre `plan` y `build` ([doc de modos](https://open-code.ai/en/docs/modes), [recorrido secundario](https://learnopencode.com/en/3-workflow/01-plan-build), [educative](https://www.educative.io/courses/learn-opencode/plan-mode-vs-build-mode)). Clave de diseño: el artefacto del plan **se escribe en un archivo**, no vive en el chat.
- **Claude Code**: el plan mode tiene **una tool propia para salir** — `ExitPlanMode` "presents a plan for approval and exits plan mode" ([tool reference oficial](https://code.claude.com/docs/en/tools-reference)). O sea: la aprobación humana es una **tool call bloqueante**, no un mensaje. Se entra con `--permission-mode plan`, con `{"permissions": {"defaultMode": "plan"}}` por proyecto, o con una tool `EnterPlanMode` ([issue del repo](https://github.com/anthropics/claude-code/issues/19426), [análisis secundario del mecanismo](https://diaozxin007.github.io/reading-claude-code/en/interaction/exit-plan-mode.html), [dev.to sobre el schema vacío de EnterPlanMode](https://dev.to/_94be737e156beb4d74df2/claude-code-tools-deep-dive-2-enterplanmode-why-an-empty-schema-is-a-design-choice-51d1)). Hallazgo interesante y verificable sólo por análisis de terceros: `ExitPlanMode` tiene **schema vacío** y el menú de opciones que presenta **no está documentado** (issue #19426) — el punto de fricción conocido es que una vez aprobado se pasa a auto mode.
- **aider**: **architect mode** usa **dos modelos en dos pasadas** — un modelo arquitecto propone el cambio en prosa y un modelo editor lo traduce a ediciones concretas en el formato diff de aider ([doc oficial de modos](https://aider.chat/docs/usage/modes.html), [guía secundaria](https://www.deployhq.com/guides/aider), [cheat sheet](https://computingforgeeks.com/aider-cheat-sheet/)). Costo explícito: "roughly doubling inference on those tasks" ([secundario](https://tokenminning.ai/ides/aider)).
- **Codex CLI**: los tres modos `suggest`/`auto-edit`/`full-auto` funcionan como **nivel de autonomía por invocación**, con sandbox por defecto ([secundario](https://freeacademy.ai/lessons/codex-approval-modes), [skillshub](https://skillshub.wtf/TerminalSkills/skills/openai-codex-cli)). **No consta** que exista un "plan mode" con artefacto propio en Codex; el eje documentado es aprobación, no plan.
- **Papers** (plan como estructura explícita y su ejecución):
  - **ReWOO** (arXiv [2305.18323](https://arxiv.org/pdf/2305.18323)): paradigma **Plan-Work-Solve** — el planificador escribe un *blueprint* completo por adelantado, los workers ejecutan y guardan evidencia como variables, el solver sintetiza. Argumento de eficiencia: se ahorran tokens porque las observaciones **no vuelven al razonador**.
  - **LLMCompiler** (arXiv [2312.04511](https://arxiv.org/abs/2312.04511)): planificador que emite un **DAG de llamadas con dependencias** + *Task Fetching Unit* que despacha en paralelo lo independiente + ejecutor; reporta hasta **3.7× menos latencia, 6.7× menos costo y ~9% más accuracy** frente a ReAct en sus benchmarks ([abstract y PDF](https://arxiv.org/pdf/2312.04511), código del autor en [SqueezeAILab/LLMCompiler](https://github.com/SqueezeAILab/LLMCompiler)).
  - **Plan-and-Act** (arXiv [2503.09572](https://arxiv.org/pdf/2503.09572), ICML 2025): planificador que emite planes estructurados + ejecutor que los traduce a acciones del entorno, con datos sintéticos (Synthetic-PA) para entrenar el planificador; el abstract sostiene la mejora en tareas de horizonte largo.
  - **Plan-and-Patch** (arXiv [2610.10786](https://arxiv.org/pdf/2610.10786)): extendiende el mismo eje a un planificador que **genera y repara** el plan; útil como evidencia de que la pieza que falta en el patrón puro es la **reparación** del plan, no sólo su generación.
- **Desviación detectable**: ninguna de las fuentes de esta pasada implementa una **comparación plan-vs-ejecución** explícita. Lo más cercano es Plan-and-Patch (el planificador repara el plan cuando el ejecutor falla) y `ExitPlanMode` (la aprobación congela el plan antes de ejecutar). Un contador de desviación por paso **no consta** en ningún sistema consultado → sería aporte propio.

### (B) GITHUBS inspiracionales

- **[SqueezeAILab/LLMCompiler](https://github.com/SqueezeAILab/LLMCompiler)** — el **plan como lista de tareas con `dependencies`**, y el ejecutor que respeta ese orden. Es lo más cercano a "desviación detectable": si una tarea declara depender de otra, ejecutarla fuera de orden es un error formal, no una impresión.
- **[billxbf/ReWOO](https://github.com/billxbf/ReWOO)** — implementación original del planificador con **placeholders `#E1`, `#E2`** que el worker rellena con evidencia. Mecanismo copiable: el plan referencia resultados por identificador, así el plan sigue siendo verificable después de ejecutado.
- **[SqueezeAILab/plan-and-act](https://github.com/SqueezeAILab/plan-and-act)** ([ICML 2025](https://github.com/SqueezeAILab/plan-and-act)) — separación planner/executor como **dos prompts y dos modelos**, no dos clases.
- **[datastax/agent-patterns](https://pypi.org/project/agent-patterns/)** (paquete `agent-patterns`, fuente: [PyPI](https://pypi.org/project/agent-patterns/)) — catálogo ejecutable de Plan&Solve y ReWOO; sirve como **referencia de forma**, no como dependencia. (No verifiqué el repo en GitHub; sólo la página de PyPI.)
- **LangChain**: la guía oficial de plan-and-execute es un blog del vendor ([blog.langchain.dev](https://blog.langchain.dev/planning-agents/)) con tres variantes en LangGraph; el ejemplo `plan-and-execute` vive en el repo de LangGraph (no abrí el repo en esta pasada → **no verificada la ruta**).

### (C) Diseño mínimo para el harness

Tres piezas, ninguna nueva dependencia, todas en `supervisor.py`:

1. **`Planear` (Node) antes de `UnPaso`**: una sola llamada que devuelve `{"pasos": [{"n": 1, "tool": "...", "args": {...}, "listo_cuando": "..."}]}` acotada a `MAX_PASOS` pasos. Se guarda en `shared["plan"]` y **se escribe en `salidas/plan.md`** (mismo escritor que ya usa el repo; el plan sobrevive a la sesión).
2. **Aprobación = el HITL que ya existe**: `pedir_aprobacion("¿Ejecuto este plan?", cuerpo=plan_md)` (`utils/aprobaciones.py:74`). Rechazo → se vuelve a planear **una** vez; segundo rechazo → se aborta como hoy. No hace falta una tool `ExitPlanMode`: el HITL del repo ya devuelve bool y ya pausa por navegador.
3. **Desviación detectable sin juicio nuevo**: cada ronda compara la tool elegida por `UnPaso` contra `plan[ronda]["tool"]`; si no coincide, se registra `desvio` en `shared["hechos"]` (una línea de texto por ronda: `plan=X real=Y`) y se **permite** el desvío pero se le pasa al modelo como feedback en el mensaje de la ronda siguiente. Al cierre, `Sintetizar` imprime la tabla `plan vs real`. Esto es más débil que el DAG de LLMCompiler y más barato: no requiere grafo ni topología.

**Lo que NO se copia**: el par architect/editor de aider (duplica inferencia; su costo sólo se paga con un modelo editor barato, que no es nuestro caso con un único proveedor) y el DAG paralelo de LLMCompiler (el harness es secuencial por diseño y el paralelismo ya tiene su precedente medido en `juez_lote`).

---

## 3. DRIED / CONVERGENCIA DE LOOPS — parar cuando el texto dejó de cambiar

### (A) Estado del arte

- **Reflexion** (arXiv [2303.11366](https://arxiv.org/pdf/2303.11366), NeurIPS 2023): el agente reflexiona verbalmente sobre la señal de feedback, guarda el texto reflexivo en una **memoria episódica** y lo usa para inducir mejores decisiones en el siguiente intento ([alphaXiv](https://www.alphaxiv.org/resources/2303.11366)). El bucle es **entre intentos** (trial → reflexión → trial), no dentro de una respuesta. Código del autor: [noahshinn/reflexion](https://github.com/noahshinn/reflexion).
- **Self-Refine** (arXiv [2303.17651](https://arxiv.org/abs/2303.17651)): un solo LLM genera, se da feedback y refina; el paper no exige datos supervisados ni RL. Código del autor: [madaan/self-refine](https://github.com/madaan/self-refine).
- **Condición de parada en la práctica**: la forma que aparece en el material consultado es **tope de iteraciones + criterio del propio modelo** ("pide mejoras hasta que el modelo emite feedback diciendo que no hay más issues, o se llega a N iteraciones") ([catálogo de patrones](https://www.agentpatternscatalog.org/landing/patterns/self-refine/), [blog con `MAX_ITERATIONS` concreto](https://www.linkedin.com/pulse/reflexion-pattern-how-build-self-correcting-agent-langgraph-shah-5w7ec)). No encontré una fuente primaria que defina un criterio **textual** de convergencia (p. ej. "el texto no cambió").
- **Loops infinitos como modo de fallo con nombre propio**: entre las defensas listadas están "set max_iterations, loop detection, circuit breakers" y "limit by iteration count or token budget" ([blog de patrones](https://devops.gheware.com/blog/posts/ai-agent-design-patterns-implementation-guide-2026.html)). Es decir: la industria parchea con topes; detectar la meseta es una mejora, no un requisito.
- **La otra primaria que pedía el pedido**: **Large Language Monkeys** (arXiv [2407.21787](https://arxiv.org/abs/2407.21787)) no es un loop de refinamiento: muestra que **coverage** (la fracción de problemas resueltos por *alguna* muestra) escala con el número de muestras a lo largo de cuatro órdenes de magnitud, con muestreo independiente y el **mismo prompt** ([HTML del paper](https://arxiv.org/html/2407.21787v3), [blog del lab](https://scalingintelligence.stanford.edu/blogs/monkeys/), código [ScalingIntelligence/large_language_monkeys](https://github.com/ScalingIntelligence/large_language_monkeys)). Implicación dura para nuestro diseño: **repetir sin cambiar el prompt converge sólo si hay un verificador que elija**; el paper mide el techo, no la señal de parada.
- **No consta** en las fuentes de esta pasada: una métrica de "dried"/delta de texto usada por un framework de producción.

### (B) GITHUBS inspiracionales

- **[madaan/self-refine](https://github.com/madaan/self-refine)** — el bucle generate→feedback→refine con **el criterio de parada explícito en el prompt** ("no further refinements"). Mecanismo copiable: la condición de parada se **pide al modelo** y se combina con un tope fijo.
- **[noahshinn/reflexion](https://github.com/noahshinn/reflexion)** — memoria episódica **acotada** (se guardan las últimas reflexiones, no todas). Mecanismo copiable: la memoria del loop es un buffer de tamaño fijo, no un log creciente.
- **[ScalingIntelligence/large_language_monkeys](https://github.com/ScalingIntelligence/large_language_monkeys)** — código que **genera N muestras y evalúa correctness** por muestra; es el patrón más barato para medir "cuántas repeticiones valen la pena" sobre nuestro propio banco, sin LLM nuevo.
- Para "delta de texto como criterio" **no aparece ningún repo** en estas búsquedas: **no consta**.

### (C) Diseño mínimo para el harness

La pieza más chica es una **función pura** y un contador en `shared`, sin nodo nuevo:

```python
def seco(a, b):
    """True si b no aporta nada nuevo sobre a: mismo texto normalizado o
    casi (ratio de tokens idénticos por encima del umbral)."""
```

- Se llama al cierre de cada ronda del loop que ya existe (p. ej. `Sintetizar` parcial vs. el cierre anterior, o el borrador del juez entre rondas). Aritmética de conjuntos de tokens con `difflib`/`str.split` de stdlib — **cero dependencias**.
- Regla de corte: **dos cierres secos** ⇒ se termina el loop como si hubiera llegado a `MAX_PASOS` (el texto no cambia; otra ronda cuesta lo mismo que la primera). Un solo seco no corta, porque una ronda puede ser una lectura que no produjo texto nuevo.
- Telemetría obligatoria: anotar en `shared["hechos"]` la ronda en que secó y el `MAX_PASOS` vigente, para poder responder "¿cuánto se ahorró?" con datos del banco existente (`banco/`, `salidas/evals/`).
- **No se copia** el bucle de reflexión entre intentos de Reflexion: el harness no tiene un verificador de éxito por intento fuera del juez, y sin verificador repetir es caro y no garantiza nada (lo dice el propio LLMCompiler comparison y el mapeo del prototipo).

---

## Veredicto: con cuál arrancar (≤5 líneas)

Arrancar por **(3) DRIED**: es la pieza más chica (una función pura + dos contadores en `shared`), **cero llamadas extra al LLM**, usa infraestructura que ya existe (`MAX_PASOS`, `shared["hechos"]`, el banco para medir el ahorro) y su evidencia es primaria y consistente (Reflexion/Self-Refine parchean con topes; Large Language Monkeys muestra que repetir sin verificador sólo sube el costo). Segundo, **(1) explorador aislado**, porque reusa el toolset filtrado y el contrato "devuelve un resumen" ya probados en el prototipo, y su riesgo de seguridad (LLM06 Excessive Agency) se cierra con una lista blanca. **(2) plan mode** es el de peor razón evidencia/costo: exige una llamada de planificación por tarea (duplica la inferencia, como architect mode), el plan se desactualiza en cuanto el modelo se desvía y ninguna fuente consultada implementa el detector de desviación — sería aporte propio, no copia.

## Huecos honestos (lo que no encontré)

- **No leí la doc oficial de Codex CLI** ni la de aider en su sitio primario (sólo el `docs/...` de aider y secundarios para Codex): las afirmaciones sobre los tres modos de aprobación se apoyan en blogs.
- **No hay fuente primaria** del criterio de convergencia textual (`dried`): es diseño propio inspirado en `fractal_agent__1_.py:186-189` (ya mapeado), no un patrón publicado.
- **No verifiqué** la existencia de un "OWASP Top 10 for Agentic AI" oficial distinto del Top 10 for LLM Applications.
- **No abrí** ningún repo de GitHub en esta pasada: los mecanismos se citan por README/página en los resultados de búsqueda.
