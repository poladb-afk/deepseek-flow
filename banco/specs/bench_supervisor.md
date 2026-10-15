# Bench: supervisor reactivo vs agente PLANO con tool-calling nativo

La pregunta sin respuesta medida: ¿el supervisor actual (Laya elige herramienta
+ mayoría 2-de-3 en la duda + DeepSeek redacta args = hasta 3 llamadas remotas
por paso) le gana a un agente DeepSeek plano con tool-calling nativo sobre las
mismas herramientas (1 llamada por paso: elige herramienta Y args juntos)?
El roadmap tiene "Choose a escala (~2.400 casos)" — ese gasto se GATEA con
este bench: si el plano empata, el despacho se simplifica y los vetos/self-
healing (que son código) se quedan; si el supervisor gana, se escala.

## La pieza: `banco/bench_supervisor.py` (standalone, como bench_juez.py)

### Tareas — `banco/supervisor_tareas.jsonl`

6 tareas cortas, cada una verificable por CÓDIGO PURO (grading dinámico: la
verificación calcula la verdad al momento, sin constantes que deriven):

1. `contar-utils`: "¿Cuántos archivos .py hay exactamente en la carpeta
   utils/? Respondé con el número y cómo lo obtuviste." — verificar: el texto
   contiene str(len(list(Path('utils').glob('*.py')))).
2. `constante-max-pasos`: "¿Cuál es el valor de MAX_PASOS en supervisor.py?"
   — contiene "5".
3. `firma-veredicto`: "¿Qué devuelve la función veredicto() de utils/laya.py
   y con qué umbrales compara por defecto?" — contiene "met" y "0.85"
   (lee el archivo al gradear: si la constante cambiara, el grading la busca
   con regex `alto.*?([\d.]+)` — mejor: contiene 'met' y 'uncertain').
4. `tablas-trazas`: "¿Cuántas tablas tiene la base trazas.db? Usá la tool de
   esquema." — verificar: sqlite3 `SELECT count(*) FROM sqlite_master WHERE
   type='table'` y el texto contiene ese número.
5. `linea-marcadores`: "¿En qué línea de banco/banco.py está definido el
   dict MARCADORES? Da archivo:línea." — verificar: busca con regex la línea
   real (`^\s*MARCADORES` en el archivo) y el texto contiene ese número.
6. `conteo-routing`: "¿Cuántas decisiones (líneas) tiene hoy salidas/
   routing.jsonl? Decí el número." — verificar: `len(open(...).readlines())`
   (si el archivo no existe, la tarea se salta con motivo).

Una línea por tarea: `{"id", "tarea"}`. Las VERIFICACIONES viven en el
script (dict id → callable(texto) -> bool) — código puro, testeable.

### Las dos vías

- **Supervisor**: `supervisor.supervisar(tarea, salida=tmp)` tal cual es
  (nada se toca del supervisor). El informe final es el texto a gradear.
- **Agente plano** (nuevo, en el bench): un bucle mínimo con el MISMO action
  space que el supervisor (`supervisor._TODAS` + `supervisor.REGISTRO`,
  anti-recursión incluida) vía `call_llm_agent` con tool-calling nativo:
  system corto ("resolvé la tarea con las tools, hasta N rondas, luego
  respondé"), user = tarea, loop hasta 8 rondas de tools o respuesta sin
  tool_calls (ejecutar con `fs_tools.run_tool_call` para heredar hooks);
  el texto final es la respuesta a gradear. MISMO presupuesto de pasos que
  el supervisor (5 ejecuciones de tools máx: a la 8ª ronda se retiran las
  tools y debe responder).

### Métricas (las tres, por tarea y total)

- **llamadas remotas**: contar envolviendo `utils.call_llm.call_llm` y
  `utils.call_llm.call_llm_agent` con contadores (decorador en el bench;
  el contador es función pura testeable).
- **tiempo de reloj** por tarea.
- **calidad**: la verificación determinista (1/0) por tarea.

Salida: markdown `salidas/evals/bench_supervisor_FECHA.md` con la tabla
(tarea | vía | ok | llamadas | seg) + totales y el veredicto agregado, y el
JSONL crudo al lado. Baseline al estilo de la casa: comparar sin pisar
(`--actualizar-baseline` explícito; default es solo comparar/informar).

Contención: un crash de una vía en una tarea NO tira el bench (ese celda
queda "error" con el motivo, patrón exp/20).

## Tests (sin LLM; fakes inyectables)

1. Cada verificación con un texto que pasa y uno que no (incluida la
   dinámica de contar-utils).
2. El contador de llamadas envuelve y cuenta (fake).
3. El bucle del agente plano con `call_llm_agent` fake: 2 rondas de tools y
   respuesta → ejecuta las tools (IMPL fake), devuelve el texto final y el
   conteo de rondas respeta el tope (a la última ronda va sin tools).
4. `banco/supervisor_tareas.jsonl` carga y cada id tiene su verificación.

## Uso

`python3 banco/bench_supervisor.py [--solo supervisor|plano] [--tareas n]`

## Candado final

pytest verde y ruff limpio. No modificar supervisor.py ni nodes.py.
