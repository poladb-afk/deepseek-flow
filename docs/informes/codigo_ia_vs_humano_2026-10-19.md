# Código de IA vs código humano: patrones, evidencia y gates (2026-10-19)

**Pregunta:** el harness funciona, pero el código tiene "ruido" de IA —más
defensivo, más verboso, más decorado, más duplicado— frente al estilo humano
más prolijo y minimalista. ¿Qué dice la evidencia, qué se puede medir y qué
se puede gatear?

**Método:** papers con métricas sobre código generado, reportes de industria
con datasets grandes, docs oficiales de los vendors, señales de comunidad y
repos que atacan el problema; después medición del propio harness contra una
referencia humana y adopción de gates deterministas. Los números de la
sección 7 son mediciones de este árbol (2026-10-19), no estimaciones.

## 1. De "slop" a "firma de máquina"

- "Slop" es la palabra del año 2025 para Merriam-Webster: *contenido digital
  de baja calidad producido usualmente en cantidad por IA*. Simon Willison
  (2024) la acotó mejor: no es todo contenido de IA, es el *no pedido y
  generado sin cuidado*.
- Kommers et al., *Why Slop Matters* (ACM AI Letters; arXiv 2601.06060),
  evita una definición esencialista y da tres propiedades de familia:
  **competencia superficial** (parece bueno y no lo es), **asimetría de
  esfuerzo** (cuesta muchísimo menos producirlo) y **producibilidad
  masiva**.
- En código, el equivalente no es un bug: es un **"machine signature"** de
  hábitos estructurales que pasan los tests (Zhu et al., *AI-Generated
  Smells*, arXiv 2605.02741). El ruido sobrevive a la review porque *parece*
  competente.

## 2. Evidencia académica

| Fuente | Qué midió | Hallazgo que nos importa |
|---|---|---|
| **Show and Tell** — Bohr, arXiv 2511.13972 | 160 sesiones de 2 turnos (Gemini 2.5 Pro), 4 estrategias de prompt | El código de control fue 2.560 tokens; **directivas explícitas de concisión −56%** (1.113); instrucciones+ejemplos **−70%** (759). Densidad de docstrings 0.996 → 0.28–0.38. Un pedido genérico de "mejorar legibilidad/mantenibilidad/errores" **infló todo** (+126 a +268 tokens); las directivas mantuvieron la disciplina en el turno 2, los ejemplos no. |
| **AI-Generated Smells** — Zhu, Tsantalis, Rigby (Concordia), arXiv 2605.02741 | 90 problemas de CodeContest × 5 modelos + 5 escenarios generados con MetaGPT | LLMs: **Long Method** (Qwen-480B: 11 vs 1 humano); humanos: Temporal Field (4 vs 0). A escala: God Class, *Redundant Implementation* y **"Modular Mirage"** (separan archivos sin cohesión). **"Volume-Quality Inverse Law"**: el volumen predice la degradación; few-shot **no** la mitiga; correctitud y calidad están desacopladas. |
| **Debt Behind the AI Boom** — Liu et al. (SMU), arXiv 2603.28592 | **304.362 commits** atribuidos a IA en **6.275 repos**, 5 asistentes | 484.606 issues introducidos; **code smells = 89,1%**; >15% de los commits introducen ≥1 issue; **24,2% sobreviven** al HEAD. Smell #1: **Broad exception handling (41.723 casos, 8,6%)**, luego variables/argumentos sin usar y shadowing. |
| **SlopCodeBench** — Orlanski et al. (UW-Madison et al.), arXiv 2603.24755 | 20 problemas, 93 checkpoints de extensión iterativa del propio código | Dos métricas: **verbosity** (redundancia/duplicación) y **structural erosion** (masa de complejidad en funciones CC>10, masa = CC·√SLOC). Erosion sube en **80%** de las trayectorias, verbosity en **89,8%**; el código de agente es **2,2× más verboso** que 48 repos humanos; el humano queda plano y el agente **empeora iteración a iteración**; un prompt de calidad mejora el inicio **pero no frena la degradación**. |

**Lectura:** la forma es separable de la correctitud; la directiva explícita
es una palanca real (y medible), pero **la degradación iterativa necesita
gates por iteración, no solo un buen prompt**.

## 3. Evidencia de industria

- **GitClear, *The Maintainability Gap* (2026)**: 623M de cambios 2023–2026.
  Refactoring −70% (21% → 3,8% de las líneas), copy/paste +41% (9,4% →
  15,7%), **block duplication +81%** (40,3 → 73,0 por millón de líneas),
  conectividad entre archivos −35%, mantenimiento de código legacy −74%,
  construcciones que enmascaran errores **+47%**. Su lectura: modo
  *write-only*. *Caveat:* es un vendor comercial; la metodología es pública
  y el dataset es enorme, pero conviene leer los números como señal, no como
  experimento controlado.
- **DORA 2024** (Google Cloud): la adopción de IA aumenta la productividad
  individual pero **impacta negativamente la estabilidad y el throughput de
  entrega** — "las fundamentales (lotes chicos, testing robusto) siguen
  siendo cruciales".
- **METR 2025** (RCT, arXiv 2507.09089): 16 devs expertos, 246 issues: con
  IA tardaron **19% más** y aun así creían haber ido 20% más rápido. La
  percepción de velocidad no es evidencia.
- **slop-scan** (comunidad): benchmark reproducible de repos "AI" vs OSS
  maduro fijado a SHAs previos a 2025: score mezclado **6,91 vs 1,00**
  (6,9×); findings/KLOC **3,04 vs 0,56** (5,4×).
- **Contrapunto honesto**: autores como Tura y un reporte de JetBrains
  muestran que los plugins de "ahorro de tokens" rinden poco en tareas
  largas. Todo claim de reducción hay que medirlo en el repo propio.

## 4. Docs oficiales (lo que los vendors dicen)

- **Claude Code — Best practices** (code.claude.com/docs/en/best-practices):
  "[CLAUDE.md] keep it short and human-readable"; *"For each line, ask:
  'Would removing this cause Claude to make mistakes?' If not, cut it.
  Bloated CLAUDE.md files cause Claude to ignore your actual instructions!"*;
  el patrón de falla "over-specified CLAUDE.md"; y una advertencia directa
  contra el exceso de review: *"A reviewer prompted to find gaps will usually
  report some... Chasing every finding leads to over-engineering: extra
  abstraction layers, defensive code, and tests for cases that can't
  happen."* También: las instrucciones son advisory; los **hooks** son
  deterministas — la justificación de los gates.
- **Anthropic — Effective context engineering for AI agents** (sep 2025):
  la meta es *"the smallest possible set of high-signal tokens"*; el
  *context rot* degrada la adherencia; tools: "un conjunto mínimo viable",
  sin solapamientos.
- **Anthropic — Writing effective tools for agents** (sep 2025): más tools no
  es mejor; respuestas token-efficientes; un tool se describe como a un
  nuevo integrante del equipo.
- **GitHub Copilot** documenta instrucciones personalizadas equivalentes; la
  norma de facto (`AGENTS.md`) ya la usan varios agentes.

## 5. Comunidad: quién está atacando esto

| Repo | Qué es | Qué se llevó |
|---|---|---|
| **[mattpocock/skills](https://github.com/mattpocock/skills)** — 296k ★, 24,9k forks | "Skills for real engineers, **not vibe coding**": grill, TDD, diseño de módulos, code-review con baseline de smells de Fowler, `improve-codebase-architecture`, `retro`. Su falla #2 es literalmente *"The Agent Is Way Too Verbose"* | La raíz del ruido es el **lenguaje compartido y el diseño**, no el formato: un `GLOSSARY.md`/`CONTEXT.md` hace que el agente use 1 palabra donde usaba 20. **No es un humanizer automático**; es disciplina de ingeniería. |
| **[Ponytail](https://github.com/DietrichGebert/ponytail)** — 167k ★, 9k forks | "El senior más vago de la sala": la pirámide YAGNI (¿necesita existir? → ¿ya está en el repo? → stdlib → nativo → dep instalada → una línea → mínimo + un test), con "lazy, **not negligent**": no se recortan validación, seguridad ni accesibilidad. Reporta −53% código, −41% tiempo, −45% tokens, y 98% de la lógica riesgosa con test (vs 68%) | La pirámide entra a `AGENTS.md`; el "nunca negligente" evita el recorte peligroso. *Caveat:* benchmark autodeclarado; HN lo discutió (98 pts, 17 comentarios) y hay escepticismo sobre el ahorro real en tareas largas. |
| **[code-humanizer](https://github.com/LeonardNJU/code-humanizer)** — 82 ★ | Skill que remueve los *tells* de código de IA: **16 patrones en 5 tiers** (duplicación/reinvención, abstracción especulativa, defensa excesiva, ruido, test slop) + 3 reglas de hierro (preservación de comportamiento, sin tests no se edita, un patrón por commit) y guarda de falsos positivos (severidad 1 = justificado) | El catálogo determinista que usan `tests/test_estilo_humano.py` y el ratchet: banners, docstrings de relleno, wrappers vacíos, `except` amplio. |
| **[slop-scan](https://github.com/modem-dev/slop-scan)** — 322 ★ | CLI determinista de slop para JS/TS + benchmark contra OSS maduro pre-2025 | El método de medición (normalizar por KLOC/función y comparar con una referencia humana). |
| **[anti-slop](https://github.com/miqdadbadjuber/anti-slop)** — 6,5k ★ | 38 reglas para UI, copy y **comentarios** de código (`antislop-code`) | Solo la parte de comentarios aplica; el foco es UI/texto. |
| `ex_slop` (Elixir), `skew202/antislop` (linter multi-lenguaje), `unslop`/`attention-span` (texto/salida), `taste-skill` (UI) | Ecosistema | Confirman el patrón, pero **no** son para Python ni para estructura de código. |

**Respuesta directa a la pregunta:** el nombre correcto es **Matt Pocock**
(educador de TypeScript); **sí tiene algo así**: `mattpocock/skills`
(296k estrellas). No es un "humanizador" que reescribe el código: ataca las
causas (lenguaje compartido, diseño de módulos profundos, TDD, review con
baseline de smells). "Matt Pollock" no aparece como autor de un proyecto de
este espacio.

## 6. Catálogo consolidado de patrones (y qué se puede gatear)

| # | Patrón | Tell | Fuente | ¿Determinista? | Gate adoptado |
|---|---|---|---|---|---|
| 1 | `except` amplio o mudo | convierte crashes visibles en corrupción invisible | Debt (smell #1), code-humanizer D8 | sí | `ratchet.py` `excepts_amplios` |
| 2 | try-import fallback injustificado | `try: import rápido except ImportError: import stdlib` sin benchmark ni test | D9 | parcial | review (14 en el harness) |
| 3 | reimplementar helper / duplicar | un `_foo` nuevo igual a algo que ya existe en `utils/` o un módulo hermano | code-humanizer #1 (el "signature tell"), slop-scan, GitClear +81% | sí (por nombre) | `ratchet.py` `helpers_duplicados` (20) |
| 4 | abstracción de una sola implementación / wrapper vacío | ABC/registro con un solo caso; función que solo reenvía argumentos | D4/D6 | parcial | `test_estilo_humano.py` wrappers |
| 5 | docstring de relleno / comentario narrador | repite el nombre o la línea siguiente | D12/D13 | sí (relleno) / review (narrador) | `test_estilo_humano.py` docstrings |
| 6 | banner decorativo | `# ===== SECCIÓN =====` que no aporta | D14 | sí | `test_estilo_humano.py` (61 → 0) |
| 7 | defensa paranoica | `if x is not None` sobre algo recién construido | D11, Show&Tell | parcial | review |
| 8 | Long Method / God Class / erosión | funciones y clases que crecen iteración a iteración | 2605.02741, SCBench | sí (C901/erosion) | C901 en las fronteras (ya existía); erosión medida |
| 9 | verbosidad | más tokens/docstrings/defensas que lo necesario | Show&Tell, SCBench (2,2×) | medible | directiva en el system prompt |
| 10 | test slop | assert del mock, asserts triviales/duplicados | D15/D16 | review | regla blanda |
| 11 | sobre-especificación de reglas | instrucciones infladas que se ignoran | Claude Code docs, Show&Tell turno 2 | sí (presupuesto) | AGENTS.md ≤160 líneas; prompt ≤1.400 chars |

## 7. Medición del harness vs una referencia humana

Alcance: los mismos 69 archivos que mide `ratchet.py` (raíz + `modules/` +
`utils/`). Referencia: `requests` (18 archivos, código humano pre-IA, de
calidad reconocida). *Caveat:* distinto dominio; la referencia ubica el
orden de magnitud, no es un target.

| Métrica | harness | requests | Lectura |
|---|---|---|---|
| `except` amplios | **55** (39,0% de 141 `try`) | **1** (1,6% de 64) | **la firma más fuerte**: 24× la tasa humana |
| `except: pass` | 9 | 6 | mismo orden relativo |
| Banners decorativos | **61** en 10 archivos | 8 (todos en `compat.py`) | ruido de agente, no de dominio |
| Try-import fallbacks | 14 | 11 | esperable (deps opcionales); no se gatea |
| Cobertura de docstrings | 0,52 | 0,68 | ok |
| Ratio defensivo (`try`+`None`+`assert` / SLOC) | 0,0256 | 0,0358 | el harness **no** es más defensivo en agregado; el problema es la *proporción de amplios* |
| Erosión estructural (masa CC>10, SCBench) | **0,204** | 0,390 | el harness está **mejor** que la referencia; no necesita ratchet de erosión |
| Comentarios / SLOC | 8,1% (865) | 10,4% (432) | el repo comenta más **en proporción similar** al humano: los "porqués" NO son el ruido |
| Helpers privados duplicados | 20 ocurrencias / 8 nombres | — | deuda ya congelada por el ratchet |

**Conclusión honesta:** el ruido del harness no es "demasiado comentario" ni
"funciones gigantes": es **excepción amplia (el smell #1 de la literatura),
decoración (banners) y duplicación de helpers**. Eso es exactamente lo que
los gates nuevos congelan o eliminan.

## 8. Qué se adoptó

- **`ratchet.py` gana `excepts_amplios`** (deuda, menor mejor): siembra 55;
  un `except Exception` nuevo frena el gate. No se prohíben (hay rutas
  best-effort legítimas): el número no crece sin decisión humana.
- **`tests/test_estilo_humano.py`**: banners decorativos = 0 (61 → 0), sin
  docstrings de relleno, sin wrappers vacíos sin justificar, y el system
  prompt del producto debe pedir el mínimo código sin crecer del presupuesto.
- **Directiva en el system prompt** (`main.system_prompt`): la palanca que
  Show&Tell midió (−56/−70% de tokens y densidad de docs) aplicada a lo que
  el harness genera cuando escribe código.
- **`AGENTS.md` R9 + sección "forma humana"**: la pirámide de Ponytail, el
  tell de reimplementar, defensas solo en la frontera, docstrings para el
  porqué, nada de banners ni `_v2` en paralelo.

**No adoptado, con motivo:** deslop automático masivo (las reglas de hierro
de code-humanizer exigen preservación de comportamiento y tests; reescribir
55 `except` es cambio semántico, va como paydown medido); el tier NLI de
ruleward (ruido); las herramientas JS/TS (otro stack); copiar 16 patrones
como 16 gates (muchos no son deterministas: quedan como review).

## 9. Límites y contradicciones de la evidencia

- La evidencia es mixta: hay estudios que miden *menos* issues de SonarQube
  en código de LLM (citado y criticado en 2605.02741: mezcla lint superficial
  con estructura). La conclusión robusta es sobre **estructura**, no sobre
  "bugs".
- GitClear y los benchmarks de Ponytail/slop-scan tienen interés comercial o
  autodeclarado; se usan como señal de magnitud, con la metodología dicha.
- Los gates cubren el subconjunto determinista; "comentario narrador", "código
  muerto por si acaso" y "test slop" siguen siendo review.
- La comparación `requests` es de otro dominio: sirve para detectar la
  anomalía de los 55 `except` amplios, no para fijar un ideal.

## 10. Fuentes

**Papers** (verificados por abstract/HTML el 2026-10-19):
[2511.13972](https://arxiv.org/abs/2511.13972) · [2605.02741](https://arxiv.org/abs/2605.02741) ·
[2603.28592](https://arxiv.org/abs/2603.28592) · [2603.24755](https://arxiv.org/abs/2603.24755) ·
[2601.06060](https://arxiv.org/abs/2601.06060) · [2507.09089](https://arxiv.org/abs/2507.09089)

**Industria / docs oficiales:**
[GitClear — The Maintainability Gap](https://www.gitclear.com/the_ai_code_quality_maintainability_gap) ·
[GitClear — signal graphs](https://www.gitclear.com/industry_stats/ai_code_quality_signal_graphs) ·
[DORA 2024](https://dora.dev/research/2024/dora-report/) ·
[Claude Code best practices](https://code.claude.com/docs/en/best-practices) ·
[Anthropic — context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) ·
[Anthropic — writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)

**Repos y comunidad:**
[mattpocock/skills](https://github.com/mattpocock/skills) ·
[Ponytail](https://github.com/DietrichGebert/ponytail) ·
[code-humanizer](https://github.com/LeonardNJU/code-humanizer) ·
[slop-scan](https://github.com/modem-dev/slop-scan) ·
[anti-slop](https://github.com/miqdadbadjuber/anti-slop) ·
[MINT Lab — AI Slop: definitions](https://mintresearch.org/reports/ai-slop/)

## 11. Actualización (misma jornada): paydown y A/B de la directiva

- **Paydown de `except` amplios: 55 → 48.** Se acotaron 7 handlers a la
  excepción real que esperan manejar (logs JSONL → `OSError`; arranque del
  HITL → `(OSError, ValueError)`; `git rev-parse` de la sonda →
  `(OSError, subprocess.SubprocessError)`), y los 48 restantes quedaron con
  **motivo visible** (`# noqa: BLE001 (motivo)`). Un gate nuevo
  (`tests/test_estilo_humano.py`) exige ese motivo en todo handler amplio: de
  34 sin motivo visible a 0.
- **exp/51 — la directiva de forma, medida** (`banco/probes/forma_codigo.py`,
  criterio pre-registrado en su docstring): A/B del `system_prompt` con la
  única diferencia del párrafo de forma, 2 tareas de escritura de código × n=4
  por brazo, deepseek-flash. Medianas por brazo: **SLOC 193 → 44 (−77%)**,
  tokens estimados −81%, funciones 11 → 2, densidad de docstrings **0,487 → 0**,
  `try` 3,5 → 1, comentarios 55 → 12. El efecto se sostiene por tarea
  (csv_stats 162,5 → 47; config_loader 266 → 35). Veredicto: **criterio
  cumplido**; 0/15 errores de sintaxis en el código extraído, 1/16 respuestas
  sin bloque de código. **Límite:** n=4, un modelo, una corrida — el efecto es
  grande, pero hay que repetirlo (roadmap).
