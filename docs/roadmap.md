# Próximos pasos (roadmap)

Priorizado por valor/costo, decidido al cierre de la etapa 2026-10-04.
Cada ítem indica qué pieza lo apoya y qué falta.

## 1. Datos: Effective N y `pasos` en los rounds

**El hallazgo pendiente de explotar.** La auditoría y la BD mostraron:
- round3 tiene 4.825 trazas pero posible duplicación con `verified`
  (distribuciones idénticas) — falta medir el **Effective N** real
  (deduplicación por contenido).
- Los rounds 1-3 **no traen `steps`** (0 registros con pasos; la raíz sí:
  2.314/2.764) — si se re-entrena Laya con rounds, la distribución no
  incluye el campo `steps` que el estado de Choose usa en producción.
- Los `relabelled` están vacíos (fallo de volcado del pipeline).

Acción: pieza `effective_n.py` (deduplicación exacta en código +
informe) + decidir la corrección del pipeline de rounds. Apoya la
decisión de re-entrenar que el debate dejó condicionada.

## 2. Fine-tune de Laya para routing

El router funciona (4/5 con compuerta de confianza) pero su punto débil
es "hechos actuales". La mejora real no es más prompt-tuning (random walk
medido) sino fine-tunear el checkpoint multilingual con ejemplos de
routing — la stack de entrenamiento de bmo sirve tal cual. Al terminar:
activar `USE_LAYA_ROUTER=1` por defecto y promover Laya a **Choose del
supervisor** (despacho local de pasos).

## 3. Streaming + memoria entre sesiones

- Streaming: respuestas token a token + interrupción del usuario.
- Memoria: persistir/comprimir `messages` entre sesiones (hoy cada
  arranque es borrón y cuenta nueva; dentro de la sesión el historial se
  reenvía completo — costo creciente).

## 4. Self-healing batch + heartbeat

- Pasos fallidos del supervisor re-encolados con el feedback del error
  (hoy son datos para la síntesis, no reintento).
- Heartbeat: las piezas (auditoría, informe) corriendo solas de noche
  con la salida lista a la mañana.

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
