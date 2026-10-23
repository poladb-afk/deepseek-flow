# Mapeo: el agente fractal viejo (`fractal_agent__1_.py`) → roadmap del harness (mesas 4, 5, 6)

**Fecha:** 2026-10-23 · **Origen:** `docs/informes/fractal_agent__1_.py` (531 líneas), `docs/informes/mock_llm__1_.py` (41), `docs/informes/server.py` (60) · **Destino:** `docs/roadmap.md` mesas 4/5/6 (líneas 224–253) y el harness actual (`main.py`, `nodes.py`, `modules/`, `juez_lote.py`, `informe.py`).
**Método:** lectura directa de los cuatro archivos citados y del código de destino; cada afirmación sobre el harness va con `archivo:línea` verificado. Lo que no verifiqué se dice explícitamente.

## Veredicto

El agente fractal **no es código a portar: es un prototipo de referencia** con cuatro ideas maduras (spawn en paralelo con presupuesto heredado, best-of k, loops con condición de parada observable, catálogo como fold), **un sustrato que el harness no tiene ni necesita copiar** (DBOS como motor de durabilidad) y **dos piezas que el harness ya resolvió mejor** (HITL y paralelismo acotado). El valor está en las ideas, no en el archivo: portarlas es trabajo de la mesa 4/5/6, no una migración.

Lo que el auditor dio como contexto —"la mesa 4 y la mesa 5 resueltas de diseño: Spawn lanza sub-agentes como workflows hijos en paralelo y BestOf corre k borradores en paralelo"— **se confirma en el código** (`fractal_agent__1_.py:224-246` y `:203-222`), **pero no está resuelto en el roadmap**: la mesa 4 lista los sub-agentes como tarea abierta (`docs/roadmap.md:224-230`) y la mesa 5 lista research/comité/supervisor (`docs/roadmap.md:231-235`); `spawn` y `best_of` no aparecen en ninguna de las dos. El prototipo prueba que el diseño cierra; el harness no lo implementó.

## 1. Qué es el prototipo (mapa de 12-factor)

El docstring declara el mapa (`fractal_agent__1_.py:3-7`) y el resto del archivo lo cumple:

| Factor | Dónde | Qué hace |
|---|---|---|
| F1/F4 (una sola boca al LLM, prompts propios) | `:50-56` ROLES, `:112-143` `Ask` | un nodo `Ask` por rol; cada rol ve solo sus campos |
| F2/F3 (system fijo, contexto propio) | `:24-48` `render`/`Ctx` | bloques `<campo>` solo con valor |
| F5/F6 (durabilidad) | `:61-72` `llm`, `:451-470` `agent` | cada llamada al LLM es `@DBOS.step`; el agente es `@DBOS.workflow` |
| F7 (human-in-the-loop) | `:148-170` `AskHuman` | `DBOS.set_event` + `recv` con timeout de 30 días |
| F8 (flujo de control propio) | `:395-432` `compile_plan` | compilador determinista: plan JSON → `AsyncFlow` |
| F9 (error compacto) | `:120-127`, `:442-447` `retry` | error de 200 chars vuelve al planificador; 3 seguidos → humano |
| F10 (fractal) | `:224-246` `Spawn`, `:203-222` `BestOf` | ver §2 |
| F11 (lanzar/consultar/responder) | `:472-531` + `server.py` | cola de 4 workers, HTTP con token |
| F12 (catálogo como fold) | `:249-345` `Toolkit` | piezas con contrato; `restore` pliega los resultados de workflows raíz previos |

## 2. Las dos ideas que el auditor señaló (verificadas) y su estado en el roadmap

### 2.1 Spawn: sub-agentes como workflows hijos en paralelo, con presupuesto heredado

- `Spawn(AsyncParallelBatchNode)` (`fractal_agent__1_.py:224`) reserva `0.8` del saldo, lo divide por subtarea y llama `DBOS.start_workflow_async(agent, …, depth=depth+1)` una vez por subtarea (`:228-235`). El paralelismo es de pocketflow; la durabilidad la da DBOS: cada hijo es un workflow con su propio id.
- El tope de profundidad está en el kernel, fuera del alcance del agente: `Budget.reserve` lanza `PlanError("profundidad máxima")` con `depth >= max_depth` (`:105-109`), `max_depth=2` (`:101`), y `compile_plan` además prohíbe la pieza `subagent` a esa profundidad (`:406-407`). Doble cerrojo: el planificador no puede pedirla ni aunque la pida.
- La **devolución del sobrante** ocurre en `post_async`: `s["budget"].left += child["left"]` (`:240`) y los `outcomes` del hijo se aplican al catálogo del padre (`:241-243`). El hijo devuelve `{result, outcomes, left}` (`:468`).
- Lo que el hijo **no** hereda: `Budget.left` es un valor propio; lo heredado son `tokens`, `depth`, `parent`, `guidance` y `known` (`:232-234`). Es una donación, no un presupuesto compartido: el hijo no puede devolver más de lo que recibió y el padre no ve el gasto en tiempo real.

**Estado en el roadmap:** la mesa 4 pide "agents/ como modules/ (sub-agentes especializados: mini-flows con prompt y subset de tools, expuestos como tools)" (`docs/roadmap.md:224-226`) y la mesa 6 anota "loops fractales con presupuesto heredado (depth máx 2)" entre los siguientes sin fecha (`docs/roadmap.md:248-249`). Son **exactamente** las dos mitades de `Spawn`, y ninguna está hecha: el harness hoy despacha sub-agentes vía `supervisor.py`, secuencial, con `class UnPaso(Node)`/`class Ejecutar(Node)` (`supervisor.py:201`, `supervisor.py:233`), sin profundidad ni presupuesto.

### 2.2 BestOf: k borradores en paralelo y un juez elige

- `BestOf(AsyncNode)` con `k` acotado a 5 (`fractal_agent__1_.py:203-208`), `asyncio.gather` sobre `k` vistas con `variant=i/k` (`:213-215`) y una elección por `picker` (`:216`). Comentario del propio código: "2 rondas en vez de k" (`:202`).
- Diferencia con self-consistency: aquí los borradores **no votan**, un juez elige. El `picker` pide `{"best": int}` (`:40-41`) y cae a `drafts[0]` si el índice se sale de rango (`:220`).

**Estado en el roadmap:** la mesa 5 sólo menciona el comité de jueces vía `juez_lote + mayoria()` (`docs/roadmap.md:228-229`) y la mesa 4 el comité de jueces (`:230`). `best_of` no figura. Lo más cercano ya construido es `juez_lote.py` (AsyncParallelBatchFlow con semáforo, `juez_lote.py:8-13` y `:41-45`): la mecánica de fan-out está; la pieza "k borradores + selector" no.

## 3. Mesa por mesa: qué se porta, qué se convierte, qué se descarta

### Mesa 4 — Agentes fractales

| Idea del prototipo | Veredicto | Nota |
|---|---|---|
| Sub-agente como mini-flow con prompt + subset de tools | **Se porta** | Ya existe a medias: `skills/*.yaml` limita el subset de tools por skill (`docs/roadmap.md:274-279`) y `modules/memoria.py` es el patrón de "mini-flow expuesto". Falta el contrato `needs/gives` de `Piece` (`:249-256`). |
| Spawn en paralelo con `depth` y presupuesto heredado | **Se porta como diseño, sin DBOS** | Ver §4: en el harness el paralelismo se hace con `AsyncParallelBatch*` + semáforo (`juez_lote.py:41-45`), no con workflows hijos. `depth` y `reserve(0.8)` son lógica pura y se copian enteros (`:101-109`). |
| Best-of k | **Se porta** | Cuesta k llamadas; sólo se justifica donde el bench muestre mejora, igual que la puerta de correlación del voto (`nodes.py:908-915`). |
| Catálogo como fold (F12) + promoción `incubating→promoted/rejected` con 2/3 (`:273-278`) | **Se descarta por ahora** | El harness no tiene catálogo mutable de piezas; `Toolkit.adapt` sólo combina plantillas, nunca escribe código (`:265-267`), así que el riesgo es bajo, pero es un subsistema nuevo sin demanda medida. |
| `AskHuman` con `DBOS.recv(timeout=30 días)` | **Ya resuelto, no se copia** | El harness tiene HITL web con Event, timeout 300s y puerto elástico (`utils/hitl_web.py:1-37`, `:158`) y HITL terminal (`utils/aprobaciones.py:74`). El valor del prototipo es que la pausa es **durable entre procesos**; el del harness es que la pausa es **aprobable desde el navegador**. Son cosas distintas: si se quiere retomar una sesión pausada días después, el harness hoy usa `resume.py`. |

### Mesa 5 — Async donde falta

- `research.py` sigue con `BatchNode` en serie (`research.py:14`, `:70`): la mesa 5 lo pide explícitamente (`docs/roadmap.md:231-232`) y el prototipo no aporta nada ahí; el patrón medido es `juez_lote` (`juez_lote.py:8-13`).
- El `asyncio.gather` de `BestOf` (`:215`) es el mismo patrón que ya está en `informe.py` vía `AsyncParallelBatchNode` (`informe.py:154`) y en `juez_lote.py`.
- **Aporte real del prototipo a la mesa 5:** el comentario "arrancan en orden: replay determinista" (`:215`) y "se lanzan en orden: mismos ids al retomar" (`:230`) — la regla de lanzar en orden y recolectar por índice. En el harness esa regla ya aparece en `juez_lote.py` ("Cada tarea lleva su ÍNDICE… no en orden de terminación", `:11-13`).

### Mesa 6 — Contexto y loops

- Compacción: hecha (`docs/roadmap.md:236-244`); el prototipo no la tiene (el hijo arranca con contexto fresco, `:232-234`, que es otra estrategia: **aislamiento** en vez de **resumen**).
- **Aporte concreto:** `dried` (`fractal_agent__1_.py:186-189`) mide la convergencia sobre el **texto** ("se mide el texto, no lo que el agente dice"). Es la forma barata de la telemetría de convergencia que la mesa 6 dejó pendiente (`docs/roadmap.md:245-248`).
- **Aporte concreto:** `BudgetExceeded` **no** cae al `default` (`:120-122`): un presupuesto agotado no se rellena con una respuesta de relleno. En el padre se degrada explícitamente a `"[sin presupuesto: …]"` (`:459-460`).

## 4. La brecha de sustrato (y por qué no se copia)

El prototipo apoya F5/F6/F10 en DBOS: `@DBOS.step` sobre cada llamada al LLM (`:61`), `@DBOS.workflow(name="agent")` (`:451`), cola con `worker_concurrency=4` (`:475`), eventos para HITL (`:161-164`) y `start_workflow_async` para los hijos (`:233`).

Busqué DBOS en todo el harness (excluyendo `salidas/` y `banco/`): las únicas apariciones están en los tres archivos del prototipo. El harness no tiene motor de durabilidad; tiene replay de trazas (`replay.py`) y sesión persistida (`utils/estado_sesion.py`, `resume.py`). Portar DBOS sería cambiar el sustrato de todo el harness para ganar reanudación exacta de llamadas pagadas — un cambio de plataforma, no una mesa. **Recomendación: no se porta**; si algún día se quiere, es un experimento `exp/` propio con su puerta, no parte de las mesas 4/5/6.

## 5. Diferencias de calidad observables en el prototipo (no copiar tal cual)

- `BestOf.exec_async` contabiliza los k borradores sobre el MISMO objeto `Budget` del padre (`self.inner.call(s, v)` → `s["budget"].spend`, `:129-131`, llamado k veces concurrentes por `:215`). Hoy es correcto porque asyncio intercala solo en `await`s y `spend()` no tiene ninguno: cada resumición lo ejecuta atómico. La salvedad real es de sustrato: si algún día los borradores corren en threads o procesos, ahí sí hay carrera — conviene que la copia lo anote.
- `server.py:22` usa `asyncio.run(fa.load_outcomes())` dentro de un handler síncrono de `ThreadingHTTPServer`: crea y destruye un event loop por request. Funciona, pero es frágil como patrón.
- (Corregido por el auditor: una versión anterior de esta sección afirmaba un "bug latente" en `authorized()` porque devuelve `None` tras el 401 — falso: ambos handlers hacen `if not self.authorized(): return` y `None` es falsy, cortan bien. También se atribuía al GIL una atomicidad que da el event loop. Lección igual a exp/92: las afirmaciones sobre código se verifican, no se citan de memoria.)

## 6. Recomendación (una)

**Portar sólo dos piezas y con la forma del harness:** (a) el par `depth` + `reserve(share)`/devolución del sobrante de `fractal_agent__1_.py:101-109` y `:240` como lógica pura en el supervisor, y (b) `dried` (`:186-189`) como condición de parada de loops. Ambas son código puro, medibles y no tocan el sustrato. Spawn con workflows hijos y BestOf quedan como diseño registrado en este informe hasta que un bench muestre que el paralelismo o el k-borradores ganan algo medible; el sustrato DBOS se descarta.

**Límite de este análisis:** no corrí el prototipo (requiere `dbos` + `pocketflow` async y una base SQLite) ni medí nada; todas las afirmaciones son de lectura. Las citas van verificadas línea a línea; las afirmaciones SEMÁNTICAS (comportamiento) fueron re-auditadas por el operador — dos de la §5 original eran incorrectas y están corregidas arriba.

**PENDING del análisis original (resuelto por el operador):** registrar `spawn`/`best_of` y `dried` como líneas explícitas en `docs/roadmap.md` mesas 4/6 — resuelto con un puntero al mapeo en la mesa 4 (las piezas se registran como líneas propias cuando la mesa se des-estacione).
