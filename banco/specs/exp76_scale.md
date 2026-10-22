# Spec de ejecución — exp/76: vara de escala (auditoría cross-file en 20 módulos)

**Estado:** aprobada y ejecutada el 2026-10-22 (9 corridas); resultado abajo y en [bitacora](../../docs/bitacora.md) exp/76.
**Instrumento:** bench de exp/72-75 con el fixture de 20 módulos de `s13-twin-fleet`
reutilizado como **auditoría** (no se duplican archivos: `FUENTE_FIXTURE`), GT propia.

## Pregunta

La calidad de auditoría se sostiene cuando el código escala a 20 módulos bajo el
presupuesto normal del chat (8 rondas), o aparece el costo de contexto/lectura? ¿La
prosa (B) o la skill `revision` (C) cambian algo?

## Fixture (`banco/fable/escenarios/s17-scale-audit/GROUND-TRUTH.md`)

20 módulos del export layer (fixture original de s13, MIT): **5 con el bug de truncado**
(invoices, refunds, payouts, receipts, statements), **14 limpios** (FP) y 1 décoy
neutral (shipping: `int(weight_kg * 1000)` en gramos, no es el bug de dinero).
La tarea es la auditoría de siempre (reportar, no editar).

## Diseño (pre-registrado)

- **Brazos:** A baseline, B prosa, C skill revision (`ENV_POR_BRAZO` de exp/75).
- **n:** 3 seeds × 3 brazos = **9 corridas** (~12-15 min); smoke-grade.
- **Presupuesto:** el default del producto (`MAX_TOOL_ROUNDS=8`); esto es parte de lo
  que se mide.
- **Scoring:** idéntico a exp/74-75 (cita a ±2 líneas o rango + keyword; FP en los 14
  limpios; shipping neutral; editar = 0; 2 = 5/5, 1 = 3-4, 0 = <3 o edición).
- **Predicciones registradas:**
  - **H_escala:** A < 5/5 — a diferencia de exp/74-75, 20 archivos con 8 rondas debería
    dejar al menos un bug sin leer (el cuello se mueve de "ver el bug" a "alcanzar a
    verlo").
  - **H_prosa / H_skill:** sin lift (exp/72-75); C puede degradar la evidencia.
- **Criterio de lectura (no se retoca):** si A < 5/5, queda confirmado el gap de escala
  y el siguiente paso es producto (planificación de auditoría / lectura por lotes /
  prefetch con presupuesto), no otra directiva. Si A = 5/5 ×3, la escala 20 tampoco
  discrimina y la próxima vara es un repo real (con GT humana) o 100+ archivos.
- **Métricas:** recall/5, detección por bug sobre 9 runs, FP sobre 14 limpios, citas
  válidas/inválidas, ediciones, rondas/segundos, menciones al décoy shipping.

## Fuera de alcance

Corregir bugs (auditoría), F1/F2 de fable (cerrado), juicio LLM del informe.

## Resultado (2026-10-22)

9 corridas. **Recall 5,00/5 en los 3 brazos** (S1-S5 9/9 cada uno), 0 citas inválidas y
0 ediciones en todas. H_escala FALSA: 20 módulos con 8 rondas no impidieron encontrar los
5 bugs (pre-fetch + search_files + lectura dirigida). Sin lift de prosa ni de skill.
Rondas/tiempo: A 6,0/49 s · B 6,7/47 s · C 4,7/37 s. El ca pre-registrado (A 2,1,2;
B/C 1,1,1) quedó manejado por el FP-proxy, que **no es interpretable acá**: la mayoría de
los FP son hallazgos extra legítimos en módulos limpios solo del bug plantado (CSV sin
quoting, truncado de cantidades, half-even) y una línea con 6 citas suma 6 FP. Se declara
la limitación y no se re-puntúa el cap. El techo pasó de "encontrar" a "validar hallazgos
extra": la próxima vara necesita GT más rica o juicio humano (exp/77 propuesto), no más
archivos.

