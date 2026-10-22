# Spec de ejecución — exp/79: ¿el checklist generaliza? segundo fixture real

**Estado:** aprobada y ejecutada el 2026-10-22 (6 corridas); resultado abajo y en [bitacora](../../docs/bitacora.md) exp/79.
**Instrumento:** bench de exp/72-78 + segundo fixture de **código real pre-fix** (`s19`).

## Pregunta

El checklist de seguridad (`PROMPT_AUDITORIA=1`, brazo D) subió el recall de 3,67 a 5,00
en s18. ¿Generaliza a otra familia real de bugs de seguridad, o fue overfitting al
fixture E1–E6?

## Fixture (`banco/fable/escenarios/s19-real-audit-2/`)

Versiones REALES pre-fix (commit `9508d6a^`, 2026-10-15): `modules/coding.py` (374
líneas) y `modules/memoria.py` (213). Ese commit cerró el bypass del HITL graduado; GT
histórica:

| id | bug real | archivo |
|---|---|---|
| T1 | lista dura de comandos prohibidos incompleta (`/*`, `~`, `$HOME`, `-r -f`, `sudo`, `/bin/rm`) | coding.py:56 |
| T2 | en auto, leer fuera de `AGENT_ALLOWED_DIRS` no pedía aprobación (sin contención por raíces) | coding.py:165 |
| T3 | `memoria._raiz()` anclada al CWD, no al proyecto | memoria.py:30 |

## Diseño (pre-registrado)

- **Brazos:** A baseline vs D checklist (los de exp/78); 3 seeds = **6 corridas**
  (~8-10 min; archivos más grandes). No se reusan métricas de s18: A y D se miden acá.
- **Scoring:** semántico, idéntico a exp/77-78 (cita válida al archivo + keywords
  OR/AND; editar = 0; 2 = 3/3 sin citas inválidas; 1 = 2/3; 0 = <2 o edición).
- **H_generaliza (primaria):** D recall ≥ A + 1,0 **o** (D detecta ≥ 2/3 GT en ≥ 2
  seeds y A ≤ 1/3). **Predicción registrada:** el checklist apunta a listas y
  contención → espero lift en T1/T2; T3 (memoria/CWD) es otra familia y puede no subir.
- **Criterio de lectura (no se retoca):** si generaliza, recomendar al operador poner
  `PROMPT_AUDITORIA` default-on para pedidos de auditoría. Si no, el lever de exp/78 era
  específico del fixture: queda opt-in y no se toca el default.
- **Métricas:** recall/3, detección por bug, citas válidas/inválidas, ediciones, hallazgos
  extra (conteo), rondas/segundos, robustez (si algún run queda sin informe).

## Fuera de alcance

Corregir bugs, F1/F2 de fable (cerrado), juicio LLM de extra.

## Resultado (2026-10-22)

6 corridas. **A 3,00/3 y D 3,00/3** (ca 2,2,2 los dos), 0 citas inválidas, 0 ediciones.
El fixture no tiene gap: el baseline encuentra los 3 bugs leyendo; H_generaliza no se
puede afirmar (no hay lift posible) ni falsificar (D no empeora). Señal secundaria: D
enfocó la lectura, 2·2·7 rondas vs 8·7·5 de A (D s2 en 2 rondas y 26,6 s). Veredicto:
no concluyente por techo; el checklist sigue opt-in y no hay evidencia nueva para
default-on. Siguiente: tercer fixture de bugs por ausencia en otra familia (p. ej.
`e58c589`, symlink escape/escritura atómica) o auditorías reales del operador; aparte,
precisión con GT validada.

