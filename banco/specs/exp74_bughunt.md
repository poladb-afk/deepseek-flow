# Spec de ejecución — exp/74: calidad de auditoría de bugs Python

**Estado:** aprobada y ejecutada el 2026-10-22 (6 corridas); resultado abajo y en [bitacora](../../docs/bitacora.md) exp/74.
**Instrumento:** el bench de exp/72-73 (`banco/probes/bench_fable.py`) reutilizado
con un fixture **propio** (no viene de fable-method): `s15-python-bug-hunt`.

## Pregunta

¿Qué calidad tiene el chat auditando código Python realista: cuántos bugs encuentra,
con citas válidas, sin falsos positivos y sin editar? ¿la prosa del método cambia algo?

## Fixture (`banco/fable/escenarios/s15-python-bug-hunt/`)

4 archivos (`billing.py`, `routes.py`, `reporting.py`, `utils.py`) con **8 bugs
plantados** en 3 archivos y **1 archivo limpio** (`utils.py`) para medir falsos
positivos. `GROUND-TRUTH.md` es machine-readable (tabla `id | archivo:línea |
keywords | severidad`) y es la fuente única del scorer.

| id | bug | severidad |
|---|---|---|
| B1 | mutable default (`history=[]`) | alta |
| B2 | comparación de float (`== 19.99`) | media |
| B3 | `datetime.now()` local vs UTC | alta |
| B4 | SQL injection por f-string | alta |
| B5 | path traversal en `os.path.join` | alta |
| B6 | late binding de lambda en loop | media |
| B7 | `except Exception: pass` | media |
| B8 | `assert` como validación (muere con `-O`) | media |

## Diseño (pre-registrado)

- **Brazos:** A baseline (`PROMPT_FABLE=0`) y B prosa (`PROMPT_FABLE=1`); el resto
  idéntico. `SKILLS=0` para aislar del disparo de la skill `revision` (la tarea es en
  español y el router la dispararía).
- **n:** 3 seeds × 2 brazos = **6 corridas** (~5 min); smoke-grade declarado.
- **Tarea:** "Revisá el código Python que está en <dir> buscando bugs. Para cada bug
  reportá archivo:línea, qué está mal y un fix concreto. No modifiques ningún archivo.
  Tu mensaje final es el informe para el equipo."
- **Scoring determinista:** cita válida = `archivo:línea` resuelta dentro del run
  (se reusa `utils/citas.extraer` del producto) y a ±2 líneas de la GT, más una keyword
  del bug en el reporte. Falso positivo = cita a `utils.py` en una línea con lenguaje
  de bug. Edición de cualquier archivo → 0. `correct_action`: 2 = 8/8 sin citas
  inválidas ni FP; 1 = 4-7; 0 = <4 o edición.
- **Métricas de calidad (las que importan acá):** bugs encontrados por corrida (de 8),
  detección por bug agregada sobre los 6 runs, citas válidas/inválidas, falsos positivos,
  ediciones, segundos/rondas.

## Criterio de lectura (pre-registrado, no se retoca)

No es el criterio de trampas de fable (acá no se decide F1/F2): es una medición de
calidad. Umbrales fijados antes de correr, sobre el promedio del **baseline A**:

- **usable:** A detecta ≥ 6/8 en promedio, 0 ediciones y ≥ 90% de citas válidas.
- **gris:** 5/8.
- **hueco:** ≤ 4/8 → justifica un experimento de producto (exp/75: skill/checklist de
  revisión con verificación de citas y formato), no el flow de fable.

Predicción registrada (secundaria): `H_prosa FALSA` — la prosa no cambia recall; sí puede
cambiar el formato (más líneas INTENT/TWINS/PENDING y citas).

## Fuera de alcance

Corregir bugs (la tarea es de auditoría), F1/F2 de fable (línea cerrada en exp/73),
`plain_language`, juicio LLM de la calidad del reporte.

## Resultado (2026-10-22)

6 corridas. **A baseline: recall 7,33/8**, 0 ediciones, 100% de citas válidas, 1 FP puntual.
**B prosa: 7,67/8**, 0 citas inválidas, 0 FP (Δ +0,33 < 1,00, n=3 → `H_prosa FALSA`,
predicha). Detección por bug sobre 6: B1 6/6, B2 5/6, B3 4/6, B4 6/6, B5 6/6, B6 6/6,
B7 6/6, B8 6/6. **Veredicto: usable** (A ≥ 6/8, 0 ediciones, ≥ 90% citas válidas). Los
faltantes son semánticos (naive datetime vs UTC; comparación de float). El scorer se ajustó
antes de leer el veredicto para aceptar rangos de línea y no contar negaciones como FP, y se
re-puntuaron los 6 reportes simétrico A/B. No se abre exp/75: si se quiere subir el piso de
los bugs semánticos, el lugar es la skill/checklist de revisión, no el flow de fable.

