# exp/20 — bench del juez: la vara que le faltaba a answer_verified

**Problema**: `answer_verified` es la herramienta insignia de calidad y no
tiene bench: cada cambio al juez se valida a ojo. El router mejoró cuando
tuvo test a mano + curva; el juez merece lo mismo.

**Qué ya está hecho** (la escribió la auditoría, no el harness):
`banco/juez_preguntas.jsonl` — 17 casos con etiquetas verificadas
mecánicamente contra el repo (15 de hecho + 2 trampas: una herramienta
inexistente y una premisa falsa con corrección positiva). Formato por caso:

```json
{"id": "...", "pregunta": "...",
 "contiene": ["..."],          # TODOS deben estar (case-insensitive) en la respuesta
 "contiene_alguno": ["..."],   # opcional: AL MENOS UNO debe estar
 "cita_archivo": "utils/x.py", # opcional: sufijo de la ruta citada esperada
 "cita_contiene": ["..."],     # la LÍNEA citada (leída del disco) contiene AL MENOS UNO
 "trampa": false}
```

## La pieza: bench_juez.py (standalone + subcomando)

`python3 main.py bench_juez [--preguntas banco/juez_preguntas.jsonl] [--actualizar-baseline]`

- **Corre**: SECUENCIAL (instrumento de medición: determinismo antes que
  velocidad), un `juez.responder_con_juez(pregunta)` por caso (rondas
  default del juez), midiendo segundos por caso.
- **Evalúa (código puro, sin LLM — el grading NO lo hace un modelo)**:
  - `respuesta_ok(texto, caso)`: todos los `contiene` presentes
    (case-insensitive) Y (si hay `contiene_alguno`) al menos uno presente.
  - `cita_ok(texto, caso)`: si el caso no tiene `cita_archivo` → None
    (no aplica). Si tiene: al menos una cita que matchee el mismo regex
    de producción (`(/[\w./-]+\.[\w]+):(\d+)`, importá CITA_RE de juez.py)
    cuya ruta termine en `cita_archivo` y cuya línea citada — LEÍDA DEL
    DISCO con ese número — contenga (case-insensitive) al menos un
    `cita_contiene`. Es la misma verificación que hace el Judge en
    producción pero INDEPENDIENTE (no confiamos en el juez para calificar
    al juez: leemos nosotros).
  - Métricas: `respuesta_ok` rate (la principal), `cita_ok` rate sobre
    los que aplican, y el detalle por caso.
- **Reporta**: markdown en `salidas/evals/bench_juez_<FECHA>.md` — tabla
  (caso, respuesta_ok, cita_ok, seg) + por cada fallo UN bloque con el
  esperado vs lo que faltó (qué token no apareció, qué cita no verificó).
- **Baseline** (patrón de evals.py): `salidas/evals/bench_juez.json` con
  {fecha, git_sha, n, respuesta_ok, cita_ok}. Sin `--actualizar-baseline`:
  si existe baseline, lo compara y reporta el delta (y NO lo pisa — la
  tool del chat del futuro hereda esta regla). Con la flag: lo guarda.
  El git sha: reusá el `_git_sha()` de evals.py si sirve, o equivalente.
- **Subcomando**: `"bench_juez": "bench_juez"` en main.py SUBCOMANDOS.

Candados (`tests/test_smoke.py`, sin LLM — las funciones de evaluación son
puras, el runner completo es la medición del exp):
1. `respuesta_ok`: caso con todos los tokens → True; falta uno → False;
   con `contiene_alguno`: uno presente → True, ninguno → False;
   case-insensitive.
2. `cita_ok`: cita correcta contra un fixture real en tmp_path (creá un
   archivo chico, citá SU línea exacta) → True; cita al archivo correcto
   pero línea que no contiene el token → False; ruta equivocada → False;
   caso sin cita_archivo → None; cita inexistente (línea beyond EOF) → False.
3. baseline: guardar → comparar reporta delta; sin flag NO se pisa
   (guardar una vez, corromper el score esperado en memoria, verificar
   que el archivo no cambió).
4. preguntas inválidas (json roto / falta id o pregunta) → error claro,
   no silencio.

## La medición del exp (la corre la auditoría, no es test)

Con el runner listo: `python3 main.py bench_juez --actualizar-baseline`
con LLM real → el baseline primero queda registrado con su git sha. Ese
número es el punto de partida de TODO cambio futuro al juez (comité de
jueces, gate de Laya, etc.).
