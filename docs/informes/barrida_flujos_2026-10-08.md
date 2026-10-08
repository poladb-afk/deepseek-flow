# Barrida de revisión — flujos, errores y estado de las ramas (2026-10-08)

**Qué se revisó.** El flujo del chat (nodes.py, flow.py), el cliente LLM y el contexto
(call_llm, compaccion, tracing, terminal, aprobaciones), las nueve piezas
(juez, juez_lote, informe, auditoría, research, supervisor, debate, effective_n, rag)
y la **integración de las 14 ramas experimentales** (exp/22–exp/35).

**Método.** Cuatro auditores adversariales en paralelo (uno falló y se relanzó partido en dos)
más sondas propias; todo sin red, sin LLM y sin cargar checkpoints. La revisión no modificó
nada: los arreglos viven en `exp/36-barrida-fixes`, que sí es de esta barrida.

## 1. Hallazgos, por severidad

### ALTO — el modo thinking NO es pegajoso en la dirección directo→herramientas
`utils/call_llm.py:106-115` decide por **tráfico de tools en el historial**, no por el modo ya
usado. Con `USE_LAYA_ROUTER=1`, una primera pregunta resuelta "directo" (DirectAnswer, historial
limpio) llama **sin** `extra_body` (thinking ON); la vuelta siguiente, que ya trae las 28 tools,
la manda con `thinking: disabled`. Sin tools previas, la regla pegajosa no la cubre: es el flip
ON→OFF que `docs/design.md:96-97` documenta como crash medido (400 `reasoning_content must be
passed back`). La excepción sale de `create()`, el nodo reintenta 3×5 s y `exec_fallback` la
relanza; nadie la atrapa (`main.py:140` solo `KeyboardInterrupt`) → **el chat muere**.

**Evidencia:** por los nodos reales, turno 1 `DirectAnswer` `extra_body=None`; turno 2 `AgentStep`
`{thinking: disabled}` sobre `[system, user, assistant, user]`. A nivel `_kwargs_agente`: ON → disabled
→ ON (dos flips en tres vueltas). Es hipótesis medida en kwargs, **no** reproducida contra la API
(requiere red): la confirmación de 10 líneas es un script de 3 turnos reales.

**Decisión pendiente (no la tomé):** o el chat unifica el modo (thinking OFF en toda la sesión,
que elimina la clase entera de flips y pierde el modo que midió descarrilos), o se mantiene ON y
la transición directo→herramientas queda expuesta. Cualquiera de las dos exige la sonda real.

### ALTO — el semáforo del informe rompía la tool en la 2ª corrida · **ARREGLADO (exp/36)**
`informe.py:36` tenía el semáforo a nivel módulo: se ataba al primer event loop y la segunda
corrida de `run_informe` en el mismo proceso fallaba con *is bound to a different event loop*
tras 3 reintentos (10 s), dejando la tool inusable el resto de la sesión. Ahora cada
`AnalizeFile` trae el suyo, por corrida. Test: dos corridas en el mismo proceso.

### SEGURIDAD — el supervisor salteaba el denylist duro · **ARREGLADO (exp/36)**
`supervisor.py:280` llamaba `REGISTRO[herramienta](**args)` directo, y `HOOKS_PRE` solo lo corre
`run_tool_call`. Medido: el mismo `rm -rf /` que el chat veta, por el supervisor **se ejecutaba**.
Ahora pasa por `run_tool_call` con el registro del supervisor (mismo seam para los tests) y el error
llega con el formato del chat (`ERROR: Tipo: msg`). Este hallazgo no estaba en ningún informe previo.

### MEDIO — el refinamiento del DRY que falta y otros tres · **2 ARREGLADOS, 2 pendientes**
- **ARREGLADO:** `DirectAnswer` no compactaba (la ruta directo mandaba el historial entero sin techo);
  ahora reusa el `prep` de AgentStep y solo fuerza `tools=None`.
- **ARREGLADO:** `/aprobaciones` volvía por `post()` → el flujo seguía al modelo con el historial
  intacto y sin reiniciar el presupuesto. Se atiende en el bucle de entrada.
- **PENDIENTE (P6):** `Researcher(BatchNode, max_retries=3)` re-ejecuta **todo el lote** si una
  búsqueda falla: las ya pagadas se pierden y se repiten. Fix: fan-out con fallo por ítem (patrón `CorrerJuez`).
- **PENDIENTE:** `compactar` puede devolver **más** contexto del que recibió (el guard compara cantidad
  de mensajes, no tamaño): 9 msgs/60.403 chars → 8 msgs/60.644. Fix de 1 línea: si no achica, no compacta.

### BAJO — cuatro que se arreglan en una línea cada uno
- `validar_historial` **sí levanta** con ids `{None, "c1"}` (`sorted`), contra su docstring "NUNCA levanta" → `key=str`.
- El mensaje de "presupuesto agotado" era **falso** en la ruta directa (nunca hubo tools) · **ARREGLADO (exp/36)**.
- Un stream cortado sin deltas dejaba `content: null` en el historial y un turno vacío · **ARREGLADO (exp/36)**.
- Un **typo en un setting** casteado sin try mata el chat: reproducido con `COMPACTION_CHARS=sesenta mil`
  (`ValueError` en `AgentStep.prep`, que corre fuera del retry). 13 sitios así; fix: `_entero/_real` (~10 líneas).

### Instrumentación — el linter de evals se acusa a sí mismo
Sobre **214 trazas reales**: 38 violaciones, de las cuales **27 son falsas** — falta `("Judge","retry")`
en `ACCIONES_CANONICAS` (el juez usa esa arista en `juez.py:233`) y faltan cuatro tools en
`TOOLS_CONOCIDAS` (`ver_imagen`, `ver_pdf`, `agentes_remotos`, `a2a_tarea`). Las 10 de invariante (a)
son trazas truncadas al final (verificado: 10/10, el `AgentStep tool` es el último evento) y la (d) es
una traza histórica previa al fix de `evento_tool` (0 eventos de tools-flujo en la del 05, todos en la del 06).
Fix: dos líneas.

### Lo que está bien (y se verificó)
- **Cero acciones sin arista**: todas las devueltas por los nodos tienen sucesor en su grafo.
- **Cero bucles sin presupuesto**: los `while` del repo son el input del chat, índices y timeouts del banco.
- **Frontera de tools consistente**: 28 esquemas ↔ 25 impls de módulo + 3 del CORE, sin esquema huérfano,
  sin firma incompatible en parámetros requeridos y sin implementación no expuesta.
- `terminal.py` y `aprobaciones.py` sin hallazgos; `main` verde (221 tests).
- Falsos positivos descartados por los auditores: `EffectiveNMulti._run` (el job no se pierde),
  la colisión de claves `analisis`/`feedback` (los flujos no comparten `shared`), `juez_lote` y `debate`
  (sin cuelgues), la arista `directo - "tool"` (defensiva e inalcanzable), el off-by-one del no-progreso
  (los tests lo fijan a propósito), `presupuesto`/`fingerprint`/`historiar` (docstring = código).

## 2. Integración de las 14 ramas (medida en un clon, sin tocar el repo)

**Conflictos y resolución:**
- `22 × 24` en **informe.py**: el hunk abarca `collect_files` y la def de `leer_registro`. Correcto:
  cuerpo de 24 (`max_files=None`) **+** `sin_enlaces` de 22, conservando `leer_registro`. Si gana 22 →
  `ImportError: cannot import name 'leer_registro'` en `carga_trazas.py`; si gana 24 → vuelve el
  agujero de enlaces (probado con un symlink externo).
- `22 × 26` en informe.py: solo la línea de import → quedan ambos.
- `25 × 35` en nodes.py: **gana 35** (supersede declarado; su `exec` ya incluye la guarda).
- Todos los demás pares conflictúan **solo** en `tests/test_smoke.py` (cada rama agrega tests al EOF): unión.

**Merge completo** (22→…→29, 30→31→33→35, 32, 34): `ruff` limpio y **255 passed / 4 failed / 5 skipped**.
Tres fallos son artefacto del clon (rutas literales `Pocketflow/deepseek-flow/…`, fallan igual en main).
El cuarto es real: **`test_router_laya_no_mata_el_chat_si_la_inferencia_falla` (exp/25)** monkeypatchea
`laya.preguntar` y espera una tupla, pero exp/35 usa `preguntar_detalle` → hay que reescribirlo al
contrato de 35 (y ojo: al fallar hace una inferencia real de Laya en pytest).

**Casos borde:** exp/35 **sin** exp/25 conserva la guarda (probado con respuestas reales: excepción,
etiqueta rara y NaN caen a herramientas); exp/24 sin exp/22 deja el agujero de enlaces; exp/31 sin exp/30
haría `ModuleNotFoundError` en `post()` (sin retry → mata el chat), pero solo si se cherry-pickea solo.
Único acoplamiento frágil: **31 depende de 30**.

## 3. Lo que queda en manos del dueño

| Tema | Por qué es decisión, no fix |
|---|---|
| Modo thinking del chat | Calidad (ON midió descarrilos) vs seguridad (cualquier flip es 400). Necesita sonda real de 3 turnos |
| `Researcher` con retry de lote | Cambia la forma del fan-out (AsyncParallelBatchNode por ítem) |
| `compactar` que no achica | 1 línea, pero toca el camino caliente del contexto |
| Helper `_entero/_real` (13 sitios) | Robustez de configuración: 10 líneas + tests |
| Linter (2 líneas) y README (1 línea) | Instrumento y documentación: bajo riesgo, alto ruido evitado |

**Estado:** `exp/36-barrida-fixes` tiene los seis arreglos con gate verde (**223 tests**). `main` quedó
intacto y las 14 ramas siguen sin mergear.
