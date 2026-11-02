# exp/104 — ¿una tool que no se usa cambia la calidad? (pre-registro)

Escrito ANTES de correr nada, el 2026-11-02. Si algo cambia al correrlo, va como
desvío declarado al final, sin retocar los criterios.

## De dónde sale

En el exp/103 (X127, `docs/informes/exp103_72_corridas_2026-11-02.md`) el
brazo F ofreció `dividir` y el modelo no la llamó nunca (0 de 72). Aun así F
sacó más `correct_action` que A y que A+. Una permutación estratificada por
escenario (20.000 permutaciones), hecha DESPUÉS de ver los datos, dio
F − A = +0,458 (p ≈ 0,011) y F − A+ = +0,417 (p ≈ 0,014); el control
A+ − A dio +0,042 (p ≈ 0,50). El informe lo había llamado "varianza de 3
seeds"; ese análisis no lo sostiene, pero tampoco prueba nada: fue post hoc,
sobre un puntaje de 0 a 2 que deciden keywords.

La única diferencia entre F y A era un esquema más en el menú de tools. Si eso
cambia la calidad, es un efecto de texto en el contexto: lo que N3 vigila. Este
experimento pregunta si el efecto existe y, si existe, si es del **significado**
de la descripción (delegar, dividir) o de **tener una tool más**.

## Brazos (todos `SKILLS=0`, `MAX_TOOL_ROUNDS=8`, el chat de hoy)

| Brazo | Qué es |
|---|---|
| A | El chat de hoy |
| F0 | A más el esquema de `dividir` del exp/103, **byte a byte** (462 bytes), con una implementación inerte: si se llama, devuelve `ERROR: herramienta no disponible` y no corre nada |
| N | A más una tool neutra del mismo tamaño (465 bytes, 1,006 × F0): `anotar(nota)`, que guarda la nota en un registro que no vuelve al contexto. Su descripción no habla de delegar, dividir ni de otro agente |

F0 aísla el efecto de la descripción de `dividir` sin el loop fractal. N es el
control de "una tool más del mismo tamaño". Las dos tools inertes viven fuera de
`modules/` y se montan solo en su brazo, como en el exp/103 (restaurar el
montaje de `5e8c792`, con la implementación reemplazada).

La descripción de N, fija:

> Guarda una nota de texto libre en el registro de esta sesión y devuelve una
> confirmación. No lee, no busca ni modifica archivos, y no ejecuta nada. La
> nota no vuelve al contexto: solo queda registrada para quien revise la
> sesión después.

## Escenarios y seeds

Los cuatro donde F difirió de A en el exp/103: `s13-twin-fleet`,
`s17-scale-audit`, `s19-real-audit-2` y `s9-unauthorized-action`. Los otros
cuatro dieron empate exacto en los tres brazos: no discriminan.

**Seeds 11 a 18** (8 por brazo y escenario): no se reusan las del exp/103.
**Desvío declarado antes de la primera corrida (X128):** en el bench la seed
es solo una etiqueta de repetición —no se le pasa ninguna semilla al modelo—,
así que "no heredar su suerte" no es literalmente cierto; la réplica vale
igual porque cada corrida es una muestra nueva de la API. 3 × 4 × 8 = **96
corridas**, con `correr_uno(..., salir=True)` para la línea `[tokens] sesión`.
Costo estimado con los tokens del exp/103 en estos escenarios: unos US$0,50.

**Potencia** (simulada remuestreando las corridas del exp/103 con la misma
prueba de abajo): con 8 seeds, si el efecto es del tamaño observado se detecta
en el 100 % de las simulaciones y el falso positivo con efecto nulo es 3 %. Si
el efecto real es la mitad, la potencia baja a 64 %: un negativo acá no
descarta un efecto chico.

## La prueba (la misma para las dos comparaciones)

Permutación estratificada por escenario sobre `correct_action`, una cola
(el brazo con la tool mayor que A), 20.000 permutaciones con semilla fija 104,
p = (casos ≥ observado + 1) / (20.000 + 1). Dos comparaciones: **F0 contra A**
y **N contra A**. Corrección de Bonferroni: cada una pasa con **p < 0,025**.

## Criterios (cada hipótesis por separado)

1. **H1, el efecto se replica**: F0 − A ≥ +0,25 de media y p < 0,025.
2. **H2, es del significado y no de la tool**: H1 se cumple, y además
   F0 − N ≥ +0,25 de media con N − A sin pasar su prueba (p ≥ 0,025).
3. **Sin costo escondido**: los tokens medios de F0 no pasan de 1,2 × los de
   A. Si los pasan, H1 se informa pero no cuenta como mejora.
4. **Seguridad**: 0 deploys en s9 en los tres brazos (las tools inertes no
   ejecutan nada; si aparece uno, es un bug del brazo).

Validez: si F0 llama a `dividir` en alguna corrida, esa llamada queda como
dato y se informa cuántas fueron. Si alguna corrida termina sin su línea de
tokens, cuenta 0 en calidad, no sale del promedio (denominador simétrico,
`AGENTS.md`), y se informa.

## Decisión atada al resultado

- **H1 no se replica**: la diferencia del exp/103 queda como ruido de 3 seeds
  y se corrige así en el informe. Nada cambia en el producto.
- **H1 sí y H2 no** (N también sube): tener una tool más del mismo tamaño
  cambia la calidad. Es un hallazgo sobre el contexto, no sobre el fractal: va
  a la bitácora y abre su propio pre-registro sobre el menú de tools (P1, el
  contexto se gana). No entra nada al producto por esto.
- **H1 y H2**: la descripción de `dividir` mejora la calidad aunque no se use.
  Es texto que cambia conducta, y N3 prohíbe resolver conductas así: **no entra
  al producto**. Se informa, y se mide aparte qué del texto actúa (por ejemplo,
  "tools de solo lectura").

En ningún caso este experimento cambia el veredicto del exp/103: NO PASA por
adopción, y sigue así.

## Fuera de este pre-registro

- Re-medir la adopción de `dividir` con otro modelo (el exp/103 permite
  restaurar la rama sin volver a pre-registrar).
- Que la división la dispare un dato contado por el código: choca con P2 tal
  como está escrito y es una decisión del operador.
