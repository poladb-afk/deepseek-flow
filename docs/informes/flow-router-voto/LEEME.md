# El paquete Kaggle de router_voto — 2026-10-05

## Qué es

El checkpoint del VOTO de confirmación del router (Mesa 3): segunda opinión
local antes de responder directo. La pregunta `confirma_herramientas` es el
contrato; el estado es `{"pregunta": ...}` igual que el router.

## Datos

- `data/router_voto_verified.jsonl`: 288 casos verificados por juez ciego
  (500 generados dirigidos a la banda de confusión imperativos/trampas;
  el juez se quedó con los defendibles).
- `tasks/router_voto_test.jsonl`: 30 held-out (15/15), muestreados del pool
  verificado con seed 42.

## La puerta de aceptación (lo que decide si se promueve)

La correlación de errores router↔voto sobre el bench (evals.py): si los dos
checkpoints fallan juntos en los falso-directos, el voto local es eco y NO
reemplaza al de DeepSeek — queda como hallazgo. Ver design.md de
deepseek-flow, Mesa 3.

## Corrido

    kaggle datasets create -p . (con dataset-metadata)
    kaggle kernels push -p . (T4x2, internet)
