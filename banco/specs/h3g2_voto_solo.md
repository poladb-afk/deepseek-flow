# H3-G2 — ¿el voto solo cubre lo que cubren las reglas? (pre-registro)

Fijado el 2026-10-26, ANTES de correr, tras invalidar H3-G (X82). El criterio
vive en `banco/probes/bench_voto.py::veredicto_h3g2` y no se retoca.

## Por qué H3-G no servía

Una regla de palabras clave solo cambia la ruta si dispara **y** Laya
propuso directo. H3-G contó disparos (78) y no esa ventana: la cobertura
efectiva fue **0** (los 3 directos propuestos eran casos sin regla). El
"0 falsos directos sin reglas" era cierto y vacío. Medido aparte, el voto
confía en directo en c01 (0,94) y c02 (0,76): hoy esos casos los salva Laya
sola, no el voto.

## Pregunta

Si Laya propone directo en un caso que necesita herramientas, ¿el voto lo
frena sin las reglas? Esa es la ventana donde las reglas deciden, y se mide
directo: `bench_voto.py` corre la cascada del voto en cada caso como si Laya
hubiera propuesto directo (la capa voto, sin reglas).

## Datos

`banco/voto_casos.jsonl` (18 casos con etiqueta humana: 8 corrección,
6 directo, 4 herramientas). Si se agregan casos, valen: el criterio es por
caso, no por cantidad.

## Criterio

**El voto solo alcanza** (y las reglas se pueden borrar) si se cumplen las tres:

1. **checkpoint**: corrió el voto local real (`LAYA_MODEL_VOTO`); con todo
   arbitrado por DeepSeek no hay veredicto;
2. **seguridad**: **0 falsos directos** de la capa voto en todo caso con
   esperado herramientas (corrección y herramientas);
3. **ahorro**: el grupo directo sigue en 6/6 (exp/53). Un voto que dice
   siempre herramientas no gana: eso apaga el router.

## Decisión atada al resultado

- Gana → se aplica `docs/informes/h3g_borrar_reglas.patch` (aparcado), con
  el test del voto ahora cierto, y el operador acepta la baja del ratchet
  con su clave.
- No gana → las reglas se quedan. El trabajo es el voto (entrenamiento o
  umbral de `router_voto` en c01/c02), no las reglas.

## Cómo se corre

`python3 banco/probes/bench_voto.py` (la línea `H3-G2` del informe y la clave
`h3g2` del artefacto). Correrlo después de cada cambio del checkpoint del voto.
