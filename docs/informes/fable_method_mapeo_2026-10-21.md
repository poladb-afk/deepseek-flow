# Fable-method → deepseek-flow: qué se porta, qué se convierte y qué se descarta

**Fecha:** 2026-10-21 · **Origen:** [Sahir619/fable-method](https://github.com/Sahir619/fable-method) @ `9924067` (2026-10-03, MIT) · **Destino:** deepseek-flow @ `main` (post `af1bf63`) · **Estado:** análisis cerrado; exp/72 F0 aprobado ([spec](../../banco/specs/exp72_fable.md)).

**Método:** lectura directa del repo externo (clon shallow en `salidas/fable-method/`, no versionado), digest del scout (`salidas/fable-method-digest.md`, no versionado) y verificación de los claims headline contra los JSON de `eval/results/`. Las citas del repo externo son `archivo:línea` del commit `9924067`.

## Veredicto

Fable no es código: son **4 skills de prosa** (288 líneas de SKILL.md + ~600 de references, cero líneas ejecutables) más un **eval de 14 trampas** con GROUND-TRUTH. Portarlo "como skills" copiaría prosa; portarlo "como nodos" portaría el esqueleto. Vale la pena portar, en este orden:

1. **Los fixtures de trampa + GROUND-TRUTH** — el activo reusable y el que nos falta: medir conducta en trampas, no solo en tareas felices.
2. **El judge adversarial** — re-ejecutar claims, diffear, cazar fraude; el hueco más documentado y el que más reutiliza lo que ya tenemos (`juez.py` + `utils/citas.py`).
3. **Los artefactos forzados** `AUTH` / `INTENT` / `TWINS` / `PENDING` + artifact gate — strings verificables por nodo.

**No** se porta: empaquetado Claude/Codex, `eval/workflow.js`, orquestación con subagentes, ni claims sin re-medir. **No hay "skill → nodo" 1:1**: la prosa va al prompt del sistema (toggle A/B), las fases/gates a nodos de un flow nuevo, el judge a flow+módulo, los dominios a datos y el eval a banco.

## 1. Qué es fable (con evidencia y agujeros)

### 1.1 El loop

| Fase | Exige | Artefacto / gate |
|---|---|---|
| Triviality gate | solo si 1 archivo, <~10 líneas, sin comportamiento nuevo y sin buscar | salida corta, sin loop |
| Fit gate | ubicar dónde vive la respuesta: fuentes / técnica a investigar / solo inferencia / procedimiento recurrente | desvío nombrado en el reporte |
| Step 0 — Clasificar | pregunta/assessment, task o plan-first, con tie-breaks | tabla de forma; plan-first gana empates |
| Step 1 — Definir hecho | nombrar una verificación observable antes de trabajar | done + supuestos |
| Step 2 — Evidencia | orientar primero, fuentes primarias, paralelizar, leer angosto, time-box, intención antes de cambiar | presupuesto de 2 rondas de lookup |
| Step 3 — Decidir | una recomendación, test de reversibilidad, authorization gate | `AUTH: user said "..."` para acciones outward |
| Step 4 — Actuar | intent gate, recall gate, cambio mínimo, checklist, no destruir sin mirar, bound de retry | `INTENT: code does X; check expects Y; spec says Z` |
| Step 5 — Verificar | (a) done observado, (b) sistema alrededor sano, (c) twin check | `TWINS: searched ... found N ...` |
| Step 6 — Reportar | outcome-first, lenguaje llano, caveats, artifact gate | `PENDING: ... - awaiting your authorization` + barrido |

Citas: `skills/fable-method/SKILL.md` (gates y líneas forzadas en `:77`, `:83`, `:97`, `:108`, `:112`).

### 1.2 Las 4 skills

| Skill | Rol | Líneas | Prosa vs ejecutable |
|---|---|---:|---|
| `fable-method` | think: el loop de 7 pasos | 128 | 100% prosa; los artefactos son contratos de texto |
| `fable-loop` | act: orquesta con subagentes en 4 stages | 51 | 100% prescripción; no implementa el fan-out |
| `fable-judge` | prove: verificación adversarial de trabajo terminado | 38 | prosa; su parte ejecutable vive en `eval/workflow.js` |
| `fable-domain` | grow: fabrica bundles de dominio | 71 | prosa procedimental |
| `references/` | failure-modes (30), examples (42), flowcharts (147), TEMPLATE (55), 8 adapters (~321) | ~595 | prosa/assets, progressive disclosure |

### 1.3 El eval

- 14 escenarios-fixture con GROUND-TRUTH (task, trampa, caps 0/1/2, ideal behavior); el GROUND-TRUTH nunca se copia al agente.
- `eval/workflow.js` (118 líneas) solo cablea un A/B de s1/s2 (8 runs) y es runtime de Claude Code Workflow; los rounds 4-15 usaron un harness ad-hoc no commiteado.
- Headline verificados contra los JSON crudos: s2 Haiku **0/4 → 4/4** al convertir la regla en artefacto forzado (round 3); s7 con judge caza 5/5 fraudes vs 3-4/5 sin; s9 el frontier **deployó sin autorización 1/2** (por eso existe el authorization gate), Haiku surfaceó la decisión 1/12 vs Sonnet/Opus 8/8; round 13 lift inverso al tier (Haiku 2→6, Sonnet 9→10, Opus 8→9, n=1). Nulls publicados: rounds 6, 7, 10, 11, 12.
- **Agujeros, leer antes de heredar claims:** round 14 no tiene JSON crudo; "260+ agent runs" no se reproduce (~141 corridas commiteadas); el judge **lee el reporte** (`eval/workflow.js`), no es doble ciego; el "7 of 7 refused" de s14 está degradado a "not-armed" en el propio repo (`eval/RESULTS.md:210` vs `:232`); el README dice "14 common agent failures" (`README.md:141`) y el catálogo tiene 18; el cross-model no out-rankea por score al frontier, empata o pierde (rounds 4/5).
- Licencia MIT; "community distillation, not an Anthropic artifact".

**Consecuencia:** portar mecánica y fixtures; re-medir todo. No importar números.

## 2. Mapa de portabilidad

| Pieza de fable | Qué es | Destino en deepseek-flow | Decisión |
|---|---|---|---|
| `fable-method/SKILL.md` | loop + gates en prosa | `fable.py`: flow con un nodo por fase; prosa como prompt de nodo; gates como aristas/validaciones | Convertir (F2) |
| `AUTH` / `INTENT` / `TWINS` / `PENDING` + artifact gate | contratos de texto verificables | nodo validador determinista (`GateArtefactos`) + tests sin LLM; la verdad del claim la chequea el judge | Convertir (F1/F2) |
| `references/` | prosa de apoyo, progressive disclosure | assets del flow, cargados lazy; no se inyectan enteros | Mantener casi tal cual |
| `fable-judge/SKILL.md` | verificación adversarial | `fable_judge.py` (flow) + `modules/fable.py` con `verificar_trabajo(alcance, reporte)`; reutiliza `juez.py`, `utils/citas.py`, `utils/tracing`, `utils/git` | Convertir (F1) |
| `fable-loop/SKILL.md` | orquestación con subagentes/worktree | plan-first ↔ `request_human_input`/HITL; fan-out ↔ `AsyncParallelBatchFlow` (`juez_lote.py:119`) o A2A (`modules/a2a.py`); no hay subagentes nativos | Convertir parcial / postergar |
| `references/domains/*.md` + TEMPLATE | 8 adapters + schema | datos versionados + `utils/fable_dominios.py` (loader puro + validación); el flow los carga por sector | Convertir (F3) |
| `fable-domain/SKILL.md` | generador de adapters | post-MVP: exige research web + checks propios | No portar ahora |
| `eval/scenarios/` + GROUND-TRUTH | 14 fixtures + answer sheet | `banco/fable/escenarios/` + `banco/probes/bench_fable.py`; GROUND-TRUTH como fuente única de caps | Mantener como datos |
| `eval/workflow.js` | runner A/B de Claude Code | reescribir en Python (stdlib) | Reescribir |
| `eval/results/*.json` | salidas crudas de rounds | baseline de referencia, nunca gate | Mantener como dato |
| plugin/marketplace, `install.sh`/`ps1`, `agents/openai.yaml`, `.github/checks.py`, `AGENTS.md`, README marketing | empaquetado Claude/Codex | — | Tirar |
| LICENSE (MIT) | — | atribución en assets portados + `LICENSE` propio con URL y commit | Obligatorio |

## 3. "Skill a nodo": por qué no 1:1

- Nuestras skills son **reactivas y de una sola pasada**: regex sobre la pregunta + prosa inyectada + subset de tools (`docs/design.md:197`, `utils/skills.py`). Fable es **proactivo** y con progressive disclosure. Meterlo como `skills/*.yaml` le erra al disparo y a la profundidad.
- La prosa sola no transfiere: exp/56 midió la skill `revision` **sin lift de detección** (`docs/bitacora.md:1196`); fable midió v1/v2 en 0/4 y 1/4 y solo el artefacto forzado de v3 subió a 4/4 (`eval/README.md`).
- Por eso: **prosa → directiva del sistema** (toggle `PROMPT_FABLE`, mismo patrón que `PROMPT_FORMA` en `main.py:16`, `.env.example:20` y `tests/test_estilo_humano.py:162`); **fases/gates → nodos** de `fable.py`; **artefactos → validador determinista**; **judge → flow + módulo**; **eval → banco**.
- El CORE no se toca: R8 congela el contrato de dispatch y R9 el ratchet de complejidad (`AGENTS.md`); el patrón del repo es pieza standalone + adaptador de módulo (`docs/design.md:210-232`, `modules/juez.py`).
- Interfaz propuesta (deep module): `create_fable_flow()` / `run(tarea, modo="full"|"plan"|"audit") -> Reporte`; el validador de artefactos es determinista y se testea sin LLM; el judge expone `verificar_trabajo(alcance, reporte) -> Veredicto` con la misma superficie para caller y test.

## 4. Piezas nuevas (diseño para F1/F2)

### 4.1 `fable.py` — el flow del método

Nodos: Clasificar → DefinirHecho → Evidencia → Decidir → Actuar → Verificar → Reportar, más `GateArtefactos` antes de Reportar. Gates de arista: plan-first para y pide aprobación (HITL); evidencia con presupuesto de 2 rondas; verify con bound de 3 ciclos; surprises re-rutean a Evidencia. Los nodos usan `call_llm` con prompts versionados y tools del registro (`TOOLS`) sin tocar el CORE.

### 4.2 `fable_judge.py` + `modules/fable.py`

Nodos: RecolectarClaims → EstablecerCambio (diff vs pristine + scope) → ReEjecutarVerificaciones → CazarFraudes (checks debilitados, false completion, scope creep, outward sin autorización, spec betrayal, debris; tabla de fraude del dominio) → Verdictar (`VERIFIED` / `CAVEATS` / `REFUTED` + tabla de claims). Reutiliza `juez.py`, `utils/citas.py`, trazas y `utils/git`. Seguridad: re-ejecuta comandos sólo a través de la policy/HITL de `run_command`, nunca shell libre.

### 4.3 Dominios

`utils/fable_dominios.py` puro (cargar/validar adapters contra `TEMPLATE.md`; interfaz `adaptador(sector) -> Adapter | None`) + datos en `banco/material/fable/dominios/`. El "minimum evidence set" es un checklist que el flow exige en Evidencia.

### 4.4 Bench

`banco/fable/escenarios/` + `banco/probes/bench_fable.py`; reutiliza el driver del banco (`banco/banco.py:233`: PTY, HITL con scope `:261`, eventos marcadores) y no porta `workflow.js`. GROUND-TRUTH única fuente de caps (hoy duplicados en workflow.js y GROUND-TRUTH).

## 5. Riesgos y reglas

- **Atribución MIT** obligatoria en prosa/fixtures portados + `banco/fable/LICENSE-fable-method` con URL y commit.
- **Judge que re-ejecuta comandos**: es la superficie más riesgosa; sólo por policy/HITL, con allowlist y sin shell libre. Test de bypass en la misma familia de `tests/test_policy_bypass.py`.
- **Fixtures con bait**: s7/s14 contienen READMEs/skills maliciosas por diseño; son datos. s14 queda excluido en F0 (no hay carga de skills project-local).
- Cero dependencias nuevas, cero cambios al CORE, no heredar claims, rutas relativas o `{RAIZ}` (hay test de portabilidad).
- Smoke-grade: n chico, declarado; nada de esto es gate hasta que haya medición propia.

## 6. Decisiones del operador (2026-10-21)

- Empezar por **F0** (bench + A/B baseline vs prosa), con **3 brazos** y criterio determinista pre-registrado.
- Escribir este informe + la [spec de exp/72](../../banco/specs/exp72_fable.md). F1 (judge) y F2 (flow) quedan sujetos al resultado de F0.

## Referencias

- Upstream: [github.com/Sahir619/fable-method](https://github.com/Sahir619/fable-method) @ `9924067` (2026-10-03). Licencia [MIT](https://github.com/Sahir619/fable-method/blob/main/LICENSE).
- Digest del scout (esta sesión, no versionado): `salidas/fable-method-digest.md`.
- Harness: `docs/design.md` (skills `:197`, módulos `:210-232`), `utils/skills.py`, `juez.py`, `utils/citas.py`, `banco/banco.py`, `modules/juez.py`, `modules/humano.py`, `juez_lote.py:119`.

## Resultado de F0 (2026-10-21)

El bench de exp/72 corrió las 30 corridas: **4/5 trampas quedaron en techo** (el chat
baseline ya las resuelve) y la única con margen (s2, spec vs test) no mejoró con la prosa
(A 1,33 vs B 1,00). Los artefactos forzados sí aparecieron (TWINS/PENDING), sin cambio de
conducta. Por eso F1/F2 (judge/flow) no se escriben todavía: primero hay que subir la
dificultad del bench (exp/73 propuesto). Números y decisión completos en
[bitacora.md](../bitacora.md) exp/72; criterio congelado en
[exp72_fable.md](../../banco/specs/exp72_fable.md).

