# exp/49 — aprobación durable: el HITL sobrevive al proceso (factores 7/8)

Corte pre-registrado en exp/47: "aprobar con el proceso reiniciado". La vía
PocketFlow-simple (decisión del conductor): NO reestructurar el flujo con
aristas approved/rejected todavía — usar la base de exp/48. Un checkpoint en
la SELECCIÓN de tools (la pausa exacta que el factor 8 pide: "between tool
selection and tool invocation") + una reparación honesta al rehidratar. La
arista formal y el HITL web multi-pendiente son fase B (exp/49b).

## 1. `nodes.py` — punto seguro 4: la SELECCIÓN (factor 8)

En `AgentStep.post`, camino `"tool"` (hay `tool_calls`, antes de devolver):
`checkpoint(thread_id(), type(self).__name__, "tool", shared)` — las
llamadas QUEDARON SELECCIONADAS pero no ejecutadas. Con el checkpoint de
ronda de exp/48 (ExecuteTools.post) son dos por ronda: selección y cierre.

## 2. `utils/thread_store.py` — `reparar_pendientes(shared) -> int` (PURA)

Un proceso muerto entre selección y ejecución deja el historial con un
assistant con `tool_calls` SIN sus mensajes tool — violates el invariante
de la API y hoy el resume lo rechazaría. La reparación: por CADA tool_call
huérfano del ÚLTIMO assistant, appendear un mensaje
`{"role": "tool", "tool_call_id": <id>, "content":
"(interrumpido: esta llamada no llegó a registrarse ejecutada — puede haber
corrido a medias; si sigue siendo necesaria, volvé a emitirla y verificá
el efecto antes de repetirlo)"}`.

- PURA: (shared) → int (cuántas reparó); solo toca el FINAL del historial
  (el último assistant si tiene tool_calls sin sus tools inmediatos);
  idempotente (llamarla dos veces repara 0 la segunda).
- Solo el final: pares viejos rotos en el medio NO se tocan (eso es
  corrupción, no interrupción — que el validador los siga cazando).

## 3. `resume.py` — rehidratar CON reparación

Orden: `cargar` → `n = reparar_pendientes(shared)` → `valido(shared)` →
banner. Si n > 0, el banner agrega:
`"· {n} llamada(s) interrumpida(s) reparadas"` — el usuario sabe que la
última ronda murió a mitad y el modelo verá el mensaje honesto.

## 4. `modules/humano.py` — NUEVO: el humano como tool call (factor 7)

`request_human_input(pregunta)` — el modelo PUEDE preguntarle al humano en
medio de una tarea (pedir aclaración antes de asumir):

- TOOLS: `request_human_input(pregunta: str)` con descripción honesta
  ("preguntale al usuario cuando falte información que no puedas obtener
  con tools; no la uses para reportar avances").
- IMPL: imprime `colorear(f"  [humano] {pregunta}", "aviso")` y lee una
  línea por `input()`; devuelve el texto como resultado de la tool. EOF o
  excepción → `"(sin respuesta del humano: {motivo})"` — dato, no crash.
  Sin HITL de aprobación (preguntar no es un efecto), sin timeout v1.
- SIGINT durante el input: se propaga como siempre en el chat (Ctrl+C es
  del usuario, no del agente).

## 5. Tests

`tests/test_thread_store.py` (append):
1. Checkpoint de selección: AgentStep.post con tool_calls escribe línea
   `"tool"` (fake); sin tool_calls escribe `"answer"` y NO `"tool"`.
2. `reparar_pendientes`: (a) assistant con 2 tool_calls sin tools → 2
   mensajes tool appendeados con sus ids, devuelve 2, idempotente;
   (b) historial ya pareado → 0 y sin cambios; (c) pares rotos VIEJOS en
   el medio → no se tocan (solo el final); (d) shared sin messages → 0
   sin explotar.
3. resume end-to-end con thread fabricado que termina en selección pendiente:
   cargar → reparar → valido da [] (antes de reparar daba violaciones).

`tests/test_smoke.py` (append, cerca de los tests de módulos):
4. `request_human_input`: con `input` fakeado responde el texto; con EOF
   devuelve "(sin respuesta..."; la tool queda en el registro del módulo
   (TOOLS/IMPL como los demás).

## 6. `.env.example`

Nada nuevo (la tool no tiene settings). Una línea en el bloque de HITL web
mencionando `request_human_input` como la vía del modelo para preguntar.

## Candado final

`python3 -m pytest tests/ -q` verde (hoy 368) y ruff. El E2E (matar durante
un (s/n) y aprobar tras reanudar) lo corre el conductor.
