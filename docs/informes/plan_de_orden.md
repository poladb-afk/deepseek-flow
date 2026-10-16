# Plan de orden — deepseek-flow

**Fecha:** 2026-10-16 · **Base:** el árbol consolidado (zip + `consolidacion_2026-10-15.patch` + tus cambios encima).
**Objetivo:** ordenar sin cambiar conducta. Ninguna feature nueva.

## Reglas para todos los PR

1. **Gate verde en cada PR:** `./calidad.sh` → ruff limpio, C901 ≤ 12 en las fronteras de seguridad (PR 6) y pytest sin fallos, con la **misma cantidad de tests o más**.
2. **Sin cambio de conducta:** si un test existente cambia su aserción, el PR está mal partido. La única excepción es mover un test de archivo sin tocar su cuerpo.
3. **Un PR = un tema.** Se revierte con `git revert` sin arrastrar otra cosa.
4. **Primero se protege, después se mueve:** el PR 1 va antes que todos porque es el que detecta si un PR posterior rompe la documentación.

## Resumen

| PR | Tema | Archivos | Riesgo | Esfuerzo |
|---|---|---|---|---|
| 1 | Tests contra la desalineación docs ↔ código | 1 nuevo | nulo | 30 min (el test ya está escrito, abajo) |
| 2 | Documentación: estado vivo, archivo, design/bitácora/roadmap | `docs/` | nulo | 2–3 h |
| 3 | Deduplicar código | ~15 | bajo | 2 h |
| 4 | Partir `test_smoke.py` + `conftest.py` + markers | `tests/` | bajo | 2 h |
| 5 | Datos personales y artefactos | `banco/`, `heartbeat`, `call_llm` | bajo | 1–2 h |
| 6 | Refactor de `run_command` y `search_files` | 2 | medio | 2 h |
| 7 | CI | 2 | nulo | 30 min |

Dependencias: **1 → (2, 3, 5 en cualquier orden) → 4 → 6 → 7**. El 4 va después del 3 porque mover tests y deduplicar los imports en el mismo PR hace el diff ilegible. El 6 va después del 4 para que los tests de policy ya estén en su archivo propio.

---

## PR 1 — Tests contra la desalineación

**Problema medido:** el README decía 24 tools y había 29. Había 18 settings leídos y no documentados, `LAYA_UNSURE_HIGH` aparecía documentado dos veces con valores distintos, y faltaban 3 subcomandos en el README. Todo esto se encontró a mano.

**Cambio:** `tests/test_docs_sin_deriva.py`, con 5 tests que no dependen de red, LLM ni Laya.

**Verificado:**

| Árbol | Resultado |
|---|---|
| Zip anterior a la consolidación | **5 de 5 fallan**, cada uno con la deriva concreta (`README dice 24 tools y hay 29`, `subcomandos … sin línea: ['bench_juez', 'replay', 'resume']`, los 18 settings, el duplicado) |
| Zip + patch de consolidación | **5 de 5 pasan**, ruff limpio |

> Si en tu árbol actual alguno falla, es una deriva real que entró después de la consolidación (por ejemplo, un setting nuevo sin documentar). Se corrige la documentación, no el test.

<details><summary><b>tests/test_docs_sin_deriva.py</b> (listo para copiar)</summary>

```python
"""Guardas contra la deriva docs ↔ código (PR 1 del plan de orden).

Lo que hoy se detectaba a mano (README con 24 tools cuando había 29, 18
settings sin documentar, subcomandos sin README) pasa a ser un test: la
documentación no puede volver a mentir en silencio."""
import re
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Lo que el harness lee pero no es "configuración del usuario"
NO_DOCUMENTABLES = {"HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "DEEPSEEK_API_KEY"}
LECTORES = [
    r'_(?:setting|entero|real|umbral)\(\s*["\']([A-Z][A-Z0-9_]+)["\']',
    r'environ(?:\.get)?\(\s*["\']([A-Z][A-Z0-9_]+)["\']',
    r'environ\[\s*["\']([A-Z][A-Z0-9_]+)',
    r'setting(?:_modelo)?\s*=\s*["\']([A-Z][A-Z0-9_]+)["\']',
    r'(?:disponible|agente)\(\s*["\']([A-Z][A-Z0-9_]+)["\']',
]


def _fuentes():
    for p in RAIZ.rglob("*.py"):
        rel = p.relative_to(RAIZ).as_posix()
        if rel.startswith(("tests/", "docs/", ".")) or "__pycache__" in rel:
            continue
        yield rel, p.read_text(encoding="utf-8")


def _settings_usados():
    usados = {}
    for rel, src in _fuentes():
        for rx in LECTORES:
            for m in re.finditer(rx, src):
                usados.setdefault(m.group(1), rel)
    return {k: v for k, v in usados.items() if k not in NO_DOCUMENTABLES}


def _settings_documentados():
    env = (RAIZ / ".env.example").read_text(encoding="utf-8")
    return Counter(re.findall(r"^#?\s*([A-Z][A-Z0-9_]{2,})=", env, re.M))


def test_todo_setting_usado_esta_documentado():
    faltan = {k: v for k, v in _settings_usados().items() if k not in _settings_documentados()}
    assert not faltan, f"settings leídos por el código y ausentes de .env.example: {faltan}"


def test_ningun_setting_documentado_dos_veces():
    dobles = {k: n for k, n in _settings_documentados().items() if n > 1}
    assert not dobles, f"settings documentados más de una vez en .env.example: {dobles}"


def test_readme_cuenta_bien_las_tools():
    import nodes

    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    m = re.search(r"## Capacidades \((\d+)", readme)
    assert m, "el README perdió el encabezado '## Capacidades (N ...)'"
    assert int(m.group(1)) == len(nodes.TOOLS), (
        f"README dice {m.group(1)} tools y hay {len(nodes.TOOLS)}")


def test_readme_menciona_cada_tool():
    import nodes

    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    tabla = readme.split("## Capacidades", 1)[1].split("\n## ", 1)[0]
    nombres = {t["function"]["name"] for t in nodes.TOOLS}
    faltan = sorted(n for n in nombres if f"`{n}`" not in tabla)
    assert not faltan, f"tools sin fila en la tabla de Capacidades del README: {faltan}"


def test_readme_lista_cada_subcomando():
    from main import SUBCOMANDOS

    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    listados = set(re.findall(r"python3 main\.py ([\w-]+)", readme))
    faltan = sorted(set(SUBCOMANDOS) - listados)
    assert not faltan, f"subcomandos de main.py sin línea en 'CLI completo': {faltan}"
```

</details>

**Criterio de aceptación:** pasa en verde; si en un PR posterior agregás un setting sin documentarlo, falla con el nombre y el archivo.

---

## PR 2 — Documentación

**Problema medido:** `docs/informes/` tiene ~19 archivos y ~470 KB, con 5 auditorías que se pisan entre sí y numeraciones distintas (A01–A28, H01–H21, R01–R26), más 2 `.patch` ya aplicados. `design.md` tiene 2.336 líneas y mezcla el diseño vigente con la bitácora de exp/2…exp/50. `roadmap.md` tiene 392 líneas, la mayoría de cosas ya hechas.

**Estructura propuesta:**

```
docs/
├── design.md          # SOLO lo que es verdad hoy: grafos, contratos de shared,
│                      # leyes/límites, settings por subsistema
├── estado.md          # NUEVO: una fila por hallazgo, viva
├── bitacora.md        # NUEVO: exp/2…exp/50 con sus mediciones (sale de design.md)
├── roadmap.md         # solo hacia adelante (la sección "Hechos" pasa a bitácora)
├── agents/            # sin cambios
└── informes/
    ├── (informes vigentes de diseño: patron-prep-exec-post, integracion_laya…)
    └── archivo/2026-10/   # auditorías, contrastes, correcciones, consolidación
```

**`docs/estado.md`, formato de cada fila** (la base es tu `contraste_auditoria_2026-10-15.md`, que ya mapea A↔H↔R):

| Id | Alias | Tema | Estado | Evidencia | Test que lo cubre |
|---|---|---|---|---|---|
| A01 | H01 | Bypass del HITL graduado | ✅ cerrado 2026-10-15 | `utils/policy.py` `_SEPARADORES`, `_FLAGS_PELIGROSOS` | `test_policy_bypass.py` |
| A06 | H07 | Prefiltro sin Laya recortaba | ✅ cerrado 2026-10-15 | `utils/contexto.py` | `test_consolidacion.py::test_prefiltro_*` |
| A07 | H07 | El prefiltro de memoria puntúa rutas, no contenido | ⏳ abierto | `utils/contexto.py` `str(unidad)` | — |
| … | | | | | |

Reglas: un hallazgo sin test no puede quedar en `✅`; un `⏳` lleva el motivo o el dueño.

**Pasos:**
1. Crear `estado.md` con todos los ids de las auditorías (A, H, R y los extra del contraste) y marcar el estado de cada uno contra el árbol actual.
2. Mover las auditorías, contrastes, informes de corrección y consolidación a `informes/archivo/2026-10/`.
3. **Borrar** `deepseek-flow-fixes.patch` y `consolidacion_2026-10-15.patch` de `docs/informes/`: ya están aplicados y el historial vive en git.
4. Partir `design.md`: cada sección `### exp/N — …` pasa a `bitacora.md` y en `design.md` queda una línea con el resultado vigente y el enlace.
5. En `roadmap.md`, mover «Hechos» y los ítems `✅` a la bitácora.
6. Actualizar los enlaces del README («Documentación»).
7. Opcional: dejar `docs/informes/` sin exclude en `pyproject.toml` si `reproducir_auditoria.py` también pasa al archivo (o mover el `.py` a `archivo/` y mantener el exclude solo ahí).

**Criterio de aceptación:**
- `design.md` queda en menos de 900 líneas y sin secciones `exp/N`.
- `informes/` raíz queda con menos de 8 archivos.
- Gate verde: el PR no toca código.
- `grep -r "docs/informes/" README.md docs/*.md` no deja enlaces rotos.

---

## PR 3 — Deduplicar código

**Duplicados medidos** (comparación AST de cuerpos de función + constantes con el mismo valor):

| Duplicado | Hoy en | Destino |
|---|---|---|
| `_approve`, `YES`, `PREVIEW_LINES` | `modules/coding.py`, `modules/escritura.py` | `utils/aprobaciones.py` → `pedir_aprobacion(prompt, cuerpo) -> bool` y `YES` |
| `_clip` (dos variantes: por chars y por líneas) | `coding.py`, `escritura.py` | `utils/terminal.py` → `recortar_chars()` / `recortar_lineas()` |
| `DIR_RUNS = Path(".runs")` ×4 | evals, replay, minar_errores, triaje_trazas | `utils/rutas.py` |
| `DIR_SALIDA = Path("salidas/evals")` ×5 | bench_juez, triaje, minar, evals, replay | `utils/rutas.py` |
| `RAIZ = Path(__file__)…` ×9 (3 profundidades distintas) | sondas, heartbeat, banco, probes | `utils/rutas.py` → `RAIZ_PROYECTO` (una sola, absoluta) |
| `_git_sha()` | `triaje_trazas.py`, `minar_errores.py` | `utils/rutas.py` → `git_sha()` |
| `preguntas_de_archivo`, `preguntas_de_escenarios`, `ANSI`, `IGNORAR`, `MIN_LARGO`, `PROMPT_ARBITRO` | `banco/probes/etiquetar_router.py`, `calibrar_voto.py` | `banco/probes/_comun.py` |
| Defaults `"deepseek-flash"` / `"https://api.deepseek.com"` | `modules/vision.py`, `banco/probes/thinking_flip.py` | `from utils.call_llm import DEFAULT_MODEL, DEFAULT_BASE_URL` (o `_model()`) |
| `SEARCH_MAX_FILES`, `SEARCH_MAX_MATCHES` | `modules/memoria.py`, `utils/fs_tools.py` | dejarlos **separados a propósito** si los topes pueden divergir; si no, importarlos de `fs_tools` |
| `TIMEOUT_S = 120` | `coding.py`, `vision.py` | **no tocar**: son el mismo número por casualidad, no el mismo concepto |
| 3 × `comparar_baseline` | evals, bench_juez, replay | **opcional**: `utils/baseline.py` con la métrica como parámetro. Solo si el PR queda chico |

**Pasos:**
1. Mover los helpers y dejar en el sitio viejo un import: `from utils.aprobaciones import pedir_aprobacion as _approve`. Así los `monkeypatch.setattr(coding, "_approve", …)` de los tests siguen funcionando.
2. Correr el gate.
3. En un commit aparte del mismo PR, quitar los alias que ya no use nadie.

**Criterio de aceptación:**
- Gate verde, con el mismo número de tests.
- La búsqueda AST de cuerpos idénticos no devuelve nada fuera de `docs/`.
- `grep -rn 'Path(".runs")' --include=*.py | grep -v utils/rutas.py` vacío.

**Riesgo:** los tests que hacen `monkeypatch` sobre el símbolo viejo. Los alias del paso 1 lo cubren.

---

## PR 4 — Tests

**Problema medido:** `tests/test_smoke.py` tiene 4.051 líneas y 233 tests. Hay archivos nombrados por fecha o por PR (`test_policy_bypass`, `test_consolidacion`, `test_pendientes`) y no por lo que protegen. Hay 8 tests que se omiten sin un marker que diga qué recurso necesitan.

**Estructura propuesta:**

```
tests/
├── conftest.py              # RAIZ, _tc(), fixture autouse de AGENT_ALLOWED_DIRS,
│                            # fakes de LLM (call_llm / call_llm_agent / stream)
├── test_fs_tools.py         # _resolve, list/read/search, symlinks, escribir_atomico
├── test_policy.py           # clasificar, explicar, denylist, _sale_de_raices
│                            #   ← test_policy_bypass + partes de consolidacion
├── test_hitl.py             # escritura, coding (aprobación), hitl_web, aprobaciones
├── test_chat_flujo.py       # nodes: AgentStep, ExecuteTools, presupuesto, DSML,
│                            #   sanitizar, no-progreso, resultado_ok
├── test_streaming.py        # call_llm_agent_stream, interrupción, cortes
├── test_router.py           # LayaRouter, voto  ← junto a test_laya_routing, test_voto_router
├── test_compaccion.py       # compactar, validar_historial, zona_fria, respaldo
├── test_memoria.py          # memory_search/save, prefiltro, resumen de sesión
├── test_db.py               # sql, LIMIT, comentarios, mode=ro
├── test_modulos.py          # discover, registro de tools, mcp_server.envolver
├── test_flujos.py           # juez, informe, auditoría, research, debate, supervisor
├── test_evals.py            # evals, bench_juez, replay, baseline
├── test_contratos.py        # sha1 de los contratos Laya (intactos)
├── test_docs_sin_deriva.py  # PR 1
└── (los que ya son temáticos: test_banco, test_thread_store, test_prefetch,
     test_riesgo, test_minar_errores, test_grafos_sin_calles_muertas, …)
```

**Markers** (`pyproject.toml`):

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "laya: requiere el paquete laya y un checkpoint local",
    "bmo: requiere los archivos de bmo (BMO_TASKS_DIR)",
    "red: requiere red o dependencias opcionales (ddgs, fastmcp)",
]
```

y en cada test que hoy hace `pytest.skip(...)` por un recurso externo, `@pytest.mark.<recurso>` además del skip.

**Pasos:**
1. Crear `conftest.py` moviendo los helpers compartidos. Los tests todavía no se mueven.
2. Mover los tests **por bloques**, copiando el cuerpo sin editarlo. Un commit por archivo destino.
3. Al terminar, `test_smoke.py` queda solo con los smoke reales (import de todo, `create_agent_flow()` arma el grafo, `discover()` encuentra N módulos) o desaparece.

**Criterio de aceptación:**
- **El mismo número exacto de tests recolectados:** `pytest --collect-only -q | tail -1` es igual antes y después.
- Ningún archivo de test pasa de ~800 líneas.
- `pytest -m "not laya and not bmo and not red"` corre sin skips.

**Aplicado (2026-10-16), con dos correcciones medidas:**

1. **Hizo falta un cuarto marker, `datos`.** Los tres del plan no alcanzan para
   "sin skips": hay 4 tests que se saltean sin `trazas.db` (artefacto local que
   se genera con `carga_trazas.py`, no está en el repo) y 1 más que se saltea
   si el filesystem no soporta symlinks. El subconjunto determinista es
   `pytest -m "not laya and not bmo and not red and not datos"` → **509 passed,
   9 deseados afuera, 0 skips** (medido). Con los tres markers solos da 514
   passed acá (donde `trazas.db` existe) pero **seguiría salteando en CI**.
2. **`test_policy_bypass.py` no se fusionó** en `test_policy.py`: ya era temático
   (su docstring explica de qué spec sale). Fusionarlo era churn sin ganancia.

**Cómo se verificó el paso 2** (mover 245 bloques sin tocar un cuerpo):
`salidas/pr4_verificar2.py` extrae los bloques top-level de `HEAD:tests/test_smoke.py`
y de los 19 archivos nuevos y compara texto y AST: **245 = 245, faltan 0, sobran 0,
244 funciones con AST idéntico, 0 duplicadas**. Además
`--collect-only | sed 's/^[^:]*:://' | sort` da **los mismos 518 nombres** que antes
(el archivo cambia, el test no) y la suite entera sigue en **518 passed**.

---

## PR 5 — Datos personales y artefactos

| Qué | Hoy | Cambio |
|---|---|---|
| `heartbeat.jsonl` | versionado, con `~/Documentos/00_IA/bmo/data` | renombrar a `heartbeat.example.jsonl`; `heartbeat.py` lee `heartbeat.jsonl` si existe y si no, el example; agregar `heartbeat.jsonl` a `.gitignore` |
| `banco/escenarios/*.yaml` | ~30 con `/home/roquedb/…` | placeholder `{RAIZ}` (y `{HOME}` si hace falta) que `banco.py` reemplaza al cargar |
| `banco/calibracion_router_2026-10-08.jsonl` | contiene rutas de tu máquina | normalizar a rutas relativas, o moverlo a `banco/datos/` con nota de procedencia |
| `banco/escenarios/` | ~100 YAML, muchos de un solo uso (`exp42-aplicar` 1…5, `exp43-*`, `exp20b…e`) | `escenarios/` = la regresión vigente (`smoke`, `banco-*`, `tope-hitl-smoke`, …); `escenarios/historico/` = el resto |
| `banco/specs/` | ~60 specs de experimentos cerrados | `specs/historico/`; quedan arriba solo las de experimentos abiertos (exp/44, exp/45, exp/50) |
| `utils/call_llm.py` | lee `~/Documentos/00_IA/bmo/.env` **siempre** y sin avisar | setting `LEER_BMO_ENV` (default `0`); con `1`, el comportamiento de hoy. Documentarlo en `.env.example` (el test del PR 1 lo exige) |
| Tests con rutas `/home/roquedb` | `test_smoke.py:786` (texto DSML de ejemplo), `test_banco.py:47` | reemplazar por una ruta neutra; son literales de fixture |

**Pasos:** un commit por fila.

> ⚠ Antes de mergear la fila de `LEER_BMO_ENV`, poné en tu `.env` local los valores que hoy salen de `bmo/.env` (`LLM_MODEL`, `LLM_BASE_URL`, `LLM_MAX_TOKENS`, `LAYA_UNSURE_LOW`, `MAX_RETRIES`, según el contraste). Si no, tu chat cambia de conducta al día siguiente.

**Criterio de aceptación:**
- `grep -rln 'roquedb\|Documentos/00_IA' --exclude-dir=docs --exclude-dir=historico .` vacío (o solo el comentario de `LEER_BMO_ENV`).
- `python3 banco/banco.py banco/escenarios/smoke.yaml` corre igual que antes en tu máquina.
- Gate verde.

---

## PR 6 — Dos refactors de complejidad (solo en el camino de seguridad)

| Función | Complejidad (ruff C901) | Por qué esta sí |
|---|---|---|
| `modules/coding.run_command` | 18, y subió con exp/44 | es la frontera del shell; `registrar_riesgo` está repetido 3 veces en las ramas |
| `utils/fs_tools.search_files` | 27 | es la frontera de lectura (symlinks, raíces, tamaños) |

**`run_command`, forma objetivo:**

```python
def run_command(command):
    if not command or not str(command).strip():
        return "ERROR: comando vacío"
    command = str(command)
    nivel = _nivel(command)                      # clasificar + raíces + HITL_AUTO
    juicios = _observar_riesgo(command, nivel)   # exp/44, solo bandas humanas
    aprobado, motivo = _aprobar(command, nivel)  # auto / s/n / doble s/n
    _registrar(command, nivel, aprobado, juicios)  # aprobaciones + riesgo, UNA vez
    if not aprobado:
        return motivo
    return _ejecutar(command)                    # subprocess + timeout + clip
```

**`search_files`, forma objetivo:** `_candidatos(roots, pattern)` (recorrido, `sin_enlaces`, `SKIP_DIRS`) → `_coincidencias(path, query)` (tamaño, binario, líneas) → `_formatear(...)`.

**No tocar:** `evals.linter_traza` (23), `banco.correr` (17), `call_llm_agent_stream` (15). Funcionan, tienen tests y no son fronteras de seguridad.

**Criterio de aceptación:**
- `ruff check --select C901 --config 'lint.mccabe.max-complexity=12' modules/coding.py utils/fs_tools.py` limpio.
- Pasan sin modificar `test_policy.py`, `test_hitl.py`, `test_fs_tools.py` y los tests de symlinks.
- Una sola llamada a `registrar_riesgo` en `coding.py`.

**Aplicado (2026-10-16), con una corrección medida:**

`run_command` quedó en `_nivel` + `_observar_riesgo` + `_aprobar` + `_ejecutar`;
la aprobación y el riesgo se registran UNA vez por corrida (el riesgo, vía
`_registrar_riesgo`, que es la única llamada). `search_files` quedó en
`_candidatos` → `_coincidencias` → `_formatear_nombres`/`_formatear_contenido`.

El criterio, **tal como está escrito**, no lo cumplían solo esas dos
funciones: `edit_file` (13) y `list_files` (13) viven en esos mismos archivos
y también pasaban el tope de 12. Se bajaron sin cambiar conducta:
`edit_file` → `_error_no_aparece` (el mensaje diagnóstico, que es el 63% de
los fallos medidos) y `list_files` → `_listar` (el walk anidado, con el
conteo por retorno para no cambiar cuándo aparece el aviso de truncado).

**Cómo se verificó** (`salidas/pr6_diferencial.py`, no versionado): el módulo
de `HEAD` y el nuevo se cargan juntos y se corren sobre los MISMOS casos,
comparando salida **y** la secuencia de bookkeeping. 36 comparaciones, 0
diferencias: 12 escenarios de `search_files` (truncado, binarios, archivos
grandes, `path` a archivo, glob con barra, `**/`, rutas prohibidas), 8 de
`list_files` (depth 1/3/99, truncado, archivo, inexistente), el symlink que
apunta afuera, y 12 de `run_command` (auto / preguntar / doble, aprobado y
rechazado en cada paso, `HITL_AUTO=0`, con y sin observación de riesgo)
comparando el texto devuelto, lo impreso y el orden exacto de
`registrar_aprobacion`/`registrar_riesgo`. Suite completa: 518 passed.

El candado quedó **dentro del gate**: `calidad.sh` ahora tiene 3 palancas
(higiene → complejidad de las dos fronteras → pytest), así que la regresión
la frena el CI, no la memoria de quien edite.

---

## PR 7 — CI

`.github/workflows/calidad.yml`:

```yaml
name: calidad
on: [push, pull_request]
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install pocketflow openai pyyaml numpy requests pytest ruff==0.17.1
      - run: ./calidad.sh
        env:
          TRACE: "0"
          PREGUNTAS_LOG: "0"
          THREAD_PERSIST: "0"
```

y en `pyproject.toml`:

```toml
[project]
name = "deepseek-flow"
requires-python = ">=3.12"
```

**Notas:**
- **Sin dependencias pesadas en CI:** sin `laya`, `fastembed` ni `fastmcp`. Los tests marcados `laya`/`bmo`/`red` se omiten con su motivo, que es exactamente para lo que sirven los markers del PR 4.
- **Sin API key en CI:** el PR 1 y los tests actuales ya corren sin LLM. Si algún test pide clave, es un test mal aislado y se arregla ahí.

**Criterio de aceptación:** el workflow queda en verde en el primer push y el badge va en el README.

---

## Lo que NO se ordena (decidido)

| Tentación | Por qué no |
|---|---|
| Mover los flujos de la raíz (`juez.py`, `informe.py`, `supervisor.py`…) a `flows/` | Rompe todos los `from juez import …`, los `SUBCOMANDOS`, los escenarios del banco y `mcp_server`. Mucho costo para una ganancia estética. **Como mucho**, mover a `scripts/` las sondas y utilitarios sueltos (`sonda_*.py`, `carga_trazas.py`, `minar_errores.py`, `triaje_trazas.py`), que no importa nadie |
| Partir `nodes.py` (~460 líneas) | Una sola responsabilidad (el grafo del chat); partirlo esconde el flujo |
| Tocar los contratos de Laya | Congelados por sha1 a propósito: entrenamiento y producción leen lo mismo byte a byte |
| Unificar `TIMEOUT_S` | Mismo número, conceptos distintos (shell vs. visión) |
| Bajar la complejidad de todo lo que ruff marca | Solo las fronteras de seguridad (PR 6); el resto funciona y tiene tests |

## Checklist final

- [x] PR 1 — `test_docs_sin_deriva.py` en verde (b2f4530)
- [x] PR 2 — `estado.md` creado, informes archivados, `design.md` en 753 líneas (fc21e53)
- [x] PR 3 — sin cuerpos duplicados, rutas en `utils/rutas.py` (752cd2a)
- [x] PR 4 — `conftest.py` (8 copias → 1), `test_smoke.py` partido en 19 archivos temáticos (245 bloques movidos verbatim, mismos 518 tests, ningún archivo pasa de 664 líneas) y markers `laya`/`bmo`/`red`/`datos` (e2f291c + 6db163a)
- [x] PR 5 — sin rutas personales, `LEER_BMO_ENV=0` (029b994)
- [x] PR 6 — C901 ≤ 12 en `run_command`, `search_files`, `edit_file` y `list_files` (36 comparaciones diferenciales contra HEAD, 0 diferencias; sin tocar tests)
- [x] PR 7 — CI en verde: run 38913431915 (f642824)
