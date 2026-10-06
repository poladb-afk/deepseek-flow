# Spec: `minar_errores.py` — taxonomía de errores de tools en las trazas

(exp/9 — la escribe el revisor; la aplica el harness. Pregunta que responde:
¿los errores de tools se autocorrigen (reintento con éxito) o se repiten y
se abandona? Esa tasa decide si un triaje automático con Laya agrega valor.)

## Objetivo

Un script determinista (SIN LLM, SIN red, SIN torch — JSON puro) que mina
todas las trazas `.runs/*.jsonl` y produce la evidencia de los errores de
tools: frecuencia, firma de duración (timeouts), qué pasó después de cada
error (¿reintentó la misma tool? ¿tuvo éxito?) y sesiones afectadas.

## Límite honesto (documentarlo en el docstring)

Las trazas NO guardan el texto del error: `evento_tool` registra solo
nombre + ok/error + segundos. No se puede clasificar causa (red vs args)
desde la traza — lo que SÍ se puede medir es frecuencia, duración (un
timeout de run_command firma en ~120 s) y el destino del reintento. El
informe debe decir esto explícitamente.

## Detalle de heurística (documentarla también)

Los rechazos HITL de run_command devuelven "RECHAZADO…" que NO empieza con
"ERROR", así que en la traza cuentan como ok con duración casi nula: un
evento ok de run_command con seg < 0.5 es PROBABLE rechazo (heurística,
no certeza). Reportarlo como categoría separada con su caveat.

## Uso

    python3 minar_errores.py [--carpeta .runs] [--salida salidas/evals]

## Requisitos

1. **Reuso**: importar `_leer_eventos` de evals (mismo parseo tolerante a
   trazas corruptas — una traza rota es artefacto a saltear, no excepción).

2. **Funciones PURAS** (importables y testeables, sobre listas de eventos
   ordenados por ts de UNA sesión):
   - `es_timeout(ev, umbral=100.0)` — evento de error con seg >= umbral.
   - `es_rechazo_probable(ev)` — ev ok, nodo "run_command", seg < 0.5.
   - `destino_del_reintento(eventos, ev)` — dado un evento de error de la
     tool T en ts X, busca el PRÓXIMO evento de T en la misma sesión:
     devuelve None (no hubo), o dict {ok: bool, delta_seg: float}.
3. **Agregados** (sobre todas las sesiones):
   - Por tool: total errores, timeouts, reintentos (hubo próximo evento),
     reintentos con éxito (próximo ok), abandono (sin próximo evento),
     delta mediano del reintento.
   - Global: sesiones totales, sesiones con errores, errores por sesión,
     rechazos-probables totales, y la TASA clave: errores seguidos de
     reintento exitoso / errores totales (la tasa de autocorrección).
4. **Salidas**: `salidas/evals/errores_mineria.md` (tablas + la tasa de
   autocorrección destacada + el límite honesto arriba) y
   `errores_mineria.json` (máquina, con fecha, git-sha y por-tool). Patrón
   de laya_evidencia_*.
5. Estilo del proyecto: standalone en raíz, main(argv=None), argparse,
   comentarios en español con el PORQUÉ.

## Fuera de alcance

No integrar Laya, no tocar otros archivos, no clasificar causas (imposible
desde la traza), no modificar evals.py.
