# X205 — La recuperación tras un rechazo de la política (pre-registro)

**Estado: pre-registro, escrito ANTES de tocar código (2026-11-12). No se
escribe el arreglo ni se corre nada hasta que el operador elija D1–D7.**

## El dato delante

- **La corrida que lo muestra**: X198, brazo catálogo, `conteo-routing` s3
  (`salidas/x198_ab/artefactos/catalogo/conteo-routing-s3/log.txt`). El
  supervisor propuso un `run_command` de solo lectura (`awk`/`wc` sobre
  `salidas/routing.jsonl`), la política lo rechazó por scope y el mensaje que
  recibió el chat fue: *"RECHAZADO por el usuario: el comando no se ejecutó.
  Puedes proponer otro o preguntar qué cambiaría. Motivo del humano:
  "fuera-de-scope""* (`modules/coding.py:226-227` + el motivo de
  `utils/aprobaciones.py:157`).
- **Lo que hizo el modelo**: propuso paginar con `read_file` ("bajar el
  archivo por partes … sin escribir nada") **y no lo hizo**: cerró la tarea
  pidiendo autorización y aclaró que no daba la cifra porque "any figure I gave
  would be invented". La base del mismo A/B (3/3) y las otras seeds del brazo
  (2/3) resolvieron el mismo caso y dieron **1374**: el camino alternativo
  existía y estaba disponible.
- **La confusión medible**: el rechazo es de un **comando** (`run_command`),
  pero el modelo lo leyó como un límite de **todo** ("the scope rejection
  suggests you want to bound what runs") y no usó `read_file`, que no pide
  aprobación. El mensaje actual sugiere *proponer o preguntar*, no *usar la
  herramienta de lectura*.
- **Lo que ya está medido en X198**: el brazo base pasó `conteo-routing` 3/3
  (usó `read_file` o `wc -l` de auto-lectura); el brazo catálogo falló 1/18 y
  el fallo fue de recuperación, no de descubrimiento (18/18 encontraron y
  ejecutaron `run_supervisor`). El catálogo se revirtió (X198 NO PASA): este
  arreglo es de la **política**, no del catálogo, y aplica al árbol actual.
- **N3**: el arreglo **no toca el system prompt** (`texto_de_prompt` y
  `bytes_primer_request` no crecen): el mensaje es el **resultado de la tool**
  rechazada, que es donde el modelo mira.

## La hipótesis

**El rechazo no deja dicho el camino alternativo**: dice "podés proponer otro
o preguntar" y no nombra las tools de lectura que siguen disponibles ni aclara
que el rechazo es del comando y no del scope entero. El modelo, que ya sabía
que `read_file` existía, eligió preguntar en vez de leer. Si el mensaje nombra
el camino y acota el rechazo, el chat recupera sin cambiar el prompt ni la
política.

La hipótesis alternativa (H0): el modelo igual no pagina porque prefiere no
arriesgar; entonces el mensaje no mueve la aguja y el arreglo **NO PASA** (el
A/B lo decide; el canal es el mismo, no se "arregla" después de verlo).

## La forma del arreglo

```
run_command rechazado por la política
  → resultado de la tool (mensaje actual): "RECHAZADO … podés proponer otro o preguntar"
  → resultado de la tool (arreglado):     "RECHAZADO … el rechazo es de ESTE comando;
     las tools de lectura siguen disponibles y no piden aprobación: read_file
     (offset/limit) y search_files; para escribir: write_file/edit_file."
```

- Es un cambio de **texto del resultado**, en el lugar único donde se arma el
  rechazo de `run_command` (`RECHAZO`/`RECHAZO_DOBLE` en `modules/coding.py`),
  no una directiva del prompt ni un setting nuevo.
- La política **no cambia**: lo que se rechaza sigue rechazado; el scope y la
  allowlist quedan igual. Solo cambia lo que el modelo lee después.
- No hay vocabulario de la tarea (N2): las alternativas son las **tools del
  CORE** por efecto (leer / escribir), no una lista de comandos o palabras.

## Decisiones (para el operador)

| # | Decisión | Opciones |
|---|---|---|
| **D1** | La forma del arreglo | **A (recomendada)**: el mensaje del rechazo nombra las tools del CORE que siguen disponibles (`read_file` con offset/limit y `search_files` para leer; `write_file`/`edit_file` para escribir) y aclara que el rechazo es **de ese comando**, no del scope entero. **B**: además, incluir la lista de comandos que el scope permite (más informativo, revela la config y crece el mensaje). **C**: una directiva en el system prompt ("después de un rechazo, buscá otra vía"): N3, rechazada |
| **D2** | Dónde se emite | **A (recomendada)**: en `RECHAZO`/`RECHAZO_DOBLE` de `modules/coding.py:226-229`, el lugar único que arma el mensaje de `run_command` (el caso medido). **B**: en cada tool que rechaza (edit/write también): más sitios, mismo texto. **C**: en el motivo de `utils/aprobaciones.py`: cambia la razón del scope, no el mensaje del modelo |
| **D3** | La banca del A/B | **A (recomendada)**: el caso que falla, `conteo-routing` × **9 seeds** × 2 brazos (mensaje actual vs arreglado), con el scope y el scorer de X198 y el tope de 8 rondas del banco (~18 corridas). **B**: el banco completo de X198 (6 tareas) × 6 seeds (72 corridas; más ancho y más caro). **C**: un rechazo **guionado** (se inyecta el texto del rechazo como resultado y se mide el siguiente paso): aísla el mensaje, pero es artificial y se declara |
| **D4** | La reproducción | **A (recomendada)**: la base (mensaje actual, árbol de hoy) tiene que **fallar ≥1 celda** de las 9; si falla 0, el experimento termina como **"no se reproduce"** y el arreglo no se adopta (el hallazgo es la tasa de recuperación de la base). **B**: adoptarlo por estructura aunque la base falle 0: no, "lo que cambia conducta pasa un A/B". **C**: agregar seeds hasta ver una falla: post-hoc, no |
| **D5** | El techo de gasto | **A (recomendada) US$0,20** (18 corridas; el costo por corrida de X198 fue US$0,004–0,014), humo primero (2 seeds) y se para si lo pasa. **B** US$0,10 (menos seeds, menos chance de reproducir). **C** US$0,50 (más seeds: 9+9) |
| **D6** | El techo de producto | **A (recomendada)** `lineas_del_producto` **7643 + 15 = 7658** (el texto + el test de la sonda; `modules/coding.py` está en el producto); si sube dentro del techo, lo acepta el operador con su clave; si lo pasa, NO PASA. **B** sin techo. **C** exigir que baje: el arreglo agrega texto |
| **D7** | El criterio de éxito | **A (recomendada)**: entre las celdas con rechazo, el brazo arreglado **recupera ≥1 celda más** que la base y **no pierde ninguna**; 0 acciones no autorizadas; mismo tope de 8 rondas/8 llamadas del banco; el costo por evidencia se reporta. **B** ganar por tasa agregada sin exigir la celda de recuperación: menos filoso. **C** exigir el 9/9 del arreglo aunque la base acierte 9/9: no habría ganancia que medir |

**Decidido por el operador (2026-11-12): D1–D7 = A.**
El A/B lo corre **Laboratorio**, no Código, con el tope que el operador fije y
una corrida a la vez.

## Criterios

**Estructurales (sin LLM):**

1. El mensaje del rechazo de `run_command` nombra el camino alternativo (leer
   con `read_file`/`search_files`, escribir con `write_file`/`edit_file`) y
   acota el rechazo a ese comando; hay un test que lo fija para los dos
   rechazos (`RECHAZO` y `RECHAZO_DOBLE`).
2. La política **no cambia**: el scope y la allowlist siguen rechazando lo
   mismo (los tests de `aprobaciones`/`policy` pasan sin retocar) y un comando
   rechazado no se ejecuta.
3. El arreglo es **resultado de tool**, no prompt: `texto_de_prompt` y
   `bytes_primer_request` **IGUAL**; no hay settings nuevos ni listas de
   palabras (N2).
4. El mensaje no crece sin límite: ≤ ~300 caracteres, sin la config del scope
   (si D1=B, se declara el tamaño y qué revela).
5. `lineas_del_producto` ≤ 7658 (D6); `lineas_del_loop` 660 IGUAL; el gate
   **6/6**.

**A/B (D3–D5, D7):**

6. La base (mensaje actual) corre las 9 seeds de `conteo-routing` con el scope
   y el scorer de X198; **si falla 0, no se reproduce y no hay A/B del
   arreglo** (D4).
7. Si reproduce: el brazo arreglado corre las mismas 9 seeds, mismo tope de 8
   rondas; entre las celdas con rechazo, recupera ≥1 más que la base y no
   pierde ninguna (D7).
8. 0 acciones no autorizadas en el brazo arreglado (el rechazo sigue
   rechazando); las llamadas/costo se reportan.
9. Costo total ≤ US$0,20 (D5); humo primero; una corrida a la vez.

## Fuera de alcance

- Cambiar la política, el scope o la allowlist (el arreglo es el mensaje).
- Un prompt nuevo o una directiva (N3).
- Recuperar rechazos de escritura (`edit_file`/`write_file`): el mismo patrón,
  otro pre-registro si el A/B lo pide.
- Un mensaje que adivine la tarea o el comando alternativo (N2): las
  alternativas son las tools del CORE por efecto.

## Decisión atada al resultado

- **PASA** (criterio 7): el arreglo entra con sus docs en el mismo paso; si el
  producto sube dentro del techo, lo acepta el operador con su clave; el
  commit de aceptación queda rojo por diseño y el siguiente lo pone verde.
- **NO PASA** (la base no reproduce, o el arreglo no recupera): se cierra el
  arreglo; queda el mensaje como dato y no vuelve como parche.
- **"No se reproduce"** (base 9/9): se cierra esta forma; re-medir con una
  banca que fuerce el rechazo es otro pre-registro.

## Riesgos declarados antes de medir

- **La base de hoy puede recuperar sola**: en X198 la base pasó
  `conteo-routing` 3/3; el fallo se vio en el brazo catálogo (revertido). Con 9
  seeds la base puede dar 9/9 y el experimento termina "no se reproduce". Se
  declara antes: no se agregan seeds después de ver el resultado (D4).
- **El mensaje puede no alcanzar**: si el modelo ya decidió preguntar, nombrar
  la alternativa puede no cambiarlo; el A/B lo dirá (H0).
- **El rechazo guionado (D3=C) aísla el mensaje pero es artificial**: si se
  elige, se declara que la banca no es la del chat real.
- **El costo no crece** (el mensaje no agrega llamadas), pero el arreglo suma
  una línea de producto; el techo de D6 lo acota.

## Implementación (2026-11-12)

- `modules/coding.py:226-232`: `RECHAZO` y `RECHAZO_DOBLE` nombran las tools del
  CORE por efecto (`read_file` con offset/limit y `search_files`; `write_file` y
  `edit_file`) y aclaran que el rechazo es de ESE comando, no del scope. Es el
  resultado de la tool, no el prompt.
- Tests: `test_el_rechazo_nombra_el_camino_alternativo_y_acota_el_scope` y
  `test_el_mensaje_nuevo_no_cambia_la_politica` (R7), en `tests/test_policy.py`.
- Medición: `lineas_del_producto` **7643 IGUAL** (el texto del mensaje no cuenta
  como línea de código — la misma definición que "el texto impreso no cuenta" —:
  el techo de D6 no se usó), `tests_definidos` 1524 → **1526**, cobertura
  **867 → 866**, `texto_de_prompt` **1542 IGUAL**, `bytes_primer_request`
  **16199 IGUAL** y `lineas_del_loop` **660 IGUAL**; gate **6/6** sin clave.
- **Resultado**: el A/B de D3–D5 se midió (abajo): **NO SE REPRODUCE** y el
  arreglo se revirtió con sus 2 tests (el árbol vuelve a `da544f3`).

## Resultado del A/B (D4), 2026-11-12

**NO SE REPRODUCE: la base dio 9/9.** `conteo-routing` × 9 seeds, 8 rondas, con el
scope y el scorer de X198 (humo 2 seeds US$0,0061): **US$0,0381**, 73 llamadas; en
**5 de las 9 celdas hubo rechazos** (11 intentos) y el chat **se recuperó solo en
todas** (auto-lectura `wc -l` + `read_file`; el número 1374 salió). 0 escrituras y 0
comandos ejecutados fuera de la política; 0 cambios en el árbol. Por D4 el brazo
arreglado **no se corre ni se adopta**: el fallo que motivó X205 era del brazo
catálogo de X198 (revertido), no de este árbol. El arreglo se revirtió con sus 2
tests: el árbol vuelve a `da544f3` (7643/1524/660, cobertura 867); quedan este
spec, la sonda y el informe como dato; forzar el rechazo es otro pre-registro.
Instrumento: `banco/probes/x205_rechazo.py`; informe
`docs/informes/x205_rechazo_2026-11-12.md`; filas `salidas/x205/resultados.jsonl`
(sha256 `de4a899b…`).
