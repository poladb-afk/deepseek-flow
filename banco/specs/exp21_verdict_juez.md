# exp/21 — el verdict estocástico del juez: sondear, endurecer, degradar

**El hallazgo medido** (exp/20, 2 corridas): `AssertionError: verdict
inválido` en 5/17 y 3/17 casos — SIEMPRE casos distintos, ~60 s quemados
por caso en los 3 retries del nodo. El contrato estructurado del Judge
(`juez.py:114-116`):

```python
veredicto = extraer_yaml(call_llm(prompt))
assert veredicto["verdict"] in ("ok", "retry"), "verdict inválido"
```

falla al azar en ~1 de cada 4-5 preguntas y, al agotarse los retries,
MATA el flujo entero (en el chat: la tool devuelve ERROR; en el bench:
el caso muere como excepción).

Método de la casa: **sonda antes de construir**. No adivinamos qué formas
toma el verdict malformado — las capturamos.

---

## Fase A — la sonda: `banco/probes/verdict_juez.py`

Instrumento de UNA vez (como cache_tools.py de exp/15), código puro de
orchestration + LLM real. NO toca juez.py: lo importa y lo envuelve.

**Mecánica**:
- Monkeypatchea `juez.call_llm` con un wrapper que registra CADA respuesta
  cruda (y la clasifica después: los prompts del Judge contienen
  "Evalúa el borrador", los del Draft no).
- Corre `juez.responder_con_juez(pregunta)` para las preguntas del bench
  que YA fueron víctimas del verdict inválido en alguna corrida
  (ids: ventana-caliente, read-max, trampa-pdf-filesapi, memoria-slug,
  a2a-protocolo, modelo-default, core-tools, supervisor-umbral — leerlas
  de banco/juez_preguntas.jsonl), 1 corrida cada una.
- Aunque `responder_con_juez` levante (verdict inválido tras retries), la
  sonda atrapa la excepción por pregunta y SIGUE con la siguiente (los
  crudos ya quedaron registrados por el wrapper).
- Clasifica CADA respuesta cruda del Judge con `estructura.extraer_yaml`
  (el mismo parseo de producción) y reporta por respuesta:
  {pregunta_id, parseo: "dict"|"fence-genérico"|"yaml-pelado"|"ROTO",
   verdict_crudo: <el valor tal cual o null>, valido: bool, shape: una
   etiqueta corta de la forma (p. ej. "ok", "OK", "'ok'", "ok.", "entregar",
   "sin clave verdict", "yaml roto total")}.
- Escribe `salidas/evals/verdict_shapes_<FECHA>.jsonl` (una línea por
  respuesta del Judge) e imprime un resumen: N respuestas, M válidas,
  tabla de shapes con conteo.

**Criterio de la fase A**: la tabla de shapes con ≥1 forma inválida real
capturada (si la mala suerte da 0, correr una segunda vuelta de las
mismas preguntas — la tasa medida es ~20%, con 8-16 evaluaciones la
esperanza es 2-3 capturas).

## Fase B — el fix (spec fina DESPUÉS de la sonda; lineas generales)

Dos capas, ambas ancladas a contratos:

1. **Normalización del verdict en `Judge.exec`** (la forma exacta la dictan
   los shapes medidos): str/strip/lower + mapa de alias SOLO si la sonda
   los justifica (p. ej. "OK"/"ok." → "ok"). El contrato semántico no se
   afloja: un verdict que no sea ok/retry tras normalizar sigue siendo
   inválido.
2. **Degradación terminal en `responder_con_juez`**: si el flujo igual
   revienta tras los retries del nodo, NO se muere — se entrega el ÚLTIMO
   borrador con advertencia explícita ("el juez no pudo emitir un
   veredicto legible; se entrega el borrador sin veredicto"), el mismo
   patrón del tope de rondas (L8: el bucle se autoacota y lo entrega todo
   con advertencia). Sin borrador (el Draft también reventó): se
   re-raise tal cual. `main.py juez` y `juez_lote` heredan la degradación
   por usar responder_con_juez.

**Candados** (tests, sin LLM):
- normalización: cada shape medido → verdict correcto; "entregar"/basura
  sigue inválido.
- degradación: flow que revienta con draft presente → (draft, advertencia);
  sin draft → raise. (Monkeypatch del flow o del call_llm.)

## Fase C — re-medición

`python3 main.py bench_juez` (SIN --actualizar-baseline primero: ver el
delta contra 76.5%; actualizar si el veredicto es mejora). Objetivo:
excepciones → 0; los ex-casos-muertos ahora puntúan por su borrador.
