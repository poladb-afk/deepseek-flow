# Pre-registro — fases 3b + 4a de elegancia: un solo camino, sin router

**Estado:** pre-registrado el 2026-10-28 (X105), ANTES de escribir el código.
Consecuencia de la 3a (`fase3.md`): NO PASÓ, así que la 3b va por la opción
(b) — el router sale del camino del chat. No se retoca después de ver
resultados (un cambio va como desvío declarado en la bitácora).

## Hipótesis

Con el router fuera, toda pregunta va por `Contexto → AgentStep` con las
tools ofrecidas y el modelo decide si usarlas. Las preguntas que hoy van
directo (conocimiento puro, conversación) se responden igual de bien, sin
llamar tools y a un costo comparable. Si es así, el router, el voto y las
reglas de palabras no deciden nada que el modelo no decida solo.

## Qué se borra

- `LayaRouter` (155 líneas, el nodo largo más grande), `DirectAnswer`,
  `voto_confirmacion_router` y sus aristas en `flow.py`.
- En `utils/laya_routing.py`: la política del router y del voto, las dos
  reglas (`regla_temporal`, `regla_imperativo_capacidad`) y su vocabulario
  (`RE_TEMPORAL`, `_IMPERATIVOS_CAPACIDAD`, `_RELLENOS`,
  `_RE_OBJETO_CAPACIDAD`).
- El log de routing y la flywheel del router (`registrar_decision`,
  `registrar_resultado`, `turno["router_pendiente"]`, la etiqueta
  ambiental): sin router no hay decisión que etiquetar.
- Los settings del router y del voto (inventario de `elegancia.md`, fase 3):
  `USE_LAYA_ROUTER`, `USE_VOTACION`, `LAYA_MODO`, `LAYA_MODEL_VOTO`,
  `LAYA_ALPHA(_VOTO)`, `LAYA_CALIBRACION_ROUTER/VOTO`,
  `LAYA_UNSURE_HIGH_VOTO`, `LAYA_LOG_*`. El número exacto lo da el ratchet.
- Las sondas y benches que solo miden al router o al voto se retiran con él
  (lista cerrada en el PR, cada una con su motivo en la bitácora).

`LAYA_MODEL` y `utils/laya.py` se quedan: los usan el servidor MCP, el
prefiltro de memoria y el juez de riesgo.

## Qué se mueve

**Los skills.** Hoy se activan dentro de `LayaRouter.post` (solo en
enforce). Pasan a un nodo propio a la entrada de la pregunta (después de
`PreFetch`, antes de `Contexto`), con la misma regla `skill_para` hasta la
5b, que la cambia por activación por descripción. Gate: `exp55-skills`
(revisión dispara y recorta tools; el control no dispara) y
`test_skills.py`.

## Riesgos que el banco tiene que medir

1. **Costo**: que una pregunta simple ahora llame tools sin necesidad.
2. **Descarrilos**: con tools en el request, `_kwargs_agente` apaga el
   thinking. La bitácora midió descarrilos en directo con thinking apagado
   (prompts ajenos, tags que parten palabras). Hoy `DirectAnswer` va SIN
   tools, o sea con thinking; en 3b ya no.

## Instrumento

Escenario `banco/escenarios/fase3b-directas.yaml`: las 12 preguntas
`esperado: directo` de `producto_router` (`voto_casos` d01–d06 y
`voto_control` t01–t06), una por turno. Ninguna dispara skill ni regla
(verificado al escribirlo), así que en la base las decide el router.

Por turno: marcadores del banco (`ronda`, `sanitizado`, `dsml_ignorado`) y,
de la traza (`.runs`, eventos `usage` de X98), prompt, completion y
`cache_hit`. USD con las tarifas de `utils.costos` (sin dato de caché = miss).
**Cada brazo con su propio `.runs` desde el principio** (worktree propio):
nada de reconstruir directorios por mtime (lección del A/B de 3a).

## Corridas

| brazo | árbol | corridas |
|---|---|---|
| base | HEAD de X105 (router encendido, el default) | `fase3b-directas` × 3 |
| 3b | el PR de 3b+4a | `fase3b-directas` × 3 |

Las auditorías de fable (s17–s20) no se re-corren si en las 16 trazas del
brazo A del A/B de 3a `LayaRouter` devolvió `herramientas` en todas: ahí el
camino no cambia. Si alguna fue `directo`, se corre ese escenario ×3 en los
dos brazos.

## Criterios (todos)

1. **Sin tools de más**: en 3b, al menos 10 de las 12 preguntas con 0 rondas
   de tools en las 3 corridas, y ninguna con más de 1 ronda.
2. **Costo**: USD total del escenario en 3b ≤ **1,5 ×** la base (mediana de
   las 3 corridas). La base incluye lo que hoy cuesta decidir: el árbitro
   DeepSeek del voto cuando Laya duda.
3. **Sin descarrilos de más**: `sanitizado` + `dsml_ignorado` en 3b ≤ base,
   sumados en las 3 corridas.
4. **Todos los turnos ok** (sin timeouts) en los dos brazos.
5. **Skills**: `exp55-skills` igual que hoy.

Si 1, 2 o 3 fallan, la 3b no entra y se registra cuál falló. El remedio NO
es una regla de palabras ni texto en el prompt (R-elegancia C1/C5): se
vuelve a este documento con el dato.

## Efecto esperado en los ratchets (no es criterio)

`vocabulario_hardcodeado` 7 → 3, `settings_leidos` 78 → ~66, `nodos_largos`
14 → 13. Además el chat deja de cargar el checkpoint del router.

## Brazo 3b escrito (X106)

El código del brazo 3b es el árbol de X106. Desvíos respecto de "Qué se
borra", declarados antes de correr:
- `LAYA_UNSURE_HIGH/LOW` también se van (los leía `utils.laya.veredicto`
  solo para el router; quedan sus defaults). `LAYA_LOG_*` estaba en el
  inventario como contrato de privacidad; se va con el sink que apagaba.
- `utils/conformal.py` se va: sin router no tiene lectores en el producto.
- `delegar_tarea` pierde `shadow` (existía para alimentar la flywheel).
- Escenarios `exp43-demo` y `exp54-reglas` borrados; `exp55-skills` sigue
  siendo el gate de los skills.

Resultado en ratchets: `settings_leidos` 78 → **64**, `vocabulario` 7 → **3**,
`nodos_largos` 14 → **13** (la estimación decía ~66, 3, 13).


## Veredicto (2026-10-30, corrido por el operador; commit 7a23b63)

Cada brazo en su worktree con su `.runs` desde el principio. 8 corridas
(3× `fase3b-directas` + 1× `exp55-skills` por brazo), 104 turnos, 0 timeouts.
Los cinco criterios en verde:

1. **Sin tools de más**: 12/12 preguntas directas con 0 rondas de tools en
   las 3 corridas del brazo 3b (pedía ≥10/12; ninguna >1).
2. **Costo**: USD mediana 3b 0,00204 vs base 0,00313 = **0,65×** (tope
   1,5×). La base pagó 17 llamadas por corrida contra 12: las 5 extra son
   el árbitro DeepSeek del voto cuando Laya dudaba — el costo de decidir
   que este pre-registro mandaba incluir.
3. **Descarrilos**: sanitizado + dsml_ignorado = 0 en los dos brazos.
4. **Turnos ok**: 104/104.
5. **Skills**: `exp55-skills` dispara la skill de revisión y no el control
   en los dos brazos (el marcador pasa de `laya` a `skill`).

Condición de fable sin re-corrida: 0 eventos `LayaRouter/directo` en las 16
trazas del brazo A del A/B de 3a — en las auditorías el camino no cambia.
**PASA: la 3b+4a sale de la rama y se mergea a main.** Evidencia:
`salidas/banco/fase3b-ab/` (base-*/3b-*) y 8 trazas con usage en `.runs/`.
