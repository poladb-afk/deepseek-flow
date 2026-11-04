# exp/110 — la asimetría medida: hijos especializados (pre-registro de X148)

Escrito ANTES de correr nada y ANTES de que exista el código del brazo
(pre-registro, `AGENTS.md`; X148 de `docs/roadmap.md`). Nada entra al producto
antes del veredicto. Si algo cambia al correrlo, va como desvío declarado al
final, sin retocar los criterios.

## La pregunta

La replicación **simétrica** se midió y no se adopta: `dividir` con copias
iguales (`recursivo`) se ofreció y no se eligió en 72 corridas con
`deepseek-flash` (exp/103) ni en 72 con `deepseek-v4-pro` (exp/105). La
**asimétrica** —hijos especializados, cada uno con su prompt y sus tools, con
menos poder que el padre— nunca se midió (X144, P2b reabierta como hipótesis).

Pregunta: **¿el modelo elige delegar cuando el hijo es un especialista, y esa
forma mantiene la calidad sin inflar el costo?** No se pregunta si el árbol
"mejora" la calidad: se pregunta si se **adopta** y si **no daña** (P1: lo
simple primero; N1: sin parche).

## Los brazos

| Brazo | Qué es |
|---|---|
| **A** | El chat de hoy sobre `kernel.loop` (S9b A′): `SKILLS=0`, techo único `MAX_TOOL_ROUNDS=16`, `LLM_MODEL=deepseek-flash` pineado |
| **F** | A + **tres hijos especialistas** montados como tools del kernel vía `kernel.agente()` (cada uno con su prompt y su subconjunto de tools de LECTURA del padre), sin `recursivo`, profundidad 1 |

Los tres especialistas (nombres y prompts fijos; la descripción dice **qué
hace**, no cuándo conviene — N2/N3):

| tool | tools del hijo (subconjunto de las del padre, P2c) | system |
|---|---|---|
| `barrido` | `list_files`, `search_files` | "Sos el hijo de barrido: recorrés el alcance y devolvés un índice de los archivos relevantes, por ruta. No escribís ni ejecutás nada." |
| `lectura` | `read_file` | "Sos el hijo de lectura: extraés hechos textuales de los archivos que te piden y los devolvés con `ruta:línea`. No escribís ni ejecutás nada." |
| `sintesis` | `read_file`, `search_files` | "Sos el hijo de síntesis: armás el borrador de una parte del informe con citas verificables. No escribís ni ejecutás nada." |

Adopción = cualquiera de los tres se llama (se informa por tool). Los hijos
solo leen: todas las escrituras y el HITL quedan en el padre. `agente()` copia
las tools al construirlas y X147 va a verificar que sean subconjunto del padre
(`ValueError` en construcción si no).

## Ley 1: el saldo es uno (y hay que hacerlo cumplir en el montaje)

`kernel.agente()` comparte el `Ledger` del árbol, pero el chat deriva su saldo
de `turno["rondas"]` (X140), así que el gasto de un hijo que corre dentro de
una ronda **no se refleja** en `turno`. El montaje del brazo F (instrumento, no
producto) lo cobra al cerrar el `ActuarChat`; el detalle, el alcance y lo que
este experimento **no** prueba están en "Desviación de instrumento" (abajo).
Con esa corrección cada copia y cada ronda de hijo descuentan del mismo saldo
(R = 16) y la Ley 1 queda verificable: **llamadas al modelo del árbol ≤ 2R+1 =
33 por pregunta**, leídas de `Ledger.llamadas` (criterio 4). En el brazo A el
montaje no existe: sin hijos, su conducta es la de hoy.

## Desviación de instrumento: la Ley 1 y el `turno` del chat (declarada antes de correr)

`kernel.agente()` comparte el `Ledger` del árbol (`utils/kernel.py:232-267`):
un hijo gasta del mismo saldo. Pero **el chat no tiene un `Ledger` como
fuente**: desde X140 deriva el saldo de `turno` en cada `PasoChat.prep`, porque
`turno` es lo que corta `Contexto`, lo que checkpointea `resume` y lo que lee
S9a (`nodes.py:412-430`). Consecuencia: el gasto de un hijo que corre dentro
de una ronda queda en el `Ledger` y **no** se refleja en `turno`; en la llamada
siguiente la proyección se re-deriva de `turno` y ese gasto se pierde. Es un
**hueco de aplicación de la Ley 1 en el producto** (el kernel la cumple; el
chat todavía no la recibe), no un defecto del kernel.

Para que el A/B mida con el presupuesto igualado, el **montaje del brazo F** lo
cobra al cerrar la ronda: `turno["rondas"] = max(turno["rondas"],
presupuesto(s) - ctx.ledger.rondas - 1)`. Es una **desviación de instrumento**
—código de laboratorio, no producto— y así se declara acá y en el informe:

- el brazo A **no** lleva el parche (su `env` no monta el brazo F) y su conducta
  es exactamente la de hoy;
- el experimento mide si la forma asimétrica **se adopta y no daña** con la Ley
  1 aplicada por el montaje; **no** prueba que el producto la cumpla sin él;
- si al implementar el montaje hiciera falta tocar producto, o la corrección no
  alcanza para que llamadas ≤ 2R+1, **se para y se reporta antes de correr**: no
  se parchea el producto dentro del experimento;
- si el hueco resulta real a nivel producto, va como **paso propio del roadmap**
  (aplicar la Ley 1 del árbol al saldo del chat, con su test y su gate), separado
  de exp/110. Si exp/110 PASA, ese paso es la condición para integrar los
  especialistas al producto.

## El montaje del brazo F (instrumento; solo F lo monta)

`banco/probes/exp110_brazo_f/` con el mismo patrón que `exp103_brazo_f/`
(`sitecustomize.py` que solo actúa en el proceso del chat, `modulo/asimetria.py`):

1. Arma los tres tools con `kernel.agente(...)` y los agrega al menú del chat
   parcheando `nodes.herramientas_de` (A no los ve).
2. Cobra el gasto de hijos a `turno` (Ley 1, arriba) parcheando
   `nodes.ActuarChat.post`.
3. Suma los tres nombres al inventario del juez
   (`juez._inventario_tools`) para que un borrador que los mencione no se lea
   como herramienta inventada (X135). Es consecuencia del montaje, no del
   producto.
4. Al salir escribe, al lado del directorio de la corrida,
   `<corrida>-asimetria.json`: llamadas por tool, `ledger.llamadas`, saldo final
   y `ctx.traza` para `banco/probes/fractal.py` (adopción, D y fallas), como
   exp/103. Afuera de la corrida a propósito.

Si la Ley 1 no se puede cumplir con el montaje —es decir, si hiciera falta
tocar producto—, **se para y se reporta antes de correr**; no se corre un brazo
cuyo presupuesto no está igualado ni se cambia el producto dentro de este
experimento.

## Escenarios y seeds

Los de `banco/fable/escenarios` (puntuador determinista de
`banco/probes/bench_fable.py`), **6 escenarios × 4 seeds × 2 brazos = 48
corridas** con `correr_uno(..., salir=True)` para tener la línea `[tokens]`:

| Familia | Escenarios | Por qué |
|---|---|---|
| Ancha (5) | `s13-twin-fleet` (edita), `s17-scale-audit`, `s18-real-audit`, `s19-real-audit-2`, `s20-real-audit-3` | partes independientes: el terreno donde dividir puede pagar |
| Control (1) | `s2-surprise-trap` | secuencial: la evidencia de 2026 dice que ahí la división daña |

Seeds 1, 2, 3 y 4. En el bench la seed es solo una etiqueta de repetición (no
se le pasa semilla al modelo): cada corrida es una muestra nueva de la API (se
declara, igual que exp/104 y exp/106).

## El denominador (declarado y simétrico)

- **Calidad**: `correct_action` (0–2) del puntuador de fable, por corrida;
  medias por escenario y globales. Una corrida sin línea `[tokens]` cuenta 0 y
  **no sale del promedio** (ley de `AGENTS.md`); se informa cuántas.
- **Costo**: total de tokens de la sesión (prompt + completion) de la línea
  `[tokens] sesión`; las llamadas de las copias corren en el mismo proceso y
  cuentan.
- **Adopción**: llamadas a `barrido`/`lectura`/`sintesis` por corrida, del
  archivo del montaje (y de la traza del árbol para D y fallas).
- **Ley 1**: `ledger.llamadas` del árbol por corrida; válida si ≤ 33.

## Criterios (los cuatro, o no pasa)

1. **Adopción**: alguno de los tres especialistas se llama en **≥ 2 de las 4
   seeds en al menos 3 de los 5 escenarios anchos** (y se informa el total de
   llamadas por tool). Si el modelo no delega, no hay nada que medir: los
   criterios 2 y 3 se informan igual, pero el veredicto es NO PASA (exp/97).
2. **Calidad no inferior**: la media global de `correct_action` en los **5
   anchos** con F es **≥ la de A − 0,5**; y en el control `s2`, F **≥ A − 0,5**.
   No es una prueba de superioridad: se exige que la forma asimétrica no rompa
   la calidad. El margen 0,5 se **calibró antes de correr** remuestreando el
   brazo A del exp/105 en los mismos escenarios (4 seeds × 5 anchos, 20.000
   réplicas, semilla 606): con estas varianzas un margen de 0,25 rechazaría por
   ruido el 18 % de las veces y 0,33 el 9 %; con 0,5 es **1,8 %**. Límite
   declarado: con 4 seeds, una caída real de 0,5 se detecta ~50 % de las veces;
   una menor, no.
3. **Costo no mayor a 1,25×**: tokens medios del brazo F en los 5 anchos **≤
   1,25 ×** los de A (el mismo cómputo de la línea `[tokens]`). Es el tope que
   pidió el operador; el modo de falla de exp/108 fue ganar en costo y perder
   el informe, así que calidad y costo van **juntos**.
4. **Ley 1 (validez del brazo)**: en **todas** las corridas de F, llamadas al
   modelo del árbol ≤ **2 × 16 + 1 = 33**, con la corrección del montaje
   declarada arriba; y ninguna corrida sin su archivo de traza o sin línea de
   tokens. Si alguna corrida la viola, el brazo está mal
   montado: no es un resultado, el A/B no se evalúa y se corrige el montaje.

## Decisión atada al resultado

- **PASA (los 4)**: la forma asimétrica queda **medida y adoptada como
  mecanismo candidato**: (b) pasa de hipótesis a principio cumplido en
  `docs/principios.md` P2 (X150) y el mecanismo (los tres especialistas) es
  candidato a producto con su propio A/B de integración (no entra al producto
  en este experimento). El montaje y el instrumento quedan versionados.
- **NO PASA**: (b) queda **medida y no adoptada**, con su número escrito en la
  bitácora (y se informa cuál criterio falló: por adopción, por calidad o por
  costo). La rama y el montaje se retiran como en exp/103/105, P2 se re-expresa
  con el dato, y **no se fuerza un parche** ni se cambia el criterio (N1). Si
  falla solo por adopción y el modelo no delega, la conclusión es la misma que
  la simétrica: con este modelo, la forma que decide el modelo no aparece; si
  falla por calidad o costo, la asimetría **sí** se elige y aun así no conviene,
  que es el dato nuevo de este experimento.

## Regla de gasto (fijada antes de correr)

Proyección con los tokens del brazo A del exp/105 en los mismos escenarios
(`s18` sin datos propios: se asume la media de `s19`): A ≈ 2,23 M tokens para
24 corridas; F ≤ 1,25× → ≤ 2,79 M; total ≈ **5,0 M tokens** → **US$0,30–1,00**
según cuánto cachee (techo con todo el prompt como miss: ~US$0,98; con el cache
observado en los A/B de flash: ~US$0,30). Duración: ~30–60 min, en secuencia.

Humo de **4 corridas** (A y F en `s2` seed 1 y en `s13` seed 1) con techo
**US$0,15** y proyección de las 48 por encima de US$1,50 → se para y se reporta
antes de la tanda. El humo también verifica que el montaje arranca, que los
tres especialistas aparecen en el menú y que la Ley 1 se cumple en una corrida
con delegación. Gasto total autorizado por el operador al aprobar este spec:
**≤ US$1,00** (humo incluido).

## Fuera de este pre-registro

- La replicación simétrica (ya medida: 0/72 y 0/72) y la copia recursiva.
- Hijos que **escriben** o ejecutan comandos: el experimento mide la asimetría
  de lectura, donde no hay riesgo de acción no autorizada; un hijo con poder de
  escritura es otro pre-registro (y otra conversación con S0).
- Cambiar de modelo (la opción (a) ya quedó descartada en dos modelos).
- Integrar los especialistas al producto: si PASA, va con su propio A/B.
- Medir calidad contra `A+` de cómputo igualado: acá no se pide que F gane,
  solo que no dañe; el tope de costo 1,25× cumple el papel de control.

## Límites declarados

- **Potencia**: 4 seeds por escenario y 5 anchos; la no inferioridad tiene el
  margen declarado y su límite de potencia escrito arriba. Un negativo no
  descarta una caída chica.
- **El montaje es instrumento**, no producto: prueba que la forma funciona con
  el kernel actual **más los parches del montaje** (menú, Ley 1, inventario del
  juez). Si el producto la adoptara, esos parches serían el cambio a diseñar.
- **Un modelo** (`deepseek-flash`, pineado), un bench (`fable`, keywords y
  citas deterministas) y `s18` sin varianza histórica para calibrar.
- Los hijos son de lectura: no mide hijos con escritura, ni coordinación entre
  hijos, ni reutilización de su contexto.
- Las seeds son etiquetas de repetición, no semillas del modelo.
