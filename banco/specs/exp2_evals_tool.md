# Spec: evals como tool del chat (exp/2)

(Motivo medido: en el test exhaustivo el modelo QUISO correr evals en
vivo, no existía la tool, su run_command fue rechazado, y degradó a leer
la corrida vieja del disco. Diseño split: la parte rápida es la útil en
conversación; la pesada se pide explícita.)

## Crear `modules/evals.py` (patrón módulo: TOOLS + IMPL)

DOS tools, reutilizando las funciones de evals.py (raíz) — importarlas,
no copiarlas:

### 1. `evals_linter` — RÁPIDA (código puro, segundos, sin LLM ni checkpoints)

- Esquema: sin parámetros obligatorios (args: {}).
- Descripción: "Evals rápidas del harness: linter de invariantes sobre
  las trazas .runs + costo por sesión. Código puro, tarda segundos. Úsala
  para auditar la salud de las sesiones; NO corre el bench del router."
- IMPL: iterar los .jsonl de evals.DIR_RUNS con evals._leer_eventos y
  evals.linter_traza (junta violaciones por invariante y archivos),
  más evals.costos_runs() — devolver texto compacto: resumen (n trazas,
  violaciones por invariante, top archivos) + top 3 sesiones por costo.
  Es un RESUMEN para el modelo, no el informe completo.

### 2. `evals_bench` — PESADA (bench del router, ~medio minuto)

- Esquema: sin parámetros.
- Descripción: "Evals pesadas: bench del router contra los 30 casos
  etiquetados (usa el checkpoint local ya cargado) con comparación contra
  el baseline persistido. Solo cuando el usuario pida el bench."
- IMPL: evals.correr_bench() + evals.comparar_baseline() → texto con
  score con compuerta, crudo, ECE, veredicto vs baseline y casos fallados.

## README — fila de capacidades

En la tabla de Capacidades, la fila `evals` pasa a decir que expone
`evals_linter` (rápida) y `evals_bench` (pesada) como tools del chat,
además del CLI `python3 main.py evals`.

## Tests (append en tests/test_smoke.py)

- El registro descubre el módulo: {"evals_linter", "evals_bench"} ⊆
  nombres de TOOLS del chat.
- evals_linter IMPL con monkeypatch de evals._leer_eventos/linter_traza/
  costos_runs (sin tocar trazas re ni cargar nada): devuelve texto con
  las violaciones contadas y el top de costo.
- evals_bench IMPL con monkeypatch de correr_bench/comparar_baseline:
  devuelve score/ECE/veredicto en el texto.

## Fuera de alcance

No tocar evals.py (raíz) ni su CLI. No tocar el supervisor ni sus
contratos (las tools nuevas llegan por el fallback de DeepSeek, como
siempre). No escribir informes a disco — las tools devuelven texto.
