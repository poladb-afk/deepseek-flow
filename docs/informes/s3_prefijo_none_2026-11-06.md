# s3 — la 4.ª medición de `tool_choice="none"`: el prefijo no se comparte (2026-11-06)

**Estado: corrida y dictaminada por el pre-registro — `PREFIJO NO COMPARTIDO`.**
Hito **X173** (siguiente número libre; la numeración final la fija Chief/Diseño).
Pre-registro escrito antes de correr: `banco/specs/s3_prefijo_none.md`
(commit `cddf656`). Instrumento: `banco/probes/tool_choice_none_real.py` (mismo
commit). Filas crudas: `salidas/tool_choice_none_real/20261106-073432.jsonl`
(sha256 `e3a004e0…`, ignorado por git), `head` = `cddf656`. Una sola corrida de
4 llamadas, ejecutada por **Chief con autorización del operador** (como X158).
Nada de producto ni de tests se tocó.

## Qué se midió

X158 midió con 3 tools chicas que `tool_choice="none"` se acepta y no devuelve
tool calls, pero dejó abierta la premisa de S3: el prompt pasaba de 673 a 40
tokens y la caída era el tamaño de las 3 tools, así que el proveedor no las
contaba y el prefijo no quedaba probado (`docs/bitacora.md:1952-1996`).

Esta medición repite la pregunta con el **request real del chat**: system
prompt real (894 chars), las **30 tools** del menú (17.840 chars de JSON) y la
misma pregunta de X158. Cuatro llamadas back-to-back, en orden: `base`,
`base_repetida`, `none` (mismo request + `tool_choice="none"`) y
`none_repetida`. La `base` usa el builder del chat (`_kwargs_agente`: sin
`tool_choice`, thinking disabled), así que es el request de hoy salvo la
pregunta y el `max_tokens=64` del instrumento (desvío declarado en el spec).

## Las cuatro filas crudas

| # | llamada | prompt | completion | total | cache_hit | cache_miss | tool_calls | texto |
|---|---|---|---|---|---|---|---|---|
| 1 | `base` | 5.179 | 64 | 5.243 | 2.048 | 3.131 | 1 | — |
| 2 | `base_repetida` | 5.179 | 64 | 5.243 | **4.992** | 187 | 1 | — |
| 3 | `none` | **266** | 56 | 322 | 0 | 266 | 0 | markup DSML |
| 4 | `none_repetida` | **266** | 56 | 322 | 128 | 138 | 0 | markup DSML |

Totales: **10.890** de prompt + 240 de completion = **11.130 tokens**; 7.168 de
cache hit y 3.722 de miss. Costo medido con la tarifa de `deepseek-flash`
(`utils/costos.py:23-28`): **US$0,000724** (≈0,07 centavos), contra US$0,005
proyectados y US$0,05 de techo.

## El estado pre-registrado (C0–C4)

- **C0 ✅** — el request es estable: `prompt_tokens(base) ==
  prompt_tokens(base_repetida)` = 5.179; `sha_prefijo` `fb5afbab4dee923f`, 30
  tools, system de 894 chars, `head` `cddf656`.
- **C1 ✅ literal / ❌ conductual** — las dos llamadas con `none` se aceptan y
  devuelven `tool_calls=0`. Pero el modelo **no dejó de pedir la tool**: la
  emitió como texto DSML (hallazgo 1). El criterio se cumple en su letra y la
  premisa de S3 no.
- **C2 ✅ "no las cuenta"** — `none` cuenta 266 contra 5.179: `delta = 4.913`,
  muy por encima del umbral pre-registrado de 10 tokens. El proveedor no cuenta
  los esquemas de las tools con `none`.
- **C3 ✅ control / ❌ compartida** — la base repetida sí cachea (4.992 > 0, el
  control no falla), pero la primera `none`, después de dos `base` idénticas,
  reporta **0** de hit: el prefijo cacheado con tools no se reusa. Su repetida
  cachea **128** de sus 266 (su propia repetición). **El prefijo con tools no
  se reusa en `none`.**
- **C4 ❌ no atribuible** — el delta 4.913 queda **318 tokens (6,1 %) por
  debajo** de la ventana pre-registrada 5.231–8.718, que se armó con el ratio
  de X158 (2,558 chars/token). La explicación va como post-hoc declarado
  (hallazgo 2); el criterio no se retoca.

**Estado final: `PREFIJO NO COMPARTIDO`**, el que imprimió el instrumento.

## Hallazgo 1: `none` no apaga las tools, las manda al canal de texto

Las dos filas de `none` traen `tool_calls=0` pero el texto es el markup interno
de DeepSeek para tool calls, idéntico y byte a byte en las dos (el instrumento
guarda solo los primeros 120 chars, límite abajo):

```
\n\n<｜｜DSML｜｜ calls>\n<｜｜DSML｜｜ invoke name="list_files">\n<｜｜DSML｜｜ parameter name="path" string="true">/home/roquedb/Docum
```

O sea: `tool_choice="none"` no desactiva el menú; **saca la llamada del canal
nativo y la degrada a texto**. En el producto eso no la desactiva: `normalizar`
recupera el texto DSML como tool calls y las ejecuta cuando las tools viajan en
el request (`utils/proveedor.py:93-119`, bloque `dsml_recuperado` en
`:106-112`; se llama desde `nodes.responder_llm` en `nodes.py:383` y desde
`utils/kernel.py:126`). Solo cuando las tools se retiran (`tools=None`) la
recuperación se frena y el markup se ignora (L8, `utils/proveedor.py:115-119`).

**Esto es lectura de código, no una corrida del chat**: el instrumento llamó a
la API directo, sin pasar por `normalizar`. Lo medido es el texto crudo; la
consecuencia en el producto se sigue de `normalizar`, no se midió acá.

## Hallazgo 2: por qué C4 quedó fuera de la ventana (post-hoc declarado)

Post-hoc, a nombre del operador (lo levantó Chief al ver el delta), recomputado
por Laboratorio desde las filas:

- si `none` hubiera contado el sistema o no, se ve en su prompt: **266 tokens
  ≈ el system + el pedido** (933 chars de prosa), no los ~40 de X158 sin
  system. El sistema **se quedó**; el delta 4.913 es **todo tools**.
- el ratio que falló es el de X158: 1.619 chars → 633 tokens dan 2,558
  chars/token en 3 tools chicas; las 30 del chat implican **3,63** chars/token
  (17.840 / 4.913) y el propio request da **3,83** (1.018 chars de mensajes /
  266). Con el ratio del propio request la predicción es **4.662** tokens:
  **5,1 %** del medido, sin residuo que atribuir a otra cosa.

Conclusión: C2 no cambia (`none` no cuenta los esquemas, pre-registrado) y C4
era informativo; la ventana estaba calibrada con un ratio que no transfiere al
menú de 30. Se declara post-hoc y no se reescribe el criterio.

## Qué deja para S3

El "esquema fijo" no tiene por dónde ganar con este proveedor:

1. **Caché**: no hay prefijo compartido. `none` cuenta solo el system + el
   pedido y no reusa la caché que dejó la llamada con tools.
2. **Conducta**: `none` no impide pedir tools; el harness las recupera del
   texto DSML y las ejecuta. La única forma medida/implementada de frenar una
   tool es **retirar `tools`** (L8), que es exactamente lo que cambia el
   prefijo y hoy hace el cierre.

La decisión de S3 (cerrarlo, o re-expresarlo con otro mecanismo) es del
operador/Diseño con este dato delante; esta medición no la toma. Lo que sí
queda medido: **la premisa "mismas tools con `none`" no se sostiene** ni en
caché ni en conducta.

## Límites declarados

- El instrumento guarda **solo los primeros 120 chars** del texto
  (`banco/probes/tool_choice_none_real.py:68`): el markup DSML se ve y es
  idéntico en las dos llamadas, pero no se guardó completo ni se parseó.
- Una sola corrida, un modelo/endpoint (`deepseek-flash` / `api.deepseek.com`)
  y el **prefijo idéntico** (mismas messages + mismas tools): no mide el hit
  parcial de un historial que crece (eso es un A/B de S3, no esta medición).
- No se registró `finish_reason` por llamada.
- La recuperación DSML en el producto es lectura de código; no se corrió el
  chat con `none` (el producto hoy no lo usa).

## Desvíos post-dato declarados

1. La explicación de C4 (ratio chars/token) se escribió **después** de ver los
   datos, a nombre del operador: no es criterio, es atribución.
2. El hallazgo 1 salió de mirar el texto crudo que el pre-registro no anticipó
   como estado posible (el spec preveía `tool_calls=0` como bueno); se informa
   como hallazgo, no como criterio pre-registrado.
3. Los docstrings del instrumento decían "los cinco estados" (son cuatro, con
   siete casos de autotest): se corrige en este mismo pase de docs, cosmético,
   sin cambio de conducta (el instrumento que corrió es `cddf656`).

## Reproducir

```
python3 banco/probes/tool_choice_none_real.py --autotest   # 7 casos, sin red
python3 banco/probes/tool_choice_none_real.py --dry-run    # 4 requests, sin red
python3 banco/probes/tool_choice_none_real.py              # 4 llamadas
```

El JSONL de esta corrida quedó en `salidas/` (ignorado por git) con su hash y
`head` en el resumen; el informe no reemplaza al instrumento.
