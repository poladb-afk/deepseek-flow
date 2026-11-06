# s3 — la 4.ª medición de `tool_choice="none"`: ¿el prefijo se comparte con las tools? (pre-registro)

**Estado: pre-registro, escrito ANTES de correr la medición y ANTES de que exista
la corrida (2026-11-06, HEAD `000c8d0`).** Es una medición de laboratorio: no
toca producto y **no decide la adopción de S3**; decide un solo dato que S3
necesita antes de pre-registrarse. Si algo cambia al correrlo, va como desvío
declarado al final; los criterios no se retocan después de ver los datos.
El pre-registro y el instrumento van en un commit **antes** de la corrida: el
JSONL de la corrida cita ese commit (`head`), así el orden queda como evidencia.

## La pregunta

X158 midió, con **3 tools y sin system prompt**, que DeepSeek acepta
`tool_choice="none"` y no devuelve tool calls (`docs/bitacora.md:1952-1996`),
pero dejó la salvedad abierta: el prompt cayó de **673 a 40 tokens** y la caída
de 633 es exactamente el tamaño de las 3 tools, o sea que el proveedor **no las
cuenta** cuando el parámetro está en `none`; y el `cache_hit=0` de la repetida
no informa porque 40 tokens queda por debajo del mínimo cacheable
(`docs/bitacora.md:1981-1991`). El tablero (`docs/estado.md:158`) y el roadmap
(`docs/roadmap.md:110`) piden por eso una **cuarta medición con prompt
realista** antes de que S3 se apoye en el prefijo fijo.

La pregunta, una sola: **¿el prefijo del request se comparte con y sin tools?**
En concreto, con el menú real del chat (system prompt real + las 30 tools):

1. ¿el proveedor **cuenta los esquemas** de las tools en `prompt_tokens` cuando
   `tool_choice="none"`?
2. ¿una segunda llamada idéntica **reporta caché**, y la llamada con `none`
   **comparte** la caché que dejó la llamada con tools?

**Por qué importa.** El cierre por arista de S3 (esquema de tools fijo) solo
ahorra el prefijo si el request con `none` cuenta lo mismo que el request con
tools y el proveedor cachea ese prefijo. Si no, el esquema fijo ahorra código
(no retirar `tools` en el cierre) pero **no** ahorra prompt, y S3 no puede
apoyarse en el caché.

## Lo que se mide: cuatro llamadas, en este orden

| # | Etiqueta | tools | `tool_choice` | Para qué |
|---|---|---|---|---|
| 1 | `base` | las 30 del chat | **ausente** (el `auto` de hoy) | el request de hoy byte a byte salvo la pregunta y `max_tokens`: referencia de `prompt_tokens` **con** tools |
| 2 | `base_repetida` | las 30 | ausente | control de que el prefijo literal **es cacheable** a este tamaño (sin este control, el `cache_hit` de `none` no informa) |
| 3 | `none` | las 30 | `"none"` | ¿acepta con el menú real? ¿`tool_calls=0`? ¿cuenta los esquemas? ¿comparte la caché de 1–2? |
| 4 | `none_repetida` | las 30 | `"none"` | control de caché de la propia llamada `none` |

Las cuatro van **en un solo proceso, back-to-back y sin otro tráfico a la API
en el medio**: la medición de caché depende del orden, no del reloj.

**Construcción exacta del request** (verificada al escribir esto):

- system prompt **real** del chat: `main.system_prompt()` (`main.py:47`), 894
  chars con el CWD del repo, y es el primer mensaje de `shared` (`main.py:117`);
- menú **real**: `nodes.TOOLS` (`nodes.py:153-154`), **30 tools**, 17.840 chars
  de JSON (`ensure_ascii=False`); sin filtro de skill (es el primer request de
  una pregunta: `nodes.py:408`);
- el builder es el del chat: `_kwargs_agente(mensajes, tools)`
  (`utils/call_llm.py:157-204`), que es lo que usa `call_llm_agent`
  (`utils/call_llm.py:207-213`); incluye `extra_body={"thinking":
  {"type": "disabled"}}` y **no** manda `tool_choice` en el caso base;
- la pregunta: `"Listá los archivos del directorio actual."` (la misma de X158,
  para que la única diferencia con X158 sea el menú real);
- modelo y endpoint pineados: `deepseek-flash` en `https://api.deepseek.com`
  (`utils/call_llm.py:83-84` y `:76-80`), tal como el chat;
- `max_tokens=64`: un tope de salida del instrumento para acotar el costo (el
  chat real no lo manda; no toca prompt ni caché, se declara abajo).

## Métricas (por llamada)

- `acepta` (HTTP 200) o el error exacto;
- `tool_calls` (cantidad) y `texto` (primeros 120 chars);
- `prompt_tokens`, `completion_tokens`, `total_tokens`;
- `prompt_cache_hit_tokens` y `prompt_cache_miss_tokens` cuando el proveedor los
  informe (`None` si no);
- en el resumen: `modelo`, `n_tools`, `chars_system`, `chars_tools`,
  `sha_prefijo` (sha256 del system prompt + el JSON de tools), `head` (commit),
  la fecha del run y el estado de los criterios de abajo.

## Criterios (estados de la medición; no hay "pasa/no pasa" del producto)

- **C0 — el request es estable.** Por construcción las cuatro llamadas salen del
  mismo builder (mismo `modelo`, mismo `n_tools`, mismo `sha_prefijo`; el
  instrumento arma los cuatro requests una sola vez); y se verifica el conteo
  determinista: `prompt_tokens(base) == prompt_tokens(base_repetida)`. Si C0
  falla, es **SIN DATO**: el instrumento o el prompt no son estables y no se
  informa nada del proveedor.
- **C1 — el parámetro sirve con el menú real.** Las dos llamadas con `none`
  aceptan y devuelven `tool_calls=0`. Falla si aparece un 400 que nombre
  `tool_choice`, o si alguna de las dos devuelve tool calls.
- **C2 — el proveedor cuenta los esquemas en `none`.**
  `prompt_tokens(none) == prompt_tokens(base)` → **las cuenta**;
  `delta = base − none ≥ 10 tokens` → **no las cuenta** (el delta se informa y
  se atribuye con C4); `delta ≤ −10` → **SIN DATO** (`none` cuenta más que la
  base: el prompt cambió de otra forma, no es la omisión esperada);
  `|delta| < 10` → **indeterminado** (SIN DATO sobre C2: el conteo es
  determinista para el mismo input, así que una diferencia chica no alcanza
  para atribuir la omisión de 17.840 chars de esquemas, pero tampoco la
  descarta).
- **C3 — la caché se comparte.** Control: `base_repetida.cache_hit > 0` (si el
  control falla, no hay dato de caché y el estado es SIN DATO). Con el control
  ok: `none.cache_hit > 0` y `none_repetida.cache_hit > 0` → **compartida**;
  si `prompt_tokens` es igual pero los `cache_hit` de `none` son 0, el tamaño
  coincide y la caché **no** se comparte. Los valores absolutos y los
  `cache_miss` se informan igual.
- **C4 — atribución del delta (informativo, no criterio).** Si C2 dice "no las
  cuenta", el delta debería ser del orden del tamaño de las 30 tools:
  predicción de **6.974 tokens** con el ratio medido en X158 (17.840 chars /
  2,558 chars por token); fuera del ±25% (5.231–8.718) se reporta "no
  atribuible" y **no** se usa para concluir nada.

## Decisión atada al resultado (qué le queda a S3)

- **PREFIJO COMPARTIDO** (C0 ∧ C1 ∧ C2 "las cuenta" ∧ C3 "compartida"): con el
  menú real, `none` conserva el tamaño contado del prompt y comparte la caché
  que dejó el request con tools. **La salvedad de X158 queda cerrada**: S3 se
  pre-registra apoyado en el esquema fijo (mismas tools, `none` en el cierre),
  en su propio spec.
- **PREFIJO NO COMPARTIDO** (C0 ∧ C1, y C2 "no las cuenta" **o** C3 "no
  compartida"): S3 se pre-registra **sin apoyarse en la caché**: el esquema fijo
  deja de ser un ahorro de prompt y queda solo el ahorro de código (no retirar
  `tools` en el cierre). Si C4 atribuye el delta a los esquemas, el dato es más
  fuerte; si no, se informa como no atribuible.
- **NO VIABLE** (¬C1): con el menú real de 30 tools, `none` no sirve (400 o pide
  tools igual). S3 se cierra como no viable con este proveedor y se documenta
  la diferencia con X158 (3 tools): el tamaño del menú cambia la conducta.
- **SIN DATO** (¬C0, o C3 sin control, o C2 indeterminado, o error operativo):
  no decide. Se repite **una vez** la corrida completa con este mismo spec, sin
  cambiar nada; si el segundo intento vuelve a dar SIN DATO, se publica como
  medición sin dato y S3 queda como está (no se fuerza una conclusión).

## Qué invalida la corrida (no es dato del proveedor)

- 503, red caída, timeout, clave ausente o cuota: el instrumento sale con código
  ≠ 0 y **sin veredicto**; se reintenta una vez el set completo (declarado).
- Un 400 que **no** nombre `tool_choice` (tools inválidas, modelo, parámetro
  desconocido): error operativo, no veredicto.
- `usage` ausente o `prompt_tokens=0`, o campos de caché ausentes en las cuatro
  llamadas: SIN DATO (no se imputa un número).
- `sha_prefijo` distinto entre llamadas (system prompt con algo variable): SIN
  DATO.
- Que el modelo escriba mucho o pida tools en `base` **no** invalida: `max_tokens`
  puede truncar la salida y el prompt/caché no dependen de ella; si trunca una
  tool call, se informa y no toca C1 (que se mide en `none`).
- Si en la corrida `len(nodes.TOOLS) != 30`, no invalida (base y `none` usan el
  mismo menú); se informa `n_tools` y la lectura de "menú real" se hace contra
  ese número.

## Costo y regla de gasto (fijada antes de correr)

- Prompt proyectado: 18.858 chars del request real (system + mensajes + tools)
  ≈ **7.400 tokens** por llamada con el ratio de X158; cuatro llamadas
  ≈ 29.600 tokens de prompt en el peor caso (todo miss) + 4 × 64 de completion.
- Tarifa `deepseek-flash` (`utils/costos.py:23-28`): miss 0,15 / completion 0,60
  USD por millón → proyección **US$0,005**.
- **Techo: US$0,05** (10× la proyección), que cubre un set completo de
  reintento. Si el primer set da datos completos, **no se reintenta**.
- Una sola corrida a la vez; ningún `./calidad.sh` en paralelo (el 8791 de HITL
  colisiona) ni otro experimento en el medio.
- La corrida la corre **Chief con autorización del operador** (como X158).
  Laboratorio escribe el pre-registro, el instrumento y el informe; no gasta.

## Instrumento

- **`banco/probes/tool_choice_none_real.py`** (nuevo, de Laboratorio): las 4
  llamadas; importa el system prompt real (`main.system_prompt`), `nodes.TOOLS`,
  `_client` y `_kwargs_agente` (no toca producto); imprime una línea JSON por
  llamada y un resumen con el estado de C0–C4; escribe el JSONL en
  `salidas/tool_choice_none_real/<timestamp>.jsonl` (ignorado por git).
- **Sin red**: `--autotest` corre el veredicto sobre filas sintéticas (los cuatro
  estados posibles, con tres casos de SIN DATO: control de caché fallido, delta
  indeterminado y `none` que cuenta más) y `--dry-run` imprime los cuatro
  requests (modelo, tools, chars, `tool_choice`, `extra_body`) **sin mandar
  nada**. La corrida real es sin flags.
- Comandos de la corrida:
  ```
  python3 banco/probes/tool_choice_none_real.py --autotest   # sin red
  python3 banco/probes/tool_choice_none_real.py --dry-run    # sin red
  python3 banco/probes/tool_choice_none_real.py              # 4 llamadas
  ```
  La clave sale del `.env` del repo o del entorno, como el chat (`_client`,
  `utils/call_llm.py:65-80`).

## Desvíos declarados desde el inicio

1. **`max_tokens=64`** en las cuatro llamadas: el chat real no manda ese
   parámetro. Es un tope de gasto del instrumento; no cambia el prompt ni el
   prefijo cacheado (parámetro de generación), y se declara porque el request
   de `base` no es literalmente el del chat. Las cuatro (también `none`) viajan
   con el `extra_body` de thinking disabled que manda el chat
   (`_kwargs_agente`), que X158 tampoco mandaba: ninguna de las dos cosas toca
   el prompt.
2. **El menú son las 30 tools del chat, no las 3 de X158** (diferencia
   declarada, no desvío): es el diseño de la medición (prompt realista); X158 y
   esta medición **no** se comparan en tokens absolutos, solo se usa su ratio
   chars/token para C4.
3. El system prompt incluye el CWD y las raíces permitidas del entorno
   (`main.system_prompt`), así que sus 894 chars pueden variar con el entorno:
   se registran chars y `sha_prefijo` reales en el JSONL.
4. El conteo de tokens es del proveedor: no se estima ni se corrige. Si el
   proveedor no informa caché, C3 queda SIN DATO; no se infiere del tiempo.
5. **Límite de la conclusión**: se mide el prefijo **idéntico** (mismas
   messages + mismas tools). En el cierre real de S3 el historial crece y el
   `none` comparte con él solo el prefijo común; el hit parcial de ese caso lo
   mide el A/B de S3, no esta medición. Acá se mide el tamaño contado y que el
   proveedor cachea ese prefijo con tools + `none`.
6. La corrida es de un solo modelo y endpoint (`deepseek-flash` /
   `api.deepseek.com`): no se generaliza a otros.

## Fuera de alcance

- Implementar S3, el cierre por arista o cualquier cambio de producto.
- Medir el hit de caché de un historial que crece (eso es el A/B de S3).
- Otros modelos, endpoints o `tool_choice` distintos de ausente y `"none"`.
- Reintentar re-montajes o cambiar el menú: si `n_tools` no es 30, se informa,
  no se ajusta para que dé 30.

## Después de correr

Con el resultado: informe en `docs/informes/` (con las 4 filas crudas y el
estado de C0–C4), la medición en `docs/bitacora.md`, y la fila del tablero en
`docs/estado.md` con el veredicto y el path del JSONL. Si el estado es
PREFIJO COMPARTIDO o NO COMPARTIDO, recién ahí se escribe el pre-registro de
S3 con el dato delante; nada de S3 se toca antes.
