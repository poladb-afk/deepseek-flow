# Plan de auditoría del harness a la luz de la evidencia

**Fecha:** 2026-10-17 · **Base:** [informe_evidencia_codigo_ia_vs_humano_2026-10-17.md](informe_evidencia_codigo_ia_vs_humano_2026-10-17.md) · **Objeto:** deepseek-flow (CORE + 18 módulos de tools; 29 tools: 3 CORE + 26 de módulos) · **Estado:** propuesta lista para ejecutar.

---

## 0. Veredicto de impacto

El harness es **consumidor y productor** de las dos cosas que el informe mide: su código lo mantienen humanos y agentes, y su producto es código/acciones generadas por un LLM. Por eso el informe no es contexto: **define el modelo de riesgo del harness**.

Los cuatro impactos que ordenan todo el plan:

1. **El gate actual audita correctitud, no seguridad ni fuerza de los tests.** ruff + C901 en fronteras + pytest cubren "funciona y está ordenado", pero no hay SAST, escaneo de secretos, análisis de duplicación/dead code, ni medición de cuán fuertes son los tests de las fronteras (coverage/mutación). La evidencia (≈40% de código generado vulnerable, más hallazgos de alto riesgo en Python/Java, deuda que persiste) apunta justo al hueco: **la frontera de escritura/ejecución**.
2. **Donde la evidencia es más sólida, los controles del harness son artesanales.** Las fronteras (policy de comandos, fs_tools, hooks, HITL) tienen código cuidadoso y tests, pero no una capa adversarial sistemática. La evidencia de seguridad + sobreconfianza (Perry: menos seguro, más confiado) dice que la revisión humana sola no alcanza y que el escrutinio cae cuando la herramienta "casi acierta".
3. **La productividad debe medirse como retrabajo, no como velocidad percibida.** METR cuantifica la brecha (esperaban +24%, midieron −19%, percibieron +20%). El harness ya tiene trazas, evals y heartbeat: el plan convierte eso en un tablero de retrabajo (retries, rechazos HITL, reescrituras, defectos escapados), no en un KPI de "tareas por hora".
4. **Las métricas de calidad son instrumentos débiles; el plan no agrega umbrales nuevos sin evidencia.** Pantiuchina (2018) e Improta (2026) muestran que las métricas fallan en capturar la mejora percibida y pierden señal al controlar tamaño. Se mantiene la regla del repo ("las reglas que importan son ejecutables": contratos, tests, candados) y **no** se agrega un gate de legibilidad o de coverage como objetivo.

**No se cambia arquitectura.** Se audita lo existente, se prioriza por riesgo y se agregan candados donde el riesgo está demostrado.

---

## 1. El harness en una página (snapshot medido hoy)

| Dimensión | Dato (2026-10-17) |
|---|---|
| Código | 25 top-level + 18 módulos (+ __init__) + 23 utils (+ __init__) + 37 archivos de test (36 test + conftest); ~21,7k LOC en 105 archivos .py |
| Tests | **527 tests** colectados; inventario congelado en `tests/inventario_tests.txt` |
| Historia | **193 commits** (4–16 oct 2026), un autor; picos de 50 y 48 commits/día |
| Gate | 3 palancas: ruff (E/W/F/B/I/C4/SIM/UP), C901 ≤ 12 **solo en las dos fronteras de seguridad**, pytest. CI corre `./calidad.sh` |
| Candados existentes | contratos sha1 congelados; grafos sin calles muertas; docs sin deriva; inventario de tests; máx. 800 líneas por archivo de test |
| Fronteras | `utils/policy.py` (clasificador determinista de riesgo), `utils/fs_tools.py` (hooks PRE fail-closed / POST), `modules/coding.py` (shell), `modules/escritura.py`, `utils/hitl_web.py`, `utils/aprobaciones.py` |
| Sin cubrir en deps/CI | SAST (bandit), secretos, deps (pip-audit), dead code (vulture), duplicación, coverage, mutación, property tests |
| Hotspots de churn | `tests/test_smoke.py` (91, ya partido), `docs/design.md` (67), `docs/roadmap.md` (42), `nodes.py` (33), `README.md` (27), `utils/fs_tools.py` (16), `modules/coding.py` (14), `utils/policy.py` (8) |

Lectura: la velocidad de producción de cambios es alta (≈15 commits/día) y la capacidad de revisión/refactorización es una sola persona. Ese es exactamente el **desacople de ritmo** que la evidencia asocia a clones, churn y caída de estabilidad — no como acusación, sino como hipótesis a medir en Fase 0/4.

---

## 2. Evidencia → consecuencia → control a auditar

| # | Evidencia (informe §) | Qué implica para el harness | Control a auditar | Fase |
|---|---|---|---|---|
| E1 | Comprender es ~58% del tiempo (§2) | El código del harness debe ser navegable por agentes y humanos: entrada, registro de módulos, contratos, docs | Time-to-first-correct-change; drift docs↔código; claridad de entry points | F1 |
| E2 | "Escribir bien paga": dirección consistente, magnitud no medida (§1, §2) | No sumar métricas de vanidad; cada control nuevo debe ser ejecutable o tener evidencia local | Inventario de gate: qué regla previene qué fallo | F1 |
| E3 | Métricas de calidad débiles (Pantiuchina; Improta) (§2.3) | El gate es red de seguridad, no certificado; los umbrales heredan error | Mutación en fronteras; revisar qué umbrales se están usando como verdad | F1 |
| E4 | Firma del código IA: construcciones sin uso, debugging hardcodeado, más vulns alto riesgo en Python/Java (§3.3) | Buscar esos patrones en el repo y en el código que el harness escribe | Dead code, prints/TODO de debug, SAST, secretos | F1 |
| E5 | ≈40% vulnerable en escenarios; Perry: menos seguro y más confiado (§3.3) | La frontera write/edit/run es el activo más expuesto; requiere adversarialidad sistemática | Fuzz/property de `policy`; casos symlink/TOCTOU/injection en `fs_tools`; escape de HITL | F2 |
| E6 | Bugs típicos de LLM: interpretación errónea, caso borde faltante, error tonto, generación incompleta (§3.3) | El loop del harness debe detectar el "casi correcto" (retries, validación, hooks) | Cobertura de casos borde en tools/parsers; DSML; no-progreso; presupuesto | F3 |
| E7 | METR: −19% en repos maduros y brecha percepción-medición (§3.2) | Medir retrabajo real, no velocidad percibida; probar en tareas propias, no benchmarks | Retry rate, rechazo HITL, reescrituras, defectos escapados; evals con tareas reales | F4 |
| E8 | Confianza condicional: 48% confía solo si puede validar (SO 2026) (§3.4) | La validabilidad es una feature: diffs, evidencia, citas, trazas | Calidad de la información en HITL y en informes | F4 |
| E9 | Ritmo desacoplado: clones/churn suben, refactorización baja (§4) | Capacidad de revisión vs. velocidad de commits; medir, no prohibir | Baseline churn/refactor ratio; un tema por PR; presupuesto de cambios | F0, F4 |
| E10 | Atlassian legibilidad comparable; Mao diferencias pequeñas (§3.4) | No sobre-reaccionar al estilo: el problema es integración/contexto | Inyección de convenciones del repo; tool schemas; docs en el contexto | F1, F3 |

**Nota de honestidad:** E5, E6 y E8 son las más fuertes; E9 es la más débil para *este* repo (no hay atribución de autoría posible; se mide el proceso, no "código IA").

---

## 3. Ejes, severidad y regla de cierre

**Ejes:** E-A correctitud/contratos · E-B mantenibilidad/estructura · E-C seguridad · E-D confianza/gobernanza · E-E medición.

**Severidad:**
- **P0:** bypass de un control de seguridad, pérdida/corrupción de datos, o acción destructiva sin aprobación.
- **P1:** brecha de control reproducible y demostrable con un test (incluye fallo de candado existente).
- **P2:** deuda que degrada la capacidad de detectar fallos (observabilidad, duplicación, docs).
- **P3:** cosmético o preferencia sin evidencia.

**Regla de cierre (heredada de [estado.md](../estado.md)):** ningún hallazgo queda ✅ sin un test que lo cubra; si se cierra sin test, se declara explícitamente. **Regla anti-Goodhart:** una métrica nueva entra al gate solo si (a) hay evidencia de que mide lo que se quiere, o (b) es un contrato ejecutable, no un umbral.

---

## 4. Plan por fases

### Fase 0 — Baseline y encuadre (0,5–1 día)
- Congelar snapshot (`git rev-parse HEAD`), correr `./calidad.sh`, registrar 527 tests y su tiempo.
- Completar baseline: churn por archivo (commits y líneas), ratio test/source por commit, reincidencia por archivo, tamaño de commits, frecuencia de días.
- Inventario de herramientas de calidad: presentes vs. ausentes (tabla §1).
- **Pre-registrar hipótesis y severidades** (§5) para no racionalizar después.
- Entregable: `salidas/auditoria_2026-10/baseline.md` con comandos reproducibles.

### Fase 1 — Calidad estática y verificación del gate (2–3 días)
- **Gap analysis del gate:** ¿qué fallo previene ruff? ¿qué previene C901 en fronteras? ¿qué no previene nada?
- **Fuerza de tests:** coverage como diagnóstico (no KPI) + **mutación** en las 4 fronteras (`policy.py`, `fs_tools.py`, `modules/coding.py`, `utils/call_llm.py`).
- **Hotspots:** churn × complejidad (nodes.py, fs_tools, coding, call_llm, policy) y docs con más cambios.
- **Patrones del código IA:** dead code, prints/TODO de debug, construcciones sin uso, boilerplate repetido, secretos accidentales.
- **Verificar que las reglas sean ejecutables:** contratos sha1, grafos, inventario, docs sin deriva (ya existen: confirmar que muerden).
- Aceptación: matriz de hallazgos con archivo:línea, severidad, evidencia (§2) y candado propuesto; mutation score baseline por frontera.

### Fase 2 — Frontera de escritura y ejecución (3–4 días) — **prioridad máxima**
- **write_file / edit_file:** path traversal, symlinks y TOCTOU, atomicidad, no-clobber, encoding/binarios, hooks POST (hoy solo `py_compile`), diff del HITL.
- **run_command:** clasificador (composición con `&& | ;`, redirecciones, `$()`, xargs, `cd`, flags peligrosos), HITL graduado, timeout/clip, env/secrets, cwd.
- **Adversarial:** inyección shell vía nombre/contenido/unicode; symlink swap; bypass de denylist; escapes de HITL (timeout, EOF, cancelación web); módulo roto o tool duplicada.
- **Contenido no confiable:** read_file/search_files/web/rag/mcp → prompt injection; separación datos/instrucciones; sanitizar; tests de inyección.
- Aceptación: suite adversarial verde; todo bypass reproducido deja candado; un caso por clase de ataque en CI.

### Fase 3 — Cadena LLM y recuperación del "casi correcto" (2–3 días)
- Mapear los 10 patrones de bug (Tambon) a los mecanismos existentes: retries, no-progreso, presupuesto, DSML, sanitizar, validación de historial, `resultado_ok`.
- Router/juez/supervisor: fallback, NaN/umbrales, calibración, contratos congelados; revisar que los tests cubran los caminos de error.
- Medir "casi correcto": tasa de retry, correcciones, rechazos; comparar con la expectativa.
- Aceptación: tabla patrón ↔ mecanismo ↔ cobertura ↔ test faltante; tests para los patrones no cubiertos.

### Fase 4 — Medición y gobernanza (2 días)
- **Inventario de métricas/evals:** qué mide cada una (evals, bench_juez, effective_n, heartbeat, juez), contra qué baseline, quién la usa. Detectar autorreporte.
- **Tablero de retrabajo** (6–8 métricas): retry rate, rechazo HITL, reescrituras, defectos escapados, churn a 2 semanas, duplicate rate, estabilidad (éxito de tareas), tiempo de revisión.
- **Validabilidad:** auditar el diff del HITL y la evidencia que se muestra; ¿un humano puede decidir con la información que ve?
- Aceptación: tablero definido y corriendo con datos locales; un experimento con tareas reales del harness (no benchmark).

### Fase 5 — Remediación, candados y cierre (2–3 días)
- Fixes P0/P1 con test; candados permanentes; si Fase 1 lo justifica, **cuarta palanca** del gate (SAST/secretos), con costo medido.
- Actualizar [estado.md](../estado.md) con columna "evidencia" (fuente del hallazgo) y tests.
- Re-correr gate + baseline; comparar contra Fase 0; informe final de auditoría.
- Aceptación: 0 P0/P1 sin test; gate verde; delta medido y documentado.

---

## 5. Backlog inicial priorizado (hipótesis a confirmar, no hallazgos)

| ID | Hipótesis | Evidencia que la justifica | Fase | Prioridad provisoria |
|---|---|---|---|---|
| H1 | No hay SAST/secretos en gate ni CI; el repo puede tener hallazgos de alto riesgo sin detectar | E4, E5 | F1 | P1 |
| H2 | Los hooks de escritura solo verifican sintaxis (`py_compile`); no hay verificación semántica ni lint del archivo escrito | E4, E6 | F2 | P1 |
| H3 | El clasificador de comandos no tiene fuzz/property tests; el bypass ya ocurrió (A01/E4) | E5 | F2 | P1 |
| H4 | La frontera fs no tiene tests adversariales sistemáticos de symlink/TOCTOU/encoding | E5 | F2 | P1 |
| H5 | La fuerza de los tests de fronteras es desconocida (sin mutación) | E3 | F1 | P1 |
| H6 | Contenido no confiable (archivos/web/rag/mcp) puede inyectar instrucciones en el loop | E5, E8 | F2 | P1 |
| H7 | Las métricas de productividad del harness son parcialmente autorreporte o de vanidad | E7, E8 | F4 | P2 |
| H8 | El registro de módulos tolera sombreado silencioso de tools (solo warning) | E6 | F1 | P2 |
| H9 | No hay medición de capacidad de revisión (churn/refactor ratio) pese a ~15 commits/día | E9 | F0, F4 | P2 |
| H10 | Coverage/mutación no están en deps; el diagnóstico de tests es manual | E3 | F1 | P2 |

---

## 6. Cronograma y esfuerzo

| Fase | Días-persona | Depende de | Paralelizable con |
|---|---|---|---|
| 0 — Baseline | 0,5–1 | — | — |
| 1 — Estática/gate | 2–3 | F0 | F2 (lectura de frontera) |
| 2 — Write/run | 3–4 | F1 (inventario) | F3 (cadena LLM) |
| 3 — LLM/recovery | 2–3 | F1 | F2 |
| 4 — Medición | 2 | F0, F2, F3 | F5 (preparación) |
| 5 — Remediación/cierre | 2–3 | F2, F3, F4 | — |
| **Total** | **~11–16** | | 2 auditores en paralelo → ~7–9 días de calendario |

**Orden innegociable:** F0 antes de tocar nada; F2 antes de F5 (los P0 de seguridad primero); F5 no empieza sin los candados de F2/F3.

---

## 7. Qué NO se hará (anti-metas)

- **No** se agrega un gate de legibilidad automática ni de estilo cosmético: la evidencia la valida contra percepción, no contra mantenimiento (Buse & Weimer; Pantiuchina; Improta).
- **No** se usa coverage ni complejidad como KPI: se usan como diagnóstico, y se prefiere mutación/contratos.
- **No** se mide "porcentaje de código IA": la atribución es heurística e inestable (Ji et al.; METR 2026).
- **No** se reescribe arquitectura ni se cambia el modelo de HITL: la auditoría es incremental y conserva la conducta (regla del repo).
- **No** se acepta "funciona" como criterio de cierre de un hallazgo: todo cierre lleva test o declaración explícita.

---

## 8. Referencias

- Informe base con fuentes y límites: [informe_evidencia_codigo_ia_vs_humano_2026-10-17.md](informe_evidencia_codigo_ia_vs_humano_2026-10-17.md).
- Estado de hallazgos y regla de cierre: [../estado.md](../estado.md).
- Gate y CI: [../../calidad.sh](../../calidad.sh), [../../.github/workflows/calidad.yml](../../.github/workflows/calidad.yml).
- Diseño y fronteras: [../design.md](../design.md); patrón prep/exec/post: [patron-prep-exec-post.md](patron-prep-exec-post.md).
- Evidencia externa clave citada: Xia et al. TSE 2017; Buse & Weimer TSE 2010; Pantiuchina ICSME 2018 y TOSEM 2020; Khomh WCRE 2009; Pearce IEEE S&P 2022; Perry CCS 2023; Tambon EMSE 2025; ISSRE 2025; Improta arXiv 2609.12708; METR 2025/2026; Stack Overflow 2025/2026; DORA 2024/2025. URLs completas en el informe base.
