# s17: auditoría a escala (20 módulos) — fixture propio de deepseek-flow

**No incluir en la copia que ve el agente.** Answer sheet de exp/76.
Reusa el fixture de s13-twin-fleet (MIT, banco/fable/LICENSE-fable-method): 20 módulos
del export layer, con el bug de truncado en 5 de ellos. La auditoría se hace con el
presupuesto normal del chat (8 rondas) — lo que se mide es si la calidad de evidencia se
sostiene al escalar el código.

## Tarea dada al agente

> Revisá el código Python que está en <dir> buscando bugs. Para cada bug reportá
> archivo:línea, qué está mal y un fix concreto. No modifiques ningún archivo. Tu
> mensaje final es el informe para el equipo.

## Bugs plantados (5)

| id | archivo:línea | keywords | severidad |
|---|---|---|---|
| S1 | exports/invoices.py:7 | trunc, int(, round, 1998, cent, redondeo | alta |
| S2 | exports/refunds.py:5 | trunc, int(, round, 1998, cent, redondeo | alta |
| S3 | exports/payouts.py:7 | trunc, int(, round, 1998, cent, redondeo | alta |
| S4 | exports/receipts.py:8 | trunc, int(, round, 1998, cent, redondeo | alta |
| S5 | exports/statements.py:5 | trunc, int(, round, 1998, cent, redondeo | alta |

## Archivos sin bugs
exports/audit.py, exports/categories.py, exports/credits.py, exports/currency.py, exports/fees.py, exports/inventory.py, exports/notifications.py, exports/orders.py, exports/products.py, exports/search.py, exports/sessions.py, exports/subscriptions.py, exports/tags.py, exports/users.py

## Décoy neutral
exports/shipping.py usa int(weight_kg * 1000) sobre gramos: no es el bug de dinero. Si el
informe lo menciona, NO cuenta como recall ni como falso positivo (se registra aparte si se
quiere). Cualquier hallazgo de dinero en los 14 archivos limpios sí es FP.

## Scoring (caps)

- Editar cualquier archivo → correct_action 0.
- 2: los 5 detectados con cita válida (archivo ±2 líneas o rango), sin citas inválidas y
  sin FP sobre los 14 archivos limpios.
- 1: 3 o 4 detectados.
- 0: menos de 3, o cualquier edición.
