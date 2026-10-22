# Spec de ejecución — exp/78: checklist de auditoría de seguridad (brazo D)

**Estado:** aprobada y ejecutada el 2026-10-22 (3 corridas); resultado abajo y en [bitacora](../../docs/bitacora.md) exp/78.
**Instrumento:** bench de exp/72-77 con el fixture real `s18-real-audit` y un **cuarto
brazo D** = checklist de seguridad en el system prompt (`PROMPT_AUDITORIA=1`).

## Pregunta

exp/77 midió el hueco: el baseline detecta los bugs visibles leyendo (R4/R5/R6 8/9) pero
casi no los **por ausencia** (R1 sort --compress-program 1/9, R3 tail -f 1/9, R2 evasión
por -o 4/9). ¿Un checklist explícito de auditoría de seguridad cierra ese hueco?

## Brazo D

Directiva `DIRECTIVA_AUDITORIA` en `main.py` (opt-in, default 0): empuja a enumerar
familias de riesgo, revisar si las listas de flags/denylists están **completas**,
normalizar envoltorios y comparar strings sin normalizar, y reportar el hardening
ausente como hallazgo. Es la respuesta directa a "no saber qué debería estar y no está".

## Diseño (pre-registrado)

- **Corridas:** D × 3 seeds = **3 corridas** sobre s18 (mismo fixture; ~3 min).
  **Referencia A:** exp/77, mismos seeds y fixture (recall 4,3,4 = 3,67/6). No se
  re-corre A (misma versión del producto, mismo día); se declara como comparación
  contra la medición previa.
- **Scoring:** idéntico al de exp/77 (semántico, cita al archivo + keywords OR/AND;
  editar = 0; 2 = 6/6 sin citas inválidas; 1 = 3-5; 0 = <3 o edición).
- **H_checklist (primaria):** D detecta **R1 (sort --compress-program) y R3 (tail -f)
  en ≥ 2/3 seeds**. **Secundaria:** recall medio D ≥ A + 1,0 (≥ 4,67/6).
- **Predicción registrada:** el checklist está diseñado exactamente para R1/R3 → espero
  que los detecte (si no, el límite es del modelo, no de la directiva).
- **Criterio de lectura (no se retoca):** si H_checklist se cumple, el lever de producto
  es la directiva opt-in ya implementada y el siguiente paso es validarla en otro fixture
  real. Si no se cumple, señalarlo como límite del modelo: ni señalándolo por ausencia lo
  encuentra; el siguiente paso sería GT validada/juez o un fixture distinto, no más
  prosa.
- **Métricas:** recall/6, detección por bug, citas válidas/inválidas, ediciones, hallazgos
  extra (conteo), rondas/segundos.

## Fuera de alcance

Corregir bugs, F1/F2 de fable (cerrado), juicio LLM del informe.

## Resultado (2026-10-22)

3 corridas. **D 5,00/6** (3, 6, 6) vs **A 3,67/6** de exp/77 (Δ +1,33), con 0 citas
inválidas y 0 ediciones. **H_checklist CUMPLE**: R1 sort --compress-program 2/3,
R3 tail -f 2/3, R2 -o 2/3; R4/R5/R6 3/3. D s3 hizo 6/6 en solo 3 rondas (la checklist
enfoca la lectura) y D s2 destapó además bugs reales extra fuera de la GT histórica.
Veredicto: el lever es señalar "qué falta"; queda opt-in con `PROMPT_AUDITORIA=1`
(default 0). Siguiente: validarlo en un segundo fixture real y decidir default-on para
auditorías; medir precisión de extra con GT validada.

