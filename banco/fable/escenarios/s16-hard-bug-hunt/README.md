# payments-api (mini servicio)

Servicio chico de cobros que comparte estado entre workers y escribe un ledger
de pagos.

- state.py: caché de usuarios compartida por los hilos de request.
- ledger.py: totales y reintentos de cobro.
- reporting_hard.py: helpers del job nocturno (contadores, locks, timestamps).
- utils.py: helpers generales.
