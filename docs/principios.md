# Principios del harness

## Visión

Un harness **minimalista, con forma de grafo y replicación fractal
asimétrica**. Se conforma por un **CORE**; al CORE se le enchufan
**módulos**; un módulo es una capacidad, y los módulos le dan sus capacidades
al CORE. Minimalista no quiere decir simple: el minimalismo está en las
piezas —mínimas e interconectadas— y la complejidad **emerge** de cómo se
conectan (operador, 2026-11-04; el objetivo final textual del 2026-11-02
está en `docs/handoff.md`, sección 1).

Fractal quiere decir que el loop se **replica**: una instancia del harness
contiene instancias del mismo harness. Asimétrica, que las réplicas no son
copias iguales (P2).

Las fuentes fundamentales son tres: **PocketFlow**, **12-Factor Agents** y
**Laya**. De ellas salen las dos familias de principios:

- **Diseño (P1–P4)**: qué es el harness.
- **Elegancia (EL1–EL9)**: cómo es cada pieza, en código y en funcionamiento
  — lo que las tres fuentes tienen en común.

Una restricción (S0) y cuatro prohibiciones (N1–N4) las acotan. Las reglas
de proceso (cómo se escribe y cómo se decide) viven en `AGENTS.md`; las
pruebas de elegancia (F1–F7, C1–C7), el plan del refactor y el inventario de
settings, en `docs/elegancia.md`. Los demás documentos citan estos números y
no los reescriben (N4 también vale para los docs: X144).

Cada entrada nombra el gate que la verifica. Un gate que todavía no existe se
declara "sin gate" con lo que falta: así no se disfraza de regla (lo verifica
`tests/test_handoff.py`).

## Precedencia

1. **S0** (seguridad).
2. **N1–N4** (prohibiciones): ningún principio justifica un parche.
3. **P1–P4** (diseño) y **EL1–EL9** (elegancia). Si dos chocan, decide una
   medición con el cómputo igualado; si la medición no puede decidirlo (una
   pregunta de forma, no de conducta), decide el operador y queda escrito.

## Restricción

| # | Restricción | Qué es | Se verifica con | Cede ante |
|---|---|---|---|---|
| S0 | **Seguridad: falla cerrada y HITL graduado** | Lo no reconocido pregunta; lo irreversible pide doble confirmación; si la política no valida, el chat no arranca. Una copia hereda los frenos de su padre (política, HITL, saldo): la recursión nunca abre un camino que el loop raíz no tenga. P1 no se usa para recortar seguridad (de Pi se toma el núcleo mínimo, no correr sin permisos) | `tests/test_policy_bypass.py`, `test_falla_cerrada_si_los_datos_no_validan`, `test_una_tool_sin_efecto_declarado_escribe_y_corre_en_orden` | Nada |

## Principios de diseño

| # | Principio | Qué es | Se verifica con | Cede ante |
|---|---|---|---|---|
| P1 | **Minimalismo elegante (KISS)** | Lo mínimo que funciona en código, conducta y prompt: un loop, pocas tools en el CORE y un prompt que describe el formato. El contexto se gana: skills y memoria como menú que se carga con una tool. Prefijo estable: nada variable en el system prompt ni tools en caliente. Lo que no decide nada se borra | `texto_de_prompt`, `settings_leidos`, `tests/test_estilo_humano.py`, `bytes_primer_request` (prompt + esquemas de tools) y `lineas_del_loop` (kernel + chat), desde X124 | S0 |
| P2 | **Grafo fractal asimétrico** | Una sola definición del loop (agente = Flow = Node = Tool) que se **replica** en instancias distintas, asimétrica en tres sentidos. **(a) Especialización**: cada instancia lleva su prompt, sus tools y su parte del saldo (`kernel.agente(nombre, descripcion, system, tools)`). **(c) Jerarquía**: un hijo hereda TODOS los frenos del padre —política, HITL, saldo, profundidad— (una política agregada una vez llega a todos los niveles) y recibe, como mucho, las capacidades del padre; la síntesis vuelve siempre al padre. **(b) Forma** —el árbol crece donde el trabajo lo pide y queda corto donde no— queda **medida y no adoptada** (X150, exp/110): la SIMÉTRICA no se elige (0 de 144 llamadas: exp/103 y exp/105) y la ASIMÉTRICA se elige **más** (6 delegaciones en 24 corridas, casi todas con `barrido`), pero no alcanza el umbral pre-registrado (2 de 5 escenarios anchos; pedía 3) y la calidad cae 0,55 con el margen pre-registrado de 0,50. `s19` y `s18` cayeron **sin delegar**, así que con 4 seeds el A/B no separa el daño atribuible del ruido, y F tenía 3 tools más en el menú aunque no delegara (confundido declarado). Queda como capacidad **medida y no perseguida**; con otro modelo o con más n se puede re-medir. Y **cuando la elige no rinde**: de las corridas de F en los anchos, las 5 con al menos una delegación dieron 0,60 de calidad media contra 1,07 de las 15 sin delegar (análisis post-hoc, n=5, no concluyente, dirección de exp/108). La literatura de 2026 la favorece contra lo homogéneo, con costo de coordinación (fuentes de apoyo). **Ley 1**: cada ronda y cada copia descuentan 1 del mismo saldo R, así que llamadas ≤ 2R + 1 con cualquier abanico y profundidad. **Ley 2**: si la rama i recibe la fracción rᵢ del alcance del padre, D resuelve Σ rᵢᴰ = 1; con D ≈ 1 dividir paga, con D > 1 las ramas releen lo mismo. (c) cumplido por construcción (X147): `agente()` declara en `Tool.hijas` lo que verá el hijo y `loop()` falla cerrado al armar si no es un subconjunto de las tools del padre (`ValueError`) | `tests/test_kernel.py`, `tests/test_gate_fractal.py` (los tres niveles, X138), `test_la_profundidad_y_el_saldo_frenan_la_replicacion`, `test_el_arbol_no_pasa_de_2r_mas_1_llamadas_con_cualquier_abanico` (la Ley 1) y `test_d_mide_si_las_copias_se_repartieron_el_alcance` (la Ley 2, `banco/probes/fractal.py`) | S0. Una división entra al producto solo si gana un A/B con el cómputo igualado |
| P3 | **Modularidad** | El CORE no conoce sus módulos; un módulo es una capacidad: un archivo con `TOOLS`, `IMPL` y, si hace falta, `HOOKS`. Agregarlo es dejarlo y quitarlo es borrarlo. El núcleo absorbe primitivas (loop, saldo, efecto, hooks), no features. `Ctx` es lo que el árbol comparte por instancia (`llm`, `ledger`, traza). El despacho y la política son únicos por proceso (`fs_tools.run_tool_call` + `HOOKS_PRE`): eso es lo que hace que un hijo herede los frenos sin poder cambiarlos (X138; redacción aprobada por el operador en X157). Lo opcional (Laya, RAG, MCP, web) es módulo y sin él el harness anda. El producto no sabe que lo miden | `core_importa_modulos`, `tests/test_core_sin_modulos.py`, `producto_conoce_lab`, `tests/test_laya.py` | S0 |
| P4 | **Complejidad emergente** | Las capacidades complejas salen de componer piezas mínimas (loop, tool, saldo, efecto): supervisor, juez y auditoría son composiciones, no subsistemas. El control vive en las aristas y el `shared` guarda solo datos JSON. Los errores vuelven como texto (`ERROR: …`) y el modelo se corrige; **la garantía es del loop, no de cada tool** (decisión del operador, X144): la da un despacho único y compartido, `fs_tools.correr_protegido`, que usan `run_tool_call` y `kernel.Actuar` (X146), sin sumar `except` amplios. La emergencia se observa, no se supone: las fallas topológicas de DIG (terminación temprana o faltante, ramas huérfanas, el mismo subproblema resuelto varias veces, reruteo excesivo) se chequean sobre la traza sin LLM | `nodos_largos`, `test_el_diagrama_del_readme_es_el_grafo_del_chat`, `test_una_tool_desconocida_vuelve_como_error`, `test_las_fallas_topologicas_se_ven_en_la_traza`. Una capacidad nueva entra sin tocar `utils/kernel.py` (review) | S0 |

## Principios de elegancia

Lo que PocketFlow, 12-Factor Agents y Laya tienen en común (X116). Cada fila
dice cómo lo hace cada fuente y con qué se verifica acá; la prueba de detalle
(F/C) está en `docs/elegancia.md`. Antes vivían en ese archivo como "P1–P9",
lo que chocaba con los P de diseño: desde X144 son EL1–EL9.

| # | Principio | PocketFlow | 12-Factor Agents | Laya | Se verifica con | Cede ante |
|---|---|---|---|---|---|---|
| EL1 | **Una primitiva que se contiene a sí misma** | `Flow` hereda de `BaseNode`: un flujo es un nodo | el agente como `foldl` (factor 12) | tres tipos (`noul`, `choice`, `score`) para todo `if` semántico | `test_un_agente_que_se_llama_a_si_mismo_reparte_y_suma`, `tests/test_gate_fractal.py` (F4) | S0 |
| EL2 | **El control es un dato** | `post` devuelve la acción; `-` y `>>` arman la topología | intents como unión tipada (factores 1 y 4) | `choice` como arista condicional | `nodos_largos`, `test_el_diagrama_del_readme_es_el_grafo_del_chat` (F3) | S0 |
| EL3 | **Decidir no es ejecutar** | `exec` no recibe `shared`; el retry envuelve solo a `exec` | "the LLM decides, your code controls" | devuelve una distribución; actúa el que llama | sin gate (review, C2: ¿la decisión se testea sin I/O ni mocks?) | S0 |
| EL4 | **Un solo estado serializable** | `shared` | el thread; el estado de ejecución se deriva (factor 5) | sin estado: estado → respuesta | `test_la_caja_es_json`, `test_checkpoint_ida_y_vuelta_es_identidad` | S0 |
| EL5 | **Composición ortogonal, no casos** | Batch × Async × Parallel por herencia | HITL, errores y pausa: eventos del mismo loop | hooks: cualquier subconjunto de métodos | `helpers_duplicados`, `cuerpos_duplicados` (C1) | S0 |
| EL6 | **Lo particular es dato del que llama** | `params` y utilidades propias | own your prompts; el pre-fetch como dato (apéndice 13) | la pregunta es un dict | `vocabulario_hardcodeado` (F1) | S0 |
| EL7 | **Elegancia por borrado** | sin proveedores ni dependencias | el diff del pre-fetch: casi todo `-` | no genera texto: nada que parsear | `lineas_del_producto` (solo baja); que un diff borre un caso es review (N1) | S0 |
| EL8 | **El default es el seguro** | `exec_fallback`; aviso de arista faltante | escalar al humano | se abstiene; un hook sin definir es no-op | `test_una_tool_sin_efecto_declarado_escribe_y_corre_en_orden`, `test_falla_cerrada_si_los_datos_no_validan` (F6) | Nada |
| EL9 | **Los límites se declaran** | `warnings.warn` en vez de cortar callado | agentes de 3 a 20 pasos (factor 10) | publica su ECE y su recorte de contexto | sin gate (review, C5: ¿el comentario sigue siendo verdad sin su `exp/N`?) | S0 |

## Prohibiciones

La cara negativa de la elegancia: la regla madre ("un arreglo borra un caso,
no lo agrega") dicha como lo que no se hace.

| # | No se hace | Señal de que se violó | Se verifica con | Cede ante |
|---|---|---|---|---|
| N1 | **Parches situacionales**: el arreglo va a la raíz | El arreglo suma un caso: un umbral, una rama, un `if` sobre un nombre concreto | sin gate (review: ¿borra un caso o lo suma?) | Nada |
| N2 | **Hardcodear keywords o hints** para volver determinista lo semántico | Una regex o una lista de palabras juzga significado. La lista blanca de comandos (`utils/politica_comandos.json`) no cuenta: enumera lo permitido y lo demás pregunta (S0). Las listas negras de flags sí: perdieron tres veces (E1, E2, X114) | `vocabulario_hardcodeado` (meta 0) | Nada |
| N3 | **Soluciones por system prompt** | Una frase agregada al prompt para corregir una conducta | `texto_de_prompt` (solo baja) | Nada |
| N4 | **Duplicidad** | Dos implementaciones del mismo concepto: dos loops, dos techos, dos helpers | `helpers_duplicados`, `cuerpos_duplicados`. Un solo loop: cumplido (X126, S9b A′), y su política agregada única tiene gate (X138, ver P2) | Nada |

## De las capas anteriores a esta lista

| Antes | Ahora |
|---|---|
| Antes | Ahora |
|---|---|
| D1 Minimalista, D12 Prefijo estable, D15 Forma humana | P1 |
| D3 Fractal, D8 Presupuesto en todo bucle | P2a (D8 es la Ley 1); la replicación que decide el modelo en ejecución es P2b |
| D2 Modular, D7 Laya opcional, D13 Memoria como biblioteca, D14 Producto sin laboratorio | P3 |
| D4 El grafo dice la verdad, D9 Errores como información | P4 |
| D5 Cada decisión en su lugar, D6 Generalidad, M2 Mecanismo, no lista | N2 |
| M1 A la raíz, M10 Borrar antes que agregar | N1 |
| E10 El prompt no corrige conductas | N3 |
| E4 Un concepto, un lugar | N4 |
| D10 Errores reversibles, D11 Seguridad | S0 |
| E1–E12 y M3–M11 (proceso) | `AGENTS.md`: R1–R10 y la sección "Método" |
| Patrones P1–P9 de `docs/elegancia.md` (X116) | EL1–EL9, en este archivo (X144) |

## Fuentes

Leídas por resumen y abstract: los números son de sus autores, no se
reprodujeron acá. URLs verificadas el 2026-11-02: 33 de 35 responden 200 —una
estaba mal escrita y se corrigió—, el DOI de Parnas es válido por Crossref
aunque ACM da 403 a los bots, y `solosoft.dev` no responde desde esta red.
Las cuatro de 2026 sobre heterogeneidad se sumaron el 2026-11-04 (X144),
también por abstract. Las cuatro de arquitectura fractal (FRACTAL-MAS,
FRACTAL, Lár, FractFlow) se sumaron el 2026-11-07 (X192b), por resumen.

### Fundamentales

| Fuente | URL | Qué tomamos | Dónde se aplica |
|---|---|---|---|
| PocketFlow | https://github.com/The-Pocket/PocketFlow | Grafo + shared store en 100 líneas, sin módulos de proveedor | P1, P4 |
| 12-Factor Agents (HumanLayer) | https://github.com/humanlayer/12-factor-agents | Factor 7 (el humano como tool call), 8 (controlá tu flujo) y 10 (agentes chicos y enfocados) | P2, P4, `request_human_input` |
| Laya | https://github.com/NandhaKishorM/laya | El smart-if: tres tipos de decisión cerrada (`noul`, `choice`, `score`) en una pasada, la pregunta como dato y abstenerse ante la duda | N2, P3, `utils/laya.py` |

### De apoyo

Evidencia que contrasta, acota o mide los principios; no los define.

| Fuente | URL | Qué tomamos | Dónde se aplica |
|---|---|---|---|
|---|---|---|---|
| bmo (harness del operador) | (repo privado) | Un nodo, un módulo, una capacidad; leyes de bucles (L1 anti-recursión, L8 presupuesto); hechos en código e interpretación en el LLM | P3, N2, P2 |
| Anthropic, *Building effective agents* | https://www.anthropic.com/engineering/building-effective-agents | Lo simple y componible antes que el framework; workflows antes que agentes | P1, P2 |
| Anthropic, *Effective context engineering for AI agents* | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | Prompts a la altitud correcta, sin if-else rígido; tools mínimas; compaction | P1, P3, N3 |
| Manus, *Context Engineering for AI Agents* | https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus | KV-cache: prefijo estable, no agregar ni quitar tools en caliente | P1 |
| Anthropic, *Agent Skills* | https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills | Divulgación progresiva por descripción (medida en la 5b: no pasó con este modelo) | S7, `banco/specs/fase5b.md` |
| Rich Sutton, *The Bitter Lesson* | http://www.incompleteideas.net/IncIdeas/BitterLesson.html | Las capas que tapan debilidades del modelo envejecen; lo general escala | N2 |
| mini-swe-agent | https://github.com/SWE-agent/mini-swe-agent | Un agente útil en ~100 líneas | P1 |
| SWE-agent (Yang et al., 2024) | https://arxiv.org/abs/2405.15793 | La interfaz agente–computadora; el linter en la edición como guardrail medido | hook `py_compile`, P4 |
| *Show and Tell* | https://arxiv.org/abs/2511.13972 | Instrucciones explícitas de concisión bajan 56–70 % los tokens del código | `DIRECTIVA_FORMA`, exp/51 |
| D. L. Parnas, *On the criteria to be used in decomposing systems into modules* (1972) | https://doi.org/10.1145/361598.361623 | Un módulo esconde una decisión de diseño | P3 |
| Robert C. Martin, *The Clean Architecture* | https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html | La regla de dependencias: hacia adentro | P3 (F5) |
| Gary Bernhardt, *Functional Core, Imperative Shell* | https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell | Núcleo puro, efectos en el borde | P4 (C2) |
| Martin Fowler, *Yagni* | https://martinfowler.com/bliki/Yagni.html | No construir lo que el pedido no pide | P1 |
| Ponytail | https://github.com/DietrichGebert/ponytail | La pirámide YAGNI y "lazy, not negligent" | P1, `AGENTS.md` |
| code-humanizer | https://github.com/LeonardNJU/code-humanizer | El catálogo de tells de código de IA | P1, `tests/test_estilo_humano.py` |
| slop-scan | https://github.com/modem-dev/slop-scan | Medir contra código humano previo a 2025 | P1 |
| mattpocock/skills | https://github.com/mattpocock/skills | Skills para ingeniería real; el lenguaje compartido como raíz del ruido | P1, `skills/revision.yaml` |
| git-agent-ratchet | https://github.com/monk-eee/git-agent-ratchet | Baseline que solo mejora y guardia anti-bypass | R6, `ratchet.py` |
| ruleward | https://github.com/kernullist/ruleward | Lint de reglas: bloat y deriva | R3, `tests/test_deriva_reglas.py` |
| AI-Agent-Coding-Rules | https://github.com/Emmanuel-Bamidele/AI-Agent-Coding-Rules | Reglas con checklist | `AGENTS.md` |
| fable-method (Sahir619) | https://github.com/Sahir619/fable-method | El juez adversarial de trabajo terminado (se queda); el método como prosa (3 A/B sin lift, borrado en X112) | `fable_judge.py`, `modules/fable.py` |
| Gandhi et al., *Recursive Agent Optimization* (2026) | https://arxiv.org/abs/2605.06639 | Una sola política que lanza copias de sí misma para subtareas | P2, `utils/kernel.py` |
| Lumer et al., *Recursive Agent Harnesses* (2026) | https://arxiv.org/abs/2606.13643 | El harness entero como unidad recursiva, con profundidad acotada: la mejora sale del harness con el modelo fijo | P2, `banco/specs/exp103_fractal.md` |
| Zhang, Kraska y Khattab, *Recursive Language Models* (2026) | https://arxiv.org/abs/2512.24601 | Al padre vuelve solo el resultado del hijo, nunca su contexto | P2, P3 |
| Kim et al., *Towards a Science of Scaling Agent Systems* (2026) | https://doi.org/10.21203/rs.3.rs-8414536/v1 | Más agentes dañan en tareas secuenciales y saturan cuando el agente solo ya resuelve | P2 (cede ante la medición), `banco/specs/exp103_fractal.md` |
| *Single-Agent LLMs Outperform Multi-Agent Systems… Under Equal Thinking Token Budgets* (2026) | https://doi.org/10.48550/arxiv.2604.02460 | Comparar con el presupuesto igualado: sin eso, la ventaja multi-agente es cómputo | Método, `banco/specs/exp103_fractal.md` |
| Center for Open Science, *Preregistration* | https://www.cos.io/initiatives/prereg | Criterios antes de ver los datos; desvíos declarados | Método |
| Harness² (revisión externa, 2026-11-01) | (texto privado, sin URL) | El sesgo del denominador: la tarea que no entrega sale del promedio de un brazo y vale 0 en el otro | Método |
| Pi (Mario Zechner) | https://pi-deep-dive.vercel.app/ | Cuatro tools, prompt corto, extensiones y lazy skills; se adopta el núcleo mínimo, no la falta de permisos | P1, P3, S0 |
| Databricks vía SoloSoft, *Pi: 2x cheaper* (2026) | https://www.solosoft.dev/post/pi-minimal-coding-agent-harness/ | El harness cambia el costo por tarea más de 2× con la misma calidad (no verificable desde esta red el 2026-11-02) | P1 |
| *The 99 KB Hello World* (2026) | https://agenticcontrolplane.com/blog/what-coding-harnesses-send-before-your-prompt | Medir los bytes del primer request: prompt + esquemas de tools | P1 |
| Nijholt, *Native harness tools* (2026) | https://www.nijho.lt/post/native-harness-tools/ | Lo que pesa son los tokens, no la familiaridad de las tools | P1 |
| *Harness Engineering: eleven systems* (2026) | https://arxiv.org/pdf/2609.00006 | Siete subsistemas canónicos; ningún framework pesado en el runtime | P3, P4 |
| DIG, *Dynamic Interaction Graph* (2026) | https://arxiv.org/abs/2603.00309 | Fallas topológicas de la colaboración, chequeables sobre la traza | P4 |
| MS-Eval, *Benchmarking Sub-Agent Delegation and Orchestration* (2026) | https://arxiv.org/html/2610.22869 | Sub-agentes especializados rinden más que genéricos, pero delegar sube el costo y paga según la calidad de la delegación | P2 (b), X145 |
| AgentCARD, *Specialize Roles, Mix Deployments* (2026) | https://arxiv.org/html/2606.20629 | Equipos heterogéneos en la frontera costo–precisión: hasta +44 % contra homogéneos de costo equivalente | P2 (a) y (b) |
| *Understanding Agent Scaling in LLM-Based Multi-Agent Systems via Diversity* (2026) | https://arxiv.org/html/2602.03794 | Lo homogéneo satura por redundancia: 2 agentes diversos igualan o superan a 16 iguales | P2 (b): por qué el 0/144 simétrico no refuta lo asimétrico |
| *The Coordination Tax and the Heterogeneity Dividend* (2026) | https://arxiv.org/abs/2610.37700 | Descomponer en un pipeline simple multiplicó el costo 3,22× sin ganar precisión | P2 (b): el costo se mide junto a la calidad (exp/108) |
| FRACTAL-MAS, *Divide, Conquer, and Standardize* (ICLR Blogposts 2026) | https://iclr-blogposts.github.io/2026/blog/2026/fractal-mas/ | El sistema tiene la misma forma que un agente; MCP y A2A como conectores estándar; el agente como herramienta (caja negra) | P2, `docs/arquitectura.md` (el conector) |
| FRACTAL, *A Self-Similar Multi-Agent Orchestration Architecture* (2026) | https://arxiv.org/abs/2610.22561 | Cada nodo del árbol repite el mismo patrón (con un ensamble de 3–5 perspectivas); límite formal de profundidad; hermanos aislados | P2, `docs/estrategias.md` (swarm diferenciado, graduador) |
| Lár, *Recursive Graph Composition* (2026) | https://docs.snath.ai/core-concepts/11-fractal-agency/ | Presupuesto de tokens propagado entre ramas; validadores de topología heredados (tools, nodos, profundidad); puertas humanas antes de juntar | P2, S0, `utils/kernel.py` (Ledger, `hijas`) |
| FractFlow (2026) | https://github.com/EnVision-Research/FractFlow | Unidades agente–herramienta anidables; el agente de arriba lee la descripción de las de abajo para elegir | P2, P3 |
