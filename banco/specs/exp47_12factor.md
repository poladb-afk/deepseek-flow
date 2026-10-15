# exp/47 — 12 factor agents: gap analysis del harness contra la metodología

Contexto: el harness ya cita la metodología (design.md habla de "12-factor
#5/#6/#8" en compacción, HITL y evals — numeración de una versión vieja del
repo). Este experimento hace el análisis SISTEMÁTICO: el material oficial
está en `banco/material/12factor/` (13 archivos, el factor 7 es
"contact-humans-with-tools.md"). La tesis del dueño: **PocketFlow envolvería
la metodología** — el harness como implementación PocketFlow-native de los
12 factores.

## El método (patrón exp/19: auditoría dirigida)

POR CADA factor (13 filas): leer su .md y producir

1. **Qué pide** (2-3 líneas, del documento — sin parafrasear de memoria).
2. **Qué tiene el harness** — con EVIDENCIA verificable (archivo o sección
   de design.md). Un "cubierto" sin cita no vale. Para encontrarla:
   grep/search sobre el repo (nodes, modules/, utils/, docs/design.md).
   OJO: la numeración vieja citada en design.md puede no coincidir con la
   del repo — lo que importa es el CONTENIDO del factor, no el número.
3. **Estado**: `cubierto` / `parcial` / `ausente` / `no-aplica` (con motivo).
4. **Si hay gap**: qué pieza lo cerraría AL ESTILO DE LA CASA (un módulo, un
   flow, una arista del grafo, un setting) y esfuerzo S/M/L. La pregunta
   marco: ¿cómo se construiría en PocketFlow (nodos/aristas/shared)?

## El entregable

`salidas/informe_12factor_2026-10-14.md`:

- Tabla de 13 filas (factor | qué pide | evidencia | estado | gap/pieza).
- **Top-3 gaps recomendados** por valor/esfuerzo, cada uno con: por qué
  duele hoy (o va a doler), la pieza PocketFlow que lo cierra, y qué
  experimento lo mediría (número de exp siguiente: exp/48+).
- Una sección corta "PocketFlow y la tesis del factor 8": el repo dice
  "own your control flow / no heavy frameworks" — PocketFlow (100 líneas,
  cero deps) ES esa tesis; el informe lo dice con las propias palabras del
  repo (citar factor-08).
- Honestidad: lo que el repo recomienda y la casa RECHAZÓ con evidencia
  (p. ej. pre-rank de tools exp/15, triaje LLM exp/9) se lista como
  "divergencia informada", no como gap.

## Reglas

- Solo LECTURA del repo + escritura del informe (hitl solo para ese write).
- Cada claim de evidencia se verifica antes de escribirse (grep real, no
  recuerdo).
- El informe es de ~150-250 líneas, sin relleno.
- Numerar los experimentos propuestos a partir de exp/48 (47 es este).

## Candidatos que el conductor YA baraja (verificar CONTRA el código, no
copiar): persistencia/resume de corridas (factor 6 — el mayor ausente
esperado), HITL como arista del grafo (factor 7 — ya anotado en design.md
como pendiente de la Mesa 8), unificación de estado (factor 5 — design.md
documentó colisiones y lo diferido), pre-fetch como política (apéndice 13 —
hoy existe solo ad-hoc en el juez y el catálogo de memoria).
