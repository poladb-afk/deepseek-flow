# Pre-registro — fase 4b-mín de elegancia: `alcance_amplio` sin la regex de palabras

**Estado:** pre-registrado el 2026-10-28, ANTES de borrar nada. Decisión del
operador: 4b-mín en vez del presupuesto por novedad (exp/52-B ya midió que la
redundancia real del chat es ≈0: no hay nada que la novedad recorte).

## Hipótesis

`alcance_amplio` decide con tres señales: palabras de totalidad
(`_PALABRAS_AMPLIAS`, una regex de vocabulario — hardcodeo), un directorio
mencionado con ≥ 10 archivos de código, o masa mencionada ≥ 300 líneas (las
dos últimas las cuenta el código contra el disco: datos exactos). La regex
no decide nada que el conteo no decida ya.

## Contrafáctico 1 — los 14 escenarios de fable (calculado, 2026-10-28)

| escenario | con la regex | sin la regex |
|---|---|---|
| s7, s13, s17, s18, s19, s20 | amplio | amplio |
| s1, s2, s3, s9, s10, s11, s15, s16 | — | — |

**Ninguno cambia.** Los seis amplios lo son por el conteo en disco.

## Contrafáctico 2 — preguntas reales (lo corre el operador)

`banco/probes/alcance_sin_palabras.py` lee `salidas/preguntas.jsonl` (origen
web/terminal) y clasifica cada pregunta con y sin la regex. Criterio:

- **0 preguntas** que pasen de amplio a no-amplio → se borra la regex.
- **1 o más** → se listan y se decide CASO POR CASO antes de borrar (si una
  es "todo el repo" sin ruta mencionada, el remedio es que el conteo mire la
  raíz, no volver a la regex).

## Qué se borra si pasa

`_PALABRAS_AMPLIAS` (−1 en `vocabulario_hardcodeado`). Nada más. Sin banco:
la regla es determinista, el contrafáctico ES la medición.

## Resultado (2026-10-28, X104)

Contrafáctico 2 (operador, con el comando del pre-registro): **36 preguntas
únicas · 12 amplias con la regex · 0 dejan de serlo sin ella → PASA**. Se
borra `_PALABRAS_AMPLIAS`. La sonda `alcance_sin_palabras.py` se borra con
ella: sin regex no queda qué comparar.

**Lo que cambia, declarado**: una frase de totalidad SIN ruta mencionada
("revisá todo el repo") ya no sube el tope a 16. En las 36 preguntas reales
no hubo ninguna así; si aparece en producción, el remedio pre-registrado es
que el conteo mire la raíz, no volver a la regex.
