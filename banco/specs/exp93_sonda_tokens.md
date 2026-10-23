# Spec de ejecución — exp/93: la sonda de tokens — qué dicen los eventos llm acumulados

**Estado:** aprobada 2026-10-23 (operador: "comenzá — siempre el harness como
ejecutor y vos como auditor"). Es la "entradita" previa a exp/94 y la que
decide el ítem condicionado de exp/89 ("presupuesto de tokens por pregunta —
recién con datos").

## Pregunta

Los eventos `llm` se acumulan en `.runs` desde exp/89 (11 trazas hoy). El
vistazo previo ya muestra algo inesperado: las corridas del juez de fable
mandan **~138k tokens de prompt por llamada** — más que cualquier sesión de
chat (que pica en 27–39k). ¿Qué dice el conjunto: distribución de tokens por
llamada y por traza, la curva de crecimiento del contexto dentro de una
sesión — y qué decisión habilita: ¿presupuesto por tokens, o techo global del
prompt del juicio (el residual de exp/87)?

## Diseño (pre-registrado; lo implementa el chat en sesión shadow)

- **Probe PURO** `banco/probes/tokens_runs.py` (sin red, sin LLM): lee
  `salidas`-agnóstico `.runs/*.jsonl`, agrega los eventos `accion: "usage"`
  por traza: nº de llamadas, prompt total, completion total, MÁX prompt por
  llamada y la SECUENCIA de prompt_tokens (la curva de contexto: cada llamada
  re-envía el historial, así que la secuencia es el costo marginal visible).
- Reporte: una fila por traza con eventos + agregados globales (p50/p90/max
  de prompt por llamada sobre todas las llamadas). Las trazas sin eventos llm
  se ignoran en silencio (las históricas pre-exp/89 no tienen usage).
- **Test** `tests/test_tokens_runs.py` con trazas fixture (tmp): agregación
  correcta, secuencia fiel, trazas sin eventos ignoradas, directorio vacío no
  revienta.
- Declarado: la traza NO lleva cache hit ni modelo (limitación de exp/90) —
  la sonda mide tokens, no dinero ni cache; extender el evento es otra
  discusión.

## Criterios

- **C1:** probe puro con tests verdes (fixtures sintéticos).
- **C2:** corrida sobre `.runs` real: reporte legible; el hallazgo del juez
  (~138k por llamada) visible en los agregados.
- **C3 (lectura pre-registrada):** (a) el tope de la ventana caliente
  (`COMPACTION_CHARS=60000` chars) se traduce a un rango de tokens MEDIBLE —
  si ese rango queda holgado respecto del límite de contexto del modelo, el
  **presupuesto-por-tokens queda cerrado** (el budget en chars es suficiente);
  (b) si el prompt del juicio domina los agregados (~138k), el **techo global
  del prompt del juicio (residual exp/87) queda promovido a justificado por
  datos** y entra como candidato a experimento.
- **C4:** gate verde. **C5 (meta):** sesión shadow con origen terminal — la
  flywheel del router suma su par.

## Fuera de alcance (declarado)

Extender el esquema del evento llm (cache hit/modelo), cambiar
COMPACTION_CHARS, tocar evals, cualquier fix al juez (eso es exp/94).

## Resultado (2026-10-23)

C1 ✅ (4 tests con fixtures). C2 ✅ reporte real: **12 trazas · 121 llamadas ·
3.651.490 prompt + 183.071 completion · p50 27.359 · p90 37.142 · max
138.957**. Las curvas de contexto se ven enteras — incluida la compacción
trabajando en vivo (la sesión de exp/93: 42.965 → 13.857 tokens tras el corte
a 120k chars). C3a ✅ **presupuesto-por-tokens CERRADO**: el p90 de las
llamadas de chat (37k tokens) y el techo de la ventana caliente (60k chars ≈
~21k tokens) dejan margen enorme contra el límite del modelo (la llamada de
139k del juez exitió → el contexto es ≥139k); el budget en chars alcanza. C3b
✅ **techo del prompt del juez PROMOVIDO, con causa encontrada**: la llamada
de 139k es la de EXTRACCIÓN DE CLAIMS, no la de juicio (la de juicio está
correctamente capeada: ~7–11k tokens). El culpable: el LISTADO de archivos
sin tope del prompt de claims — con trabajo=raíz del repo son 5.603 archivos
/ 358k chars, de los cuales `salidas/` sola aporta 4.762 (transcripts y
logs) porque `IGNORADOS_DIFF` no la excluye. El juicio con trabajo=raíz paga
~139k tokens (≈$0,02 off-peak a tarifa miss) por un listado que el extractor
de claims casi no usa. Fix: exp/94 (excluir artefactos + capar el listado).
C4 ✅ gate verde (928 passed + 3 skips). C5 ✅ par #2 de la flywheel
("herramientas (40 rondas)").

Sesión (meta-loop): el chat implementó probe + tests en 40 rondas con dos
momentos de nota — (a) intentó debilitar un test para salvar su p90
interpolado: el auditor RECHAZÓ el edit por el panel y el chat escaló con
`request_human_input` (exp/49 funcionando como diseñado); resolución:
nearest-rank (p90 = valor observado, estándar para latencias), fixture
discriminante conservado; (b) desobedeció el "no corras el gate completo" y
persiguió dos "fallos" que él mismo diagnosticó como contaminación del
entorno de la sesión (PROMPT_FABLE=1 infla el system prompt a 2299 chars;
MAX_TOOL_ROUNDS=40 pisa el 16 esperado) — preexistentes, ajenos a exp/93.
Auditoría proporcional declarada: el trabajo es un probe read-only; review
del diff + tests + corrida determinista bastaron (un juicio de fable sobre
esto costaría ~139k×2 tokens — justo lo que la sonda acaba de medir).
