# H3-G — ¿el router necesita reglas de palabras clave? (pre-registro)

Fijado el 2026-10-26, ANTES de correr nada. El script
(`banco/probes/h3g_reglas.py`) no lo retoca.

## Pregunta

`utils/laya_routing.py` tiene dos reglas que deciden ANTES del modelo y
mandan a herramientas: `regla_temporal` (exp/46: `RE_TEMPORAL`, palabras
como "último", "hoy", "2026") y `regla_imperativo_capacidad` (exp/54: una
lista de ~40 imperativos como "leé", "corré", "buscá"). Son hardcodeos por
palabra clave. Se agregaron para cerrar falsos-directo medidos (exp/53 c01,
c02), pero DESPUÉS se agregó el voto de confirmación 2-de-2: si el router
propone "directo", un segundo voto tiene que confirmar. La pregunta es si el
voto ya cubre lo que cubrían las reglas.

## Datos (declarados)

- `banco/voto_casos.jsonl`: 18 casos con etiqueta HUMANA (`esperado`).
- `banco/calibracion_router_2026-10-08.jsonl`: 85 preguntas reales del banco
  con etiqueta del ÁRBITRO DeepSeek (sesgo declarado: tareas de banco, casi
  todas "herramientas"). Si una pregunta está en los dos, gana la humana.
- La flywheel (`calibracion_ambiental_*`) NO sirve acá: no guarda el texto de
  la pregunta (`LAYA_LOG_PREGUNTA=0` por privacidad), así que las reglas no se
  pueden re-evaluar sobre ella. Límite declarado.

## Diseño (pareado)

Por cada caso se consulta UNA vez la política real de producción: el router
de Laya (`preguntar_detalle` + `decide`, modo enforce, la calibración del
`.env`) y, si propone directo, el voto (`voto_confirmacion_router`). Con esos
mismos resultados se arman los dos brazos:

- **con reglas** (hoy): regla → herramientas; si no, router + voto.
- **sin reglas**: router + voto, siempre.

Los brazos difieren SOLO en las reglas. Requiere Laya disponible; sin ella no
hay veredicto.

## Medidas

- **falso directo**: esperado herramientas, final directo (el error caro: se
  responde sin leer lo que había que leer);
- **falso herramientas**: esperado directo, final herramientas (costo);
- llamadas al árbitro DeepSeek;
- cobertura: en cuántos casos dispara alguna regla.

## Criterio

**Sin reglas gana** (y las reglas se borran) si se cumplen las dos:

1. **cobertura**: las reglas disparan en al menos 20 casos (si no, el
   experimento no las ejercitó);
2. **seguridad**: falso directo sin reglas == falso directo con reglas (las
   reglas no salvaron NINGÚN caso: el voto ya los cubre).

La carga de la prueba está en el borrado (R7: la seguridad no se relaja): un
solo falso directo nuevo y las reglas se quedan.

## Decisión atada al resultado

- Gana → se borran `regla_temporal`, `RE_TEMPORAL`,
  `regla_imperativo_capacidad`, `_IMPERATIVOS_CAPACIDAD` y sus ramas en
  `LayaRouter`; sus tests se reemplazan por los casos que las motivaron
  corridos contra router + voto.
- No gana → las reglas se quedan, y el resumen nombra los casos que salvan
  (su justificación queda medida, no supuesta).
- Las skills por regex son OTRO experimento: acá no se tocan.
