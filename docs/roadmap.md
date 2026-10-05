# Próximos pasos (roadmap)

Priorizado por valor/costo, decidido al cierre de la etapa 2026-10-04.
Cada ítem indica qué pieza lo apoya y qué falta.

## 1. Datos: Effective N y `pasos` en los rounds — ✅ hecho (2026-10-04)

Pieza `effective_n.py` (código puro, informe markdown) + módulo
`run_effective_n`. Los hallazgos, medidos y en design.md:

- **Effective N = 6.717 de 15.595** (56,9% duplicación), 0 contradicciones
  de etiqueta. La "duplicación round3↔verified" era exacta:
  `round3/harness_choose_verified.jsonl` es **copia byte a byte** del
  choose (la verificación no filtró nada).
- round3 es acumulativo (contiene el 89,6% de round2): round2 aporta solo
  275 casos nuevos. Subconjunto entrenable máximo: raíz_verified +
  round1_verified + round3 = **6.141**.
- Rounds 1-3 sin `steps` (usan `observation`); producción y raíz usan
  `steps`. `relabelled` vacío por volcado nunca poblado.

Decisión tomada: el volcado de rounds no está versionado y dejó los tres
defectos; antes de re-entrenar hay que regenerar los rounds con el
generador versionado de bmo (`train/generate_targeted.py`, que emite
`steps`). Entretanto: entrenar con el subconjunto de 6.141 y tratar
round3/verified como choose. El fine-tune (ítem 2) sigue condicionado a
esa regeneración.

## 2. Fine-tune de Laya para routing — ✅ hecho (2026-10-04)

Hecho, con la stack de bmo tal cual (task `router_flow` en
`bmo/train/kaggle-router/`): 840 casos generados con DeepSeek sobre 12
contextos de tráfico → juez ciego (821 verificados) → Kaggle T4 →
checkpoint `.modelos/router_flow-1k`.

| checkpoint | crudo | ECE | con compuerta |
|---|---|---|---|
| base multilingual | 13/24 | 0.379 | 12/24 |
| router_flow-1k | 20/24 | 0.077 | **22/24** |

`USE_LAYA_ROUTER=1` es ahora el default (flow.py). El supervisor pasó a
bucle reactivo con Choose local (task supervisor_dispatch, 18 opciones):
r1 8/24 → r2 **11/24 · ECE 0.222** (hallazgos: head truncado a 256 tokens,
87% del dataset con hechos de herramientas inventadas, dosis 60/opción);
r3 (15/24, 13 despachos 9 correctos) y round dirigido r4 sobre los
pares confusos (3.283 casos): **14/24 crudo con 8/8 despachos locales
correctos** — integrado y activo. El crudo tiene techo (~15) porque parte
del matiz es convención; la calibración quedó perfecta para el sistema:
lo que despacha local no falla. El contrato
entrenamiento≡producción (pregunta y estado byte a byte) es el que
cuenta — documentado en design.md. Pendiente dentro de esta línea:
promover el patrón a **Choose del supervisor** (falta la task de despacho
con su catálogo) y un round dirigido de "hechos actuales" para el único
falso-directo que resiste (mundial, 0.83).

## 3. Streaming + memoria entre sesiones

- Streaming: respuestas token a token + interrupción del usuario.
- Memoria: persistir/comprimir `messages` entre sesiones (hoy cada
  arranque es borrón y cuenta nueva; dentro de la sesión el historial se
  reenvía completo — costo creciente).

## 4. Self-healing + heartbeat — ✅ hecho (2026-10-05)

- Self-healing en el supervisor reactivo: el fallo de un paso es un
  hecho con ERROR; el reintento recibe el error como feedback en el
  prompt de args; dos fallos y la herramienta se veta (L8). El informe
  final lleva la sección "Pasos" (auditoría). Medido en dos tareas
  reales: sin fallos duros, recuperación suave de facto (truncado →
  relectura acotada). Tests de integración sin red.
- `heartbeat.py`: tareas programadas (heartbeat.jsonl) con el supervisor
  completo, estado + log de auditoría, línea de cron sugerida. Probado
  con dos tareas reales nocturnas (trazas + effective_n de bmo/data).

## 5. HITL web

Migrar la aprobación de escritura de `input()` a una arista del grafo
(`needs_approval` → AskHuman → `approved/rejected`) y el chat a
FastAPI/Gradio cuando se quiera interfaz de navegador.

## 6. Visor del trace

`.runs/*.jsonl` ya registra nodo/acción/duración por ejecución. Falta un
visor HTML simple (leer el jsonl y dibujar el recorrido del grafo).

## Descartes explícitos

- **Voz** — no interesa.
- **Vision/PDF, A2A** — no prioritarios (A2A solo si sirve para consumar
  agentes remotos de otros equipos).
- **Majority vote / ensambles** — cuando haya una pregunta cuya
  incorrectitud duela.
