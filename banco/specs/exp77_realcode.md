# Spec de ejecución — exp/77: auditoría sobre código real con GT histórica

**Estado:** aprobada y ejecutada el 2026-10-22 (9 corridas + 2 reruns de transporte); resultado abajo y en [bitacora](../../docs/bitacora.md) exp/77.
**Instrumento:** bench de exp/72-76 con un fixture de **código real pre-fix** del
propio repo y GT sacada de la historia de git.

## Pregunta

Auditando código real (no bugs plantados), ¿qué recall y qué precisión tiene el chat?
¿La prosa de fable (B) o la skill `revision` (C) cambian algo?

## Fixture (`banco/fable/escenarios/s18-real-audit/`)

Versiones REALES pre-fix de `utils/policy.py` (311 líneas) y `utils/votacion.py`
(31 líneas), extraídas de `git show 3653daf^`. Ese commit cerró los hallazgos
**E1–E6** de la auditoría externa 2026-10-21; esos seis son la GT histórica:

| id | bug real | archivo |
|---|---|---|
| R1 | `sort --compress-program` ejecuta programa y quedaba en auto | policy.py:125 |
| R2 | bloqueo de `pytest -p` evadible por `-o/--override-ini` | policy.py:127 |
| R3 | `tail -f/-F` no termina y quedaba en auto | policy.py:119 |
| R4 | doble confirmación evadible por envoltorios/formas (`sudo rm`, `-rF`, `git -C`) | policy.py:156 |
| R5 | `explicar` describía el primer token, no el segmento que fija el nivel | policy.py:300 |
| R6 | `mayoria()` ignoraba el desempate en 2-2 | votacion.py:28 |

E7 (en `nodes.py`) queda fuera por tamaño. Extra: validez de las citas y
**precisión real** de los hallazgos fuera de la GT, validada a mano con la rúbrica
de la GT (válido / no soportado / caveat).

## Diseño (pre-registrado)

- **Brazos:** A baseline, B prosa, C skill revision; 3 seeds = **9 corridas** (~7 min).
- **Scoring:** semántico (no exige línea exacta, porque R3/R4 son bugs por AUSENCIA):
  cita válida al archivo + una alternativa de keywords OR/AND; editar = 0;
  2 = 6/6 sin citas inválidas; 1 = 3-5; 0 = <3 o edición.
- **Predicciones registradas:**
  - **H_real:** A < 5/6 — los bugs de seguridad/política por ausencia (R3, R4)
    deberían ser más difíciles que los plantados.
  - **H_prosa / H_skill:** sin lift; C puede degradar la evidencia (exp/75).
- **Criterio de lectura (no se retoca):** si A ≥ 5/6, la calidad de auditoría se
  sostiene en código real y el cuello sigue siendo la validación de extra; si A < 3/6
  hay gap real → proponer producto (checklist de auditoría o skill corregida).
  La precisión fuera de GT se reporta por separado (validación manual de los 3
  reportes de A; B y C solo conteo de claims).

## Fuera de alcance

Corregir los bugs (auditoría), F1/F2 de fable (cerrado), juicio LLM del informe.

## Resultado (2026-10-22)

9 corridas (+2 reruns de fallas de transporte). **A baseline 3,67/6** (4,3,4), **B prosa
4,00/6** (4,4,4), **C skill revision 2,33/6** (3,50 en las 2 corridas válidas). Sin lift
de prosa ni de skill. Detección /9: R4 8, R5 8, R6 8 (se ven leyendo) vs **R1 1, R3 1,
R2 4** (bugs de seguridad por AUSENCIA: flags que faltan en la lista/evasión por
envoltorios). **H_real VERDADERA** (A < 5/6): la calidad de las varas plantadas no se
sostiene en código real con bugs históricos.

Robustez: 3/9 corridas fallaron al principio (stream reset, DSML, timeout 301 s por loop
de comandos fuera de scope); A s3 y B s2 se re-corrieron OK, C s3 queda fallida y
reportada. Precisión de extra: spot-check de A s1 (8 hallazgos: 3 GT, 2 de la misma
familia, 3 límites; sin funciones inventadas); la medición formal queda como deuda.

**Siguiente propuesto:** exp/78 con un cuarto brazo de checklist/directiva de auditoría de
seguridad (flags peligrosos, envoltorios, "qué NO está en la lista") sobre el mismo
fixture; si sube R1/R3, es el lever de producto. Alternativa: GT validada/juez para
precisión.

