# Spec de ejecución — exp/86: presupuesto dinámico determinista — subir el tope cuando el pedido es amplio

**Estado:** ejecutada el 2026-10-22; C1-C5 OK (con una recalibracion registrada: AMPLIO_LINEAS 400 -> 300). Resultado en bitacora exp/86.
**Instrumento:** contrafáctico sobre las corridas históricas del banco (exp/72–80, 56b) + regla determinista + e2e.

## Contexto

Mesa 3 pedía "presupuesto dinámico de rondas". El diseño arranca de tres hechos ya medidos:

1. **El tope es un CAP, no un gasto** (X21/exp/52-A: p50 2 rondas): una pregunta que necesita 2
   usa 2 aunque el cap sea 8 — bajar el tope para pedidos acotados no ahorra nada y solo
   arriesga cortar. La dirección útil del presupuesto dinámico es SUBIR.
2. **El hueco real es A37**: el alcance amplio (repo completo, auditoría de módulos) agota 8 y
   queda corto; hoy lo resuelve el usuario a mano (`MAX_TOOL_ROUNDS>=16`) o el modelo declara
   alcance parcial.
3. **La redundancia de la cola es ≈0** (X22/exp/52-B): las rondas extra de la cola no eran
   desperdicio — no hay nada determinista que recortar sin riesgo.

## La regla (determinista, sin LLM — los datos exactos los cuenta el código)

`alcance_amplio(pregunta)` → True si cualquiera:
1. **palabras de totalidad**: "todo el repo", "todos los", "cada módulo/archivo", "auditoría
   completa", "el código en general" (regex);
2. **directorio referido con ≥10 archivos** de código/doc (el path mencionado resuelve a un
   dir del disco y SE CUENTAN sus archivos);
3. **masa referida ≥400 líneas**: la suma de líneas de los ARCHIVOS mencionados que existen.

`presupuesto(shared)` sin override ni perfil: si `alcance_amplio` → `MAX_TOOL_ROUNDS_AMPLIO`
(default 16, setting); si no, `MAX_TOOL_ROUNDS` como hoy.

## Contrafáctico pre-registrado (contra las corridas de exp/72–80 y 56b)

- **C1 (el que importa):** TODO run histórico que agotó el cap (rondas ≥ 8/8: s13, s18, s19,
  s20, y los 8 aislados de s16/s7) tiene que clasificar amplio por la regla.
- **C2:** los runs cómodos (rondas ≤ 4: s1, s10, s11, s15) clasifican NO amplio.
- **C3:** ningún run exitoso queda CORTO — estructuralmente garantizado: la regla solo sube
  (un cap mayor no recorta nada).
- **Predicción registrada:** C1 pasa por las señales 2-3 (s13/s17: árbol exports de 20+
  archivos; s18-20: 2 archivos pero ~600-925 líneas); s16 queda borde (4 archivos, ~350
  líneas) y si clasifica no-amplio está bien (sus rondas típicas son 2-4; sus 8 aislados se
  declaran límite). Riesgo declarado: un fix-task con blast radius amplio pero pedido angosto
  (estilo s13 sin mencionar el árbol) no lo agarra la regla — el protocolo de continuación
  ("seguí") sigue siendo la salida.

## Criterio de producto (e2e)

- **C4:** un escenario de banco de auditoría amplia (fixture s18) con la regla activa corre
  con tope visible 16 (el marcador `⚙ ronda N/16`), exit 0 del banco, y sin regresión de
  recall respecto de exp/77 (A 3,67/6).
- **C5:** tests sin LLM de la regla (palabras, dir con archivos, masa de líneas, no-amplio
  acotado) y de `presupuesto` (override > perfil > amplio > default); gate verde.

## Fuera de alcance

Bajar topes (cap no es gasto), estimación Laya de rondas (Mesa 3 original: recién si lo
determinista no alcanza), cambiar el protocolo de continuación, F2.


## Resultado (2026-10-22)

**Desvio registrado (la honestidad del e2e):** el primer contrafáctico dio C1
por una casualidad — la masa de `banco/fable/escenarios/s18` incluía el
GROUND-TRUTH.md (~300 líneas de answer sheet que el agente NUNCA ve). El e2e
lo cazó: marcador `ronda N/8` y regla en False sobre el run real (masa
visible de s18: 342 líneas < 400). Recalibrado con la masa VISIBLE al agente
(sin GROUND-TRUTH, misma regla que el juez de fable): **AMPLIO_LINEAS=300**
— las familias que agotaban el cap quedan arriba con margen (347 · 587 ·
930), las cómodas muy abajo (máx 111) y s16 se queda afuera como estaba
predicho.

- **C1 ✅** (tras recalibrar): s13/s17 (24 archivos), s18/s19/s20 (masa) clasifican
  amplio; los 8 aislados de s16 (2/9 runs) quedan al tope de siempre —
  límite declarado en la predicción.
- **C2 ✅**: s1/s10/s11/s15 (y s16) no amplio.
- **C3 ✅** estructural: la regla solo sube.
- **C4 ✅**: e2e con la regla activa — marcador `⚙ ronda N/16` visible, la
  seed 1 usó las 16 completas (headroom real); recall medio 3,67/6 =
  **sin regresión vs exp/77** (3,67/6). Declarado: entre dos lotes de n=3
  del MISMO brazo A el recall osciló 3,67-5,0 — la varianza domina a este n;
  la hipótesis nunca fue más recall, era headroom (A37).
- **C5 ✅**: gate verde (872 tests).
