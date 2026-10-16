# Sonda del flip de thinking — el hallazgo ALTO no se reproduce (exp/38)

**Qué se probó.** La barrida marcó como ALTO que el router manda la primera
vuelta "directo" con thinking ON y la siguiente —con las 28 tools— con thinking
`disabled`, y que ese flip ON→OFF dentro de una conversación es el 400 que
`docs/design.md:96-97` documenta como crash medido. La evidencia era el
`extra_body` medido por los nodos, **no** una respuesta de la API.

`banco/probes/thinking_flip.py` hace las tres llamadas reales, con los esquemas
de tools reales y el historial en la forma en que el chat lo manda (assistant
sin `reasoning_content`):

| Paso | Petición | Resultado medido |
|---|---|---|
| 1 | system + user, sin tools, sin `extra_body` (thinking ON) | **OK 2,1 s** · `reasoning_content` **sí** · 0 tool_calls |
| 2 | + assistant + user, **con 28 tools** y `thinking: disabled` | **OK 1,3 s** · sin reasoning · 1 tool_call |
| 3 | + assistant + user, sin tools, sin `extra_body` (ON otra vez) | **OK 1,7 s** · `reasoning_content` **sí** |

**Veredicto: sin 400.** Los dos flips (ON→OFF y OFF→ON) pasan en esta secuencia,
que es la del chat.

## Qué significa

- El flip **existe en las peticiones** (eso la barrida lo midió bien), pero la API
  ya no lo rechaza en esta forma. O cambió el comportamiento del proveedor, o el
  400 original tenía un disparador más angosto (por ejemplo, devolver
  `reasoning_content` en un turno posterior, cosa que el código no hace).
- **No hay que cambiar la política de thinking por este hallazgo.** La regla
  pegajosa actual es del lado seguro y su costo es acotado: después de una vuelta
  con herramientas, las vueltas directas corren sin thinking.
- Queda una optimización posible **sin urgencia**: el paso 3 muestra que la API
  acepta volver a ON después de un turno OFF, así que la regla pegajosa podría
  relajarse para recuperar thinking en las vueltas directas posteriores a una
  agéntica. Antes de tocarla hay que re-correr esta sonda con el historial LARGO
  de producción (acá son 3 mensajes cortos).

## Límites de la sonda

- 3 llamadas, un modelo (`deepseek-flash`), un día. La sonda es re-ejecutable:
  `python3 banco/probes/thinking_flip.py` (≈10 s).
- El historial es corto y el system prompt es de una línea; producción manda
  historiales largos con herramientas ya ejecutadas.
- No mide el 400 inverso con `reasoning_content` presente (el código nunca lo
  manda: `historiar()` lo descarta).

## Corrección al informe de la barrida

`docs/informes/barrida_flujos_2026-10-08.md` lista este punto como ALTO y
"decisión pendiente". Con esta medición queda **degradado a "no reproducido"**:
se mantiene la regla actual, no se toca el modo, y la sonda queda como artefacto
para volver a chequear cuando el proveedor cambie. El resto de los hallazgos de
esa barrida no se ven afectados (los seis arreglos están en `exp/37`, y los de
la rama `exp/36`).
