> Los ítems ya cumplidos y la sección "Hechos" viven en [bitacora.md](bitacora.md) (movidos el 2026-10-16): acá queda solo lo que falta.

# Próximos pasos (roadmap)

## Refactor de elegancia (auditoría 2026-10-27) — fases 1–5

Fase 0 cerrada (X91): la deuda quedó contada en siete ratchets. Siguen las
fases 1–5 de [elegancia.md](elegancia.md), cada una con su gate de salida.
Fase 1 cerrada: 1a (X92, `core_importa_modulos` 3 → 0) y 1b (X93,
`producto_conoce_lab` 10 → 0). Fase 2 en curso (plan en
`docs/elegancia.md`): **2a cerrada** (X94, el kernel con el shared solo de
datos) y **2b-1** (X95, `Contexto`: la compacción como nodo). Plan de 2b
revisado (incremental, cada PR verde y con sus tests migrados): **2b-2
cerrada** (X96: `Observar` cuenta la ronda y el presupuesto es la arista
`Contexto → Cierre`). **2d**: instrumento listo (X98, `cache_hit` y
`llamador` en la traza) y pre-registro en `banco/specs/fase2d.md`. **2d no
entra** (X99: 2 cierres reales en 16 corridas, casos insuficientes). Fase 3:
gate previo PASA (X102). **3a NO PASA** (X105: el A/B dio 2,2×–6,9× el USD y s17+s18 −2; cableado
borrado). **3b + 4a pre-registradas** (`banco/specs/fase3b_4a.md`) y **escritas**
(X106: el router sale del chat; falta el A/B `fase3b-directas` ×3 por brazo y
la clave del operador para `tests_definidos` 1132 → 1004) — **3b PASA** (12/12 sin tools, 0,65× USD; `fase3b_4a.md`). **5a hecha** (X108: política de comandos como datos en `utils/politica_comandos.json`; 0 diferencias en los casos por entrada y en el fuzz; la foto real la confirma el operador). **4b-mín cerrada** (X104:
la regex de palabras se borró, 0 cambios en 36 preguntas reales). Fase 6 (limpieza de las piezas sueltas) aprobada, después de la 5.
2b-3 queda para después de la fase 4 (o se descarta si sigue sin haber
sub-agentes); 2b-3 `AgentStep`/`ExecuteTools` →
`Paso`/`Actuar` del kernel con renombre y alias en `replay`/`evals`. Sin
cambio de conducta; 2d (esquema de tools fijo + `tool_choice="none"`) espera
la línea de base de fable s17–s20 sobre `012b92f` y la prueba de que
DeepSeek acepta `tool_choice="none"`.

## Refactor del harness (auditoría 2026-10-26) — la secuencia vigente

Cada etapa tiene un gate medible y ninguna empieza hasta que la anterior lo
pasa. Hechos: H1 (el pedido HITL como dato, X66), H1b (cierre y gate de H2,
X67), H1c (IDs), H1d (escenarios que miden, X68), H1e (suite sin el aprobador
del chat, X69). **H1 cerrado** (X70): `friccion-auto` 7/7 con 2 HITL (glob)
en 6 tareas, aceptado por el operador.

**H2 PR 1 cerrado** (X71, X72): kernel y explorador; gates deterministas
verdes, caracterización idéntica y `explorar()` en vivo (citas correctas,
`usó 3 de 3`). El gate "fable s17–s20 con `EXPLORAR=1`" estaba mal escrito:
`explorar` solo existe en el catálogo del supervisor, y fable corre por el
chat (0 llamadas en las 4 corridas). La medición del explorador pasa al PR 2.

**H2 cerrado** (X77). El kernel quedó como el loop de los sub-agentes
(explorador, supervisor); el chat conserva su loop con políticas y comparte
con el kernel la normalización, el historial y el despacho.

**H3-B resuelto** (X79): el explorador no ganó (0 llamadas en 24
corridas; calidad 0,50 vs 1,33) y se borró. Dato que queda: en s17 (20
módulos) el supervisor ganó 3/3 sin delegar.

**H3-G inválido** (X82): 78 disparos, 0 donde la regla decide; las reglas
se quedan. **H3-G2** (X83, `banco/specs/h3g2_voto_solo.md`; cerrado sin ganar en X89) era el gate del
borrado: el voto solo, con el checkpoint real, sin falsos directos y con el
grupo directo 6/6 (`python3 banco/probes/bench_voto.py`). Hoy falla en
c01/c02: el trabajo pendiente es el voto (`router_voto`), no las reglas.

**F resuelto** (X85): la directiva de alcance se borró (sin ella, calidad
0,92 → 1,25 en s17–s20 con menos tokens); la de citas se quedó (sin ella,
calidad 1,22 → 1,06 aunque VerificarCitas corrija después).

**H sin objeto** (X86): `max_profundidad` 1 vs 2 no se puede medir porque
nada en producción construye agentes como tools (el supervisor usa `loop` y
`semilla`, no `agente`). Vuelve si aparece una agent-tool en producción.

**Reentreno del voto cerrado** (X87–X89): r3 no ganó (c02 y la familia de
recencia no se movieron con 858 casos: el límite de exp/46); H3-G2 se cierra
y las reglas quedan como cobertura permanente.

**Ahora — el producto completo sobre el control** (X90): k13 y k15 son
falsos directos del voto que ninguna regla cubre. Medir la política entera
(skills → reglas → router → voto) sobre bench + control:
`python3 banco/probes/producto_router.py` (necesita Laya). De H3 queda E
(sandbox, opcional y sin diseño).

**H2 — la pieza única (kernel fractal: agente = Flow = Node = Tool).**
"Parche mínimo" levantado para H2 (X71). El kernel vive en `utils/kernel.py`
(design.md, "El kernel fractal"); DSML y sanitizado en `utils/proveedor.py`.
Streaming y Ctrl+C entran con el PR 4 (el chat es el único loop que los usa);
Laya como nodo, también en el PR 4. Un PR por loop, del más chico al más grande:

| PR | Reemplaza | Gate propio |
|---|---|---|
| 1 ✅ (retirado en H3-B, X79) | `explorador.py` | deterministas + `explorar()` en vivo (el de fable no podía ejercitarlo: ver X72) |
| 2 ✅ código | `supervisor.py` (comparte el `Ledger` con el explorador) | `bench_supervisor` igual o mejor y ≤ llamadas, con `EXPLORAR=0` y `EXPLORAR=1`; con `=1`, `explorar` llamado al menos una vez (si no, el brazo no midió nada) |
| 3 ✅ revisado | `juez`, `research` | no aplica: pipelines con el reintento como arista, no loops de tools (X74) |
| 4a ✅ | el chat: estado por pregunta en `shared["turno"]` y estado de sesión en el checkpoint (F5, X75) | caracterización idéntica + sesión guionada idéntica |
| 4b ✅ | una sola normalización del proveedor para chat y kernel (X76); el loop del chat se queda como "el loop con políticas" (X77) | 7/7 casos iguales + caracterización idéntica |

Gate común: `tests/test_caracterizacion_chat.py` pasa sin cambiar una línea,
`./calidad.sh` verde, ratchet sin empeorar; el viejo se reemplaza (sin `_v2`).

**H3 — que la evidencia decida** (con el kernel en producción; se queda solo
lo que gana; los criterios vigentes están en cada spec):

| | Qué | Resultado |
|---|---|---|
| B | swarm de exploradores en auditorías amplias | ❌ se borró el explorador (X79) |
| G | router de Laya sin reglas de palabras clave | inválido (X82); H3-G2 cerrado sin ganar (X89): las reglas son cobertura permanente |
| F | sacar del prompt lo que la estructura reemplazó | alcance se borró, citas se quedó (X85) |
| H | `max_profundidad` 1 vs 2 | sin objeto (X86): ningún agente delega en producción |
| E | sandbox en vez de whitelist | opcional, sin diseño |

**Regla para el banco**: todo escenario nuevo trae `verificar:` con un
chequeo que falle si el modelo no hace nada (lo exige `cargar_escenario`).
**Regla para los gates**: un gate que mide una pieza tiene que probar que la
pieza CORRIÓ (conteo de llamadas, marcador en la traza). Sin eso mide ruido.

## Historial (cola previa a la auditoría)

Priorizado por valor/costo, decidido al cierre de la etapa 2026-10-04.
Cada ítem indica qué pieza lo apoya y qué falta.

## Estado del tablero (2026-10-13, tras la revisión + la jornada Laya)

**Corriendo solo (procesos, no ítems):**
- **exp/43 — la flywheel**: router en shadow, cada pregunta deja par
  decisión↔resultado unido por id; `etiquetar_ambiental.py` produce la
  calibración. **Veredicto exp/45 ✅ (2026-10-19)**: 125 pares, base rate de
  "directo" 17,6% → SEGUIR; alpha propio 0,02 (único con precisión 100% en
  directos) → enforce con la calibración ambiental (detalle en bitácora).
- **exp/44 — juez de riesgo en observación**: tres preguntas de una
  dimensión sobre (comando, último mensaje) en las bandas humanas; el s/n
  del humano es la etiqueta. Primeros datos: el checkpoint base es débil →
  fine-tune cuando el log acumule (siguiente de esta línea).

**Cola priorizada** (en orden de número; el 17 no existe —nunca hubo tal ítem, verificado en la historia del archivo— y los números no se
reasignan porque otras partes del doc los citan):
1. ~~**exp/48** — persistencia/resume de corridas~~ **✅ hecho (2026-10-14)**:
   `utils/thread_store.py` + 3 puntos seguros + `main.py resume <id>`;
   E2E con kill -9 y continuidad verificados (design.md). Los otros flows
   (supervisor, juez) heredan la base cuando duela.
2. ~~**exp/49** — HITL como arista del grafo~~ **✅ hecho (2026-10-14, vía
   PocketFlow-simple)**: checkpoint de SELECCIÓN (la pausa del factor 8) +
   `reparar_pendientes` al rehidratar + `request_human_input` (el humano
   como tool call). Corte demostrado E2E: aprobar con el proceso
   reiniciado (design.md). **Fase B (exp/49b)**: arista formal
   approved/rejected e hitl_web multi-pendiente (dos HITL en paralelo).
3. ~~**exp/50** — pre-fetch como política declarativa (nodo `PreFetch`,
   apéndice 13)~~ **✅ hecho (2026-10-14; cerrado 2026-10-19)**: A/B ON/OFF
   medido — las preguntas sobre archivos bajan de **2 rondas a 0**, 5/5
   turnos OK y 0 errores en ambos brazos (detalle en
   [bitacora.md](bitacora.md)).
4. ~~**exp/45** — veredicto del router con datos propios~~ **✅ hecho
   (2026-10-19)**: 125 pares etiquetados, base rate 17,6% → SEGUIR; curva
   conformal LOO propia elige alpha=0,02 → enforce con calibración ambiental
   (el falso directo de 0,93 cae por conjunto ambiguo). Ahorro efectivo
   chico (1,6% de turnos) por recall 41%: ver ítem 15.
5. **Fine-tune del juez de riesgo** — readiness auditada (2026-10-19): el
   log tenía 1467 etiquetas (606/861) pero la procedencia no era confiable
   (59% de rechazo = banco sintético mezclado). Ya se instrumentó `origen`, y
   exp/71 (2026-10-21) midió que además la SUITE escribía 541 filas como
   `terminal`: el log viejo quedó en cuarentena y el conteo arranca limpio
   (`python3 banco/probes/estado_riesgo.py` · **70/300 orgánicas, 6/100
   rechazos** al 2026-10-25 — el conteo arrancó a mover con las sesiones
   reales de exp/95–102; las corridas delegadas quedan fuera: origen
   `delegado`, exp/101). **Criterio pre-registrado, sin cambios: ≥300
   etiquetas orgánicas y ≥100 rechazos orgánicos** (las históricas sin
   procedencia no se usan; el banco no cuenta). `requiere_revision` casi no
   dispara (5/1467): esa dimensión es la que el fine-tune tiene que arreglar.
   Umbrales del log propio y enforcement recién después.
6. **Mesa 3 (restos, re-priorizados)**: gate del juez (después del 5),
   presupuesto dinámico/convergencia de loops (empezar DETERMINISTA con las
   features de exp/9, Laya solo si no alcanza), Laya vía MCP como producto.
7. ~~**Mesa 1: bench de decisiones del voto como dataset permanente**~~
   **✅ exp/53 (2026-10-19)**: `banco/voto_casos.jsonl` (18 casos versionados:
   8 corrección, 6 directo, 4 herramientas) + `banco/probes/bench_voto.py`
   con la cascada real (voto local LAYA_MODEL_VOTO + árbitro con el prompt de
   producción). Corrida: corrección 6/8, directo 6/6, herramientas 4/4; el
   voto local resolvió 10/18. **Hallazgo c01**: "debatí en 2 rondas…" → voto
   local conf 0,94 directo (no consulta al árbitro, que habría dicho
   herramientas) → falso directo de producto; c02 lo cubre `regla_temporal`.
   ~~Queda pendiente de la mesa: costo por sesión (tokens/latencia) as
   first-class~~ **✅ exp/89 (2026-10-22)**: usage capturado por llamada (evento
   `llm` en `.runs` sin contenido), reporte `[tokens]` al salir del chat y
   columna tokens en el informe de evals; la latencia ya la medía `costo_traza`.
8. **Mesas 4/5/7/8** (agentes fractales, async, skills, web UX): sin
   cambios de prioridad por la evidencia nueva.
9. ~~**Paydown del ratchet**: 20 ocurrencias de helpers privados duplicados
   (los peores `_git_sha` y `_fmt_pct` con 4 copias)~~ **✅ (2026-10-19)**:
   `_git_sha` → `utils/git.py` (`sha_corto`/`sha_largo`/`sha_o_motivo`),
   `_fmt_pct` → `utils/formato.py` (`pct`), `_leer_eventos` → `utils/trazas.py`
   (`leer_eventos`) y se van los imports privados entre piezas. Ratchet de
   helpers **20 → 10**. Las reglas blandas de `AGENTS.md` se gradúan a gate
   cuando duela.
10. ~~**Paydown del ruido (2026-10-19)**: 55 `except` amplios (39% de los
    `try`; la referencia humana tiene 1,6%)~~ **✅ cerrado en dos pasadas
    (2026-10-19)**: 15 acotados a su excepción real (JSON, input, archivos,
    calibración, YAML, bookkeeping) y el resto justificado con motivo visible
    + gate (`# noqa: BLE001 (motivo)` obligatorio); ratchet **55 → 36**. Los
    36 restantes son fronteras de integración/bookkeeping: no hay más
    candidatos deterministas. Los otros tell no deterministas (comentario
    narrador, código muerto "por si acaso", test slop) quedan como review de
    `AGENTS.md` R9.
11. ~~**A/B de la directiva de forma**~~ **✅ exp/51 (2026-10-19)**: A/B
    pre-registrado con `banco/probes/forma_codigo.py`, n=4 por brazo y tarea,
    deepseek-flash: SLOC 193 → 44 (−77%), tokens −81%, docstrings 0,487 → 0,
    `try` −71% (detalle en la bitácora). Criterio cumplido.
12. ~~**Repetir exp/51 con más n y otro modelo**~~ **✅ (2026-10-19)**:
    `--runs 8` en deepseek-flash y deepseek-chat, con tokens reales de la
    API: SLOC −79%/−67%, tokens completion −76%/−66%, docstrings 0,56/0,63
    → 0 (detalle en la bitácora y en el informe). Caveat a vigilar: 2/16
    respuestas sin bloque en flash.
13. ~~**Medir la directiva en el chat real**~~ **✅ (2026-10-19)**: setting
    `PROMPT_FORMA=0|1` + escenarios `exp51-chat-on/off.yaml` (write_file +
    edit_file con HITL por scope) + sonda `banco/probes/forma_chat.py`. n=2
    por brazo: SLOC 133,5 → 32 (−76%), docstrings 1,00 → 0,33, `try`
    −83%, sesiones ~15% más rápidas. 4/4 sesiones OK. Límite: n=2.
14. ~~**Repetir exp/51 chat con más n**~~ **✅ (2026-10-19)**: flash n=5 por
    brazo (SLOC 115 → 25, −78%; sesiones 32,3 → 25,7 s) y deepseek-chat n=3
    (179 → 21, −88%; 33,6 → 24,6 s), 16/16 sesiones OK. El efecto del
    one-shot se sostiene (y crece) en el bucle real. exp/51 queda cerrado;
    la cola vuelve a exp/45 (veredicto del router, pre-registrado).
15. ~~**Pre-registrar el criterio de ROI del router**~~ **✅ pre-registrado
    (2026-10-19)**: `banco/probes/veredicto_router.py` computa ROI y aplica
    la regla nueva SOLO en la próxima revisión (no retroactiva): ahorro
    efectivo <5% con precisión de directos ≥99% → apagar; si no, mantener y
    re-elegir alpha. Preview con los datos de hoy: **APAGAR** (1,6% de
    ahorro), pero la decisión de exp/45 queda como está.
16. **Revisión de ROI del router (condición pre-registrada)**: cuando haya
    **≥250 pares y ≥14 días** (**14/250 y 3/14** al 2026-10-25 — el par #14
    fue el primero sin auditor al timón, exp/99), correr
    `python3 banco/probes/etiquetar_ambiental.py && python3 banco/probes/veredicto_router.py`
    y aplicar la regla de ROI. El banco no cuenta: las decisiones llevan
    `origen` y el join solo acepta `web`/`terminal` (el log previo a exp/71b,
    que no tiene el campo, también queda afuera: 80 de sus 152 pares eran del
    banco); vigilar falsos directo del enforce.
    **Acumulación:** ventanas de uso con la política en shadow (en enforce el
    par no se etiqueta, exp/43) — desde exp/100 la palanca es delegar desde
    el chat con `delegar_tarea` y `shadow="1"` — y, hasta la revisión, NO
    correr `etiquetar_ambiental` con la salida default (pisa el artefacto
    que usa `.env`); progreso con `python3 banco/probes/estado_flywheel.py`.
18. ~~**Paydown de test slop**: 12 ocurrencias (6 pares) de tests copiados en
    `test_db`, `test_policy` (×2), `test_replay`, `test_smoke` y
    `test_ratchet`~~ **✅ (2026-10-19)**: los 6 pares pasaron a
    `@pytest.mark.parametrize` con ids estables; `cuerpos_test_duplicados`
    **12 → 0**; el inventario se actualizó con los ids parametrizados y la
    cobertura ahora cuenta CASOS (547 → 611), así parametrizar no la baja.
19. ~~**exp/52-B — convergencia determinista del loop**~~ **✅ cerrado
    (2026-10-19)**: (a) instrumentación `evento_tool.huella` (sha1 corto de
    nombre+argumentos, sin contenido; replay OK) y (b) regla `CORTE_NOVEDAD=k`
    (default 0=off, mínimo 3, reset por pregunta; 6 tests). (c) A/B del ítem
    20: **negativo**.
20. ~~**A/B de exp/52-B en el banco**~~ **✅ NEGATIVO (2026-10-19)**: escenario
    con lecturas repetidas forzadas, brazos `CORTE_NOVEDAD=0` vs `2`, n=2:
    4/4 sesiones OK, **cero cortes y mismas rondas**; en trazas instrumentadas
    solo 1 ronda sin novedad de 15 y 0 ciclos alcanzarían racha k=2. La
    redundancia real por (tool, args) es ≈0: no hay ahorro que cobrar. La
    regla queda en 0 por default; la instrumentación se conserva (traza más
    atribuible). No se recomienda forzar k=1 (una ronda sin novedad no es
    evidencia y arriesga calidad).
21. ~~**exp/56b — skill `revision` sin techo (pre-registrado, listo para
    correr)**~~ **✅ corrida (2026-10-22)**: la hipótesis de detección de exp/56 no tenía margen porque el
    pre-fetch ya inyectaba el archivo (control 3/3). Para medirla hay que
    quitar el techo ANTES: `PREFETCH=0` y/o fixture con issues sutiles
    (off-by-one, global mutada, denominador mal calculado); el criterio quedó
    fijado en la bitácora de exp/56 antes de la corrida. Es una corrida de
    banco (`banco/escenarios/`), no deuda de código.
    **Resultado**: C0 ✅ sin pre-fetch el control ya no está en techo
    (recall anclado 7,67/8); C1 ❌ la skill no suma detección (7,00/8,
    −0,67 vs control); C4 ✅ ruido 0,41× (−59%). La skill queda como
    reductor de ruido, no detector (detalle en bitácora exp/56b).
22. **Diff paginado a pedido en el HITL web** (follow-up de exp/98, la otra
    mitad de la cola chica junto al ya-cerrado motivo de exp/102): el panel
    muestra los hunks que caben; falta poder VER los que quedaron fuera.
    Media sesión, necesita diseño de UX propio (paginación del `<pre>`).

**Descartado hoy por evidencia:** Choose a escala (~2.400 casos — el bench
lo volvió innecesario), round de "hechos actuales" (regla dura lo cierra),
y el menú congelado de 18 se jubiló con el supervisor v2.

## 6. Streaming + memoria entre sesiones

- **Streaming implementado (2026-10-05)**: `call_llm_agent_stream` en
  `utils/call_llm.py` (mismo contrato de modo thinking pegajoso y filtro
  de `reasoning_content`, con `stream=True`) imprime en vivo cada delta de
  CONTENT (flush, sin saltos extra) y descarta los de reasoning; reconstruye
  `.content` y `.tool_calls` desde los fragmentos (id/name en el primer
  fragmento, arguments por concatenación). `AgentStep.exec` (y por herencia
  `DirectAnswer`) elige stream con `CHAT_STREAM` (default 1), clásica con 0.
  Si el sanitizado corta, tras el aviso se imprime la versión limpia; y con
  stream `post()` NO reimprime la respuesta (la respuesta ya salió en vivo:
  solo cierra la línea).
- **Interrupción del usuario (2026-10-05)**: Ctrl+C durante la generación
  corta el stream y conserva lo parcial (el chat sigue); `CHAT_STREAM_INTERRUPT`
  (default 1) la activa, `0` propaga el Ctrl+C como salida.
- **Memoria entre sesiones implementada (2026-10-05)**: como
  **biblioteca consultable, NO contexto auto-inyectado**. Cada chat arranca
  con la memoria vacía (nada se inyecta al inicio; el system prompt no se
  toca) y el agente la consulta por tools cuando el pedido lo justifica.
  `modules/memoria.py` expone `memory_search` (busca texto en los markdown
  de `memoria/` y lista la biblioteca; código puro) y `memory_save`
  (escribe `memoria/nota_FECHA_slug.md` con el título como primera línea:
  sin HITL —es la libreta del agente— pero con contención dura, solo dentro
  de `memoria/`, slug del título sin rutas ni `..`). Al salir del chat, con
  `MEMORIA=1` (default) y ≥2 preguntas, UNA llamada a `call_llm` resume la
  conversación en `memoria/sesion_FECHA.md` (bookkeeping, sin HITL; si
  falla, se sale igual). `memoria/` está en `.gitignore`. Descartado por
  ahora: persistir/comprimir `messages` completo (el historial se reenvía
  entero dentro de la sesión — costo creciente); vuelve cuando duela.

## Menú de desarrollo (registrado 2026-10-05)

Siete mesas más una de UX, decididas al cierre del día. Orden aceptado como
secuencia oficial (matiz del consejo, 2026-10-05: es el orden por
defecto, no un waterfall — los cortes ligeros y reversibles de otras
mesas pueden avanzar en paralelo con evidencia propia): (1) Replay-evals, (2) HITL graduado + hooks, (3) Laya en
el voto del router.

**Mesa 1 — Evals (el harness juzgándose, 12-factor #8) — ✅ MVP hecho (2026-10-05):** evals.py (bench del router con baseline git-sha: 93.3%/ECE 0.0658, reproduce los históricos; linter de invariantes sobre 114 trazas — detectó el ciego histórico de evento_tool; costo por sesión). Matiz del consejo en la primera corrida: es instrumento de SEÑAL, no gate — antes de bloquear cualquier CI hay que medir sensibilidad/especificidad contra los P0/P1 históricos (¿cuáles habría bloqueado?) y la tasa de falsos bloqueos. ~~Pendiente de la mesa: replay de trazas de .runs contra código actual (regresión de comportamiento, no de unidades)~~ — **✅ replay hecho (exp/41, 2026-10-13):** `replay.py` valida las caminatas reales de .runs contra los grafos VIVOS (emisibilidad, adyacencia del chat, registro de tools, política del router sobre routing.jsonl). Primera corrida 214 trazas: 0/0/0/2/0 (los 2: artefactos de tests viejos), baseline fijado. limitación documentada: la traza no guarda contenido — la regresión SEMÁNTICA sigue siendo de los benches con contenido. ~~Sigue pendiente de la mesa: bench
de decisiones del voto (los casos donde corrigió a Laya como dataset
permanente); costo por sesión (tokens/latencia) como métrica first-class
derivable de las trazas.~~ **Ambos cerrados:** el bench del voto en exp/53
(2026-10-19, `banco/voto_casos.jsonl` + `bench_voto.py`) y el costo por
sesión en exp/89 (2026-10-22, usage por llamada + reporte `[tokens]` +
columna tokens en el informe de evals).

**Mesa 2 — HITL graduado + hooks (12-factor #6) — ✅ MVP hecho (2026-10-05):**
`utils/policy.py` (clasificador determinista sin LLM: `auto`/`preguntar`/`confirmar_doble`)
+ integración en `run_command` (`HITL_AUTO=1` default; `0` = todo pregunta como hoy)
+ hooks post-tool en `run_tool_call` (`HOOKS_POST`; `py_compile` tras edit/write de `.py`
como error-como-feedback). Reglas de composición: `&&`/`|` exigen que TODOS los segmentos
sean auto; redirección/`$()`/backticks/`xargs` ⇒ preguntar; `python3 -c` siempre pregunta;
`git push`/`rm -rf` ⇒ doble confirmación. **Residual del denylist ✅ cerrado (2026-10-05):**
`utils/fs_tools.HOOKS_PRE` (hooks PRE con poder de CANCELAR) + denylist dura de `run_command`
(`rm -rf /`, fork bomb) que veta sin s/n, registrada desde `modules/coding.py`.
Residuales todavía diferidos: pytest tras write de .py (más caro que py_compile),
GET del hitl_web sin validar origen (mitigado por la validación de origen actual),
naming `_pendido`/`_pendiente` (no existe `_pendido` en el código: nada que renombrar).

**Mesa 3 — Laya en más mecanismos — ✅ voto del router promovido (2026-10-05, jornada de fine-tune completa):** task router_voto (contrato PREGUNTA_VOTO, sha1 congelado) → 930 generados/558 verificados por juez ciego en dos rondas (el juez rechazó ~40%: la banda de confusión es cara de etiquetar; corrección de dirección imperativo≠tools) → r1 (288 casos) REPROBADO por la puerta: banda confiable vacía, ahorro 0 (honestidad del instrumento) → r2 (528 casos) PROMOVIDO: 27/30 crudo, 96% en banda confiable, ahorro medido 80% de los turnos-directo (24/30), 0 ecos, 0 errores nuevos, correlación de errores router↔voto limpia. Producción: tres niveles en voto_confirmacion_router (Laya-voto decide acuerdos/desacuerdos confiables; banda incierta la arbitra DeepSeek; sin checkpoint, voto DeepSeek de siempre). Verificado e2e. Nota operativa: medir router+voto en UN proceso dio OOM (2×615MB + 15GB de máquina) — un checkpoint por proceso, dumps en /tmp. Siguientes de la mesa (sin fecha): gate del juez, presupuesto dinámico de rondas, triaje de memoria, exposición MCP. El voto del router (mejor ROI: dispara en
cada directo-met y hoy paga DeepSeek); gate del juez (clasificar ok/retry, juez
completo solo si duda); presupuesto dinámico de rondas (estimación Laya de
cuántas rondas necesita el pedido); triaje de memoria (¿esta nota merece
biblioteca?). Cada candidato cuesta un round de entrenamiento: el filtro es la
frecuencia de la decisión que reemplaza.

**Mesa 4 — Agentes fractales:** agents/ como modules/ (sub-agentes
especializados: mini-flows con prompt y subset de tools, expuestos como tools;
el supervisor ya lo es de facto); debate con tools (debaters que grep/lean/corren
antes de argumentar — medir win-rate en temas factuales); comité de jueces
(juez_lote + mayoria() = self-consistency 2-de-3); coding loop como sub-flow
(plan→edit→test→revert, presupuesto propio).
- **Diseño listo, no portado (2026-10-23):** el agente fractal viejo del operador
  trae `spawn` (sub-agentes paralelos con presupuesto heredado, depth ≤ 2 con
  devolución del sobrante), `best_of` (k borradores + picker) y `dried`
  (convergencia medida sobre el texto) ya resueltos de diseño — ver
  [informes/fractal_agent_mapeo_2026-10-23.md](informes/fractal_agent_mapeo_2026-10-23.md);
  se portan cuando la mesa se des-estacione por uso.

**Mesa 5 — Async donde falta:** research de BatchNode a AsyncParallelBatchNode
(mismo patrón medido que juez_lote); comité de debates paralelos (N debates
sobre sub-preguntas + síntesis); supervisor con sub-tareas independientes (salto
reactivo→DAG).

**Mesa 6 — Contexto y loops:** compacción de contexto (12-factor #5 — messages
crece sin techo, sesión de fixes como evidencia; validar contra el modo thinking
pegajoso) — **✅ compacción hecha (2026-10-06):** `utils/compaccion.py` (código
puro, sin LLM) + `AgentStep.prep`: la zona fría se reemplaza por un resumen
`[compacción]` y la ventana caliente (system + últimos 6, con assistant+tools
como unidad indivisible) queda intacta; `COMPACTION_CHARS` (default 60000), una
vez por ronda por huella sha1, `shared['compacciones']` cuenta. Invariantes del
modo thinking clavados por `validar_historial` (sin reasoning_content, dicts
canónicos, sin assistant sin sus tools, primer mensaje system). 124 passed.
Siguientes de la mesa (sin fecha): telemetría de convergencia (hechos nuevos por
ronda: comprar ronda si converge, cortar si estanca); agentic RAG como flow
dedicado (gap del cookbook); loops fractales con presupuesto heredado (depth máx
2).
- Nuevo de la investigación 2026-10-05: **pre-filtro de contexto** — Laya
  elige qué notas de memoria/ o chunks de RAG entran al prompt ANTES de
  pagar tokens (patrón de la wild con ~80% de costo/tiempo reportado) —
  **✅ construido (2026-10-06):** `utils/contexto.py` (helpers puros:
  `unidades_bloques`, `elegir_por_laya`) + ganchos en `rag_search`
  (`RAG_PREFILTRO`/`RAG_PREFILTRO_N`) y `memory_search`
  (`MEMORIA_PREFILTRO`/`MEMORIA_PREFILTRO_N`). Sin checkpoint
  (`LAYA_MODEL_PREFILTRO`) el filtro es no-op: entran todos, como siempre
  (hasta el 2026-10-15 recortaba a los primeros N: corregido en la consolidación)
  (no se pierde recall; cercado por tests con Laya simulado). Siguiente
  real: entrenar el checkpoint `router_prefiltro`.
  Y **¿el trabajo está listo?** — clasificador de convergencia de loops
  (el judgment kernel del agente mu hace exactamente esto: riesgo de
  comando, qué queda en contexto, cuándo terminar).

- ~~Nuevo de la investigación 2026-10-05 (patrones de la wild): **exponer
  Laya vía MCP** como producto del harness (referencia typesafe-mcp /
  mcp-laya: el juicio tipado y calibrado como tool consumible por
  cualquier agente MCP — nosotros ya tenemos mcp_server.py)~~
  **✅ exp/65 (2026-10-19)**: `utils.laya.juicio` (estado + instrucciones +
  opciones `{etiqueta: criterio}` → `{juicio, confianza, probabilidades}`) y
  tool `juicio_laya` en `mcp_server.py` (texto JSON con `modelo`), expuesta
  por default en `MCP_EXPOSE` y despachada por `run_tool_call`; e2e real por
  protocolo MCP con el checkpoint local (p=0,8222) y `ERROR:` sin checkpoint.
  No suma tool al action space del chat.
**Mesa 7 — Skills y triggers:** ~~skills/ declarativas (paquete
prompt+tools+condición de disparo, a lo ZCode)~~ **✅ exp/55 (2026-10-19)**:
`skills/*.yaml` (regex de disparo, instrucciones, subset de tools) +
`utils/skills.py`; en enforce el `LayaRouter` fuerza herramientas e inyecta
`[skill]`, `AgentStep` anuncia solo el subset; shadow no cambia; SKILLS=0
apaga; e2e `exp55-skills` 3/3. Pendiente de la mesa: **webhook autenticado**
sobre el server del HITL web (el harness como servicio, seguridad primero)
— **✅ exp/57 (2026-10-19)**: `POST /webhook` + `GET /eventos` con token en
tiempo constante (vacío ⇒ 503), loopback, cuerpo máx y rate limit; CLI
`python3 main.py webhook`; e2e curl y 11 tests de seguridad. **Mesa 7:
cerrada.** Efecto de la skill `revision` medido en exp/56: **NO CUMPLE** la hipótesis de
detección por techo (pre-fetch + modelo ya detectan 3/3); señal secundaria
prometedora: −40% de palabras con las mismas citas válidas (n=3).

**Mesa 8 — UX (incorporada a pedido):** ✅ **pulido de terminal** (rótulo
`DeepSeek:` en streaming, colores por tipo, progreso de rondas), ✅ **HITL UX**
(diffs con highlight, explicación antes del s/n, historial `/aprobaciones`) y
✅ **visor --watch** + ✅ **catálogo de memoria al arrancar** (nombres SIN
inyectar) — verificados con e2e y tests en exp/58 (2026-10-19) y ✅ **chat web
completo** (SSE + sesiones aisladas, stdlib, token por sesión) en exp/59
(X29): la mesa quedó cerrada.

**Pulido de terminal ✅ (2026-10-05):** `utils/terminal.py` — `colorear(texto,
tipo)` con códigos ANSI por tipo de evento (`tool`/`ok`/`error`/`info`/`aviso`/
`respuesta`) y `progreso_ronda(ronda, tope)` (`⚙ ronda 2/8`). Sin tty, o con
`NO_COLOR`/`COLOR=0`, degrada a texto plano (nada cambia en CI, pipes ni logs).
`ExecuteTools` anuncia cada tool ANTES de correrla (`→ read_file`, para que una
espera no parezca colgada) y etiqueta la ronda consumida con su avance. Los
avisos de recuperación DSML y sanitizado van coloreados como `aviso`.

**Visor --watch ✅ (2026-10-06):** `visor.py --watch` re-genera el HTML de
la traza cuando crece (tail -f de `.runs/`), con `--intervalo` configurable.
No re-renderiza sin cambios y un Ctrl+C sale limpio.

**Catálogo de memoria al arranque ✅ (2026-10-06):** `main.catalogo_memoria()`
imprime el listado de notas de la biblioteca al arrancar (nombre + conteo),
SIN inyectar su contenido al contexto — el arranque vacío sigue siendo regla
(la memoria es una biblioteca que el agente consulta con `memory_search`).
Con `MEMORIA=0` o biblioteca vacía, silencio; nunca corta el arranque.

Sin ítems abiertos: el chat web se cerró en exp/59 (X29) y el HITL UX en
exp/58 (X28).

## Descartes

- **Voz** — no interesa.

## Ciclo de experimentos exp/ (2026-10-06)

Workflow: branch exp/N → gate ./calidad.sh verde → medición en el mensaje
del commit → merge --no-ff solo del ganador. El banco (banco/banco.py)
mide: marcadores por turno en conversación real contra DeepSeek.

- **exp/1 ✅ mergeada** — política HITL: `cd` neutro + `sort` whitelist +
  partir por `;` (hueco medido: `ls ; rm -rf /tmp/x` clasificaba auto).
  Los 5 run_command reales de la sesión del test exhaustivo: 2 pasan a
  auto, 0 se relajan peligrosos.
- **exp/6 ✅ mergeada** — banco de conversación: escenarios YAML contra el
  chat real por PTY, conteo de marcadores por turno (laya, voto, hitl,
  compacción, auto...), no contamina memoria, exit 0 = todo OK. Primera
  corrida 7/7 y prueba en vivo de exp/1 (run-auto sin s/n).
- **exp/7 ✅ mergeada** — sonda_laya.py: evidencia de Laya con vara propia
  (ECE, curva de compuerta, latencia CPU ~0.2 s, RSS 2.86 GiB/proceso).
  La compuerta 0.9 del supervisor = rodilla precisión=100% de su curva.
  Sección "Laya: estado de la evidencia" en design.md.
- **exp/8 ✅ mergeada** — compuerta del router 0.7→0.85 por datos + split
  LAYA_UNSURE_HIGH_VOTO (el veto conserva 0.7). El veto confirmaba el
  falso-directo "mundial" (0.78 met): error correlacionado medido; la
  compuerta nueva lo bloquea antes. Ensamble 25/30 → 26/30. Sección en
  design.md.
- **exp/9 ✅ mergeada** — minar_errores.py: 43 errores en 108 sesiones,
  tasa de autocorrección 67% (94% entre los reintentados) — el lazo
  error-como-feedback ya ES el triaje. **Triaje con Laya descartado por
  evidencia**; único candidato residual: reintento determinista para los
  4 timeouts por firma de duración. Sección en design.md.
- **exp/11 ✅ mergeada** — scope de aprobación por path en el banco:
  el driver del banco parsea el objetivo de cada HITL y solo aprueba
  dentro del scope del escenario; denylist dura del conductor (.env,
  .git/, memoria/, git push, rm -rf). Auto-prueba en vivo: el ataque al
  .env se rechazó solo (evento hitl-fuera-de-alcance), el permitido
  corrió. Sección en design.md.
- **exp/4 ✅ mergeada** — presupuesto visible: la nota de la anteúltima
  ronda viaja en el resultado de la tool (el modelo ya ve su tope),
  protocolo de continuación documentado ("seguí" reinicia) y env por
  escenario en el banco (MAX_TOOL_ROUNDS=40 para aplicar). HALLAZGO:
  la recuperación DSML by-pasea el retiro de tools — candidato a fix.
- **exp/10 ✅ mergeada** — edit_file con feedback rico: diagnóstico de
  indentación (incluye old_strings de 1 línea), candidatos con línea y
  ocurrencias listadas. Medido: reintento único y cero relecturas en el
  caso tab-vs-espacios. Línea de base: 27 errores históricos. Primera
  corroboración de campo: 0 errores en 25 llamadas post-fix (vs 9% pre).
- **exp/12 ✅ mergeada** — bypass DSML del presupuesto cerrado: la
  recuperación no re-arma tools retiradas por el tope (markup cortado +
  mensaje honesto + aviso en terminal). Re-medición del escenario que
  by-paseaba: cero ejecución tras el retiro, continuación limpia.
- **exp/3 ✅ mergeada** — hook py_compile visible: `[hook] ⚠ SINTAXIS
  devuelta al modelo` en terminal (el veto ya imprimía; el hook no).
- **exp/5 ✅ mergeada** — search_files con conteo exacto: "N archivos"
  con N real calculado antes del tope + sugerencia de find (auto desde
  exp/1). Fin del "50+" del test exhaustivo.
- **exp/2 ✅ mergeada** — evals como tool del chat (estilo run_informe:
  informe a disco + ruta). Corrección de fondo del conductor: la tool
  compara pero NO guarda el baseline (`actualizar_baseline=False`).
  Medido: tool nativa, 25 s, baseline intacto.
- **exp/13 ✅ mergeada** — router_prefiltro entrenado e integrado:
  530 casos (anti-fuga aplicado), test 54%→79% ECE 0.33→0.09, banda
  confiable no vacía. A/B del pre-filtro: poda 18→2 (89%) por consulta,
  menos churn de búsqueda, costo de ranking local. El claim "~80%" de la
  wild queda reemplazado por la medición propia. Sección en design.md.
- **exp/14 ✅ mergeada** — ranking del pre-filtro en lote (predict_batch):
  3.2× en el camino real (377 ms/bloque warm vs 1211 secuencial),
  decisiones idénticas. Mitiga el único costo medido del prefiltro.
- **exp/15 ✅ mergeada (descarte)** — pre-rank de tools matado por el
  KV-cache: los esquemas ya son ~gratis (miss 215/4311 por llamada);
  variar la lista ahorraría nada y arriesga el action space. Sonda
  re-ejecutable en banco/probes/cache_tools.py.
- **exp/16 ✅ mergeada** — triaje_trazas.py: selección determinista
  (linter + outliers) 37/139 → 73.4% de ahorro de la auditoría nocturna,
  sin checkpoint. Tercer "Laya no acá" por evidencia. Cableado como tarea
  del heartbeat (exp/17, tipo=triaje: 0 llamadas LLM, 0.1 s verificados).
- **exp/19 ✅ mergeada** — auditoría dirigida de modules/: método por
  tandas con anotación incremental (la compacción se comía las primeras
  tandas: 9/16 → 16/16). 6 hallazgos (1 alto: descripción de ver_pdf
  mentía el mecanismo; 1 medio: default de salida de run_auditoria),
  confirmados y corregidos.
