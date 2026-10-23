# Spec de ejecución — exp/89: tokens por llamada — la métrica first-class que faltaba

**Estado:** ejecutada el 2026-10-22; C1-C4 OK. Es el ítem pendiente de Mesa 1 ("costo por
sesión (tokens/latencia) como métrica first-class derivable de las trazas") y la conclusión #2
de la comparativa del paper: "el próximo experimento con retorno real no es una capability más,
es instrumentar tokens por pregunta".

## Diagnóstico

`costo_traza` (evals) mide SEGUNDOS; ninguna llamada registra su `usage` (el cliente descarta
`response.usage` de la API). Sin tokens por llamada no hay costo por pregunta, ni ROI del
router medible en dinero, ni señales para decidir dónde recortar contexto.

## Diseño

- **Captura** en los cuatro caminos de `utils/call_llm.py` (`call_llm`, `call_llm_agent`,
  `call_llm_agent_stream` —con `stream_options={"include_usage": True}` para que el último
  chunk traiga usage—, `call_llm_async`): SIN contenido, solo `prompt_tokens` y
  `completion_tokens` (F4: la traza no guarda contenido; el usage es un número).
- **Registro en dos niveles**: (a) `tracing.evento_llm(pt, ct)` → `.runs/*.jsonl` (un evento
  por llamada, mismo esquema espíritu que evento_hitl); (b) acumulador por proceso
  (`uso_de_sesion()`) para el reporte de salida.
- **Reporte**: al salir del chat, junto al resumen de sesión: `[tokens] sesión: N llamadas —
  X prompt + Y completion`. Best-effort, nunca corta la salida.
- **evals**: `tokens_traza(eventos)` agrega los eventos llm de una traza; la sección de costos
  del informe suma la columna tokens (las trazas VIEJAS no tienen eventos: se declara, el
  conteo empieza de cero).

## Criterios

- **C1:** tests sin red: cada camino registra el usage de una respuesta falsa (SimpleNamespace)
  en el evento y en el acumulador; el camino streaming lo saca del último chunk; una respuesta
  SIN usage no rompe (cuenta 0 y sigue).
- **C2:** e2e mínimo: una corrida real del chat (un turno) imprime el reporte `[tokens]` con
  números > 0 y deja eventos llm en `.runs`.
- **C3:** `evals` informa tokens por sesión sobre una traza con eventos.
- **C4:** gate verde. Privacidad: el evento NO lleva ni contenido ni pregunta — solo números
  (mismo contrato social que el resto de la traza).

## Fuera de alcance

Costo en dinero (precios del proveedor), presupuesto de tokens por pregunta (recién con datos),
el roteo por costo, cambiar el resumen de sesión de memoria.


## Resultado (2026-10-22)

C1 ✅ (los tres tests de captura: acumulador+evento, sin-usage no rompe,
streaming con stream_options y chunk final sin choices); C2 ✅ e2e real: el
chat imprime `[tokens] sesión: 1 llamadas — 5.009 prompt + 1 completion` al
salir y el evento queda en .runs sin contenido; C3 ✅ tokens_traza sobre la
traza real; C4 ✅ gate verde (891 tests). Primer dato visible del producto:
**el system prompt cuesta 5.009 tokens de prompt por llamada** — hasta hoy
era invisible.
