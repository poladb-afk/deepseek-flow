# exp/21 — fase B2: de parche a patrón (supera a la fase B)

**La crítica que motiva esta fase** (del dueño del harness, correcta): la
fase B puso DOS parches encima del problema — la línea de prompt que
enumera sinónimos prohibidos ("no uses needs_changes, revisar,
corregir…") y `_ALIAS_VERDICT` clavado al único sinónimo observado. Ambos
persiguen el token medido: un sinónimo nuevo (`revisar`, `changes_needed`,
"OK!") los atraviesa. Y la degradación terminal, sola, convierte el crash
en entrega SIN JUZGAR — pérdida silenciosa del control de calidad.

**El patrón correcto ya vive en este harness**: error-como-feedback con
reintento informado (el supervisor re-entra los args de una tool fallida
con el error como feedback explícito; exp/10 le enseñó lo mismo a
edit_file). El verdict ilegible del Judge es exactamente ese caso.

## El fix estructural en `juez.py` (Judge.exec)

1. **Quitar los dos parches**: la línea de prompt con la lista de
   sinónimos prohibidos y `_ALIAS_VERDICT` entero. El prompt del Judge
   vuelve a su forma original (que pide yaml con verdict ok/retry).
2. **Canonicalización mínima** (esto NO es parche: case/whitespace son
   ruido de codificación, no semántica): `str(v).strip().lower()`.
3. **Loop de reparación con feedback** (el corazón): validar el yaml
   parseado con un helper `_veredicto_valido(d) -> (bool, motivo)` que
   chequee AMBAS condiciones del contrato (verdict ∈ ok/retry tras
   canonicalizar, y problems lista si está). Si invalida —incluido
   extraer_yaml levantando—: UN reintento INFORMADO: el mismo prompt +
   bloque de feedback que cita la respuesta inválida del modelo VERBATIM
   (recortada a ~300 chars) y el contrato. Print observable en terminal
   estilo banco-markers: `[juez] verdict ilegible → reintento con
   feedback` (colorear aviso, flush), para que el banco y el usuario lo
   vean cuando dispara.
4. **Fallback semántico** (ni con feedback validó): NO crash, NO entrega
   sin juzgar muda: devolver `{"verdict": "retry", "problems": ["el juez
   no pudo emitir un veredicto legible (último crudo: <recorte>); revisá
   precisión y citas del borrador"]}` — el lado SEGURO del contrato binario:
   si no se puede confirmar ok, no está ok; el borrador da una vuelta más
   con ese problema como feedback, bounded por max_rounds (L8) como todo
   bucle del harness. Al agotarse las rondas, el camino de siempre entrega
   con advertencia.
5. La degradación try/except de `responder_con_juez` (fase B) queda como
   armadura de último recurso (Draft muerto por API, etc.): con este
   patrón, para el verdict es prácticamente inalcanzable.

**Semántica del costo**: un verdict ilegible cuesta 1 llamada extra de
reparación (no 3 retries ciegos del nodo que re-preguntan lo mismo); el
fallback cuesta una ronda de borrador que el tope ya acota.

## Candados (tests/test_smoke.py — reescribir los de la fase B)

- reparación: call_llm mocking en SECUENCIA — primero inválido
  ('needs_changes'), segundo válido ('retry') → verdict final 'retry' con
  problems del segundo (la reparación FUNCIONA para el sinónimo medido
  sin alias alguno).
- fallback: ambos inválidos → verdict 'retry' con el crudo citado en
  problems (y problems es lista) — nunca raise por verdict.
- extraer_yaml revienta (yaml roto total) → mismo loop (reparación o
  fallback), sin excepción que escape de exec.
- canonicalización pura: ' OK ' → ok (queda de la fase B).
- problems con forma inválida (string) también dispara la reparación.
- la degradación de responder_con_juez sigue con sus 2 tests de la fase B.

## Re-medición

`python3 main.py bench_juez` comparando contra el baseline vigente
(94.1 / 87.5): el objetivo es SOSTENER (sin parches) — y el marcador
`[juez] verdict ilegible` en la salida del bench dice cuántas veces el
patrón trabajó. Sin regresión → `--actualizar-baseline`.
