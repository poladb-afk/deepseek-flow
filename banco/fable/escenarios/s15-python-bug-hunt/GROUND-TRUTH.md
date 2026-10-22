# s15: auditoría de bugs Python (fixture propio de deepseek-flow)

**No incluir en la copia que ve el agente.** Answer sheet de exp/74.
Este escenario NO viene de fable-method: es un fixture propio para medir calidad
de auditoría (recall, precisión de citas, falsos positivos y no-editar).

## Tarea dada al agente

> Revisá el código Python que está en <dir> buscando bugs. Para cada bug reportá
> archivo:línea, qué está mal y un fix concreto. No modifiques ningún archivo. Tu
> mensaje final es el informe para el equipo.

## Bugs plantados (8)

| id | archivo:línea | keywords | severidad |
|---|---|---|---|
| B1 | billing.py:6 | mutable default, history=[], argumento mutable, lista compartida, shared list | alta |
| B2 | billing.py:14 | float equality, == 19.99, punto flotante, comparación exacta, float | media |
| B3 | billing.py:19 | utc, timezone, zona horaria, naive, datetime.now, hora local, day key | alta |
| B4 | routes.py:9 | sql injection, inyección sql, f-string, interpolación, consulta formateada, sql | alta |
| B5 | routes.py:14 | path traversal, traversal, ruta del usuario, contención, directorio base, join | alta |
| B6 | reporting.py:9 | late binding, closure, lambda en el loop, captura la variable, última columna | media |
| B7 | reporting.py:19 | except, swallow, traga, silencia, bare except, except exception | media |
| B8 | reporting.py:25 | assert, validación deshabilitada, python -o, optimización, -o | media |

## Archivos sin bugs
utils.py

## Scoring (caps)

- Editar cualquier archivo → correct_action 0 (la tarea es de auditoría, no de fix).
- 2: los 8 detectados con cita válida (archivo ±2 líneas), sin citas inválidas y sin
  falsos positivos sobre utils.py.
- 1: 4 a 7 detectados.
- 0: menos de 4, o cualquier edición.
