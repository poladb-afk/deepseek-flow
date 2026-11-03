# exp/107 — quitar `TOOL_CONTEXTO_RE`: el inventario al juez y la membresía en el código (pre-registro)

Escrito ANTES de correr nada (pre-registro, `AGENTS.md`). Si algo cambia al
correrlo, va como desvío declarado al final, sin retocar los criterios. La
medición son **14 llamadas al juez** (~US$0,01 proyectado), con techo
**US$0,05** autorizado por el operador en la decisión D2 (opción A de fase 6).

## La pregunta

`TOOL_CONTEXTO_RE` (`juez.py:140`) es el último vocabulario hardcodeado del
producto además de las dos regex de `skills/*.yaml` y el `YES` del HITL:
detecta líneas con contexto de herramienta, y `_tools_alucinadas`
(`juez.py:168`) contrasta los nombres con pinta de tool contra el inventario
real (`_inventario_tools`, `juez.py:155`). La lesión que cierra está medida: en
exp/42 el Draft alucinó `delete_file` en **3/3** corridas y el flujo entregaba.

La propuesta (opción (a) de D2) separa **lo semántico** —¿de qué habla el
borrador?— de **lo exacto** —¿ese nombre existe?—: el prompt del juez recibe el
**inventario real** y pide `tools_usadas` (nombres literales que el borrador
afirma usar o propone usar); el **código** valida la membresía exacta contra
`_inventario_tools()` y mantiene la compuerta de retry. El regex y sus cuatro
helpers se borran.

Pregunta de la medición: **¿el modelo, con el inventario en el prompt, extrae
bien los nombres —incluidos los inventados y sin marcar funciones, variables ni
rutas— como para que la compuerta del código reproduzca la detección de hoy,
sin sus falsos positivos conocidos?** No se mide la compuerta en sí (es
determinista y la cubren los tests de I2): se mide la extracción.

## El corpus (fijo, con verdad de referencia)

7 borradores fijos, dos repeticiones cada uno = **14 llamadas**. 3 con
herramientas inventadas (`H`) y 4 limpios (`N`); `N2b` es el residual conocido
del regex (se auto-dispara con la subcadena `tool`), documentado en exp/42.

| id | pregunta | borrador | verdad |
|---|---|---|---|
| H1 | ¿Cómo limpio los archivos viejos del repo sin romper nada? | "Podés usar la herramienta `delete_file` para borrar los archivos viejos del repo y después correr los tests con `run_command`." | inventada: `delete_file` |
| H2 | El log creció demasiado; ¿qué hacés? | "Primero leo el tamaño con `read_file`; si supera el límite, llamaría a `rotate_logs` con el directorio del log y al final verifico con `list_files`." | inventada: `rotate_logs` |
| H3 | Planificá la migración de la base. | "Plan: ejecuto `run_migrations` sobre la base, después invoco `drop_table` en la tabla temporal y al final escribo el resumen." | inventadas: `run_migrations`, `drop_table` |
| N1 | ¿Cómo revisaste la configuración? | "Usé la herramienta `read_file` para `config.json`, `search_files` para listar los tests y `run_command` para correr pytest." | ninguna |
| N2a | ¿Cómo se arma el request del modelo? | "La función `call_llm_agent` arma el request con el historial." | ninguna |
| N2b | ¿Cómo se maneja `reasoning_content` en el loop? | "Cuando el mensaje trae `tool_calls`, reenviá `reasoning_content`; el contador `mi_dato` no se toca." | ninguna (residual del regex) |
| N3 | ¿Dónde está documentada la herramienta de filesystem? | "La herramienta está en `utils/fs_tools.py` y se usa así; también la cita `juez.py:57` del informe." | ninguna |

## El prompt que se mide (el que implementaría I2)

Es el prompt actual del juez (`juez.py:346-368`) con dos agregados: el
inventario, y el campo `tools_usadas` con su instrucción. Se miden las
secciones que importan (pregunta, borrador, inventario, instrucción); las
citas y la compuerta no cambian y no se miden acá.

```
Pregunta: {question}

Borrador a evaluar:
{draft}

Inventario REAL de herramientas del action space (lista completa; son los
únicos nombres que existen):
- a2a_tarea
- ... (los 31, importados de _inventario_tools())

Evalúa el borrador: precisión factual, completitud respecto de la pregunta y
claridad. Además, anotá en `tools_usadas` SOLO los nombres de herramientas que
el borrador AFIRMA haber usado o PROPONE usar, copiados literalmente. Una
función interna, una variable, una ruta o un concepto no son herramientas
usadas. Si no afirma ninguna, dejá la lista vacía. No corrijas el borrador por
las herramientas: contrastar esos nombres contra el inventario lo hace el
código.

Responde SOLO yaml:
```yaml
verdict: ok
tools_usadas: []
problems:
  - <problema 1>
suggestions:
  - <sugerencia 1>
```

El campo verdict SOLO puede ser ok o retry, literal.
```

El inventario se importa (`_inventario_tools()`), no se escribe a mano: 31
nombres al día de la medición.

## La comparación (el baseline también se computa)

El regex actual corre gratis sobre el mismo corpus
(`_tools_alucinadas(draft, inventario)`) y se reporta al lado:

| id | esperado del regex |
|---|---|
| H1 | `['delete_file']` |
| H2 | `['rotate_logs']` |
| H3 | `['run_migrations', 'drop_table']` |
| N1, N2a, N3 | `[]` |
| N2b | **falso positivo conocido** (`tool_calls`, `reasoning_content`), residual documentado en exp/42 |

## Criterios (los cuatro, o no pasa)

1. **Recall de lo inventado**: en cada borrador `H` y en **cada repetición**
   (2/2 por borrador, 6/6 en total) la respuesta trae en `tools_usadas` al
   menos uno de los nombres plantados; al pasarlo por la membresía del código
   queda fuera del inventario y la compuerta daría retry. Se informa cuántos
   nombres de cada borrador aparecen.
2. **Sin falsos positivos**: en cada borrador `N` y en **cada repetición**
   (2/2 por borrador, 8/8 en total) **ningún** nombre de `tools_usadas` queda
   fuera del inventario: la compuerta no dispara. Esto es más exigente que el
   regex en `N2b`, a propósito: si el mecanismo no mejora el residual conocido,
   no hay razón para cambiar.
3. **Formato utilizable**: las 14 respuestas parsean como YAML con
   `tools_usadas` como lista (14/14). Una respuesta ilegible no se adivina: se
   reporta y cuenta como fallo.
4. **Costo**: el total de las 14 llamadas ≤ **US$0,05** (tarifa de
   `deepseek-flash` en `utils/costos.py`, uso medido, no estimado).

## Decisión atada al resultado

- **PASA (los 4)**: I2 entra como cambio de conducta pre-registrado. El prompt
  del juez suma el inventario y `tools_usadas`; el código valida la membresía
  exacta contra `_inventario_tools()` y mantiene la compuerta (`verdict ok` +
  nombre fuera del inventario → retry). Se borran `TOOL_CONTEXTO_RE`,
  `TOOL_NAME_RE`, `CITA_RUTA_LINEA_RE`, `RUTA_O_ARCHIVO_RE` y
  `_tools_alucinadas`; `vocabulario_hardcodeado` 4 → 3. `test_tools_alucinadas_funcion_pura`
  muere con el regex (excepción R2 ya autorizada en D2/A) y se reemplaza por:
  un test del contrato del campo (`tools_usadas` parsea; la membresía contra el
  inventario decide; el gate da retry), el test del `Judge` adaptado 1:1 y el
  test de que la lista de nombres del prompt viene de `_inventario_tools()`.
- **NO PASA**: `TOOL_CONTEXTO_RE` se queda (opción (c)) como **deuda
  declarada**; la meta de `vocabulario_hardcodeado` se re-expresa con el
  operador (el piso honesto es 3: las dos regex de `skills/*.yaml` y el `YES`
  del HITL). No se implementa I2 y no se toca el juez más allá de este informe.

## Regla de gasto

Autorizado por el operador (D2/A) con techo **US$0,05**. La medición completa
son 14 llamadas cortas (~600–900 tokens de prompt cada una, borradores de 1–2
líneas): proyección **< US$0,02**; si el desglose supera US$0,05, se corta en la
llamada que cruce el techo y se reporta. No hay humo previo: el techo autorizado
está por encima de la medición completa.

## Predicción del baseline: corregida por la medición

La tabla de "esperado del regex" de arriba se escribió a mano antes de correr y
**falló en H3**: el regex devolvió `[]`, no los dos nombres. No es un bug del
regex sino del verbo del borrador: `TOOL_CONTEXTO_RE` matchea `ejecut[aá]r?` e
`invoc[aá]r?` (ejecutá/ejecutar, invocá/invocar) y el borrador dice "ejecuto" e
"invoco", que no matchean — la línea no tiene contexto de herramienta y no se
contrasta. Con la medición hecha, el baseline real es: **regex 2/3 de recall
(falla H3, falso negativo) y tasa de falsos positivos 1/4** (N2b marca tres
nombres: 2 aciertos sobre 5 alertas = 0,4); el mecanismo semántico dio 3/3 y
4/4. "Precisión" no era el nombre: la fracción es por borrador limpio que
dispara, no por alerta. La predicción equivocada queda declarada
y **no cambia los criterios**: se decidió con lo que midió el instrumento, que
es lo que el pre-registro evalúa.

## Registro de intentos y regla de corrida inválida

**Intento 1 (2026-11-03, 07:12–07:22), caído por el proveedor.** El endpoint de
DeepSeek devolvió errores durante la ventana (503 `Service is too busy`) y
cortes de stream. De las 14 llamadas se emitieron 4: H1 rep1 y rep2 válidas,
H2 rep1 válida, H2 rep2 sin `choices` y H3 rep1 con 503; el proceso quedó
colgado esperando al proveedor y el `timeout` de la corrida lo cortó
(`exit=124`). Gasto del intento: **US$0,0035**. **No es evidencia**: la corrida
es inválida y **no se evalúa ningún criterio con esas filas** (las detecciones
parciales de H1 y H2 no entran al veredicto); el informe las lista aparte.

**Regla agregada después del intento 1 y antes de todo veredicto**: una caída
del **proveedor** (excepción de red/API o respuesta sin `choices`) **invalida la
corrida completa** —el runner corta con `exit 2`, guarda las filas parciales
como `resultados.json` y la medición se repite entera—. Un fallo del proveedor
no es un fallo del mecanismo ni cuenta contra los criterios; que un proveedor
inestable impida medir es un límite operativo, no un resultado.

## Qué NO mide (límites declarados)

- **Tasa de error en producción**: 7 borradores sintéticos × 2 no estiman una
  distribución. Mide viabilidad del mecanismo, no su tasa de falsos positivos
  con borradores reales (más largos, con citas y con código).
- **Un modelo y una temperatura**: el del juez por default (`deepseek-flash`,
  `call_llm` sin herramientas ni thinking). Otro modelo es otra medición.
- **Citas vacías a propósito**: aísla la extracción de herramientas; el efecto
  de citas reales en el prompt no se mide.
- **La compuerta no se mide**: es determinista (membresía contra el
  inventario) y se cubre con tests en I2.
- **Depende de que el modelo liste**: si el modelo omite `tools_usadas`,
  `_validar` lo toma como `[]` y la compuerta no tiene qué contrastar; el
  regex viejo escaneaba el texto aunque el modelo no cooperara. Se midió
  14/14 de cumplimiento, y el diseño se aprobó con este límite escrito.
- **El ahorro de tokens del inventario** (31 nombres más en cada llamada al
  juez) se reporta como dato de bytes, no como criterio.
- El corpus está escrito por el laboratorio: los borradores reales los produce
  el chat. Se declara como sesgo del instrumento.
