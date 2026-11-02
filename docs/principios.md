# Principios del harness

Un harness mínimo: un solo loop que se replica según lo que pide el trabajo,
con capacidades que se enchufan sin tocar el núcleo. La complejidad sale de
componer piezas, no de agregar mecanismos.

**Decisión del operador, 2026-11-01 (X118):** cuatro principios, cuatro
prohibiciones y una restricción de seguridad. Reemplazan a las tres capas de
X113 (D1–D15, E1–E12, M1–M11): el diseño quedó en estas nueve entradas y las
reglas de proceso (cómo se escribe y cómo se decide) viven en `AGENTS.md`.

Cada entrada nombra el gate que la verifica. Un gate que todavía no existe se
declara "sin gate" con lo que falta: así no se disfraza de regla (lo verifica
`tests/test_handoff.py`).

## Precedencia

1. **S0** (seguridad).
2. **N1–N4** (prohibiciones): ningún principio justifica un parche.
3. **P1–P4** (principios). Si dos chocan, decide una medición con el cómputo
   igualado, no la preferencia.

## Restricción

| # | Restricción | Qué es | Se verifica con | Cede ante |
|---|---|---|---|---|
| S0 | **Seguridad: falla cerrada y HITL graduado** | Lo no reconocido pregunta; lo irreversible pide doble confirmación; si la política no valida, el chat no arranca. Una copia hereda los frenos de su padre (política, HITL, saldo): la recursión nunca abre un camino que el loop raíz no tenga. P1 no se usa para recortar seguridad (de Pi se toma el núcleo mínimo, no correr sin permisos) | `tests/test_policy_bypass.py`, `test_falla_cerrada_si_los_datos_no_validan`, `test_una_tool_sin_efecto_declarado_escribe_y_corre_en_orden` | Nada |

## Principios

| # | Principio | Qué es | Se verifica con | Cede ante |
|---|---|---|---|---|
| P1 | **Minimalismo elegante (KISS)** | Lo mínimo que funciona en código, conducta y prompt: un loop, pocas tools en el CORE y un prompt que describe el formato. El contexto se gana: skills y memoria como menú que se carga con una tool. Prefijo estable: nada variable en el system prompt ni tools en caliente. Lo que no decide nada se borra | `texto_de_prompt`, `settings_leidos`, `tests/test_estilo_humano.py`, `bytes_primer_request` (prompt + esquemas de tools) y `lineas_del_loop` (kernel + chat), desde X124 | S0 |
| P2 | **Grafo: fractalidad por construcción y replicación medida** | **P2a — fractal por construcción**: una sola definición del loop con N instancias (agente = Flow = Node = Tool) que heredan los frenos de su padre —política, HITL, saldo—, así que una política agregada una vez llega a todos los niveles; los frenos son datos del árbol (saldo, profundidad, efecto) y la síntesis va siempre al padre. **Ley 1**: cada ronda y cada copia descuentan 1 del mismo saldo R, así que llamadas ≤ 2R + 1 con cualquier abanico y profundidad. **P2b — replicación en ejecución**: que el modelo decida dividirse es una capacidad medida, no una promesa: `recursivo` es una primitiva del kernel y hoy **no se adopta** (0 de 72 corridas del exp/103); se vuelve a medir con otro modelo o con un dato nuevo. **Ley 2**: si la rama i recibe la fracción rᵢ del alcance del padre, D resuelve Σ rᵢᴰ = 1; con D ≈ 1 dividir paga, con D > 1 las ramas releen lo mismo | `tests/test_kernel.py`, `test_un_agente_que_se_llama_a_si_mismo_reparte_y_suma`, `test_la_profundidad_y_el_saldo_frenan_la_replicacion`, `test_el_arbol_no_pasa_de_2r_mas_1_llamadas_con_cualquier_abanico` (la Ley 1, X119) y `test_d_mide_si_las_copias_se_repartieron_el_alcance` (`banco/probes/fractal.py`, X124). Pendientes de P2a: un solo loop (el chat sobre `kernel.loop`, S9b) y un test de que una política agregada una vez llega a todos los niveles | S0. Una división entra al producto solo si gana un A/B con el cómputo igualado (el 0/72 del exp/103 no se adoptó) |
| P3 | **Modularidad** | El CORE no conoce sus módulos; un módulo es una capacidad: un archivo con `TOOLS`, `IMPL` y, si hace falta, `HOOKS`. Agregarlo es dejarlo y quitarlo es borrarlo. El núcleo absorbe primitivas (loop, saldo, efecto, hooks), no features. `Ctx` es el registro de seams (`llm`, `ledger`; pendientes `fs` y `politica`). Lo opcional (Laya, RAG, MCP, web) es módulo y sin él el harness anda. El producto no sabe que lo miden | `core_importa_modulos`, `tests/test_core_sin_modulos.py`, `producto_conoce_lab`, `tests/test_laya.py` | S0 |
| P4 | **Complejidad emergente** | Las capacidades complejas salen de componer piezas mínimas (loop, tool, saldo, efecto): supervisor, juez y auditoría son composiciones, no subsistemas. El control vive en las aristas y el `shared` guarda solo datos JSON. Los errores vuelven como texto (`ERROR: …`) y el modelo se corrige. La emergencia se observa, no se supone: las fallas topológicas de DIG (terminación temprana o faltante, ramas huérfanas, el mismo subproblema resuelto varias veces, reruteo excesivo) se chequean sobre la traza sin LLM | `nodos_largos`, `test_el_diagrama_del_readme_es_el_grafo_del_chat`, `test_una_tool_desconocida_vuelve_como_error`, `test_las_fallas_topologicas_se_ven_en_la_traza` (las de DIG sobre la traza, X124). Una capacidad nueva entra sin tocar `utils/kernel.py` (review) | S0 |

## Prohibiciones

| # | No se hace | Señal de que se violó | Se verifica con | Cede ante |
|---|---|---|---|---|
| N1 | **Parches situacionales**: el arreglo va a la raíz | El arreglo suma un caso: un umbral, una rama, un `if` sobre un nombre concreto | sin gate (review: ¿borra un caso o lo suma?) | Nada |
| N2 | **Hardcodear keywords o hints** para volver determinista lo semántico | Una regex o una lista de palabras juzga significado. La lista blanca de comandos (`utils/politica_comandos.json`) no cuenta: enumera lo permitido y lo demás pregunta (S0). Las listas negras de flags sí: perdieron tres veces (E1, E2, X114) | `vocabulario_hardcodeado` (meta 0) | Nada |
| N3 | **Soluciones por system prompt** | Una frase agregada al prompt para corregir una conducta | `texto_de_prompt` (solo baja) | Nada |
| N4 | **Duplicidad** | Dos implementaciones del mismo concepto: dos loops, dos techos, dos helpers | `helpers_duplicados`, `cuerpos_duplicados`. Pendiente: un solo loop (S9b) | Nada |

## De las tres capas de X113 a esta lista

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

## Fuentes

Las de X113 y X116 con su "dónde" traducido a la lista nueva, más las de la
investigación del 2026-11-01 (P1–P4 contra la evidencia de 2026). Leídas por
resumen y abstract: los números son de sus autores, no se reprodujeron acá.
URLs verificadas el 2026-11-02: 33 de 35 responden 200 —una estaba mal escrita
y se corrigió—, el DOI de Parnas es válido por Crossref aunque ACM da 403 a los
bots, y `solosoft.dev` no responde desde esta red.

| Fuente | URL | Qué tomamos | Dónde se aplica |
|---|---|---|---|
| PocketFlow | https://github.com/The-Pocket/PocketFlow | Grafo + shared store en 100 líneas, sin módulos de proveedor | P1, P4 |
| bmo (harness del operador) | (repo privado) | Un nodo, un módulo, una capacidad; leyes de bucles (L1 anti-recursión, L8 presupuesto); hechos en código e interpretación en el LLM | P3, N2, P2 |
| 12-Factor Agents (HumanLayer) | https://github.com/humanlayer/12-factor-agents | Factor 7 (el humano como tool call), 8 (controlá tu flujo) y 10 (agentes chicos y enfocados) | P2, P4, `request_human_input` |
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
| Laya | https://github.com/NandhaKishorM/laya | El smart-if: tres tipos de decisión cerrada (`noul`, `choice`, `score`) en una pasada, la pregunta como dato y abstenerse ante la duda | N2, P3, `utils/laya.py` |
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
