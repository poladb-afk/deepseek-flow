# Ratchets y reglas de agente: tres repos, tres mecanismos (2026-10-19)

**Pregunta:** ¿qué hacen `monk-eee/git-agent-ratchet`, `Emmanuel-Bamidele/AI-Agent-Coding-Rules`
y `kernullist/ruleward`, y cómo se usan para mejorar el harness deepseek-flow?

**Método:** búsqueda online, lectura de los README completos de los tres repos
(HTTP 200 verificado contra `raw.githubusercontent.com`) y de su metadata
(GitHub API), y después una auditoría del harness contra los mecanismos
encontrados. Se adoptó lo que pasaba un filtro determinista y quedaba
sostenible; el resto se descartó con motivo. Los números de este informe son
mediciones del árbol, no estimaciones.

**Nota de honestidad sobre las fuentes:** los tres son repos chicos y nuevos
(0–1 stars, entre mayo y julio de 2026). No son autoridad por popularidad; el
valor está en el *mecanismo*. El más maduro es `git-agent-ratchet` (PyPI,
v1.3.0, CI + CodeQL + codecov + pre-commit + suite propia y dogfooding: corre
sus ocho ratchets contra sí mismo).

## 1. Qué hace cada repo

### `monk-eee/git-agent-ratchet` — el hook layer de AGENTS.md

Python · MIT · v1.3.0 · [repo](https://github.com/monk-eee/git-agent-ratchet) ·
[PyPI](https://pypi.org/project/git-agent-ratchet/)

Tesis: *"The rule didn't change. The cost of breaking it did."* Un `AGENTS.md`
es contexto que el modelo pesa contra todo lo demás; la longitud lo erosiona y
los conflictos se resuelven arbitrariamente. Si la regla importa, va debajo de
la prosa un **hook determinista** que falle el commit. El paquete trae ocho:

| Ratchet | Qué congela |
|---|---|
| A `no-duplicate-helpers` | nombres de helpers privados que se bifurcan entre archivos |
| B `deny-agent-chatter` | preámbulo conversacional del agente commiteado en fuentes |
| C `anti-bypass` | mutaciones de los propios archivos del ratchet sin clave humana |
| D `max-file-lines` | overage de líneas por archivo |
| E `no-cross-module-private-imports` | imports de `_privados` ajenos |
| F `no-print-outside-allowlist` | `print()` fuera de los shims |
| G `no-temporary-comments` | `TODO`/HACK/"for now"/"back-compat" |
| H `dont-use-powershell` | invocaciones PowerShell en texto commiteado |

El mecanismo central es el **baseline shrink-only**: un JSON versionado con el
número actual de la métrica. Si la corrida mejora, el hook reescribe el
baseline y lo deja en el commit; si empeora, falla; si no cambia, verde. El
número nunca crece sin que un humano exporte `HUMAN_RATCHET_BYPASS_KEY`.

Dos ideas de diseño que se llevó la adopción:

1. **Cuatro barras para que una regla gane un ratchet de deuda** (si no las
   pasa, queda prosa o linter): (a) se dispara seguido en trabajo normal;
   (b) el review humano lo deja pasar en silencio; (c) se paga con trabajo
   ordinario, no con un sprint heroico; (d) barato temprano, caro tarde.
   Un ratchet que no baja nunca es una **sinecura** y hay que retirarlo.
2. **Dos clases de gate, ejes distintos**: deuda (se juzga por movimiento del
   número) e invariante (se juzga por disuasión; ej. el anti-bypass no se mide
   por frecuencia). Confundirlos es cómo se acusa de sinecura a un gate sano.

### `Emmanuel-Bamidele/AI-Agent-Coding-Rules` — el rulebook drop-in

[repo](https://github.com/Emmanuel-Bamidele/AI-Agent-Coding-Rules) · 1 star ·
licencia "Other"

No es tooling: es un **paquete de reglas y checklists en Markdown** para pegar
en un repo (`agent-instructions/`: `AGENT.md` + 20 archivos de dominio —
principios, estilo, seguridad, testing, arquitectura, dependencias, CI/CD,
observabilidad, documentación, git, review checklist, definition of done,
plantillas de tarea/PR y formato de respuesta — más integraciones para
Codex/Claude/Cursor/Copilot). La tesis: agentes con reglas locales, explícitas
y accionables escriben parches más chicos, agregan tests, evitan requisitos
inventados y no rompen seguridad.

Lo que aporta al harness: la **estructura** de un contrato de agente (qué
pedirle explícitamente: parche mínimo, tests, DoD, formato de reporte). Lo que
*no* hay que copiar: los 22 archivos. En este repo eso sería contexto de cada
request por decenas de miles de tokens; `ruleward` lo llama *bloat* y tiene
razón. Se adaptó a **un** `AGENTS.md` de 92 líneas.

### `kernullist/ruleward` — el linter de los archivos de reglas

TypeScript · MIT · todavía no publicado en npm ·
[repo](https://github.com/kernullist/ruleward)

Tesis: los agentes leen `AGENTS.md`/`CLAUDE.md`/`.cursor/rules` en casi cada
request, esos archivos crecen y se pudren (se contradicen, se repiten, inflan
el contexto, apuntan a código que ya no existe) y **no tienen compilador ni
linter**. `ruleward` parsea los archivos a un IR (Markdown AST), construye un
índice de código con tree-sitter y corre cuatro motores:

| Motor | Chequeos deterministas | Semántico (opt-in) |
|---|---|---|
| conflict | setting en tabs vs spaces, prohibir+requerir el mismo import | contradicción NLI |
| duplication | regla que repite `package.json`/tsconfig/Prettier, near-duplicates | — |
| bloat | presupuesto de tokens, reglas vagas ("write clean code") | — |
| drift | path inexistente, script que no está en package.json, símbolo/dependencia/alias que no existe, `@deprecated` sin guardia | — |

El motor de **drift** es la parte que un linter de formato no puede hacer:
cruzа las reglas contra el código real. Salida pretty/JSON/**SARIF** (sube a
code scanning de GitHub) y `.rulewardrc.json` para calibrar. El nivel NLI
semántico es opt-in, reportado como `info` y nunca falla CI — sus propios docs
cuentan que pasó de 326 findings a 0 en 60 archivos reales, pero la recall
sigue sin caracterizar.

Lo que aporta al harness: la idea de **deriva de las reglas contra el
código** como test (no como herramienta externa) y el **presupuesto de
contexto** del archivo de reglas. Lo descartado: NLI semántico (otra
dependencia, ruido en prosa española, costo de modelo para un chequeo que acá
no cambia decisiones) y SARIF (no hay code scanning configurado).

## 2. Diagnóstico: qué ya tenía el harness (para no duplicar)

| Mecanismo del repo | Estado previo en deepseek-flow |
|---|---|
| Gate determinista antes del commit | **Fuerte**: `calidad.sh` (ruff · C901 en las dos fronteras · pytest) + CI en cada push |
| Candado de tests | **Fuerte**: `tests/inventario_tests.txt` (foto de 527) + tope de 800 líneas por archivo |
| Docs vs código | **Parcial**: `tests/test_docs_sin_deriva.py` (tool count, CLI, settings) |
| Baselines con sha y regla "no pisar" | **Fuerte en medición**: bench del router/juez/supervisor y replay (evals.py, bench_juez.py, banco/bench_supervisor.py, replay.py) |
| Contrato de agente versionado | **Ausente**: no había `AGENTS.md` (solo `docs/agents/`, heredado de una skill, que apunta a un `CONTEXT.md` que no existe) |
| Métricas estructurales con baseline | **Ausente**: inventario y 800 líneas son topes fijos, no ratchets |

Gaps medidos en el árbol (2026-10-19):

- **8 nombres de helpers privados bifurcados** en 2+ archivos, **20
  ocurrencias** (`_git_sha` y `_fmt_pct` con 4 copias cada uno; `_approve`,
  `_leer_eventos`, `_listar`, `_model`, `_prefiltrar`, `_texto` con 2).
- **0** marcadores `TODO`/`FIXME`/`HACK` reales: el ratchet G del original
  acá sería una sinecura → descartado.
- Los **30 tests** citados en `docs/estado.md` existen; los **36 paths**
  citados incluyen 4 que son ejemplos de prosa (`modulo.py`, `otro_modulo.py`…),
  no deriva → el chequeo de paths se limita a `AGENTS.md` (normativo).
- El inventario del PR 4 solo vigila su foto: **25 tests nuevos** (los de esta
  jornada) podían desaparecer sin que nada los nombre.

## 3. Qué se adoptó (y qué pasó el filtro)

### 3.1 `ratchet.py` + `ratchets/baseline.json` — el mecanismo del ratchet

Dos métricas, una por clase:

- **`helpers_duplicados`** (deuda, menor mejor): helpers privados `_foo` de
  nivel superior en 2+ archivos del harness. Pasó las cuatro barras: los
  agentes bifurcan helpers (el árbol ya tiene 20 ocurrencias que el review no
  vio), se paga solo al tocar esos módulos, y es barato detectarlo.
- **`tests_definidos`** (cobertura, mayor mejor): `def test_*` en `tests/`.
  Cierra el hueco que el inventario deja en los tests posteriores al PR 4.

Se descartaron los otros seis ratchets del original con motivo medido:
`print` (el harness imprime por diseño: es un agente de terminal), chatter
(el repo no commitea salida de agente), PowerShell (no aplica), comentarios
temporales (**0 marcadores**: sinecura), imports privados cruzados (no hay),
`max-file-lines` (contradice una decisión medida del repo —las funciones
largas son deliberadas— y los tests ya tienen tope de 800).

Guardia anti-bypass: el baseline solo se mueve hacia la mejora; editarlo a
mano se detecta comparando contra `HEAD` y `HEAD~1` (el CI hace
`fetch-depth: 2` para poder ver el commit anterior). Sin clave humana, rojo.
`--actualizar` es la llave del operador.

Dato de la siembra: **el ratchet se detectó a sí mismo**. En la primera
corrida apareció un helper `_resumen` en `ratchet.py` que ya existía en
`utils/compaccion.py`: en vez de arrancar el baseline en 22 se renombró y
quedó en 20. Es exactamente el comportamiento buscado.

### 3.2 `AGENTS.md` — el contrato de agente

Un archivo (92 líneas, presupuesto 160), adaptado de la estructura de
AI-Agent-Coding-Rules al contenido real de este repo:

- qué leer antes de tocar nada (tablero → diseño → bitácora → roadmap);
- **8 reglas no negociables**, cada una con el gate que la hace cumplir
  (patrón del "Mechanical enforcement table" de git-agent-ratchet): gate
  verde, inventario de tests, docs sin deriva, tablero con test real, helpers
  sin bifurcar, baseline shrink-only, seguridad con tests de bypass,
  contratos congelados con sha1;
- **reglas blandas declaradas** (parche mínimo, dependencias, comentarios,
  citas verificadas, commits, idioma): lo que todavía no se puede verificar se
  dice, no se disfraza;
- **bypasses prohibidos por nombre** (editar baseline/inventario, skip sin
  marker, comentar etapas del gate, exportar la clave del operador, tocar
  presupuesto/seguridad como "fix" de un test);
- **definición de terminado** y formato de reporte.

### 3.3 `tests/test_deriva_reglas.py` — el linter de las reglas

Adopción determinista de ruleward, dentro de la suite (sin dependencias):

- **bloat**: `AGENTS.md` ≤ 160 líneas / ≤ 12.000 chars;
- **drift**: toda ruta y todo test citados en `AGENTS.md` existen; los cuatro
  docs de arranque siguen nombrados;
- **enforcement**: cada fila de la tabla de reglas nombra un artefacto vigente
  (archivo, test, script) — una regla sin gate falla el test;
- **deriva del tablero**: cada test que `docs/estado.md` cita existe de
  verdad (la regla "un ✅ no puede quedar sin test" deja de ser honor system).

Lo descartado de ruleward: conflicto NLI y near-duplicates de prosa (sin señal
suficiente en español para un gate determinista) y SARIF (sin consumidor).

## 4. Verificación

- `./calidad.sh` con **cuatro palancas** (ruff · C901 · ratchet · pytest):
  verde. Suite: **594 tests** recolectados, 0 failed.
- Baseline sembrado: `helpers_duplicados` 20 · `tests_definidos` 491; tras
  los tests nuevos, 516.
- La guardia anti-bypass tiene tests propios: baseline editado a mano → rojo;
  clave humana presente → cede y no imprime la clave.

## 5. Límites conocidos

- El ratchet **congela la deuda, no la arregla**: los 20 helpers duplicados
  siguen ahí. El paydown quedó como ítem del roadmap (`_git_sha`/`_fmt_pct` a
  `utils/`; cada unificación baja el baseline sola).
- No hay pre-commit en este repo: el gate corre en `calidad.sh`/CI. El
  anti-bypass es **disuasión + auditoría**, no un sandbox: un agente decidido
  puede exportar la clave; el contrato lo prohíbe por nombre y el gate deja el
  bypass impreso si alguien lo declaró.
- La guardia depende de historia git (`fetch-depth: 2`); en clones shallow de
  un commit, la comparación HEAD~1 se saltea en silencio (por diseño
  best-effort).
- El linter de reglas no juzga semántica: un hecho de prosa puede seguir
  siendo falso si no está cubierto por un test de deriva. La regla del repo es
  agregar el test cuando duela.

## 6. Fuentes

- <https://github.com/monk-eee/git-agent-ratchet> (README completo; PyPI
  <https://pypi.org/project/git-agent-ratchet/>)
- <https://github.com/Emmanuel-Bamidele/AI-Agent-Coding-Rules> (README completo)
- <https://github.com/kernullist/ruleward> (README completo)
- Metadata de GitHub API consultada el 2026-10-19 (fechas, licencias, tamaño,
  estrellas) para no sobreestimar la madurez de las fuentes.
