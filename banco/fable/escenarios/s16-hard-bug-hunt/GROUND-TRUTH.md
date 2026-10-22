# s16: auditoría de bugs difíciles (fixture propio de deepseek-flow)

**No incluir en la copia que ve el agente.** Answer sheet de exp/75.
Fixture propio (no viene de fable-method): bugs semánticos, de estado y de
concurrencia — más difíciles que los "de libro" de s15.

## Tarea dada al agente

> Revisá el código Python que está en <dir> buscando bugs. Para cada bug reportá
> archivo:línea, qué está mal y un fix concreto. No modifiques ningún archivo. Tu
> mensaje final es el informe para el equipo.

## Bugs plantados (8)

| id | archivo:línea | keywords | severidad |
|---|---|---|---|
| H1 | state.py:15 | race, check-then-act, lock, concurren, carrera, _cache | alta |
| H2 | state.py:26 | shallow copy, copy.copy, roles, shallow, referencia, lista compartida | alta |
| H3 | ledger.py:10 | float, flotante, redondeo, acumul, centavos, int(total * 100) | alta |
| H4 | ledger.py:18 | idempot, retry, reintent, duplic, ledger, _ledger.append | alta |
| H5 | reporting_hard.py:7 | class attribute, atributo de clase, shared, compartid, history | media |
| H6 | reporting_hard.py:17 | iterator, iterador, exhaust, consum, list(rows_iter), generator | media |
| H7 | reporting_hard.py:24 | try/finally, finally, lock, deadlock, interbloqueo, release | alta |
| H8 | reporting_hard.py:29 | utcnow, naive, timestamp, utc, hora local, timezone | media |

## Archivos sin bugs
utils.py

## Scoring (caps)

- Editar cualquier archivo → correct_action 0 (tarea de auditoría, no de fix).
- 2: los 8 detectados con cita válida (archivo ±2 líneas o dentro del rango),
  sin citas inválidas y sin falsos positivos sobre utils.py.
- 1: 4 a 7 detectados.
- 0: menos de 4, o cualquier edición.
