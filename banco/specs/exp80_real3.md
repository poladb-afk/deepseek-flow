# Spec de ejecución — exp/80: tercer fixture real (symlink escape y .tmp)

**Estado:** aprobada y ejecutada el 2026-10-22 (6 corridas); resultado abajo y en [bitacora](../../docs/bitacora.md) exp/80.
**Instrumento:** bench de exp/72-79 con un tercer fixture de **código real pre-fix**.

## Pregunta

El checklist D (exp/78) subió el recall en s18 (bugs por ausencia) y quedó neutro en s19
(fixture sin gap). ¿Generaliza a una **segunda familia con gap esperado**: controles
incompletos de contención y escritura (symlink escape, .tmp)?

## Fixture (`banco/fable/escenarios/s20-real-audit-3/`)

Versiones REALES pre-fix (commit `e58c589^`): `modules/coding.py` (425 líneas) y
`utils/fs_tools.py` (500). GT histórica:

| id | bug real | archivo |
|---|---|---|
| U1 | `_sale_de_raices` lexical: un symlink dentro de las raíces (`cat link`) no se resuelve; `auto` lee fuera de `AGENT_ALLOWED_DIRS` | coding.py:170 |
| U2 | `escribir_atomico` usa nombre fijo `<destino>.tmp`: un symlink plantado redirige la escritura fuera de las raíces | fs_tools.py:149 |

## Diseño (pre-registrado)

- **Brazos:** A baseline vs D checklist; 3 seeds = **6 corridas** (~8 min).
- **Scoring:** semántico (cita al archivo + keywords OR/AND; editar = 0; 2 = 2/2 sin
  citas inválidas; 1 = 1/2; 0 = 0).
- **H_generaliza2 (primaria):** que haya gap (A no saque 2/2 en todas las seeds) y que D
  lo cierre: D recall ≥ A + 1,0, o D encuentra los 2 GT en ≥ 2 seeds mientras A ≤ 1.
  **Predicción:** el checklist apunta a canonicalización y escritura → espero lift en
  U1/U2; pero los archivos son grandes (925 líneas) y pueden alcanzar mal las 8 rondas.
- **Criterio de lectura (no se retoca):**
  - Si hay gap y D lo cierra → el checklist generaliza en 2 fixtures con gap: recomendar
    al operador discutir default-on para pedidos de auditoría.
  - Si el fixture vuelve a techo → no hay evidencia nueva; el checklist queda opt-in.
  - Si D empeora → opt-in y se documenta el límite.
- **Métricas:** recall/2, detección por bug, citas válidas/inválidas, ediciones, extra,
  rondas/segundos y robustez (runs sin informe).

## Fuera de alcance

Corregir bugs, F1/F2 de fable (cerrado), juicio LLM de extra.

## Resultado (2026-10-22)

6 corridas. **A 2,00/2 y D 2,00/2** (U1/U2 detectados 6/6), sin gap: los bugs de
contención/escritura se ven leyendo. H_generaliza2 FALSA (sin lift). Los ca=0 no son de
recall: A s2 citó una línea inválida y la autocorrigió en el texto (el scorer la cuenta);
D s1 dejó un archivo temporal `.tmp_check_denylist.py` y violó "no edites" (edit → 0).
Señal negativa para default-on: D creó un temporal en 1/3 aunque su directiva lo prohíbe;
A no creó ninguno. Veredicto: el checklist queda opt-in; el lift solo se midió en s18.
Siguiente: si se productiza, endurecer "no crees temporales" y medir en fixtures con gap;
para default-on hace falta evidencia de uso real, no más fixtures.

