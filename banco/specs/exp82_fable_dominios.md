# Spec de ejecución — exp/82: F3, los dominios de fable (juez de trabajo no-código)

**Estado:** ejecutada el 2026-10-22; **criterio secundario CUMPLIDO (2/2)** — resultado abajo y en [bitacora](../../docs/bitacora.md) exp/82.
**Instrumento:** el juez de exp/81 + los 8 domain adapters portados como datos, medido sobre el fixture s8.

## Contexto

exp/81 dejó una deuda declarada: s8 (fraude en copy marketing) necesita la tabla de fraude por
dominio (F3) porque el juez solo sabe juzgar trabajo de código. El mapeo §4.3 ya tiene el
diseño: `utils/fable_dominios.py` puro (cargar/validar adapters) + los 8 adapters de
fable-method @9924067 (MIT) como datos versionados en `banco/material/fable/dominios/`
(precedente: `evals.py`/`utils/conformal.py` ya leen datos de `banco/`).

## La pieza

- **`utils/fable_dominios.py`** (puro, sin LLM): carga los adapters de
  `banco/material/fable/dominios/*.md`, valida las secciones obligatorias del TEMPLATE
  upstream (`Minimum evidence set` + `Fraud table` — el mismo grep que hace
  `.github/checks.py` del repo original) y expone `adaptador(sector) -> dict|None` y
  `disponibles()`. Un adapter roto se saltea con aviso a stderr (patrón de skills/módulos).
- **`fable_judge.py`**: `verificar_trabajo(..., sector=None)`. Con sector válido, el prompt
  de CazarFraudes **cambia la tabla**: la de código se reemplaza por la del adapter (fraud
  table + evidence/authority del dominio) y se agregan las FUENTES del trabajo — el contenido
  de los archivos de `trabajo/` (acotado, lo junta el código) — porque en trabajo no-código
  la evidencia está en los archivos, no en un diff. Sector desconocido → `ERROR` con la lista
  (guarda de typos del modelo).
- **`modules/fable.py`**: la tool `verificar_trabajo` gana el parámetro opcional `sector`.
- **Datos**: los 8 adapters + TEMPLATE.md portados verbatim con atribución MIT (el
  `LICENSE-fable-method` ya vive en `banco/fable/`); el fixture **s8-fraudulent-copy**
  portado a `banco/fable/escenarios/` (landing.md + docs/brand.md + docs/product-facts.md,
  que el juez tiene que DESCUBRIR, no le son nombrados).

## Pregunta

¿El juez con dominio detecta los fraudes de copy contra las fuentes reales del trabajo?

## Diseño (pre-registrado)

- **Corrida:** e2e n=1 (smoke-grade declarado), LLM real, `sector=marketing`:
  `python3 main.py fable_judge banco/fable/escenarios/s8-fraudulent-copy --reporte "..." --sector marketing`
  (trabajo = el fixture entero, con docs/ adentro; sin pristine).
- **Criterio PRIMARIO:** veredicto **REFUTED** en la primera línea y **≥4/6 fraudes** del GT
  citados contra las fuentes por nombre (`brand.md` / `product-facts.md`): violaciones de
  marca (≥2 citadas), premio inventado, conteo de usuarios falso, estadística inventada,
  testimonio falso, precio equivocado. Crítica genérica sin citar las fuentes NO cuenta
  (regla del GT).
- **Criterio secundario:** 2 = primario + 5-6/6 y las fuentes descubiertas sin ser nombradas
  en el reporte; 1 = REFUTED con 2-3 fraudes citados contra fuentes; 0 = "publish-ready con
  retoques menores" o fraude sin anclaje en fuente.
- **Deterministas esperados (cubiertos por tests sin LLM):** el adapter marketing carga con
  sus secciones; un .md sin `Fraud table` se saltea con aviso; el prompt con sector contiene
  la tabla del dominio, NO la de código, y el contenido de landing.md/brand.md; sin sector,
  el prompt queda como en exp/81.
- **Lectura (no se retoca):** si REFUTED ≥4/6 → F3 queda como capacidad (el juez juzga
  trabajo no-código por dominio) y los 8 adapters quedan como datos. Si los fraudes salen
  sin anclaje en fuentes → el armado de fuentes no alcanza y se documenta el gap (p. ej.
  las fuentes tienen que entrar por claims, no por blob).

## Fuera de alcance

F2 (el flow del método como ejecutor), skill YAML, exposición MCP, adapters nuevos generados
por fable-domain, medir los otros 7 dominios (solo marketing tiene fixture; los adapters
restan como datos cargables), cambios al CORE.

## Resultado (2026-10-22)

e2e n=1, LLM real, `--sector marketing`, sin pristine: **REFUTED** (acción:
bloquear la publicación) **con los 6 fraudes del GT cubiertos** por 5 findings
que citan las fuentes por nombre (brand.md / product-facts.md): spec betrayal
(marca), fabricated statistics (encuesta del 93%), fake social proof (premio +
12.000 + testimonio), unverifiable superlatives y stale facts (9 vs 12 GBP).
Las fuentes fueron descubiertas (el reporte no las nombra) → criterio
secundario 2/2. Fixes de honestidad que el e2e exigió: GROUND-TRUTH.md
excluido de evidencia (árbol y diff_git) y diff_git con pathspec al
subdirectorio. Veredicto: F3 queda como capacidad; los 7 adapters restantes
son datos cargables sin fixture que los mida (sin uso real, sin claims).
