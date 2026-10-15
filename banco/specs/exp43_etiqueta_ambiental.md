# Spec: la etiqueta ambiental del router — la flywheel (exp/43)

Contexto (exp/35 y el diagnóstico de la revisión): el registro de decisiones
(`salidas/routing.jsonl`) ya guarda propuesta/causa/p_directo por pregunta, y
`LAYA_MODO=shadow` corre Laya sin cambiar la conducta. Lo que falta para
calibrar con tráfico real es la ETIQUETA. Hoy la produce un etiquetador LLM
(`banco/probes/etiquetar_router.py`, 1 llamada DeepSeek por pregunta). La
insight de exp/43: en modo shadow la ruta aplicada es SIEMPRE herramientas,
así que DeepSeek corre con tools — y **si responde sin llamar ninguna, la
pregunta era directo en la práctica**. Esa es la etiqueta ambiental: gratis,
en la distribución exacta de producción, crece sola con el uso. Es además la
definición OPERATIVA correcta del objetivo del router (predecir si el bucle
de tools va a arrancar), no una opinión de oráculo sobre la pregunta.

Límite honesto (documentar en el código): la etiqueta mide lo que DeepSeek
HIZO, no lo que NECESITABA — un modelo que responde de memoria una pregunta
de archivos etiqueta "directo" aunque otro modelo hubiese leído. Ruido
declarado; el volumen lo compensa.

## 1. `utils/laya_routing.py`

- Las líneas de decisión ganan un `"id"` único (`uuid4().hex[:8]`), generado
  en `nodes.LayaRouter.post` y viajando DENTRO del dict del evento —
  `registrar_decision` no cambia (ya hace `{**evento}`).
- Nueva `registrar_resultado(id_decision, rondas, ruta=None)`: appendea al
  MISMO archivo (`LAYA_LOG_ARCHIVO`) la línea
  `{"ts": ..., "evento": "resultado", "id": id_decision, "uso_tools": rondas > 0, "rondas": int(rondas)}`.
  Misma ley que `registrar_decision`: gated por `LAYA_LOG_DECISIONES`,
  bookkeeping (cualquier fallo se traga, nunca rompe el chat).

## 2. `nodes.py`

- `LayaRouter.post`: después de `registrar_decision`, si
  `config.modo == "shadow" and p_directo is not None` →
  `shared["_router_pendiente"] = <el id de esa decisión>`.
  Solo ahí: en enforce la etiqueta mediría la política (tools retiradas en
  directo → uso_tools siempre falso, sin valor), y sin probabilidades no hay
  par calibrable (p, etiqueta).
- `AgentStep.post`, en el camino que devuelve `"answer"` (sin tool_calls):
  `pend = shared.pop("_router_pendiente", None)`; si hay pendiente →
  `registrar_resultado(pend, shared.get("tool_rounds", 0))` y print coloreado
  nivel "info":
  `  [router] etiqueta ambiental: directo (0 rondas)` o
  `  [router] etiqueta ambiental: herramientas (N rondas)`.
  El pop SOLO al responder: con `"tool"` el pendiente sobrevive (la etiqueta
  espera a que el ciclo de la pregunta cierre). `tool_rounds` es por pregunta
  (lo resetea `GetQuestion.post`), así que a la altura del answer final es el
  total de la pregunta. Imports perezosos como hace la casa en ese post.
- `GetQuestion.post`: `shared.pop("_router_pendiente", None)` junto al reset
  de presupuesto — una pregunta nueva empieza limpia y un ciclo abortado
  (salir a mitad) no etiqueta la pregunta siguiente.

## 3. `banco/banco.py`

`MARCADORES` gana `"etiqueta_ambiental": r"\[router\] etiqueta ambiental"`
(para que el banco cuente la señal en los A/B).

## 4. `banco/probes/etiquetar_ambiental.py` (nuevo, código puro, sin LLM)

Lee el routing log (default `salidas/routing.jsonl`, flag `--ruta`), UNE por
`id` las líneas de decisión (con `p_directo`) con sus `resultado`, y emite el
JSONL de calibración — formato drop-in para `utils/conformal.leer_calibracion`
(claves `conf` + `correcto`) y hermano del set a mano
(`banco/calibracion_router_2026-10-08.jsonl`):

```json
{"ts": ..., "pregunta": "...", "laya": "directo", "conf": 0.91,
 "etiqueta": "herramientas", "correcto": false,
 "fuente": "etiqueta ambiental exp/43"}
```

- `laya` = la `propuesta` de la decisión; `conf` = confianza de la opción
  ELEGIDA (`p_directo` si propuesta es directo, `1 - p_directo` si no — la
  semántica que espera `conformal.puntaje`); `etiqueta` = `"directo"` si
  `uso_tools` es false, `"herramientas"` si true; `correcto` =
  `propuesta == etiqueta`. `pregunta` solo si estaba logueada
  (`LAYA_LOG_PREGUNTA=1`).
- Decisiones sin resultado (ciclos abiertos: salir a mitad) se saltan.
- El JOIN es una función PURA `(lineas) -> filas` testeable sin disco; la CLI
  aparte. Escribe incremental y reporta n + balance de clases.
- Uso: `python3 banco/probes/etiquetar_ambiental.py [--ruta ...] [--salida ...]`
  (salida default `banco/calibracion_ambiental_FECHA.jsonl`).

## 5. Tests (`tests/test_laya_routing.py`, append — seguir el estilo
monkeypatch de `test_el_nodo_pasa_la_pregunta_al_registro`)

1. `registrar_resultado` escribe la línea completa; con
   `LAYA_LOG_DECISIONES=0` no escribe; con ruta rota no levanta.
2. `LayaRouter.post` en shadow con probabilidades →
   `shared["_router_pendiente"]` es EXACTAMENTE el `id` de la línea de
   decisión escrita (el join 1:1 es el contrato).
3. `LayaRouter.post` en enforce → sin pendiente; en shadow con respuesta
   inválida (p_directo None) → sin pendiente.
4. `AgentStep.post` answer consume: `tool_rounds=0` → línea resultado
   `uso_tools=false`; `tool_rounds=3` → `uso_tools=true`; con tool_calls
   (acción "tool") el pendiente sobrevive y no hay línea.
5. `GetQuestion.post` limpia un pendiente huérfano.
6. El join del probe: decisiones+resultados intercalados se unen por id; la
   sin resultado se salta; `correcto`/`conf`/`etiqueta` dan bien en los cuatro
   casos de la tabla de verdad (propuesta × uso_tools).

## 6. `.env.example`

Comentario corto en el bloque de `LAYA_MODO`: shadow ahora además JUNTA
ETIQUETAS (decisión + resultado por id) para calibrar con tráfico real vía
`banco/probes/etiquetar_ambiental.py`; con `LAYA_LOG_PREGUNTA=1` la etiqueta
lleva la pregunta (default 0: sin texto del usuario).

## Fuera de scope (no hacer)

- No tocar `decide`/`ruta_aplicada`/umbrales: la política no cambia.
- No tocar el etiquetador LLM existente (queda para cross-check).
- No cambiar el formato de las líneas de decisión existentes salvo sumar
  `id`.
