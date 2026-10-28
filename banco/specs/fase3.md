# Pre-registro — fase 3 de elegancia: razonamiento en las rondas con tools

**Estado:** pre-registrado el 2026-10-28, ANTES de escribir el código de 3a.
Criterio fijado por el operador con las cifras de la base a la vista.

## Hipótesis

Hoy toda llamada con tools viaja con thinking DESACTIVADO (`_kwargs_agente`:
el cliente descarta `reasoning_content` y la API exige devolverlo con tools).
Preservar el `reasoning_content` de las rondas con tools y prender el
thinking ahí mejora la calidad de las auditorías (s17/s18, los escenarios que
no están en el techo), a un costo acotado.

## Gate previo (antes de cualquier corrida del banco)

Una sonda contra la API real que reproduzca las secuencias de los 400 de la
bitácora (2026-10-05: flips ON→OFF y OFF→ON dentro de la conversación, la
llamada del tope sin tools) con el historial NUEVO (reasoning preservado).
0 errores 400 en las secuencias, o 3a no se corre.

## Corridas

Brazo A, s17 ×5, s18 ×5, s19 ×3, s20 ×3, sobre el árbol de la última fase
aprobada (base) y sobre 3a.

## Criterios (todos)

1. **Mejora por encima del ruido**: la suma de `correct_action` de s17 + s18
   (10 seeds) sube al menos **2 puntos** sobre la base.
2. **Nada empeora**: ningún escenario baja su suma (s19 y s20 están en el
   techo: solo pueden empatar).
3. **Costo en dinero, no en tokens**: el reasoning se cobra como completion
   y el caché abarata el prompt, así que tokens y USD pueden decir cosas
   opuestas. Mediana de USD por corrida (desglose de exp/90) ≤ **1,5 ×** la
   de la base, por escenario.
4. **Sin ganancia de calidad no entra**, aunque cueste lo mismo: el thinking
   en rondas con tools suma latencia y un riesgo conocido (los 400).
