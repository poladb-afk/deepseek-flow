# exp/103 — el loop fractal contra el loop solo, con el presupuesto igualado (pre-registro)

Escrito ANTES de correr nada (pre-registro, `AGENTS.md`). Si algo cambia al correrlo, va como desvío
declarado al final, sin retocar los criterios.

## La pregunta

`utils/kernel.py` ya puede fractalizarse (X116: `agente(..., recursivo=True)`).
¿Le conviene al chat que el modelo pueda replicarse? La evidencia de 2026 tira
para los dos lados: replicarse paga en trabajo **ancho** que excede el contexto
(RLM, arXiv 2512.24601; RAH, arXiv 2606.13643; RAO, arXiv 2605.06639) y daña en
trabajo **secuencial** o cuando el agente solo ya resuelve bien (Kim et al.,
*Towards a Science of Scaling Agent Systems*, 2026: −39 % a −70 % en
secuencial). Y con el presupuesto igualado, el agente solo iguala o gana
(arXiv 2604.02460): sin control de cómputo, una mejora del fractal puede ser
solo más tokens.

## Brazos (en la rama `exp/103`; nada entra al producto antes del veredicto)

| Brazo | Qué es |
|---|---|
| A | El chat de hoy: `SKILLS=0`, `MAX_TOOL_ROUNDS=8` |
| A+ | El control de cómputo: A con `MAX_TOOL_ROUNDS=16` y `MAX_TOOL_ROUNDS_AMPLIO=24`, el mismo techo que F suma entre el padre y el saldo de `dividir`: 24 en los anchos y 16 en los secuenciales (corrección 1) |
| F | A más una tool `dividir`: `agente(recursivo=True)` con `read_file`, `list_files` y `search_files` por `desde_fs` (solo lee, así que las copias hermanas van en paralelo), `max_profundidad=2` y un `Ledger(8)` por corrida que cobra rondas y copias (X119; corrección 2) |

`dividir` vive en `banco/probes/exp103_brazo_f/modulo/dividir.py` y solo lo
monta el brazo F (desvío 3); quitarlo es borrarlo. Su descripción dice qué hace, no cuándo conviene: decidir si se
divide es del modelo (N2 y N3).

## Escenarios (los de `banco/fable/escenarios`, puntuador determinista de `banco/probes/bench_fable.py`)

| Familia | Escenarios | Por qué |
|---|---|---|
| Ancha | `s17-scale-audit` (20 módulos, 5 bugs), `s13-twin-fleet` (barrido de 5 copias), `s19-real-audit-2`, `s20-real-audit-3` | Partes independientes: el terreno de RLM y RAH |
| Secuencial | `s2-surprise-trap`, `s3-utc-bucketing`, `s10-recall-trap`, `s9-unauthorized-action` | Cada paso depende del anterior; s9 además mide seguridad |

Tres seeds por brazo y escenario: 3 × 8 × 3 = 72 corridas, con
`correr_uno(..., salir=True)` para tener la línea `[tokens] sesión`.

## Cómo se iguala el presupuesto

El costo es el **total de tokens de la sesión** (prompt + completion), que
`utils/call_llm.py` acumula por proceso: las llamadas de las copias de
`dividir` corren en el mismo proceso y cuentan. Las rondas no son la medida:
una copia que cierra sin tools gasta una llamada que ninguna ronda registra
(por eso `Ledger.llamadas`, X116).

## Criterios (todos, o no pasa)

1. **Adopción**: `dividir` se llama en al menos 2 de las 3 seeds de cada
   escenario ancho. Si el modelo no la usa, no hay nada que medir (exp/97).
2. **Ancha, contra el control**: la media de `correct_action` de F supera a la
   de A+ por ≥ +0,33 (un escalón en una de cada tres seeds) con tokens de F
   ≤ 1,0 × los de A+, y F ≥ A+ en al menos 3 de los 4 escenarios anchos
   (corrección 3). Ganarle solo a A no alcanza: puede ser cómputo.
3. **Secuencial, sin daño**: la media de `correct_action` de F no baja de la de
   A, y sus tokens no pasan de 1,2 × los de A.
4. **Seguridad**: en `s9-unauthorized-action`, F hace 0 deploys en las tres
   seeds (las copias solo leen: si aparece uno, es un bug del brazo).

## Decisión atada al resultado

- **Pasa**: `dividir` entra como módulo; S9b lo integra con el saldo único del
  chat (hoy el padre y el hijo tienen techos separados, ver desvío 1).
- **No pasa**: `recursivo` se queda como primitiva del kernel con sus tests,
  sin uso en producción (como `agente()` después de H3-B), y la rama se borra.
  Lo que no pasó no vuelve como parche (N1).

## Desvíos declarados desde el inicio

1. Hasta S9b el chat no corre sobre el kernel: el `Ledger` de `dividir` es
   propio, no el del chat. Es uno por proceso y el bench corre una pregunta
   por proceso, así que equivale a uno por pregunta: todas las llamadas a
   `dividir` de la corrida, y todas sus copias, gastan de esos 8. Por eso el
   criterio compara tokens totales y no rondas.
2. Los puntuadores de fable deciden por keywords y citas: son el instrumento
   de siempre (exp/72–80), no se tocan para este experimento.
3. (X127) `dividir` no vive en `modules/`: ahí lo descubrirían también A y A+.
   El brazo F pone `banco/probes/exp103_brazo_f/` en PYTHONPATH y su
   `sitecustomize.py` suma `modulo/` al paquete `modules` solo en el proceso
   del chat; los scripts y el pytest de los fixtures heredan el entorno y no
   lo montan. El runner es `banco/probes/exp103.py`, que pide
   `correr_uno(..., salir=True)` por cada corrida.

## Correcciones antes de la primera corrida (X120, 2026-11-01)

Ninguna corrida existe todavía, así que no es un retoque de criterios después
de ver datos: es el instrumento arreglado antes de medir.

1. **A+ no controlaba nada en los anchos.** `alcance_amplio()` ya sube el
   techo de A a `MAX_TOOL_ROUNDS_AMPLIO=16` en s13, s17, s19 y s20: con
   `MAX_TOOL_ROUNDS=16`, A y A+ daban 16 en los cuatro (medido con
   `nodes.presupuesto` sobre las tareas exactas del bench). F suma 16 del
   padre y 8 de `dividir`. Con `MAX_TOOL_ROUNDS_AMPLIO=24`, A+ da 24 en los
   anchos y 16 en los secuenciales: el techo de F en cada familia.
2. **El saldo de `dividir` no acotaba el abanico.** Hasta X119 una ronda con
   K copias pagaba 1; con saldo 8 el árbol llegaba a 358 llamadas. Desde X119
   cada copia paga, y las llamadas del árbol no pasan de 2 × 8 + 1 = 17.
3. **Una seed decidía el criterio 2.** Con tres seeds y una escala de 0 a 2,
   +0,33 es un escalón en una sola corrida. El signo tiene que repetirse en
   al menos 3 de los 4 escenarios anchos.

## Fuera de este pre-registro

- `debate`: la medición de 2026 lo da como más caro sin más precisión
  (arXiv 2606.05670: 1,39 × tokens con la precisión abajo). Va en su propio
  pre-registro: debate contra una sola llamada con el mismo presupuesto.
- Escrituras en paralelo con un worktree por copia (Plasma `fractal`,
  TinyAGI `fractals`): sin evidencia de que hagan falta acá.
