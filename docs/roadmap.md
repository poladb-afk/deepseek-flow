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

## Hechos

### 4 (viejo). Self-healing + heartbeat — ✅ (2026-10-05)

- Self-healing en el supervisor reactivo: el fallo de un paso es un
  hecho con ERROR; el reintento recibe el error como feedback en el
  prompt de args; dos fallos y la herramienta se veta (L8), y las
  herramientas sin-args no se repiten. El informe final lleva la sección
  "Pasos" (auditoría). Verificado con LLM real: fallo → reintento
  corregido → éxito.
- `heartbeat.py`: tareas programadas (heartbeat.jsonl) con el supervisor
  completo, estado + log de auditoría, línea de cron sugerida. Probado
  con dos tareas reales nocturnas (trazas + effective_n de bmo/data).

## 3. Visor del trace — ✅ hecho (2026-10-05)

`visor.py` (python3 main.py visor): HTML autocontenido offline con
recorrido, resumen por nodo y cronología con barras. Testeado con traces
reales del supervisor y del heartbeat.

## 4. Majority vote — ✅ hecho (2026-10-05, primera etapa)

`utils/votacion.py` (mayoría genérica) + integración en el despacho
dudoso del supervisor: 2-de-3 (DeepSeek directo, DeepSeek por
eliminación, Laya crudo). Medido con LLM real: sistema 16/24 → **17/24**,
corrigiendo los pares confusos; hallazgo: los dos votos DeepSeek
correlacionan — la independencia la pone Laya. Siguientes aplicaciones
cuando duelan: el falso-directo del router (mundial) y las respuestas
verificables del chat.

## 5. Coding agent — `run_command` con HITL

El único salto de categoría pendiente (patrón advanced del cookbook):
cerrar el ciclo escribir→**ejecutar**→corregir. read/search/write_file
ya están; falta ejecutar comandos (tests, git) con aprobación humana y
contención, y memoria del ciclo.

## 6. Streaming + memoria entre sesiones

- Streaming: respuestas token a token + interrupción del usuario.
- Memoria: persistir/comprimir `messages` entre sesiones (hoy cada
  arranque es borrón y cuenta nueva; dentro de la sesión el historial se
  reenvía completo — costo creciente). (Descartado como prioridad por el
  usuario; vuelve cuando duela.)

## 7. HITL web

Migrar la aprobación de escritura de `input()` a una arista del grafo
(`needs_approval` → AskHuman → `approved/rejected`) y el chat a
FastAPI/Gradio cuando se quiera interfaz de navegador.

## Cola final (considerados, sin fecha)

- **A2A** — solo si sirve para consumir agentes remotos de otros equipos.
- **Vision/PDF** — extracción de datos de PDFs con visión (patrón
  invoice del cookbook).

## Descartes

- **Voz** — no interesa.
