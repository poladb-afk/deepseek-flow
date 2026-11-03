# exp/107 — el inventario al juez y la membresía en el código contra `TOOL_CONTEXTO_RE` (2026-11-03)

**Estado: corrido y dictaminado por el criterio pre-registrado — PASA los cuatro
criterios. Hito X135.** La decisión atada (I2: mover la extracción al modelo y
dejar la membresía en el código) queda habilitada; la implementación es I2 de
fase 6.
Pre-registro: `banco/specs/exp107_tools_alucinadas.md`. Instrumento:
`banco/probes/exp107.py`. Filas crudas: `salidas/exp107/resultados.json` y los
dos logs (`intento1.log` inválido por el proveedor, `intento2.log` válido).

## La pregunta

`TOOL_CONTEXTO_RE` (`juez.py:140`) es el último vocabulario hardcodeado del
producto (con las dos regex de `skills/*.yaml` y el `YES` del HITL): marca
líneas con contexto de herramienta y `_tools_alucinadas` (`juez.py:168`)
contrasta los nombres contra el inventario real (`_inventario_tools`,
`juez.py:155`). La lesión que cierra está medida: exp/42, el Draft alucinó
`delete_file` en 3/3 y el flujo entregaba.

La opción (a) de D2 separa lo semántico (¿de qué habla el borrador?) de lo
exacto (¿ese nombre existe?): el prompt del juez recibe el inventario real y
pide `tools_usadas`; el código valida la membresía exacta contra
`_inventario_tools()` y mantiene la compuerta de retry. El regex y sus cuatro
helpers se borran. **La medición pregunta si el modelo extrae bien los nombres
—incluidos los inventados y sin marcar funciones, variables ni rutas— como para
que la compuerta del código reproduzca la detección de hoy sin sus falsos
positivos conocidos.** La compuerta en sí no se mide: es determinista y la
cubren los tests de I2.

## El corpus y el prompt

7 borradores fijos × 2 repeticiones = 14 llamadas; 3 con herramientas
inventadas y 4 limpios (N2b es el residual conocido del regex, que se
auto-dispara con la subcadena `tool`). El texto completo está en el
pre-registro; el prompt es el del juez más el inventario importado
(`_inventario_tools()`, 31 nombres) y la instrucción de `tools_usadas`.

| id | qué mide | verdad |
|---|---|---|
| H1 | la lesión medida en exp/42 | inventada: `delete_file` |
| H2 | generalización a otro nombre en prosa | inventada: `rotate_logs` |
| H3 | plan con dos verbos de uso | inventadas: `run_migrations`, `drop_table` |
| N1 | nombres reales en contexto de herramienta | ninguna |
| N2a | función interna (exp/42) | ninguna |
| N2b | `tool_calls`/`reasoning_content` (residual del regex) | ninguna |
| N3 | ruta + cita en contexto de herramienta (exp/42) | ninguna |

## Resultados (crudo, `salidas/exp107/resultados.json`)

| caso | rep | lo que marcó el regex | `tools_usadas` del modelo | fuera del inventario | detectada |
|---|---|---|---|---|---|
| H1 | 1 | ['delete_file'] | ['delete_file', 'run_command'] | ['delete_file'] | sí |
| H1 | 2 | ['delete_file'] | ['delete_file', 'run_command'] | ['delete_file'] | sí |
| H2 | 1 | ['rotate_logs'] | ['read_file', 'rotate_logs', 'list_files'] | ['rotate_logs'] | sí |
| H2 | 2 | ['rotate_logs'] | ['read_file', 'rotate_logs', 'list_files'] | ['rotate_logs'] | sí |
| H3 | 1 | [] | ['run_migrations', 'drop_table'] | ['run_migrations', 'drop_table'] | sí |
| H3 | 2 | [] | ['run_migrations', 'drop_table'] | ['run_migrations', 'drop_table'] | sí |
| N1 | 1 | [] | ['read_file', 'search_files', 'run_command'] | [] | no |
| N1 | 2 | [] | ['read_file', 'search_files', 'run_command'] | [] | no |
| N2a | 1 | [] | [] | [] | no |
| N2a | 2 | [] | [] | [] | no |
| N2b | 1 | ['tool_calls', 'reasoning_content', 'mi_dato'] | [] | [] | no |
| N2b | 2 | ['tool_calls', 'reasoning_content', 'mi_dato'] | [] | [] | no |
| N3 | 1 | [] | [] | [] | no |
| N3 | 2 | [] | [] | [] | no |

**Criterios (los cuatro del pre-registro):**

| criterio | resultado |
|---|---|
| 1 recall de lo inventado (6/6) | ✅ |
| 2 sin falsos positivos (8/8) | ✅ |
| 3 formato (14/14) | ✅ |
| 4 costo (≤ US$0,05) | ✅ |

**El baseline del regex, medido en el mismo corpus: recall 2/3 y tasa de
falsos positivos 1/4** (2 aciertos sobre 5 alertas = 0,4; dispara en 1 de los
4 borradores limpios, N2b). Recall: detecta `delete_file` (H1) y `rotate_logs` (H2), pero en
H3 devuelve `[]` —`TOOL_CONTEXTO_RE` matchea "ejecutá/ejecutar" e
"invocá/invocar" y el borrador dice "ejecuto"/"invoco": la línea no tiene
contexto y no se contrasta—. Precisión: en N2b marca `tool_calls`,
`reasoning_content` y `mi_dato` (residual documentado en exp/42); el mecanismo
semántico no marca ninguno. En este corpus el mecanismo **mejora las dos
puntas**: no hay regresión que comprar.

## Costo y duración

- Intento 2 (válido): **14 llamadas, US$0,0144**, prompt medio 1.366 bytes
  (el inventario de 31 nombres suma ~1 KB por llamada). Modelo del juez por
  default (`deepseek-flash`), `call_llm` sin tools ni thinking.
- Intento 1 (07:12, inválido por el proveedor): 4 llamadas emitidas,
  **US$0,0035**; 503 `Service is too busy`, una respuesta sin `choices`, y el
  proceso colgado hasta que el `timeout` lo cortó. **No entra al veredicto.**
- Total de la medición: **US$0,0179** de los US$0,05 autorizados.

## Veredicto y decisión

**PASA.** I2 queda habilitado con el prompt exacto del pre-registro: el
inventario en el prompt, `tools_usadas`, la membresía exacta en el código y la
compuerta de retry intacta; se borran `TOOL_CONTEXTO_RE`, `TOOL_NAME_RE`,
`CITA_RUTA_LINEA_RE`, `RUTA_O_ARCHIVO_RE` y `_tools_alucinadas`, y
`vocabulario_hardcodeado` pasa de 4 a 3. `test_tools_alucinadas_funcion_pura`
muere con el regex (excepción R2 autorizada por la opción A del operador) y se
reemplaza por los tests del contrato nuevo. Si I2 cambia el prompt medido, es
desvío declarado.

## Límites y desvíos

- **Límite**: 7 borradores sintéticos × 2 no estiman una tasa de producción; un
  modelo y una temperatura; citas vacías a propósito (aísla la extracción); la
  compuerta determinista no se mide acá.
- **Depende de que el modelo liste**: si el modelo omite `tools_usadas`,
  `_validar` lo toma como `[]` y la compuerta no tiene qué contrastar; el regex
  viejo escaneaba el texto aunque el modelo no cooperara. Se midió 14/14 de
  cumplimiento; el diseño se aprobó con este límite escrito.
- **Desvío 1 (predicción, no criterio)**: la tabla de "esperado del regex" del
  pre-registro falló en H3 —se esperaba que detectara y no detecta—; corregida
  en el spec con el motivo (verbos "ejecuto"/"invoco" no matchean el regex) y
  sin tocar los criterios.
- **Desvío 2 (regla de corrida)**: tras el intento 1 caído por el proveedor se
  agregó al spec que una caída del proveedor **invalida la corrida completa**
  (exit 2, se repite entera) en vez de contarse como fallo del mecanismo. Se
  agregó antes de ver un veredicto y no cambia ningún criterio.

## Cómo se reproduce

```bash
python3 banco/probes/exp107.py     # 14 llamadas; escribe salidas/exp107/
```

El runner corta en la llamada que cruce US$0,05 y deja `resultados.json` con
las filas; el resumen y el veredicto se imprimen y quedan en
`salidas/exp107/resumen.md`. La columna del baseline se midió con el regex
**pre-I2**: después de I2 el producto ya no lo tiene, y el probe conserva una
copia congelada del regex viejo (marcada "baseline congelado, no producto")
para poder re-medir esa columna sin tocar el producto.

