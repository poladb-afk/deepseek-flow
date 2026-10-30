# Pre-registro — fase 5a de elegancia: la política de comandos como datos (S10)

**Estado:** pre-registrado el 2026-10-30 (X107), ANTES de tocar `utils/policy.py`.
Sin cambio de conducta: el criterio es **0 diferencias**. No se retoca después
de ver resultados (un cambio va como desvío declarado en la bitácora).

## Hipótesis

Las listas de `utils/policy.py` son DATOS de la política, no lógica: qué
prefijos son solo-lectura, cuáles preguntan, cuáles piden doble
confirmación, qué flags vuelven escritor a un lector, qué envoltorios se
pelan y qué texto ve el humano en el s/n. Pasarlas a un archivo versionado
deja en el código solo el mecanismo (tokenizar, separar segmentos,
normalizar envoltorios, comparar), sin cambiar NINGUNA decisión.

Hallazgo previo, medido al escribir esto: `_WHITELIST_PREFIJOS` y `_LECTURA`
son los MISMOS 20 prefijos escritos dos veces (uno decide, el otro explica),
y `_NEGRA_PREGUNTAR` + `_NEGRA_DOBLE` están todos repetidos en
`_EXPLICACIONES`. Como datos, cada prefijo es UNA entrada con su nivel y su
explicación: la duplicación desaparece por construcción.

## Qué pasa a datos

`utils/politica_comandos.json` (stdlib, sin dependencia nueva; producto, no
laboratorio):

| hoy en código | en el archivo |
|---|---|
| `_WHITELIST_PREFIJOS` + `_LECTURA` | `prefijos[]` con `nivel: auto` + `explicacion` |
| `_NEGRA_PREGUNTAR`, `_NEGRA_DOBLE` + su parte de `_EXPLICACIONES` | `prefijos[]` con `nivel: preguntar` / `confirmar_doble` + `explicacion` |
| el resto de `_EXPLICACIONES` (mv, cp, mkdir, touch) | `prefijos[]` sin `nivel` (default preguntar), solo `explicacion` |
| `_FLAGS_PELIGROSOS` | `flags_peligrosos{base: [flags]}` |
| `_BASES_MODULO` | `bases_modulo[]` |
| `_ENVOLTORIOS`, `_OPCIONES_CON_VALOR`, `_GIT_GLOBAL_CON_VALOR` | `envoltorios{nombre: [opciones con valor]}`, `git_globales_con_valor[]` |

**Se queda en código** (es sintaxis del shell, el mecanismo, no vocabulario):
`_PELIGRO_SHELL`, `_EXPANSION`, `_COMILLAS`, `_SEPARADORES`,
`_DESCARTE_DEVNULL`, el orden de evaluación y las normalizaciones de `rm`
y `git`. Los textos de las explicaciones genéricas (las que no dependen de un
prefijo) también.

**Falla cerrada**: si el archivo falta o no valida (esquema mínimo: tipos,
niveles conocidos, prefijos no vacíos, sin prefijo repetido), `utils.policy`
levanta al importar — el chat no arranca. Nunca "todo auto" ni "todo
preguntar" en silencio: una lista negra vacía bajaría `rm -rf` de doble a
simple confirmación. Sin setting para cambiar la ruta (`settings_leidos` no
sube; R10).

## Instrumento

1. **La foto real** (`banco/probes/comandos_reales.py`, read-only, sin LLM):
   los comandos de `run_command` de los checkpoints (`salidas/**/threads/`,
   con los `auto` incluidos) y del log de riesgo (`salidas/riesgo.jsonl`, sin
   los que pueden venir truncados a 200). Deduplicados, rutas a
   `{RAIZ}`/`{HOME}`, sin posibles secretos. El operador corre
   `--fixture`, revisa a mano `banco/fixtures/policy_comandos.jsonl` y lo
   commitea ANTES de que se escriba el código de la 5a. Cada fila trae
   `comando`, `nivel` y `explicacion` de la política de HOY.
2. **Un caso por entrada** (sintético, derivado mecánicamente de las listas
   de HOY y congelado en el mismo commit que la foto): por cada prefijo, el
   prefijo solo; por cada flag peligroso, `base flag x`, `base flag=x` y su
   grupo corto si aplica; por cada envoltorio, `envoltorio [opción valor]
   rm -rf x`. Así ninguna entrada queda sin ejercitar aunque el tráfico real
   no la use.
3. **Los tests existentes**: `test_policy_bypass.py` y `test_policy.py` sin
   tocar una línea.

## Criterios (todos)

1. **Equivalencia**: un test nuevo pasa cada comando de la foto real y de los
   casos por entrada por `clasificar` y `explicar` del árbol de la 5a.
   **0 diferencias** en nivel y en texto.
2. `test_policy_bypass.py` y `test_policy.py` **idénticos** (byte a byte) y
   en verde.
3. **Falla cerrada** probada: archivo ausente, JSON roto, nivel desconocido y
   prefijo repetido → `ImportError`/`ValueError` al importar, en un test.
4. `ruff`, C901 en las fronteras (`modules/coding.py`, `utils/fs_tools.py`)
   y el ratchet sin empeorar.

Si 1 da una sola diferencia, la 5a no entra: se lista y se decide caso por
caso (la diferencia es un bug de la migración, no de la política).

## Efecto esperado (no es criterio)

Ninguna métrica de ratchet se mueve por sí sola: las listas de la política
no cuentan como `vocabulario_hardcodeado` (el ratchet mide palabras en
español y regex sin distinción de mayúsculas; los prefijos de shell no lo
son). Corrección de la propuesta de X106: ahí se dijo que la 5a bajaba ese
ratchet — es falso. Los 3 que quedan son `juez.TOOL_CONTEXTO_RE`, las
palabras de continuación de `GetQuestion` y el `YES` de `aprobaciones`; la
meta ≤ 2 se discute en la 5b/fase 6, no acá. Lo que la 5a sí cambia:
`utils/policy.py` ~463 → ~300 líneas y la duplicación whitelist/lectura
desaparece.

## Fuera de alcance

Cambiar cualquier decisión (agregar o sacar un prefijo, endurecer un flag).
Eso es otro PR, con su test de bypass, después de la 5a (R7).

## Desvío declarado (X108a, antes del código)

El instrumento 2 ("un caso por entrada, congelado en el mismo commit que la
foto") no llegó con la foto: la sonda de X107 no lo generaba. X108a le suma
`--casos` a la sonda; `banco/fixtures/policy_casos_entrada.jsonl` (410 casos)
se genera sobre el árbol de ANTES de la migración y va en su commit, antes
del código. Criterios intactos.

## Resultado (X108b; la foto real la confirma el operador)

| criterio | medido |
|---|---|
| 1. 0 diferencias | casos por entrada: **0/410**. Foto real (445): el test la lee si está; en el árbol del autor no está y se saltea — la corrida que cuenta es la del operador. Extra, no pre-registrado: 200.000 comandos aleatorios (tokens de las listas + separadores + sintaxis de shell), política vieja vs nueva → **0** en `clasificar`, `explicar` e `irreversible` |
| 2. tests de policy idénticos | md5 de `test_policy.py` y `test_policy_bypass.py` iguales a X107; verdes |
| 3. falla cerrada | 11 casos: ausente, JSON roto, raíz no objeto, nivel desconocido, repetido, tapado, sin `confirmar_doble`, sin explicación, token con espacio, clave faltante, flag sin guion |
| 4. ruff / C901 / ratchet | verdes; C901 ≤ 12 también en `utils/policy.py`; ninguna métrica empeora (`tests_definidos` +15) |

**Las listas derivadas son iguales a las de antes**, comparadas una por una
(whitelist, negras, `IRREVERSIBLES` en el mismo orden, flags, envoltorios).
Solo cambia el orden de `_EXPLICACIONES`, que no decide: el validador prohíbe
que un prefijo tape a otro, y es el único caso en que el orden de `explicar`
importaría.

**Efecto esperado, no cumplido**: `policy.py` 463 → 425, no ~300. Salieron
las listas (−100 líneas) y entró la validación de falla cerrada (+60); los
datos ocupan 64 líneas.
