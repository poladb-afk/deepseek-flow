# Spec de ejecución — exp/91: recorte de tool results viejos en la ventana caliente

**Estado:** aprobada 2026-10-23 (operador: "avancemos — que lo haga el harness
mientras vos lo auditás; ojo con el RAM"). Es la deuda de fondo que exp/88
declaró, ahora con la señal de exp/89/exp/90 para medirla.

## Pregunta

Cuando la ventana caliente sola supera `COMPACTION_CHARS`, la compacción no
puede bajar el historial al tope (queda rodante o no-op): el contexto se clava
(sesión real del operador, exp/88: 60–75k por ronda hasta el kill) y cada
llamada re-envía la ventana entera. ¿Recortar el CONTENIDO de los tool
results VIEJOS dentro de la ventana — manteniendo la estructura
assistant+tools y los invariantes del modo thinking — desbloquea el tamaño y
lo estabiliza?

Aclaración de exp/90 para leer bien el ROI: gran parte de ese reenvío viaja
como cache hit del servidor (50× más barato), así que el argumento DINERO es
débil; los que quedan son el límite de contexto, la latencia y los misses
cuando el prefijo cambia. El fix se justifica por esos tres, no por tarifa
llena.

## Diseño (pre-registrado; lo implementa el chat del harness con PROMPT_FABLE=1)

**Pieza pura — `utils/compaccion.py`:**

- Constantes del módulo: `PREFIJO_RECORTE = "[recorte]"`, un umbral (no vale
  recortar resultados cortos, ~500 chars), cabeza/cola conservadas (~300 chars
  c/u) y `mantener=3` (los últimos N tool results quedan INTACTOS).
- `recortar_tools_viejos(messages, mantener=3)`: PURA, no muta el input.
  Reemplaza el `content` de los tool messages VIEJOS (todos menos los últimos
  `mantener`) que superen el umbral y no empiecen con el prefijo, por
  `"[recorte] {cabeza} [… N chars recortados …] {cola}"`. Sin tool messages →
  no-op. Idempotente por el prefijo (un recortado no se vuelve a recortar).
- Estructura intacta: roles, `tool_call_id`, unidades assistant+tools.
  `validar_historial` verde antes y después (el candado de la mesa 6).

**Cableado — `nodes.AgentStep.prep`, DESPUÉS de compactar:**

- Si tras `compactar` (exitosa o no-op) el historial sigue sobre el tope →
  `recortar_tools_viejos` y una línea de terminal propia, visible (lección de
  exp/88: las causas invisibles matan sesiones): p.ej.
  `[compacción] recorte: N resultados viejos → marcadores`.
- Si el gate de complejidad lo exige (ratchet CC>12 repo-wide), extraé un
  helper — precedente: `_aviso_ventana_caliente` (exp/88).
- El aviso de X51 se evalúa sobre el tamaño FINAL (post compacción + recorte),
  en ambos caminos (compacción exitosa o no-op): si el recorte lo bajó del
  tope, no hay aviso.
- Tras el recorte se actualiza `_compaccion_huella` (mismo contrato que la
  compacción: no re-procesar lo ya procesado).
- `COMPACTION_CHARS=0` sigue apagando TODO (compacción y recorte).
- Orden invariante: el respaldo de zona fría (A17) ocurre ANTES y sobre el
  historial COMPLETO — el recorte nunca toca lo respaldado (la zona fría ya no
  está en el historial post-compacción). El recorte NO genera respaldo propio:
  los tool results son re-obtenibles (regla exp/88) y el marcador conserva
  cabeza y cola como anclas.

## Criterios

- **C1 (puro, tests/test_compaccion.py):** recorta los viejos y deja los
  últimos `mantener` intactos; no toca los cortos; idempotente; no muta el
  input; sin tools → no-op; `validar_historial` verde antes/después con los
  `tool_call_id` conservados.
- **C2 (integración de prep, tests/test_chat_flujo.py):** con la ventana sola
  sobre el tope → tras el paso el historial queda más chico, con marcadores en
  los viejos y los últimos intactos; cuando la compacción normal alcanza NO
  hay recorte (sin pérdida innecesaria); el respaldo de zona fría prevalece
  intacto.
- **C3 (contrafáctico determinista, la forma de la sesión de exp/88):** ~16
  rondas con tool results de ~12k chars (lecturas de archivos grandes): el
  historial baja del tope tras el fix y se mantiene al agregar rondas nuevas
  (antes quedaba clavado por encima).
- **C4:** gate verde completo — lo corre el AUDITOR después de la corrida
  (disciplina de RAM: durante el turno del chat solo tests dirigidos).
- **C5 (meta):** implementado por el chat vía banco (PROMPT_FABLE=1), auditado
  con `fable_judge.verificar_trabajo` sobre el diff + review del auditor.
  Desviación declarada por RAM: `USE_LAYA_ROUTER=0` en el escenario (la tarea
  no depende del router) y `COMPACTION_CHARS=120000` (que la sesión del chat
  no compacte su propio contexto a mitad del fix).

## Fuera de alcance (declarado)

Presupuesto por tokens (espera datos de uso), recortar contenidos user o
assistant (solo tool results), LLM en el recorte (puro), cambiar
`VENTANA_DEFAULT`, tocar la semántica del aviso de X51 (solo su punto de
evaluación), respaldo propio del recorte, docs (las escribe el auditor tras la
auditoría).

## Resultado (2026-10-23)

C1 ✅ (5 tests puros del chat + el del borde del auditor). C2 ✅ (recorta con
ventana sola sobre el tope / no recorta si la compacción alcanza; desviación
declarada: viven en `tests/test_compaccion.py` por convención del precedente
`test_agent_step_prep_compacta_y_cuenta`, autorizada por el auditor en la
vuelta 2). C3 ✅ (16 rondas × 12k: ≤ 60k en CADA ronda). C4 ✅ gate verde
corrido por el auditor post-corrida (915 passed + 3 skips; tests_definidos
893→902, ratchet auto-rewritten). C5 ✅ el meta-loop completo:

- Vuelta 1 (16 rondas): assessment honesto sin ediciones — el chat leyó todo
  (441k prompt tokens), verificó 4/4 citas y paró en el presupuesto pidiendo
  autorización. Lección: 16 rondas no alcanzan para leer + implementar; la
  vuelta 2 usó 40 (perfil aplicación).
- Vuelta 2: implementación completa (+259 líneas, 32 rondas, 17 HITL, 146 s)
  con reporte outcome-first.
- Juicio 1: VERIFIED WITH CAVEATS con DOS hallazgos reales que la review
  manual del auditor pasó: conteo del reporte (decía 9 tests, eran 8) y el
  borde 501–635 chars donde el marcador quedaba más largo que el original
  (fix: `len(marcador) < len(contenido)` o no se toca, + test).
- Juicio 2 (reporte con verificaciones primero): pytest re-ejecutado exit 0
  ×2; `ruff check` no re-ejecutable por HITL sin terminal (la política no
  lista ruff como solo-lectura — queda como observación del instrumento).

RAM: máximo ~4,6 Gi disponibles durante el banco (chat sin Laya); el gate se
corrió secuencial después. Limitación del instrumento declarada: MAX_CLAIMS=12
consumido por claims descriptivos deja afuera los verificables si el reporte
los lista al final — priorizar claims re-ejecutables es la mejora siguiente
del juez.
