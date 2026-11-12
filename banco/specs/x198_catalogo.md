# X198 — El catálogo: tools mínimas del CORE + catálogo + uso (pre-registro)

**Estado: pre-registro, escrito ANTES de tocar el producto (2026-11-12).
No se escribe código hasta que el operador elija las decisiones D1–D7.**

## El dato delante

- **30 tools en el request del chat** (medido acá, 2026-11-12): las **3** del
  CORE (`utils/fs_tools.py:TOOLS`) más **27** de los módulos
  (`nodes.py:153`: `MODULE_TOOLS, MODULE_IMPLS = discover()`).
- **`bytes_primer_request` = 16199** (baseline del ratchet, X124): 1270 de
  `utils/fs_tools.py:TOOLS`, ~10,6k de los 27 `TOOLS` de módulos y ~2,3k del
  system prompt y las directivas de `main.py` (detalle en
  `ratchets/baseline.json`). Es la métrica más pesada después del loop.
- **P1**: "un loop, pocas tools en el CORE … Prefijo estable: nada variable en
  el system prompt ni tools en caliente" (`docs/principios.md:52`).
- **X173**: el proveedor **cachea el prefijo**; el set fijo tiene que ser
  estable entre preguntas (`docs/arquitectura.md:137-138`).
- **X197b**: el despacho único es `run_tool_call`; una arista que no pasa por
  ahí se saltea la política (el veto PRE de research). `usar` no puede repetir
  ese agujero.
- **exp/103 y X129**: una tool en el menú que el modelo no adopta no cambia la
  calidad. El riesgo del catálogo es el opuesto: que una capacidad que hoy se
  ve deje de encontrarse.
- **El A/B de X204** (36 corridas, 6 tareas × 3 seeds × 2 brazos, calidad
  18/18 vs 18/18, US$0,2341) es el instrumento de calidad pre-registrado más
  reciente y la plantilla del criterio "calidad igual".

## Qué es "las tools mínimas del CORE"

Hoy el CORE es `utils/fs_tools.py`: 3 tools que no son de ningún módulo. El
resto (27) son capacidades que `discover()` carga en `nodes.py` y que el chat
manda enteras en cada request. X198 separa tres cosas:

- **lo fijo del primer request**: las tools del CORE + una de **catálogo**
  (qué capacidades hay) + una de **uso** (conectar una capacidad o una
  composición);
- **el catálogo**: un manifiesto por módulo (nombre, descripción corta y
  parámetros requeridos) que viaja como **resultado de la tool**, no en el
  prompt (no sube `texto_de_prompt`, N3);
- **la ejecución**: `usar` toma el nombre y los argumentos y despacha la tool
  del módulo por `run_tool_call`, el camino único (política, hooks, HITL).

```
primer request: system prompt + 3 TOOLS del CORE + catalogo + usar  = 5 tools
catalogo()                     -> manifiesto (nombre + descripción + requeridos)
usar(nombre, argumentos)       -> run_tool_call(tool del módulo) -> resultado
```

El catálogo **no** agrega tools en caliente: el prefijo estable es lo que
cachea X173 y lo que P1 pide. El manifiesto viaja en un resultado de tool, no
en el system prompt.

## Decisiones (para el operador)

| # | Decisión | Opciones |
|---|---|---|
| **D1** | Qué se mide como `bytes_primer_request` | **A (recomendada) arreglar el instrumento**: el escáner del ratchet cuenta el request **real** (system prompt + los 5 esquemas fijos) y deja de sumar los `TOOLS` de módulo que ya no viajan; el 16199 se retira y el número nuevo se re-baselinea con el operador. **B dejar el proxy**: cuenta los 27 `TOOLS` igual y la baja no se puede reclamar (el roadmap no se cumple en su métrica). **C** mover los esquemas a literales que el escáner no cuenta (otro nombre de variable): gamifica el instrumento, rechazada |
| **D2** | Cuáles son las tools mínimas | **A (recomendada)**: las 3 de `fs_tools` tal cual + `catalogo` + `usar` = **5**, y ningún módulo en el primer request. **B**: dejar fijas 1–2 de uso frecuente (p. ej. `web_search`, `research`): más bytes, menos riesgo de descubrimiento. **C**: recortar el CORE (fusionar/borrar tools): otro cambio, fuera de X198 |
| **D3** | La semántica de `usar` | **A (recomendada) despachador por `run_tool_call`**: la tool del módulo se ejecuta en el acto con la misma política, hooks y HITL; la descripción sale del manifiesto. **B** agregar la tool al request siguiente ("hot tool"): contradice P1 y X173. **C** `catalogo` devuelve el esquema completo y el modelo llama a la tool por su nombre: vuelve a meter tools en el prompt, descartada |
| **D4** | De dónde sale el manifiesto | **A (recomendada)**: se genera de los `TOOLS` de los módulos presentes en `discover()` (nombre, descripción y parámetros requeridos); una sola fuente, sin copia a mano. **B**: un `CATALOGO` escrito por módulo: duplica el esquema y puede mentir (R3/R5). **C**: un JSON versionado: otra copia que se desincroniza |
| **D5** | Con qué se mide "calidad igual" | **A (recomendada)**: A/B con `banco/bench_supervisor.py` (6 tareas × 3 seeds × 2 brazos = 36 corridas, grading determinista por código): el brazo catálogo tiene que dar **18/18** como la base y adoptar `run_supervisor` (vía `catalogo` + `usar`) en las 18. Las otras 26 tools no se ejercen en el A/B: sus tests estructurales cubren que el catálogo las lista y `usar` las resuelve (límite declarado). **B** el bench de fable (4 escenarios × 8 seeds): mide trampas de conducta, no descubrimiento de tools; no es el instrumento. **C** solo tests estructurales, sin A/B: rechazada, el catálogo cambia conducta y AGENTS.md pide A/B |
| **D6** | El gasto y las llamadas del A/B | **A (recomendada)**: tope **US$0,30** (36 corridas, una a la vez, humo primero) y el brazo catálogo puede subir hasta **+2 llamadas por tarea** (`catalogo` + `usar`); el criterio es la calidad, el costo se mide y se declara. **B**: tope US$0,15 con 2 seeds (menos potencia). **C**: solo el humo, sin tanda: no alcanza para "calidad igual" |
| **D7** | El techo de `lineas_del_producto` | **A (recomendada)**: **7643 + 80 = 7723** (el catálogo agrega `utils/catalogo.py`, el cableado en `nodes.py` y la sonda; no borra los `TOOLS` de módulo); si sube dentro del techo, lo acepta el operador con su clave; si lo pasa, **NO PASA** y se revierte. **B** sin techo, se mide después. **C** exigir que baje: imposible, agrega código |

**Decidido por el operador (2026-11-12): D1 = A, D2 = A, D3 = A, D4 = A,
D5 = A, D6 = A, D7 = A.** El A/B (D5–D6) lo corre **Laboratorio**, no Código,
con el tope de **US$0,30** y una corrida a la vez.

## Criterios

**Estructurales (sin LLM):**

1. El primer request lleva **5 tools** (las 3 del CORE + `catalogo` + `usar`),
   ningún `TOOLS` de módulo; `discover()` sigue cargando los 27 `IMPL` y los
   conectores (X194 no se toca).
2. El catálogo lista las **27** tools con `IMPL` (nombre + descripción +
   requeridos); `usar` resuelve todas; un nombre desconocido devuelve
   `ERROR: …` y no ejecuta nada (falla cerrada).
3. Despacho único: `usar` corre por `run_tool_call`; un veto PRE sobre la tool
   usada corta la llamada con **0 llamadas al LLM** (el caso X197b, ahora para
   todo el catálogo).
4. Sin pérdida de capacidad: para 2–3 tools representativas, `usar` devuelve
   el mismo texto que la llamada directa a la tool (con el cliente falseado).
5. Prefijo estable: dos preguntas seguidas arman el **mismo** set de 5 tools
   (test o sonda); no hay tools en caliente.
6. `bytes_primer_request` medido **antes y después** sobre el request real
   (sonda: `json.dumps` del system prompt y del array de tools) y sobre el
   escáner del ratchet; los dos números quedan en la bitácora. Si D1=A, el
   escáner cuenta el set fijo y se re-baselinea (declarado; el 16199 se
   retira).
7. `lineas_del_producto` ≤ 7723 (D7); `lineas_del_loop` no sube; los
   contratos congelados (`dispatch`, `prefiltro`) y el contrato de X194
   quedan intactos; `tests_definidos` no baja; cobertura y tipos como
   siempre.
8. Gate `./calidad.sh` **6/6**.

**A/B pagado (criterio 9–10, D5–D6):**

9. Bench del supervisor: 6 tareas × 3 seeds × 2 brazos; el brazo catálogo da
   **18/18** (igual que la base) y adopta `run_supervisor` en las 18; 0
   escrituras/comandos fuera de la política y 0 bypass de hooks; las llamadas
   del brazo catálogo, declaradas contra la base (+2 por tarea).
10. Presupuesto: tope **US$0,30**, una corrida a la vez, humo primero; si lo
    pasa, se para y se reporta.

## Fuera de alcance

- X199 (N simétricas + verificador) y el cookbook de recetas.
- Que el modelo decida el catálogo o lo edite: el manifiesto se genera de los
  módulos presentes.
- Más de un formato de catálogo o un segundo `usar`.
- Recortar el CORE (D2=C) o fusionar tools: otro pre-registro.

## Resultado estructural (2026-11-12)

| # | Criterio | Medido | |
|---|---|---|---|
| 1 | Primer request con 5 tools | `nodes.herramientas_de` devuelve `list_files, read_file, search_files, catalogo, usar`; ninguna de las 27 de módulo | ✅ |
| 2 | Catálogo completo y falla cerrada | el manifiesto lista las 27 capacidades (nombre, descripción y parámetros requeridos); `usar` resuelve por nombre y un nombre fuera del catálogo devuelve `ERROR` sin ejecutar | ✅ |
| 3 | Despacho único | `usar` corre por `run_tool_call`; un veto PRE sobre la capacidad la corta y la implementación no se ejecuta (test) | ✅ |
| 4 | Sin pérdida de capacidad | `run_command` y `deep_research` se ejercitan por `usar` en los tests del gate fractal (el resto, por estructura: el manifiesto las lista y `usar` las resuelve) | ✅ |
| 5 | Prefijo estable | dos llamadas seguidas a `herramientas_de` arman el mismo set de 5; no hay tools en caliente (test) | ✅ |
| 6 | `bytes_primer_request` | **16199 → 3362** con el escáner del set fijo (D1=A); el request serializado real: **18919 → 3294** bytes. El escáner se adaptó 1:1 en `test_ratchet_elegancia.py` | ✅ |
| 7 | Presupuesto de producto | `lineas_del_producto` **7643 → 7702 (+59 ≤ 7723)**; `lineas_del_loop` 660 IGUAL; `tests_definidos` 1523 → **1531**; contratos congelados intactos; cobertura 867 y tipos 0 | ✅ (clave del operador por el +59) |
| 8 | Gate | **5/6**: rojo solo el ratchet por el +59 de producto dentro del techo; 6/6 con la clave del operador y `--actualizar` | ⏳ clave |
| 9 | A/B del supervisor (6 × 3 × 2) | **NO PASA** (Laboratorio, 2026-11-12): catálogo **17/18** vs base 18/18 — falla `conteo-routing` s3 (el supervisor propuso un `run_command`, la política lo rechazó y el chat se negó a dar el número sin contar; no usó `read_file`). Adopción **18/18** vía `catalogo` + `usar`; 0 escrituras/edits ejecutados y 0 cambios en el árbol (10 comandos rechazados, 9 lecturas `auto: solo-lectura` dentro de la copia); llamadas declaradas: base 131 vs catálogo 153 (+22, +1,22/corrida; +1 típico en los 16 pares con adopción pareja) | 🔴 |
| 10 | Presupuesto del A/B | **US$0,2301** las 36 (base 0,1104 + catálogo 0,1197) ≤ 0,30; humo US$0,0126; total del experimento US$0,2427 | ✅ |

**Desvíos declarados.**

- **El cableado vive en `utils/catalogo.py`, no en `nodes.py`**: así el loop
  no suma líneas (`lineas_del_loop` 660, criterio 7); `nodes.py` solo cambia las
  dos líneas que arman/despachan por el catálogo y su import.
- **Un skill conserva sus tools directas** (recorta el action space completo,
  como antes); el catálogo es el camino sin skill. El test de skills lo fija.
- **Reescrituras 1:1 de tests** por el despacho movido a `utils/catalogo.py`:
  `test_caracterizacion_chat.py` (el fixture espía `nodes.catalogo.despachar`),
  `test_chat_flujo.py`, `test_gate_fractal.py` (el chat llama `usar`; el
  supervisor y la copia no cambian), `test_instrumentos_chat_real.py`,
  `test_skills.py` y `test_ratchet_elegancia.py` (el escáner). Ningún test se
  borró ni se debilitó: los dos del gate fractal siguen exigiendo el rechazo
  del humano y el aviso de cierre.
- **`juez.py` y `replay.py` suman `catalogo`/`usar` al inventario**: el modelo
  ahora los usa y no son "tools inventadas".
- **El gate se corrió tres veces**: las dos primeras rojas fueron del arnés de
  tests (el fixture del chat todavía espiaba `nodes.run_tool_call`) y de la
  cobertura de la rama de JSON inválido (2 líneas); se arreglaron esas dos
  cosas, no la métrica. La tercera dio 5/6 con el +59 declarado.

## Decisión atada al resultado

- **PASA**: entra con sus docs en el mismo paso (estado, roadmap, design,
  bitácora, handoff y este spec con la tabla de resultado y los desvíos).
- **NO PASA** (criterios 1–4, 9 o el techo de D7): se revierte el brazo; quedan
  este spec y la sonda. No vuelve como parche.

## Riesgos declarados antes de medir

- **El catálogo agrega llamadas**: `catalogo` y `usar` cuestan ida y vuelta;
  el A/B lo mide y el criterio 9 tolera hasta +2 por tarea. Si el costo se
  dispara más, es un desvío a declarar, no un ajuste del criterio.
- **El modelo puede pedir el catálogo dos veces** o pedir una tool y usarla
  mal: el manifiesto tiene que traer los requeridos para armarlo bien; el A/B
  lo expone.
- **El A/B ejercita una sola tool** (la que usan las 6 tareas): el resto queda
  cubierto por estructura, no por conducta. Se declara en el resultado.
- **`lineas_del_producto` sube**: es una capacidad nueva (D7); la clave es del
  operador.

## Desvíos del A/B (9–10, declarados antes de correr)

- **Recursos copiados a los dos brazos**: `trazas.db` y
  `salidas/routing.jsonl` (artefactos ignorados) para que las dos tareas de
  artefactos sean evaluables; 0 saltadas, 18 por brazo. El mismo desvío que el
  A/B de X204.
- **La tolerancia "+2 por tarea" se lee por corrida** (cada corrida ejecuta
  una tarea; con 3 seeds, el agregado por tarea tolera +6); se informan las dos
  lecturas.
- **Comandos `auto: solo-lectura`**: `HITL_AUTO` los aprueba sin evento en el
  archivo de decisiones; se cuentan del transcript (9, todos read-only dentro
  de la copia).

## Resultado del A/B (9–10), 2026-11-12

36 corridas, una a la vez, **US$0,2301** (humo 0,0126; total del experimento
0,2427), instrumento `banco/probes/ab_x198.py` (adaptación del de X204):
**catalogo 17/18 vs base 18/18**; adopción 18/18 vía `catalogo` + `usar`;
seguridad ✅; llamadas base 131 vs catálogo 153 (**+22**), que **incumplen** la
tolerancia del D6 (+2 por tarea: **+9 en `linea-marcadores`**, máx +7 por
corrida). La corrida que falla (`conteo-routing`
s3) es válida: el chat se negó a inventar el número tras un `run_command`
rechazado y no usó `read_file` (la base y las otras seeds del brazo resolvieron
el mismo caso contando). **NO PASA** por el criterio 9 (calidad) **y por las
llamadas** → se revierte el brazo;
quedan este spec y la sonda. Informe: `docs/informes/x198_ab_2026-11-12.md`;
filas `salidas/x198_ab/resultados.jsonl` (sha256 `63df3618…`).

**La reversión se ejecutó (2026-11-12).** Código, tests y baselines volvieron a
`54bfd54` (el diff `git diff 54bfd54 -- '*.py' 'ratchets/*.json'` deja solo
`banco/probes/ab_x198.py`) y el
árbol mide **7643/1524/660**, cobertura **867** y tipos **0**. El hallazgo de
la corrida que falla **no es de descubrimiento** (18/18 encontraron y
ejecutaron el supervisor): es de **recuperación tras un rechazo de la política**
—el chat se negó a paginar con `read_file` en vez de buscar otra vía— y es un
paso propio después de X199.
