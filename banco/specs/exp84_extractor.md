# Spec de ejecución — exp/84: el extractor de claims no puede depender del fraseo

**Estado:** ejecutada el 2026-10-22; C1–C4 ✅ — resultado en [bitacora](../../docs/bitacora.md) exp/84.
**Instrumento:** una ronda del chat del harness (PROMPT_FABLE=1, scope cerrado) + e2e de meta-verificación.

## Contexto

Deuda declarada por exp/83: el meta-juicio ronda 2 no re-ejecutó NADA porque el reporte
declaraba las verificaciones en prosa ("Verificaciones: pytest ... da 63 passed y ruff
check . está limpio") y el extractor las clasificó como `hecho` — sin `tipo: verificacion`
no hay `comando`, y sin comando no hay re-ejecución. La ronda 1, con otro fraseo, sí las
extrajo: es suerte de redacción, no contrato. Además, el item 2 de la spec de exp/83
(preferir `python3 -m pytest` del directorio para claims de "todos los tests" sin archivo)
nunca se implementó — lo señaló el propio meta-juicio como alcance no cubierto.

## Diseño (pre-registrado)

El principio de la casa: **los hechos los reúne el código, el LLM solo interpreta**.

1. `candidatas_verificacion(reporte)` — función PURA en `fable_judge.py`: frases
   (líneas/sentencias) del reporte que mencionan corridas o checks (pytest, tests
   pass/passed, ruff, lint, exit N, gate, calidad, verde), acotadas a ~8. Es una AYUDA de
   clasificación, no un veredicto.
2. El prompt de `RecolectarClaims` suma el bloque "Frases del reporte que el código marcó
   como candidatas a verificación" con el contrato reforzado: cada candidata que realmente
   afirme haber corrido algo va con `tipo: verificacion` y `comando` inferible exacto
   (solo python/pytest/`ruff check` sobre el trabajo); para "todos los tests" sin archivo
   específico, `python3 -m pytest` (el directorio).
3. Tests sin LLM: la pura detecta las candidatas y no matchea prosa neutra; el prompt
   contiene el bloque, el contrato reforzado y la sugerencia del directorio.

**Corrida:** un turno de banco (exp84-extractor, scope a `fable_judge.py` +
`tests/test_fable_judge.py`); si el presupuesto no alcanza, el operador cierra como en
exp/83 y queda registrado.

## Criterios (congelados)

- **C1:** banco 2/2, sin HITL fuera de scope; o cierre del operador declarado.
- **C2 (determinista):** tests de la pura y del prompt pasan; nada del modo dominio ni de
  `contenido_nuevos` se rompe.
- **C3 (e2e, el que importa):** re-ejecutar la meta-verificación de exp/83 ronda 2 — el
  reporte con verificaciones EN PROSA sobre el diff actual — y verificar en el output del
  juez que el claim de pytest se re-ejecutó (`re-ejecutado:` presente con exit 0) y el de
  ruff llega a intentarse (`re-ejecutado` o `no se ejecutó`/fuera de allowlist — lo que no
  puede volver a pasar es que las verificaciones ni aparezcan como claims de verificación).
- **C4:** `./calidad.sh` verde.
- **Predicción:** C3 pasa con pytest re-ejecutado auto y ruff pidiendo el s/n (policy:
  ruff no está en la whitelist de solo-lectura de run_command).

## Fuera de alcance

Cambiar la policy de run_command (ruff a la whitelist de autos), F2, extracción de claims
sin LLM.


## Resultado (2026-10-22)

Cerrada por el chat en UNA ronda. C1 ✅ banco 2/2; C2 ✅ tests; **C3 ✅ el
mismo reporte en prosa que extraía cero verificaciones ahora produce ambos
claims como verificacion y los dos se re-ejecutan (pytest exit 0 auto, ruff
check exit 0)**; C4 ✅ gate verde 868 tests. El REFUTED restante del e2e es
la deuda #2 de exp/83 confirmada (archivos del operador sin declarar en el
reporte) — no un fallo del extractor.
