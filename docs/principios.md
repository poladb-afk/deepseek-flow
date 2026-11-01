# Principios del harness

La constitución de deepseek-flow: **cómo es** (diseño), **cómo se escribe**
(ingeniería) y **cómo se decide** (método). Cambia poco; lo que cambia seguido
va en `docs/handoff.md`. Cada principio dice qué es, por qué existe, con qué
se verifica y ante qué cede. Un principio que no nombra un gate dice "sin
gate": así no se disfraza de regla (lo verifica `tests/test_handoff.py`).

[PENDIENTE: operador] Esta lista sale de lo que el repo ya tenía escrito
(README, `docs/design.md`, `docs/elegancia.md`, `AGENTS.md`) y de cómo el
operador decidió en el refactor. Los principios que falten, o las palabras
del operador para nombrarlos, van acá.

## Precedencia cuando chocan

1. **Seguridad** (lo irreversible lo decide un humano; ante la duda, se cierra).
2. **La medición** (un A/B pre-registrado le gana a cualquier argumento de forma).
3. **La elegancia** (un mecanismo general le gana a un caso).
4. **El minimalismo** (menos código le gana a más, a igual conducta).

Ejemplos: la validación de falla cerrada sumó ~60 líneas a `utils/policy.py`
(1 le gana a 4); la 5b era más elegante y no pasó el A/B, así que se revirtió
(2 le gana a 3).

## Capa 1 — Diseño: cómo es el harness

| # | Principio | Qué es | Por qué | Se verifica con | Cede ante |
|---|---|---|---|---|---|
| D1 | **Minimalista (KISS)** | El mínimo que funciona: un framework de 100 líneas, dependencias mínimas y nada especulativo | Cada línea y cada setting es algo que alguien tiene que entender | `texto_de_prompt`, `settings_leidos`, `tests/test_estilo_humano.py` | Seguridad (la falla cerrada de la política) y la medición |
| D2 | **Modular** | CORE + módulos: un módulo es un archivo con `TOOLS` e `IMPL` (y `HOOKS`); agregar es dejarlo y quitar es borrarlo | Una capacidad se suma o se saca sin tocar el CORE | `core_importa_modulos`, `tests/test_core_sin_modulos.py` | Nada: el CORE nunca nombra un módulo concreto |
| D3 | **Fractal** | Una definición del loop, N instancias: agente = Flow = Node = Tool; chat = sub-agente = supervisor = copia de sí mismo (`recursivo`), con un solo saldo y la recursión acotada por datos (profundidad, saldo, efecto) | Una política nueva llega gratis a todas las escalas | `tests/test_kernel.py` (el chat todavía no es `kernel.loop`: lo completa S9b) | La medición: un sub-agente entra solo si mejora algo (el explorador se borró en H3-B) |
| D4 | **El grafo dice la verdad** | El control vive en las aristas; el `shared` guarda solo datos JSON | Un turno se explica leyendo `python3 main.py grafo` | `nodos_largos`, `test_el_diagrama_del_readme_es_el_grafo_del_chat` | El bookkeeping (checkpoint, traza) puede vivir en `post`: no decide |
| D5 | **Cada decisión en su lugar** | Lo exacto lo cuenta el código, lo semántico lo juzga un modelo, lo irreversible lo decide un humano | Una regex juzgando significado falla con otro idioma o redacción | `vocabulario_hardcodeado` | Nada |
| D6 | **Generalidad** | Ningún mecanismo conoce casos particulares | Lo particular envejece y no transfiere | `vocabulario_hardcodeado` | Seguridad: la whitelist de comandos es particular a propósito (datos, no vocabulario: `utils/politica_comandos.json`) |
| D7 | **Laya acelera, no es dependencia** | Sin el paquete o sin checkpoint, cada uso degrada a su camino determinista | El harness anda en cualquier máquina; el modelo local es una optimización | `tests/test_laya.py`, los tests con marker `laya` | Nada |
| D8 | **Todo bucle tiene presupuesto** | Ley L8: rondas de tools, del juez, del debate y del supervisor; el cierre es una arista | Un loop sin techo es un costo sin techo | `test_el_presupuesto_corta_y_obliga_a_responder`, `tests/test_kernel.py` | Nada (S6 lo deja en un solo techo) |
| D9 | **Los errores son información** | Una tool que falla devuelve `ERROR: …` como texto y el modelo se corrige | Una excepción corta el chat; un texto le da al modelo el dato | `test_una_tool_desconocida_vuelve_como_error` | Seguridad: la política inválida no arranca el chat (falla cerrada, D11) |
| D10 | **Errores reversibles** | Un juicio automático decide perillas cuyo error se corrige solo; nunca le saca capacidades al agente | Un error irreversible de un clasificador no se ve ni se corrige | sin gate (se mide en cada A/B; la 3a lo rechazó) | Nada |
| D11 | **Seguridad: falla cerrada y HITL graduado** | Lo no reconocido pregunta; lo irreversible pide doble confirmación; si la política no valida, el chat no arranca | Un default permisivo es un bypass esperando | `tests/test_policy_bypass.py`, `test_falla_cerrada_si_los_datos_no_validan` | Nada (R7) |
| D12 | **Prefijo estable** | Nada variable en el system prompt; las tools no se agregan ni se quitan en caliente | Romper el KV-cache recalcula todo el contexto en cada turno | `tests/test_chat_flujo.py` | Nada (la 5b borraba el recorte de tools por esto) |
| D13 | **La memoria es una biblioteca, no contexto** | El agente consulta la memoria con tools cuando el pedido lo justifica; nunca se inyecta sola | Inyectar todo diluye el contexto y rompe el prefijo | `tests/test_memoria.py` | El pre-fetch inyecta los archivos que la pregunta nombra (exp/50, medido) |
| D14 | **El producto no es el laboratorio** | El producto no sabe que el banco existe | Una rama "si me miden" es una conducta distinta a la real | `producto_conoce_lab` | Las entradas headless (`HITL_SCOPE`, `HUMANO_RESPUESTA`) siguen en el producto; su nombre neutro está pendiente |
| D15 | **Forma humana** | Código para que lo lea una persona: sin defensas, abstracciones, banners ni docstrings que el pedido no exija | El ruido de IA se acumula y esconde lo que importa | `tests/test_estilo_humano.py`, `excepts_amplios` | Validación, seguridad y accesibilidad no se recortan |

## Capa 2 — Ingeniería: cómo se escribe

El detalle está en `AGENTS.md` (R1–R10) y en `docs/elegancia.md` (C1–C7).
Acá, una línea por regla para tenerlas juntas.

| # | Principio | Se verifica con |
|---|---|---|
| E1 | El gate va verde antes de decir "listo" (R1) | `calidad.sh` |
| E2 | No se borra ni se saltea un test para pasar el gate (R2) | `tests/test_inventario.py`, `tests_definidos` |
| E3 | Los docs no mienten: lo que citan existe (R3, R4) | `tests/test_docs_sin_deriva.py`, `tests/test_deriva_reglas.py` |
| E4 | Un concepto, un lugar (C1, R5) | `helpers_duplicados`, `cuerpos_duplicados` |
| E5 | Núcleo puro, efectos en el borde (C2) | sin gate (review) |
| E6 | Configuración mínima: cada setting es contrato del operador, no un A/B abierto (C3) | `settings_leidos`, `test_la_columna_lo_lee_del_inventario_es_la_del_codigo` |
| E7 | Imports arriba; uno perezoso lleva su motivo (C4) | `imports_perezosos` |
| E8 | El código dice el porqué actual; la historia va a la bitácora (C5) | sin gate (review) |
| E9 | Un nodo, una cosa: ≤ 40 líneas (C6) | `nodos_largos` |
| E10 | El prompt describe el formato, no corrige conductas (C7) | `texto_de_prompt` |
| E11 | Dependencias mínimas: stdlib salvo lo que ya está en `requirements.txt` | sin gate (review) |
| E12 | Español en docs, comentarios, tests y mensajes | sin gate (review) |

## Capa 3 — Método: cómo se decide

| # | Principio | Qué es | Se verifica con |
|---|---|---|---|
| M1 | **A la raíz, nunca un parche** | Si el arreglo suma un caso (una palabra, una regex, una frase al prompt), no llegó a la raíz | `vocabulario_hardcodeado`, `texto_de_prompt` |
| M2 | **Mecanismo, no lista** | Lo que puede decidir un mecanismo general (Laya, un contador, el estado del grafo) no se resuelve con una lista | `vocabulario_hardcodeado` |
| M3 | **Pre-registrar antes de medir** | Criterios escritos antes del código, en `banco/specs/`; no se retocan después; un cambio es un desvío declarado | sin gate (cada spec lo declara) |
| M4 | **Lo que cambia conducta pasa un A/B antes de entrar** | Vive en una rama hasta el veredicto; si falla, se revierte y lo viejo no vuelve como parche | sin gate (la 5b se mergeó antes y quedó declarado) |
| M5 | **Los ratchets no empeoran sin la clave del operador** | Mejorar se registra solo; empeorar exige la clave, nunca una bandera | `ratchet.py`, `test_una_bandera_cualquiera_no_es_la_clave` |
| M6 | **Mérito, no comodidad** | Cada decisión es la mejor funcional y en Python, no la más barata de hacer | sin gate (review del operador) |
| M7 | **Lo medido no es lo estimado** | Se registra el número honesto aunque no sea el redondo; no se persigue la métrica | sin gate (ver `docs/handoff.md`, errores a vigilar) |
| M8 | **La historia como fue** | Los errores y las decisiones del operador que revierten las del autor quedan escritos tal cual | `tests/test_deriva_reglas.py` |
| M9 | **Arreglar el instrumento antes que la métrica** | Si el instrumento no ve algo, se arregla aunque la métrica empeore (vocabulario 3 → 5 en X112) | `tests/test_ratchet_elegancia.py` |
| M10 | **Borrar antes que agregar** | Un arreglo elegante borra un caso; lo que no decide nada se va | `codigo_muerto_privado`, `settings_leidos` |

## Fuentes

Las del repo hasta X112 más las que fundamentan principios que no tenían
fuente escrita. **Las URL agregadas en X113 no se verificaron en línea al
escribirlas**: el operador las confirma (o corrige) al aplicar. Las de X116
(Laya y la evidencia del fractal) salen de una búsqueda del 2026-10-31.

| Fuente | URL | Qué tomamos | Dónde se aplica |
|---|---|---|---|
| PocketFlow | https://github.com/The-Pocket/PocketFlow | Grafo + shared store en 100 líneas, sin módulos de proveedor | D1, D4 |
| bmo (harness del operador) | (repo privado) | Un nodo, un módulo, una capacidad; leyes de bucles (L1 anti-recursión, L8 presupuesto); hechos en código e interpretación en el LLM | D2, D5, D8 |
| 12-Factor Agents (HumanLayer) | https://github.com/humanlayer/12-factor-agents | Factor 7 (el humano como tool call), 8 (controlá tu flujo) y 10 (agentes chicos y enfocados) | D3, D4, `request_human_input` |
| Anthropic, *Building effective agents* | https://www.anthropic.com/engineering/building-effective-agents | Lo simple y componible antes que el framework; workflows antes que agentes | D1, D3 |
| Anthropic, *Effective context engineering for AI agents* | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | Prompts a la altitud correcta, sin if-else rígido; tools mínimas; compaction | D12, D13, E10 |
| Manus, *Context Engineering for AI Agents* | https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus | KV-cache: prefijo estable, no agregar ni quitar tools en caliente | D12 |
| Anthropic, *Agent Skills* | https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills | Divulgación progresiva por descripción (medida en la 5b: no pasó con este modelo) | S7, `banco/specs/fase5b.md` |
| Rich Sutton, *The Bitter Lesson* | http://www.incompleteideas.net/IncIdeas/BitterLesson.html | Las capas que tapan debilidades del modelo envejecen; lo general escala | D6, M2 |
| mini-swe-agent | https://github.com/SWE-agent/mini-swe-agent | Un agente útil en ~100 líneas | D1 |
| SWE-agent (Yang et al., 2024) | https://arxiv.org/abs/2405.15793 | La interfaz agente–computadora; el linter en la edición como guardrail medido | hook `py_compile`, D9 |
| *Show and Tell* | https://arxiv.org/abs/2511.13972 | Instrucciones explícitas de concisión bajan 56–70 % los tokens del código | `DIRECTIVA_FORMA`, exp/51 |
| D. L. Parnas, *On the criteria to be used in decomposing systems into modules* (1972) | https://doi.org/10.1145/361598.361623 | Un módulo esconde una decisión de diseño | D2 |
| Robert C. Martin, *The Clean Architecture* | https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html | La regla de dependencias: hacia adentro | D2 (F5) |
| Gary Bernhardt, *Functional Core, Imperative Shell* | https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell | Núcleo puro, efectos en el borde | E5 (C2) |
| Martin Fowler, *Yagni* | https://martinfowler.com/bliki/Yagni.html | No construir lo que el pedido no pide | D1, D15 |
| Ponytail | https://github.com/DietrichGebert/ponytail | La pirámide YAGNI y "lazy, not negligent" | D15, `AGENTS.md` |
| code-humanizer | https://github.com/LeonardNJU/code-humanizer | El catálogo de tells de código de IA | D15, `tests/test_estilo_humano.py` |
| slop-scan | https://github.com/modem-dev/slop-scan | Medir contra código humano previo a 2025 | D15 |
| mattpocock/skills | https://github.com/mattpocock/skills | Skills para ingeniería real; el lenguaje compartido como raíz del ruido | D15, `skills/revision.yaml` |
| git-agent-ratchet | https://github.com/monk-eee/git-agent-ratchet | Baseline que solo mejora y guardia anti-bypass | M5, `ratchet.py` |
| ruleward | https://github.com/kernullist/ruleward | Lint de reglas: bloat y deriva | E3, `tests/test_deriva_reglas.py` |
| AI-Agent-Coding-Rules | https://github.com/Emmanuel-Bamidele/AI-Agent-Coding-Rules | Reglas con checklist | `AGENTS.md` |
| fable-method (Sahir619) | https://github.com/Sahir619/fable-method | El juez adversarial de trabajo terminado (se queda); el método como prosa (3 A/B sin lift, borrado en X112) | `fable_judge.py`, `modules/fable.py` |
| Laya | https://github.com/NandhaKishorM/laya | El smart-if: tres tipos de decisión cerrada (`noul`, `choice`, `score`) en una pasada, la pregunta como dato y abstenerse ante la duda | D5, D7, `utils/laya.py` |
| Gandhi et al., *Recursive Agent Optimization* (2026) | https://arxiv.org/abs/2605.06639 | Una sola política que lanza copias de sí misma para subtareas | D3, `utils/kernel.py` |
| Lumer et al., *Recursive Agent Harnesses* (2026) | https://arxiv.org/abs/2606.13643 | El harness entero como unidad recursiva, con profundidad acotada: la mejora sale del harness con el modelo fijo | D3, `banco/specs/exp103_fractal.md` |
| Zhang, Kraska y Khattab, *Recursive Language Models* (2026) | https://arxiv.org/abs/2512.24601 | Al padre vuelve solo el resultado del hijo, nunca su contexto | D3, D13 |
| Kim et al., *Towards a Science of Scaling Agent Systems* (2026) | https://doi.org/10.21203/rs.3.rs-8414536/v1 | Más agentes dañan en tareas secuenciales y saturan cuando el agente solo ya resuelve | D3 (cede ante la medición), `banco/specs/exp103_fractal.md` |
| *Single-Agent LLMs Outperform Multi-Agent Systems… Under Equal Thinking Token Budgets* (2026) | https://doi.org/10.48550/arxiv.2604.02460 | Comparar con el presupuesto igualado: sin eso, la ventaja multi-agente es cómputo | M3, `banco/specs/exp103_fractal.md` |
| Center for Open Science, *Preregistration* | https://www.cos.io/initiatives/prereg | Criterios antes de ver los datos; desvíos declarados | M3 |
