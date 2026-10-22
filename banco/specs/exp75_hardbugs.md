# Spec de ejecución — exp/75: vara más exigente (bugs semánticos y concurrencia)

**Estado:** aprobada y ejecutada el 2026-10-22 (9 corridas); resultado abajo y en [bitacora](../../docs/bitacora.md) exp/75.
**Instrumento:** bench de exp/72-74 (`banco/probes/bench_fable.py`) con un fixture
**propio** `s16-hard-bug-hunt` (no viene de fable) y un **tercer brazo** C = skill
`revision` del harness.

## Pregunta

Con bugs semánticos/de estado/concurrencia (más difíciles que los "de libro" de
s15), ¿qué recall alcanza el baseline, y qué agrega la prosa de fable (B) o la
skill `revision` del propio harness (C)?

## Fixture (`banco/fable/escenarios/s16-hard-bug-hunt/`)

4 archivos, **8 bugs difíciles** en 3 archivos + `utils.py` limpio (FP). GT
machine-readable (tabla `id | archivo:línea | keywords | severidad`).

| id | bug | archivo:línea |
|---|---|---|
| H1 | race check-then-act en caché compartida (lock sin usar) | state.py:15 |
| H2 | shallow copy que comparte la lista de roles | state.py:26 |
| H3 | acumulación de floats para dinero + truncado | ledger.py:10 |
| H4 | retry no idempotente: ledger duplicado | ledger.py:18 |
| H5 | atributo de clase mutable compartido | reporting_hard.py:7 |
| H6 | iterador agotado antes del count | reporting_hard.py:17 |
| H7 | lock sin try/finally (deadlock ante excepción) | reporting_hard.py:24 |
| H8 | `utcnow()` naive tratado como hora local en `timestamp()` | reporting_hard.py:29 |

## Diseño (pre-registrado)

- **Brazos:** A baseline (`PROMPT_FABLE=0, SKILLS=0`), B prosa (`PROMPT_FABLE=1,
  SKILLS=0`), C skill revision (`PROMPT_FABLE=0, SKILLS=1`). Misma tarea, fixture,
  seeds y scoring; lo único que cambia es el entorno del brazo.
- **n:** 3 seeds × 3 brazos = **9 corridas** (~7 min); smoke-grade declarado.
- **Scoring — idéntico a exp/74:** cita válida a ±2 líneas o dentro del rango citado
  + keyword del bug; FP en `utils.py` (negaciones explícitas no cuentan); editar = 0;
  correct_action 2 = 8/8 sin citas inválidas ni FP, 1 = 4-7, 0 = <4 o edición.
- **Predicciones registradas:**
  - **H_recall:** A < 6/8 (la vara difícil debería exponer el techo que s15 no
    mostró: 7,33/8).
  - **H_prosa:** B ≈ A (sin lift; exp/72-74).
  - **H_skill:** C ≈ A (la skill `revision` no subió detección en exp/56; predigo
    que tampoco acá, aunque puede mejorar formato/citas).
- **Criterio de lectura (no se retoca):** si A < 6/8, queda confirmado el hueco
  semántico; si **algún** brazo sube ≥ 1,0 en recall o alcanza ≥ 6/8, ese es el lever
  a proponer como producto; si ninguno lo hace, la conclusión es que la calidad en
  esta familia de bugs necesita una verificación más fuerte (tests/ejecución) y no
  otra directiva.
- **Métricas:** recall/8 por corrida, detección por bug sobre 9 runs, citas
  válidas/inválidas, FP, ediciones, segundos/rondas.

## Fuera de alcance

Corregir bugs (la tarea es de auditoría), F1/F2 de fable (línea cerrada en exp/73),
juicio LLM de la calidad del informe, `plain_language`.

## Resultado (2026-10-22)

9 corridas. **A baseline: 8,00/8** (2,2,2), 0 citas inválidas, 0 FP, 0 ediciones, 41 s.
**B prosa: 7,33/8** (1,2,1), 1 cita inválida, 58 s. **C skill revision: 6,67/8** (1,1,2),
41 s. H_recall FALSA (el baseline no tiene techo en esta familia), H_prosa sin lift,
H_skill FALSA (C queda por debajo y en s1 citó líneas corridas >2 respecto del bug: la
skill no mejora la evidencia). Detección /9: H1 9, H2 7, H3 8, H4 8, H5 8, H6 9, H7 8,
H8 9. El scorer se corrigió (resolución de citas repo-relative/absolutas; C s1 pasó de
1/8 aparente a 5/8 real) y se re-puntuaron exp/75 y exp/74 (exp/74 sin cambios). **La vara
de sutileza ya no discrimina**: el siguiente paso es escala/contexto (exp/76 propuesto),
no más bugs semánticos en 4 archivos.

