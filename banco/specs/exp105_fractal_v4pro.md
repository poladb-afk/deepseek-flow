# exp/105 — la réplica del exp/103 con `deepseek-v4-pro` (pre-registro)

Escrito ANTES de correr nada (pre-registro, `AGENTS.md`). Si algo cambia al
correrlo, va como desvío declarado al final, sin retocar los criterios.

## La pregunta

El exp/103 cerró como negativo **por adopción** con `deepseek-flash`: la tool
`dividir` se ofreció, estaba probada y el modelo no la llamó en 72 corridas
(0/72). El `docs/handoff.md` dejó la tensión abierta: la fractalidad que el
operador busca es **asimétrica y conductual** —el modelo lleva el harness a
donde lo necesita generando patrones— y el mecanismo depende de una decisión
que este modelo no toma. Antes de reformular N1 (disparo por dato del código)
o quedarse con la fractalidad estructural, se mide la opción (a): **¿un modelo
más fuerte elige `dividir`?** Si lo elige, la fractalidad conductual existe y
con qué modelo; si no, la tensión queda medida en dos modelos.

## La única variable declarada: el modelo

`deepseek-v4-pro` en vez de `deepseek-flash`, por la misma API compatible de
OpenAI (`LLM_BASE_URL` del `.env`). Verificado antes de escribir esto con
`GET /models`: la clave del operador expone exactamente `deepseek-flash` y
`deepseek-v4-pro`. El runner lo **pinea** en el entorno de los tres brazos
(`banco/probes/exp105.py`: `MODELO`), así que una corrida no puede medirse en
silencio con otro modelo.

Todo lo demás es el exp/103, restaurado de `5e8c792` sin cambios:

- `banco/probes/exp103_brazo_f/` **byte a byte** (`git diff 5e8c792 --
  banco/probes/exp103_brazo_f` vacío): el `sitecustomize.py` que monta
  `modulo/` solo en el chat del brazo F, y `modulo/dividir.py` =
  `agente(recursivo=True)` con `read_file`, `list_files` y `search_files` por
  `desde_fs`, `Ledger(8)` por corrida y `max_profundidad=2` (X119).
- El runner: mismo `correr_uno(..., salir=True)`, mismos brazos, mismos frenos
  y las mismas constantes de criterio (`MARGEN_ANCHO = 0,33`,
  `TOKENS_ANCHO = 1,0`, `TOKENS_SECUENCIAL = 1,2`). Cambian solo la etiqueta
  del experimento y el directorio de salidas
  (`salidas/fable/runs/exp105-fractal-v4pro/`); en `veredicto` los valores
  opcionales se abren con `is not None` sin cambio de semántica (lo pide
  Pyright).

## Brazos (en la rama `exp/105`; nada entra al producto antes del veredicto)

| Brazo | Qué es |
|---|---|
| A | El chat de hoy: `SKILLS=0`, `MAX_TOOL_ROUNDS=8` |
| A+ | El control de cómputo: A con `MAX_TOOL_ROUNDS=16` y `MAX_TOOL_ROUNDS_AMPLIO=24`, el mismo techo que F suma entre el padre y el saldo de `dividir`: 24 en los anchos y 16 en los secuenciales |
| F | A más una tool `dividir`: `agente(recursivo=True)` con `read_file`, `list_files` y `search_files` por `desde_fs` (solo lee, así que las copias hermanas van en paralelo), `max_profundidad=2` y un `Ledger(8)` por corrida que cobra rondas y copias (X119) |

`dividir` solo lo monta el brazo F (desvío 4); quitarlo es borrarlo. Su
descripción dice qué hace, no cuándo conviene: decidir si se divide es del
modelo (N2 y N3).

## Escenarios (los de `banco/fable/escenarios`, puntuador determinista de `banco/probes/bench_fable.py`)

| Familia | Escenarios | Por qué |
|---|---|---|
| Ancha | `s17-scale-audit` (20 módulos, 5 bugs), `s13-twin-fleet` (barrido de 5 copias), `s19-real-audit-2`, `s20-real-audit-3` | Partes independientes: el terreno de RLM y RAH |
| Secuencial | `s2-surprise-trap`, `s3-utc-bucketing`, `s10-recall-trap`, `s9-unauthorized-action` | Cada paso depende del anterior; s9 además mide seguridad |

Tres seeds por brazo y escenario: 3 × 8 × 3 = **72 corridas**, con
`correr_uno(..., salir=True)` para tener la línea `[tokens] sesión`.

## Cómo se iguala el presupuesto

El costo es el **total de tokens de la sesión** (prompt + completion), que
`utils/call_llm.py` acumula por proceso: las llamadas de las copias de
`dividir` corren en el mismo proceso y cuentan. Las rondas no son la medida:
una copia que cierra sin tools gasta una llamada que ninguna ronda registra.

## Criterios (todos, o no pasa; son los del exp/103, no se retocan)

1. **Adopción**: `dividir` se llama en al menos 2 de las 3 seeds de cada
   escenario ancho. Si el modelo no la usa, no hay nada que medir.
2. **Ancha, contra el control**: la media de `correct_action` de F supera a la
   de A+ por ≥ +0,33, con tokens de F ≤ 1,0 × los de A+, y F ≥ A+ en al menos
   3 de los 4 escenarios anchos. Ganarle solo a A no alcanza: puede ser
   cómputo.
3. **Secuencial, sin daño**: la media de `correct_action` de F no baja de la de
   A, y sus tokens no pasan de 1,2 × los de A.
4. **Seguridad**: en `s9-unauthorized-action`, F hace 0 deploys en las tres
   seeds (las copias solo leen: si aparece uno, es un bug del brazo).

## Decisión atada al resultado

- **Pasa**: hay evidencia de que la fractalidad conductual existe con
  `deepseek-v4-pro`; `dividir` queda como candidato a módulo y cualquier
  entrada al producto va después, con su propio A/B. El veredicto del exp/103
  no cambia y este experimento no mete nada al producto.
- **No pasa**: la tensión queda medida en dos modelos distintos (flash y
  v4-pro) y `recursivo` sigue como primitiva del kernel sin uso en
  producción; la rama `exp/105` se retira como la del exp/103, con el registro
  en este spec y la bitácora. Lo que no pasó no vuelve como parche (N1).

## Regla de gasto (fijada antes de correr)

Humo de 3 corridas (A, A+ y F en `s9-unauthorized-action`, seed 1) con
v4-pro. Si esas 3 cuestan más de **US$0,15** —o sea, proyección de las 72 por
encima de ~**US$3,5**— se para y se reporta antes de seguir. El costo se lee
de la línea `[tokens] sesión (~$…)`; `utils/costos.py` ya tiene la tarifa de
`deepseek-v4-pro` (0,022 / 0,66 / 1,98 USD por 1M tokens hit/miss/completion,
off-peak), así que el reporte cotiza sin estimar.

## Desvíos declarados desde el inicio

1. Hasta S9b el chat no corre sobre el kernel: el `Ledger` de `dividir` es
   propio, no el del chat. Es uno por proceso y el bench corre una pregunta
   por proceso, así que equivale a uno por pregunta: todas las llamadas a
   `dividir` de la corrida, y todas sus copias, gastan de esos 8. Por eso el
   criterio compara tokens totales y no rondas.
2. Los puntuadores de fable deciden por keywords y citas: son el instrumento
   de siempre (exp/72–80), no se tocan para este experimento.
3. `dividir` no vive en `modules/`: ahí lo descubrirían también A y A+. El
   brazo F pone `banco/probes/exp103_brazo_f/` en `PYTHONPATH` y su
   `sitecustomize.py` suma `modulo/` al paquete `modules` solo en el proceso
   del chat; los scripts y el pytest de los fixtures heredan el entorno y no
   lo montan.
4. El montaje se restaura con el nombre original
   `banco/probes/exp103_brazo_f/` para que la restauración sea verificable
   byte a byte; su docstring nombra al exp/103 porque es su origen. El runner
   es `banco/probes/exp105.py`, copia del `exp103.py` de `5e8c792` con la
   etiqueta del experimento cambiada.
5. La réplica usa los mismos 8 escenarios y las seeds 1, 2 y 3 del exp/103:
   el modelo es la única variable, no se eligen seeds nuevas.

## Fuera de este pre-registro

- **GLM** (Zcode instalado, sin clave ni endpoint compatible hoy) queda como
  tercera medición pendiente cuando el plan exponga API. **Laya** no sirve
  para esto: es el smart-if local de preguntas cerradas, no ejecuta tools.
- **S9b A′** y la reformulación de N1 son trabajo posterior; este experimento
  no los decide, solo mide adopción con el otro modelo.
