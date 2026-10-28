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

**La sonda** (agregado antes de correrla): `banco/probes/thinking_tools.py`,
seis secuencias — A ronda y respuesta, B el cierre sin tools, C el rechazo
del HITL (s19-s3: rechazo → error → respuesta), D pregunta nueva tras un
turno con tools, E compacción (la zona fría pierde el reasoning), F el flip
(historial armado con thinking OFF, la ronda siguiente con ON). Arma cada
request con `_kwargs_agente(..., pensar=True)`, el mismo builder que usaría
el chat. Un error que no es 400 deja la secuencia sin veredicto: se repite.

**Por qué E y F importan**: si dan 400, el chat no puede activar la fase 3
tal cual — la compacción tendría que conservar el reasoning de toda unidad
con tool_calls que quede en la ventana (o compactar unidades enteras), y un
`resume` de una sesión vieja (sin reasoning) tendría que arrancar con
thinking OFF hasta la próxima pregunta. El diseño del cableado en el chat
depende de este resultado: por eso se escribe DESPUÉS de la sonda.

## Resultado de la primera corrida y gate redefinido (2026-10-28)

**Primera corrida (operador, en vivo)**: A, B, C, D, E ok; **F 400**
(`reasoning_content in the thinking mode must be passed back`). El gate
original NO PASÓ y así queda registrado.

**Lectura**: en E el mensaje sin reasoning era de un turno ANTERIOR (antes
del último `user`) y pasó; en F estaba en el turno EN CURSO y dio 400.
Hipótesis: la API exige el reasoning solo en los assistant con tool_calls
posteriores al último mensaje del usuario (coincide con cómo lo resolvió
LangChain: preservar desde el último mensaje humano). Dos datos no alcanzan:
la doc dice "todas las requests subsiguientes", que es más estricto.

**Gate redefinido, fijado ANTES de correr las secuencias nuevas**:
- **G** (turno entero con thinking OFF y tools; la pregunta siguiente con ON
  y tools) tiene que dar ok. Si da 400 la regla es la estricta: el reasoning
  tendría que conservarse para siempre (compacción y `resume`) y la fase 3
  se reconsidera.
- A–E siguen teniendo que dar ok.
- **F** queda como informativa: documenta la restricción del proveedor. El
  chat de 3a la hace imposible por construcción (el modo se fija una vez por
  pregunta en `turno["pensar"]`) y un test lo clava.
- **H** (rondas ON y el cierre de ese turno OFF) es informativa y sin
  predicción: si da ok, `Cierre` y `VerificarCitas` pueden quedar OFF; si da
  400, el modo es fijo para TODA la pregunta, cierre incluido.

**Diseño de 3a si G pasa** (lo escribe el autor después de la segunda
corrida):
- `turno["pensar"]` fijado al empezar la pregunta; todas sus llamadas lo usan.
- `historiar` conserva el reasoning del turno en curso; `GetQuestion` lo
  descarta de los anteriores (respeta la regla y ahorra tokens).
- Invariante 1 de la compacción: de "sin reasoning en ningún mensaje" a
  "reasoning solo después del último `user`"; `validar_historial` y
  `thread_store.valido` igual (si no, `resume` rechazaría los checkpoints).
- Un setting TEMPORAL para prender 3a en el A/B (decisión del operador:
  `settings_leidos` 78 → 79 con su clave del ratchet; en el inventario como
  "borrar en 3b", cuando el modo lo elija Laya).

## Caso a seguir

s19-s3 en la base de 2d (ca=0): pidió un comando fuera del scope, el HITL lo
rechazó y escribió el informe sin verificar. Es el perfil donde razonar
entre rondas podría cambiar la respuesta; queda como caso a mirar en el
reporte de 3a (no es criterio: es una corrida).

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
