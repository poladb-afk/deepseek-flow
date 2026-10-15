# deepseek-flow — diseño

Agente de terminal con herramientas de lectura de archivos, conectado a
**DeepSeek V4.1 Flash** (`deepseek-flash`, `https://api.deepseek.com`),
armado con PocketFlow.

## Objetivo

Un chat que **no cierra** y que, para responder sobre los archivos del
usuario, los explora por sí mismo: decide cuándo listar y cuándo leer
(patrones Chat + Agent del cookbook). Las credenciales viven **fuera** del
proyecto: `DEEPSEEK_API_KEY` en el entorno o `LLM_API_KEY` en el `.env` de bmo.

## Flujo

```mermaid
flowchart TD
    q[GetQuestion] -->|continue| s[AgentStep]
    s -->|answer| q
    s -->|tool| t[ExecuteTools]
    t --> s
    q -->|exit| x[ExitChat]
```

Es el patrón Agent (decidir → actuar → volver a decidir) implementado con
**tool calling nativo** de DeepSeek en vez de YAML: `AgentStep` manda el
historial + definiciones de tools; si el modelo responde con `tool_calls`,
la acción `tool` ejecuta y el bucle vuelve a `AgentStep`; si responde con
texto, la acción `answer` imprime y vuelve a esperar la siguiente pregunta.

## Sanitizado de respuestas descarriladas y thinking selectivo

Tres episodios medidos en producción (2026-10-05, todos en el camino
directo): un system prompt ajeno pegado al saludo, un `<small>` que
partía una palabra, una palabra espuria ("¿EnAnswered?"). Dos capas de
respuesta:

1. **Causa raíz (la más probable)**: `call_llm_agent` desactivaba el
   thinking SIEMPRE, aunque la llamada fuera sin tools — y la restricción
   A1 (con `tools` en el request, la API exige devolver el
   `reasoning_content` completo; corregido el 2026-10-13, la versión
   original decía "API rechaza tools+thinking") solo aplica con tools.
   Sin tools ahora va con thinking normal; verificado en vivo: respuestas
   limpias en ambos caminos.
2. **Defensa en profundidad**: `sanitizar()` en `AgentStep.post` corta
   en markers de rol ajenos (`<system>`, `[INST]`…; si no queda nada,
   el reintento del nodo re-pregunta) y quita tags HTML espurios que
   parten palabras (`S<small>oy` → `Soy`), sin tocar markdown legítimo.

## Streaming de respuestas (CHAT_STREAM)

Roadmap ítem 6. `call_llm_agent_stream(messages, tools=None)` en
`utils/call_llm.py` comparte el MISMO `_kwargs_agente` que la versión
clásica (contrato de modo thinking pegajoso y filtro de `reasoning_content`
sin deriva) pero con `stream=True`: imprime en vivo cada delta de CONTENT
(`print(..., end="", flush=True)`, sin saltos extra) y descarta los deltas
de reasoning_content. Al terminar devuelve un objeto con la forma que usa
el chat: `.content` ensamblado y `.tool_calls` reconstruidos desde los
fragmentos (llegan partidos por `index`; `id` y `function.name` solo en el
primer fragmento de cada llamada; `function.arguments` se acumula por
concatenación). Si el stream se corta a mitad, devuelve lo acumulado sin
explotar.

`AgentStep.exec` (y por herencia `DirectAnswer`, sin tocar su clase) usa la
versión stream cuando `CHAT_STREAM == "1"` (default) y la clásica con `0`.
El resto del flujo no cambia (historiar, recuperación DSML, sanitizar,
ExecuteTools). Como con streaming el contenido crudo ya se imprimió en
vivo, si `sanitizar` corta, tras el aviso existente se imprime también la
versión limpia (`DeepSeek (limpio): …`). Y como ya salió en vivo, `post()`
NO reimprime la respuesta completa: con stream solo cierra la línea (los
deltas van sin salto); con la clásica mantiene el `print("\nDeepSeek: …")`.

**Interrupción del usuario (CHAT_STREAM_INTERRUPT, default 1)**: un Ctrl+C
MIENTRAS se genera corta el stream y se devuelve lo acumulado — se imprime
`[interrumpido]` y el chat sigue (el parcial queda historado y mostrado, el
flujo vuelve al prompt). Con `0`, el `KeyboardInterrupt` se propaga y `main`
lo trata como salida, como siempre. El Ctrl+C fuera del stream no se toca.

**Corte por error, sin causa muda (2026-10-05)**: el `except Exception`
del stream sigue devolviendo lo acumulado (una caída de red no rompe el
chat), pero ya no **enmascara** la causa cuando no hay nada que devolver:
con CERO contenido acumulado imprime `[stream] se cortó sin contenido
(<Tipo>: <causa>)` — un 401/429/red con respuesta vacía deja de ser un
misterio (fragilidad medida en la caza de bugs). Con contenido parcial el
corte benigno no agrega ruido.

## El historial canónico y el modo thinking pegajoso (2026-10-05)

Tres crashes medidos en producción, todos `400: The reasoning_content in
the thinking mode must be passed back to the API`, dos de ellos con el
fix anterior puesto — lo que forzó a instrumentar el cliente y capturar
el historial exacto de la request fallida (dump en fallo, hoy retirado).

**El historial rechazado era estructuralmente perfecto** (dicts
canónicos, sin reasoning, sin extras) — el veneno no era la forma de los
mensajes sino el FLIP de modo thinking dentro de la conversación:

- ON→OFF: vuelta directa (thinking) seguida de vuelta con tools (crash
  del usuario, turno 3).
- OFF→ON: 8 rondas de tools y la llamada del tope reactiva thinking
  porque `tools=None` (crash en la sesión de fixes, reproducido dos
  veces; la traza .runs muestra las 8 rondas y el dump confirma 8
  assistants con tool_calls).

Respuesta en capas:

1. **`historiar()` en `nodes.py`**: el mensaje del asistente entra al
   historial como dict canónico `{role, content, tool_calls}` — sin
   `reasoning_content`, sin campos nulos del objeto pydantic.
   `ExecuteTools.prep` y `run_tool_call` usan la forma dict.
2. **Modo pegajoso en `call_llm_agent`**: si hay tráfico de tools en el
   historial (cualquier `role:tool` o `tool_calls`), thinking va
   desactivado aunque la llamada no traiga tools — cubre la llamada del
   tope de rondas Y las vueltas directas posteriores a una agéntica.
   Conversación limpia y sin tools: thinking normal (el modo disabled
   midió descarrilos). El filtro de `reasoning_content` queda como
   segunda barrera.
3. **`extraer_yaml`**, recovery DSML y sanitizar conviven con esto: los
   dos últimos viven en `exec()` (reintento real de PocketFlow), no en
   `post()`.

Validación: matriz de probes (4 combinaciones ±reasoning ±tools en
aislamiento: todas OK — el validador solo estalla con el flip real en
sesión larga) + E2E con `MAX_TOOL_ROUNDS=1` reproduciendo el escenario
exacto del crash (ronda de tools → llamada sin tools sobre historial
agéntico → vuelta directa): responde completo, sin 400.

Nota de límites: la regla del validador dejó de ser opaca — los docs
oficiales (verificados 2026-10-13) la documentan: con `tools` en el
request, el `reasoning_content` debe devolverse COMPLETO en todas las
requests subsecuentes; sin tools se ignora. Los tres crashes eran esa
regla rompiéndose (había tráfico agéntico + reasoning ausente tras el
flip de modo), y la sonda de exp/38 confirmó que el flip SOLO ya no
rechaza. El modo pegajoso se mantiene por decisión (este cliente descarta
el reasoning): la alternativa documentada —preservarlo en el historial—
habilitaría thinking en las rondas de tools al costo de reenviarlo en
cada vuelta.

## Sanitizado de respuestas descarriladas

Medido en producción (2026-10-05): una respuesta se cortó a mitad del
saludo y el modelo siguió emitiendo un system prompt AJENO (un "file
exploration agent" genérico — texto de entrenamiento, no inyección de
nadie: episodio estocástico de decodificación, no reproducible en 3
intentos). `AgentStep.post` ahora corta el contenido en el primer marker
de rol (`<system>`, `[INST]`, `<|im_start|>`…): el chat muestra y el
historial guarda solo lo que lo precede; si no queda nada, el reintento
del nodo re-pregunta. Test con el transcript real.

## Recuperación del canal de tools (DSML como texto)

Medido en producción (2026-10-05): a veces DeepSeek emite las tool calls
como TEXTO crudo con su markup interno (DSML, `<｜DSML｜｜ invoke …>`) en
vez del canal estructurado — el chat las imprimía como respuesta y se
quedaba esperando, sin ejecutar nada. `AgentStep.post` ahora lo detecta:
sin `tool_calls` pero con la marca DSML en el contenido → `dsml_a_tool_calls`
parsea de vuelta los invokes (misma forma que la API) y los INYECTA en el
mensaje, con el markup limpiado para que el historial quede canónico. El
camino `tool` existente sigue intacto. Test con el transcript real.

## Comunicación (shared)

| Clave | Contenido |
|---|---|
| `messages` | Historial completo: system (fijo) + user + assistant (con `tool_calls` cuando pidió herramientas) + tool (resultados). Es lo único que DeepSeek recibe en cada vuelta |
| `tool_rounds` | Rondas de herramientas gastadas en la pregunta actual; lo resetea `GetQuestion` |
| `no_progress` / `_fp` | Repeticiones idénticas de la ronda de tools (huella de nombre+argumentos) y su huella anterior; los resetea `GetQuestion` (exp/13, escape por no-progreso) |
| `compacciones` / `_compaccion_huella` | Compactaciones aplicadas al historial y huella del historial ya compactado (evita re-compactar la misma ronda) |
| `operacion` / `max_tool_rounds` | Perfil de presupuesto declarado por el invocador y override explícito del techo; los lee `presupuesto()` (hoy el chat no los siembra) |

## Nodos

| Nodo | Tipo | prep | exec | post |
|---|---|---|---|---|
| GetQuestion | Node | — | `input()` (ignora vacías; EOF → exit) | `salir/exit/quit` → `exit`; si no, resetea el presupuesto por pregunta (ley L8) y agrega el mensaje user → `continue`; `/aprobaciones` imprime el historial HITL y NO entra al historial |
| AgentStep | Node (max_retries=3, wait=5) | historial + tools (sin tools si ya gastó el límite) | `call_llm_agent` (o `call_llm_agent_stream` con `CHAT_STREAM=1`) | agrega el mensaje del asistente; con `tool_calls` → `tool`; si no, imprime → `answer` (con streaming el `print` solo cierra la línea: la respuesta ya salió en vivo) |
| ExecuteTools | Node | último `tool_calls` | ejecuta cada llamada (`run_tool_call`) | agrega mensajes tool, suma `tool_rounds` → `default` |
| ExitChat | Node | — | — | imprime despedida |

## Utilities

- `call_llm(messages)` → texto (smoke test).
- `call_llm_agent(messages, tools=None)` → mensaje del asistente, con
  `extra_body={"thinking": {"type": "disabled"}}` cuando hay tráfico de
  tools. La razón DOCUMENTADA (docs oficiales, verificados 2026-10-13):
  con `tools` en el request la API exige devolver el `reasoning_content`
  completo en todas las requests subsecuentes; este cliente lo descarta,
  así que thinking va desactivado en todo tráfico agéntico (la anotación
  A1 original —"rechaza tools+thinking juntos"— describía el síntoma, no
  la regla; ver la sección del modo pegajoso).
- `call_llm_agent_stream(messages, tools=None)` → igual contrato, con
  `stream=True`; imprime el CONTENT en vivo y devuelve el mensaje
  ensamblado (content + tool_calls). La versión clásica sigue disponible
  con `CHAT_STREAM=0`.
- `fs_tools.py` — el cuerpo del agente:
  - `list_files(path?, depth)`: listing con tamaños; sin path lista los
    directorios permitidos; salta `.venv*`, `.git`, `__pycache__`,
    `node_modules`; truncado a 300 entradas.
  - `read_file(path, offset, limit)`: páginas de hasta 500 líneas,
    recortada a `READ_MAX_CHARS` (corta el medio).
  - `search_files(query?, glob?, path?)`: busca por nombre (glob) y/o por
    texto en el contenido (insensible a mayúsculas); devuelve rutas y
    números de línea; topes de 50 archivos / 200 líneas, 5 líneas por
    archivo; omite binarios y archivos de más de 4 MB en búsquedas de
    contenido.
  - `run_tool_call(tc)`: dispatch + mensaje `role=tool`. Los errores de uso
    ("ERROR: ...") se devuelven como texto para que el modelo corrija; los
    fallos transitorios del API los maneja el retry del Node.

## Leyes / límites

| Límite | Qué | Dónde |
|---|---|---|
| Contención | Ninguna ruta sale de `AGENT_ALLOWED_DIRS` (resueltas con `Path.resolve`) | `fs_tools._resolve` |
| Rondas | `presupuesto(shared)` por pregunta (override > perfil de `operacion` > `MAX_TOOL_ROUNDS`); al llegar, `AgentStep` retira las tools y el modelo debe responder. Se reinicia con cada pregunta nueva del usuario (el comando `/aprobaciones` incluido, que no agrega mensaje) | `nodes.presupuesto`, `AgentStep.prep` |
| No-progreso | Repeticiones idénticas de la ronda de tools (`fingerprint` de nombre+argumentos) a `UMBRAL_SIN_PROGRESO`: se retiran las tools sin esperar el techo, con el evento `corte_no_progreso` en la traza | `nodes.fingerprint`, `ExecuteTools.post`, `AgentStep.prep` |
| Contexto | `READ_MAX_CHARS` por lectura, listados truncados | `fs_tools` |

## Segundo flujo: informe map-reduce

```
python3 main.py informe [carpeta] [--glob '*.jsonl'] [--salida informe.md]
```

Default: `.` (el CWD — portable; `INFORME_CARPETA` en .env fija otra,
p. ej. `~/Documentos/00_IA/bmo/data` en esta máquina). También corre
directo con `python3 informe.py`.

```mermaid
flowchart LR
    s[ScanFiles] --> m["AnalizeFile (AsyncParallelBatchNode)"]
    m --> w[WriteReport]
```

Patrón Map-Reduce del cookbook con **mapa paralelo**: `AnalizeFile` es un
`AsyncParallelBatchNode` (las llamadas a DeepSeek se solapan con
`asyncio.gather`) dentro de un `AsyncFlow`; `ScanFiles` y `WriteReport`
quedan síncronos — `AsyncFlow` ejecuta los `Node` normales tal cual y solo
espera a los `AsyncNode`. La utilidad es `call_llm_async` (`AsyncOpenAI`):
dentro de `gather` tiene que haber I/O esperado de verdad, o nada se
solapa. `asyncio.gather` conserva el orden: el informe es determinista.
Hechos exactos en código, interpretación en LLM (principio de bmo).

Medido: una llamada ≈ 5,5 s; el pipeline completo (12 mapas en paralelo +
1 síntesis secuencial) ≈ 12 s.

| shared | Contenido |
|---|---|
| `folder`, `glob`, `salida` | configuración sembrada por main |
| `files` | rutas encontradas (ScanFiles) |
| `analisis` | `[{file, total, errores, modulos, ejemplos, resumen}]` (AnalizeFile) |
| `informe` | ruta del markdown final (WriteReport) |

Topes: `MAX_FILES=30`, 2 tareas de ejemplo por archivo, reintentos 3/wait 5
en mapa y reduce (el BatchNode reintenta **por archivo**, no por lote).

## Módulos: el CORE y sus capacidades

El chat es el **CORE**: capacidades base de solo lectura (`fs_tools`) más
las herramientas que aporten los módulos. Un módulo es un archivo en
`modules/` que exporta `TOOLS` (esquemas OpenAI) e `IMPL`
(nombre → implementación). `modules.discover()` los junta al arrancar y
`nodes.py` arma el action space: `core + módulos`.

- Agregar una capacidad = dejar un archivo en `modules/`.
- Quitarla = borrarlo (el descubrimiento es al iniciar el proceso).
- Una pieza puede existir standalone y exponerse como módulo:
  `modules/informe.py` es solo el adaptador de `informe.py`, que sigue
  funcionando sola (`main.py informe`).

Es la arquitectura de bmo ("one node, one module, one capability") en su
forma mínima: el action space del agente **es** el registro de módulos.

| Módulo | Herramienta | Qué hace |
|---|---|---|
| `informe` | `run_informe(carpeta?, glob?, salida?)` | lanza el pipeline map-reduce y devuelve la ruta del markdown; el progreso se imprime en vivo |
| `escritura` | `write_file(path, content)` | escribe dentro de los directorios permitidos **con aprobación humana (HITL)**: vista previa (diff si existe) y `s/n` en la terminal — o desde el navegador con `HITL_WEB=1` (`utils/hitl_web.py`); EOF/Ctrl+C/timeout cuentan como rechazo (default seguro); el rechazo vuelve al modelo como texto para que corrija; contenido idéntico → no-op |
| `juez` | `answer_verified(pregunta, rondas?)` | responde con control de calidad: borrador → juez → refinamiento; el juez verifica citas ruta:línea contra el contenido real; `rondas` fija el tope de evaluación (default 2) |
| `juez` (lote) | `juez_lote(preguntas, salida?)` | verifica N preguntas EN PARALELO (AsyncParallelBatchFlow) reutilizando el flujo del juez; informe con una sección por pregunta + speedup medido |
| `auditoria` | `run_auditoria(carpetas, glob?, salida?)` | audita varias carpetas a la vez (una sección por carpeta + síntesis comparativa) |
| `rag` | `rag_search(consulta, k?)` / `rag_index(carpeta?, glob?)` | búsqueda semántica sobre el índice local (embeddings fastembed) y (re)indexación |
| `debate` | `debate(tema, rondas?)` | debate multi-agente (proponente vs crítico por colas) con juez final |
| `mcp` | `mcp_tools()` / `mcp_call(servidor, herramienta, argumentos)` | habla el Model Context Protocol: consume herramientas de servidores MCP externos configurados en `MCP_SERVERS` — el action space deja de ser cerrado |
| `websearch` | `search_web(consulta, k?)` | búsqueda web con ddgs (DuckDuckGo, sin API key); devuelve título, URL y resumen para citar |
| `research` | `deep_research(tema, salida?)` | loop de cobertura: planner → researcher (web) → synthesizer; detecta huecos y re-planifica (MAX_ROUNDS=2) |
| `supervisor` | `run_supervisor(tarea, salida?)` | bucle reactivo: Laya (Choose local, umbral 0.9) o DeepSeek eligen la herramienta de cada paso; síntesis final |
| `db` | `sql(consulta)` / `db_schema()` | SELECT de solo lectura sobre la base SQLite de trazas (una sentencia, LIMIT forzado, sin DDL) |
| `effective_n` | `run_effective_n(carpetas?, glob?, salida?)` | deduplicación exacta por contenido de trazas .jsonl: Effective N, archivos duplicados enteros, solape por pares, contradicciones de etiqueta; 1 o varias carpetas (BatchFlow, informe conjunto) |

### HITL web — la aprobación desde el navegador
`utils/hitl_web.py` · [utils/hitl_web.py](../utils/hitl_web.py)

Con `HITL_WEB=1`, las aprobaciones de `write_file`, `edit_file` y
`run_command` dejan de pedir `s/n` por stdin: `aprobar(titulo, cuerpo)`
levanta (perezoso, una sola vez) un servidor HTTP en `127.0.0.1:8765`
(`HITL_WEB_PORT`) que sirve una página simple con el título, el cuerpo
(el diff o el comando) dentro de `<pre>` y dos forms con botones
**Aprobar / Rechazar** que hacen POST a `/decision`. Solo stdlib
(`http.server` + `threading`) — sin dependencias nuevas. Un solo pedido
pendiente a la vez (`threading.Event`), timeout `HITL_WEB_TIMEOUT`
(300s): timeout o error ⇒ `False`, el mismo default seguro que el CLI.
El chat, el agente y el CORE no cambian una línea: `_approve` de cada
módulo solo elige la fuente de la respuesta (navegador o terminal).

### Servidor MCP (dirección inversa)

`python3 main.py mcp-server` expone las capacidades del chat a OTROS
agentes por stdio ([mcp_server.py](../mcp_server.py)). Allowlist en
`MCP_EXPOSE` (default: solo lectura + rag + juez; excluye write_file por
el HITL de terminal y los pipelines largos). En stdout viaja el protocolo:
todo aviso del servidor va a stderr.

## Piezas: juez, auditoría, RAG y debate

Cada pieza es standalone (subcomando CLI) Y módulo del chat.

### Juez — evaluator-optimizer + structured output
`main.py juez "pregunta"` · [juez.py](../juez.py)

```mermaid
flowchart LR
    d[Draft] --> j[Judge]
    j -- "retry" --> d
    j -- "entregar" --> f[Fin]
```

`Draft` recibe en prep el contenido real de los archivos mencionados en
la pregunta (los hechos los reúne el código). `Judge` extrae las citas
`ruta:línea` del borrador, lee las líneas reales, y evalúa en YAML
(`verdict: ok/retry`) — `extraer_yaml` + `_veredicto_valido`: un veredicto
que no valida **no lanza** — el Judge reintenta citando el crudo inválido como
feedback (fase B2 de exp/21, abajo). Tope de rondas `JUEZ_ROUNDS` (default 2, ley L8),
configurable por corrida con `--rondas N` o `shared["max_rounds"]`; la tool
`answer_verified(pregunta, rondas?)` lo expone.

### Auditoría — BatchFlow + flujo anidado (Flow como Node)
`main.py auditoria c1 c2 [--glob] [--salida]` · [auditoria.py](../auditoria.py)

```mermaid
flowchart LR
    subgraph inner[flujo interno, por carpeta]
        s[CarpetaScan] --> m["AnalizeFile (reutilizado)"] --> x[Seccion]
    end
    b["AuditorCarpetas (BatchFlow)<br/>params: carpeta"] --> inner
    b --> r[ReduceGlobal]
```

El `AsyncBatchFlow` re-corre el flujo interno una vez por carpeta con
`params["carpeta"]` (el identificador viaja en params, los datos en
shared), y el BatchFlow mismo se enchufa como nodo en el Flow exterior
antes del reduce. Iteraciones secuenciales a propósito: comparten shared.

### RAG — offline index + online retrieve
`main.py index [carpeta] [--glob]` · [rag.py](../rag.py) · [utils/embeddings.py](../utils/embeddings.py)

Offline: `ChunkDocs → EmbedChunks → SaveIndex` (BatchNodes; chunks de
1200 chars con overlap, embeddings fastembed locales — paraphrase-
multilingual-MiniLM, sin API key — guardados en `rag_index/`). Online:
`buscar(consulta)` encasta por coseno y devuelve top-k con ruta y score.
Sin embedder disponible degrada a BM25 léxico (mismo flujo, otro scorer).
El modo viaja por `flow.set_params` — params para config de tarea.

### Debate — multi-agente con colas`main.py debate "tema" [--rondas]` · [debate.py](../debate.py)

Proponente y Crítico son dos `AsyncFlow` independientes que se
auto-apuntan (`agente - "continue" >> agente`) y se comunican SOLO por
`asyncio.Queue` (patrón Taboo del doc de multi-agent). Sentinel `FIN`
para terminar limpio; `JuezDebate` dictamina en YAML reutilizando
`extraer_yaml`. Las call_llm síncronas dentro de async son correctas:
el debate es ping-pong, solo uno piensa a la vez.

### Research — loop de cobertura (la inversión del juez)
`main.py research "tema"` · [research.py](../research.py)

```mermaid
flowchart LR
    p[Planner] --> r[Researcher<br/>BatchNode]
    r --> s[Synthesizer]
    s -- "research" --> p
```

El synthesizer juzga la COBERTURA (no la respuesta): con huecos, vuelve
al planner con feedback; presupuesto MAX_ROUNDS=2. Web por ddgs,
structured output en todo (extraer_yaml + assert + retry).

### Supervisor — bucle reactivo con Choose local
`main.py supervisor "tarea"` · [supervisor.py](../supervisor.py) · [sonda_supervisor.py](../sonda_supervisor.py)

```mermaid
flowchart TD
    e[ElegirSiguiente] -->|ejecutar| p[EjecutarPaso]
    p -->|elegir| e
    e -->|sintetizar| s[Sintetizar]
    p -->|sintetizar| s
```

ElegirSiguiente (Laya con la task **supervisor_dispatch**: 18 opciones =
17 tools + finish; `uncertain` o sin laya → DeepSeek con el catálogo) →
EjecutarPaso (args por mini-llamada DeepSeek + ejecución + el hecho
`N herramienta(args) -> resultado` que verá la elección siguiente) →
repetir hasta finish o MAX_PASOS=5 (L8) → Sintetizar. Antes era una
tanda: un plan de una vez y los pasos dependientes quedaban fuera; ahora
el paso N+1 decide con el resultado del N — el Choose de bmo. El estado
`{tarea, hechos}` y `PREGUNTA_DESPACHO` replican la task byte a byte
(test de humo vigila las 18 opciones). Anti-recursión (L1): run_supervisor
no está entre las opciones ni en el fallback. **Mayoría 2-de-3**
(`utils/votacion.py`): la vía dudosa resuelve por mayoría — voto A
(DeepSeek, prompt clásico), voto B (DeepSeek, por eliminación: framing
independiente) y voto C (el crudo de Laya, consulta ya pagada); triple
desacuerdo → gana A. Laya segura sigue despachando sola (0 llamadas); el
veto manda sobre cualquier mayoría. USE_VOTACION=0 apaga (voto único).
Medido con LLM real sobre el test de 24: sistema 16/24 (voto único) →
**17/24 (mayoría)**; corrige justo los pares confusos (search_web↔list,
db_schema↔sql, read_file↔search_web) y el hallazgo honesto: A y B
correlacionan (misma familia ante el mismo catálogo, coincidieron
equivocados en 3 casos) — la independencia real la aporta el voto C. **Self-healing** (ítem 4
del roadmap): un paso que falla es un hecho con `ERROR (...)`; reintentar
esa herramienta recibe el error como feedback explícito en el prompt de
args; a los {MAX_FALLOS_POR_HERRAMIENTA} fallos la herramienta se VETA
(ni Laya ni DeepSeek pueden elegirla; si DeepSeek desobedece, finish) —
el reintento tiene presupuesto, no bucle. El éxito limpia el contador.
El informe final lleva la sección "Pasos": la auditoría de la corrida
(una línea por paso con su resultado, errores incluidos). Verificado con LLM real en cuatro
corridas (íntegras en el log de la sesión): (1-2) tareas limpias —
trazas de bmo/data y localizar MAX_TOOL_ROUNDS — sin fallos duros, con
recuperación suave (truncado → relectura acotada); (3) archivo
inexistente: fallo → pivot ordenado (search→list→search) → cierre
honesto con alternativa; (4) SQL con columna inexistente: fallo →
reintento con feedback → corrección copiando el nombre exacto del
esquema ya ejecutado → tarea resuelta. La corrida (4) destapó dos fixes:
- **Veto de repetición sin-args**: db_schema corrió 4 veces en la primera
  versión de la tarea (patología medida — el presupuesto se quemaba antes
  del primer error). Las herramientas sin argumentos que ya corrieron
  exitosas quedan vetadas en la corrida (L8; `SIN_ARGS`).
- **Feedback reforzado**: el reintento corregía a ciegas ("programa") en
  vez de leer el esquema visible en hechos; ahora el prompt exige copiar
  los nombres EXACTOS de los pasos ejecutados. El umbral de despacho es
propio y MÁS exigente que el del router (`LAYA_UNSURE_HIGH_SUPERVISOR`,
0.9): un paso quemado pesa más que la llamada que ahorra. utils/laya
cachea agentes POR setting: el router y el supervisor son checkpoints
distintos (`LAYA_MODEL` / `LAYA_MODEL_SUPERVISOR`).

Ciclo de fine-tune medido (test a mano 24, todas las opciones cubiertas):

| checkpoint | crudo | ECE | despachos locales (umbral 0.9) |
|---|---|---|---|
| base multilingual | 5/24 | 0.574 | — |
| supervisor_dispatch r1 | 8/24 | 0.353 | (menú truncado) |
| supervisor_dispatch r2 (60/opción) | 11/24 | 0.222 | 1/24 · 1/1 |
| supervisor_dispatch r3 (164/opción, hechos 100% del menú) | 15/24 | 0.293 | 13/24 · 9/13 |
| **r4 (+round dirigido a los pares confusos, 3.283 casos)** | 14/24 | 0.238 | **8/24 · 8/8 correctos** |

Hallazgos del ciclo (todos documentados en el LEEME de
bmo/train/kaggle-supervisor): (1) **el head se trunca en silencio** —
instructions + 18 criteria ≈ 278 tokens > head_max_len 256: las últimas
opciones nunca se veían; criteria cortos → 231 tokens y +3 de acierto;
(2) **el 87% del dataset entrenó con hechos de herramientas inventadas**
(grep, ls, python...) porque el prompt no restringía los nombres — el
filtro exacto (`train/filtrar_hechos.py`) rescató 138/1.094; el prompt
corregido exige nombres del menú y 1/3 de primer paso (train viejo 12%
vs test 54%); (3) la dosis por opción manda: router 410/opción → 20/24,
harness_choose 330 → 23/24, esto 60 → 11/24; (4) la generación del
round a escala (n=216) murió con HTTP 402 (saldo DeepSeek agotado) tras
399 casos casi todos primer-paso — inservibles. El checkpoint v2 está
el round a escala se corrió tras recargar saldo: 2.946 casos (89-215 por
opción, hechos 100% del menú real) → 15/24 con 13 despachos locales de
los cuales 9 correctos. Tercera corrección del ciclo: el propio filtro
de hechos tenía un bug (findall con dos grupos → tuplas → rechazaba
todo); medición real del dataset viejo: 33% válido, y el prompt
corregido da 100%. Umbral 0.9 mantenido con números. El round dirigido a los pares
confusos (+560 verificados con generate_targeted, reescrito genérico)
curó lo que quedaba: r4 despacha MENOS (8/24) pero 8/8 correctos — el
modelo aprendió a dudar donde antes estaba seguro y equivocado. El
acierto crudo se estanca en ~14-15/24 (el matiz de los pares
search_web/deep_research, informe/auditoria, sql/db_schema es en parte
convención, no hecho); la calibración es lo que el sistema necesita:
todo lo que Laya despacha local es correcto, el resto lo decide DeepSeek.
Techo asumido: más rounds de datos no mueven el crudo.

### Base de datos — trazas interrogables
`python3 carga_trazas.py [carpeta]` → `trazas.db` · [modules/db.py](../modules/db.py)

Carga código-pura verificable (15.595 registros, cruza con los conteos
del informe); la tool `sql` es SELECT de una sola sentencia con LIMIT
forzado y vocabulario prohibido (insert/update/delete/...).

### Effective N — deduplicación exacta antes de entrenar
`main.py effective_n [carpeta ...]` · [effective_n.py](../effective_n.py)

```mermaid
flowchart LR
    s[ScanFiles] --> h["HashFile (BatchNode)"] --> w[WriteReport]
```

El informe cuenta registros por archivo; esta pieza responde la pregunta
previa al re-entrenamiento: cuántos son **distintos de verdad**. Código
puro (como carga_trazas), sin LLM: la huella de contenido es sha1 de
`(task, observation, criteria, steps, answers.next)` — ignora
`id`/`created`/`model`, que cambian entre volcados del mismo caso. El mapa
hashea archivo por archivo; el reduce cruza pares, detecta archivos
duplicados enteros (md5), contradicciones de etiqueta (misma huella sin
`next`, etiquetas distintas) y escribe el markdown.

Con VARIAS carpetas, `EffectiveNMulti` (BatchFlow) fanea el MISMO flujo por
carpeta y escribe un informe conjunto con una sección por carpeta + resumen.
Es SECUENCIAL a propósito (CPU puro: el paralelismo no aporta y el orden de
las secciones es virtud). Con UNA carpeta el resultado es idéntico al de
siempre (compatibilidad hacia atrás).

En el BatchFlow la rama es un `Flow` anidado, y `_orch` del flujo interno NO
recibe el job del batch: se usa una cola de jobs propia que respeta el orden
y se aplica a la corrida del pipeline. El modo single no entra nunca al
BatchFlow.

### Juez en lote — AsyncParallelBatchFlow (I/O-bound)
`main.py juez_lote preguntas.txt` · [juez_lote.py](../juez_lote.py)

```mermaid
flowchart LR
    p["prep: 1 job por pregunta"] --> c["CorrerJuez (AsyncNode)<br/>asyncio.gather"]
    c --> r["post: informe + speedup"]
```

Cada pregunta corre el flujo del juez EXISTENTE (`juez.create_juez_flow`)
dentro del fan-out async; el puente sync→async es `asyncio.to_thread` (el
flujo bloquea en `call_llm`). I/O-bound (LLM): el paralelismo SÍ aporta y se
MIDE — suma de los tiempos individuales vs reloj de pared → speedup (patrón
parallel del cookbook). Cada corrida lleva su índice: el informe queda en el
orden del archivo, no en orden de terminación.

| shared | Contenido |
|---|---|
| `folder`, `glob`, `salida` | configuración sembrada por main |
| `files` | rutas encontradas (ScanFiles) |
| `analisis` | por archivo: n, rotos, huellas, etiquetas, con steps/observation, dist next, md5 |
| `informe`, `resumen` | ruta del markdown y línea "N → Effective N" (WriteReport) |

Hallazgos medidos sobre `bmo/data` (12 archivos, 15.595 registros):

1. **Effective N = 6.717** (56,9% de duplicación), **0 contradicciones de
   etiqueta** — la duplicación es repetición, no ruido de etiquetas.
2. `round3/harness_choose.jsonl` ≡ `round3/harness_choose_verified.jsonl`
   **byte a byte (md5 idéntico)**: la verificación de round3 no filtró
   nada — el volcado copió choose→verified sin pasar por el juez.
3. round3 es **acumulativo**: contiene 2.316 de los 2.591 de round2
   (89,6%). Sumar round2+round3 casi no suma datos (aporta 275 casos).
4. **Rounds sin `steps`**: round1-3 traen `observation` (0 registros con
   `steps`); producción (decisions.jsonl del sandbox: 121/151) y la raíz
   verified (1.097/1.109) usan `steps`. Esquema de estado distinto: si se
   re-entrena con rounds, el modelo no ve el campo que domina en producción.
5. `relabelled` vacío (0 bytes) en raíz y round1: el volcado lo crea y
   nunca lo llena. La raíz `rejected` mezcla dos esquemas (60 con steps +
   354 con observation).
6. Subconjunto entrenable máximo no redundante:
   `raiz_verified + round1_verified + round3` = **6.141 casos** (los tres
   bloques son disjuntos por contenido entre sí).

Decisión sobre el pipeline de rounds (el ítem 1 del roadmap): el volcado
de rounds no está versionado en bmo (ningún script del repo escribe
`*_verified`/`*_relabelled`) y dejó tres defectos: verificación saltada
(round3), esquema sin `steps`, relabelled nunca poblado. Corrección:
regenerar los rounds con el generador versionado (`train/generate_targeted.py`,
que emite `steps` vía schema) o versionar el generador de observaciones;
hasta entonces, entrenar solo con el subconjunto del punto 6 y tratar
`round3/verified` como choose.

### Laya — el router del chat, afinado (activo por defecto)
[utils/laya.py](../utils/laya.py) · nodos LayaRouter/DirectAnswer · [sonda_router.py](../sonda_router.py)

Laya responde preguntas cerradas en local (carga ~12 s, inferencia ~0 s,
costo 0) con probabilidades; los umbrales de bmo (0.7/0.3) convierten la
confianza en met/uncertain/not met, y uncertain cae al lado SEGURO
(herramientas). El checkpoint es el fine-tune **router_flow** (bmo,
`train/kaggle-router/`): la task replica byte a byte `PREGUNTA_ROUTER` y
el estado `{"pregunta": ...}` es el mismo dict que produce
`Task.state` — el contrato entrenamiento≡producción que las rondas 4 de
harness_choose enseñaron por las malas (estado distinto → 14/24).

Pipeline (la stack de bmo tal cual): task YAML + 12 contextos de tráfico
→ generate con DeepSeek (json_object; 840 casos balanceados, únicos) →
verify con juez ciego (821/840 conservados) → Kaggle T4 (`layaft train`,
RLCD + calibración, 656 secuencias, median 93 tokens) → checkpoint
`.modelos/router_flow-1k` → medición local en CPU.

Medido sobre el test a mano de 24 (12/12, jamás entrenado; los 5 primeros
son la sonda histórica):

| checkpoint | crudo | ECE | con compuerta |
|---|---|---|---|
| base multilingual | 13/24 | 0.379 | 12/24 |
| router_flow-1k | 20/24 | 0.077 | 22/24 |
| **router_flow-1k curado (test 30, +300 imperativos)** | **27/30** | **0.066** | **28/30** |

El fallo del base era sistemático: sesgo a `directo` con confianza ALTA
(mundial 0.95, cómputo 0.97, clima 0.97, README 0.84) — la compuerta no
protegía porque los errores eran seguros de sí (de 12 casos-herramientas
acertaba 2). Tras el fine-tune la compuerta vuelve a servir: los errores
crudos quedan en confianzas bajas (clima 0.68, README 0.51, tests 0.57)
y caen al lado seguro. Los 2 fallos restantes: "¿quién ganó el último
mundial?" (directo 0.83, pasa la compuerta — el punto débil histórico
persiste en su forma española neutra) y el muro de Berlín (directo
correcto pero 0.63 < 0.7 → herramientas; sobre-cautela barata: cuesta
una llamada más, no una respuesta mal fundada).

`sonda_router.py` corre el test con la lógica EXACTA de producción
(`python3 sonda_router.py [ckpt ...]`, sin args usa `LAYA_MODEL`).
**Curaduría con imperativos** (2026-10-05): la sesión completa mostró
el falso-directo sistemático con imperativos de acción ("debatí…",
"investigá…", 0.78-0.96). Round dirigido de +300 casos con la regla
capacidad-vs-creativo en el prompt (generate_targeted, 300/300
verificados → 1.121 casos) y un run más: los 6 casos-imperativos del
test 6/6, y la trampa inversa ("escribime un haiku") correcta a 0.97.
Persiste el histórico "último mundial" (0.83) — en producción lo cubre
el voto. **Ensamble 2-de-2 con voto de confirmación** (medido en la sesión
completa): el checkpoint dice 'directo' con confianza 0.78-0.96 para
imperativos de acción ("debatí…", "investigá…") y las capacidades se
perdían — el test del router no tenía casos imperativos. Ahora, cuando
Laya dice directo con 'met', `voto_confirmacion_router` pide una
mini-llamada de confirmación a DeepSeek ("¿herramientas o directo?");
desacuerdo → lado seguro. Verificado en vivo: debate y deep_research
corrieron por fin como tools (planner, búsqueda, huecos, segunda ronda).
Cobertura final: **18/18 capacidades**. USE_VOTACION=0 apaga ambos
ensambles.

Verificado el flujo COMPLETO del chat contra LLM real (2026-10-05):
camino directo dos vueltas seguidas y camino herramientas con tool_calls
reales. La primera pasada destapó un bug de cableado latente desde el
flag-0: `DirectAnswer >> ask` armaba la arista default pero el post
heredado devuelve "answer" — el chat MORÍA tras la primera respuesta
directa (PocketFlow: "Flow ends: 'answer' not found"). Fix: aristas
`answer`/`tool` explícitas (test_router_aristas_del_chat lo vigila).

Hallazgos medidos: (1) el downloader de huggingface_hub cuelga en este
entorno aunque el CDN dé 32 MB/s — el checkpoint base se bajó con curl a
`.modelos/laya-multilingual` y `LAYA_MODEL` apunta ahí; (2) con path
local hay que setear `HF_HUB_OFFLINE` ANTES de `import laya`
(huggingface_hub lee las variables al importarse); (3) el fine-tune de
bmo (harness_choose) responde casi al azar (0.52/0.48) fuera de su
distribución — cada fine-tune sirve a SU pregunta; (4) la confianza útil
es `answer_confidence`, no `confidence`; (5) el lock de inferencia debe
ser RLock (preguntar → agente re-entra); (6) el generador de datos
escribe por combo y ~30% de los casos venían con etiqueta que no
ejemplificaban — la regla "the labeled answer must be the only
defensible one" en el prompt de la task + verify lo dejaron en 2,3%
(19/840); (7) los kernels de Kaggle montan los datasets en
`/kaggle/input/datasets/<owner>/<slug>`, no en `/kaggle/input/<slug>`:
resolver el base buscando `model.safetensors`, no por nombre.

Acá termina la evidencia heredada y empieza la propia. `sonda_laya.py`
(exp/7) convierte esas afirmaciones en números medidos con nuestra vara:
corre el test etiquetado de UN checkpoint a la vez, porque la RAM lo impone
(cargar dos en un mismo proceso revienta la memoria, medido), así que el
script carga, mide, escribe `salidas/evals/laya_evidencia_<nombre>.{md,json}`
y termina; no hay modo multi-checkpoint ni servidor. Es determinista a
propósito (sin LLM, sin red, sin DeepSeek): solo carga el checkpoint local
en CPU, infiere caso por caso y agrega métricas. La carga en frío se mide
aparte de la inferencia, porque la primera es costo fijo por proceso y la
segunda el costo variable que decide si Laya ahorra una llamada remota;
mezclarlas escondería cuál manda. Las métricas son funciones puras sobre
los casos: `tabla_confiabilidad` (acierto y confianza media por bucket de
answer_confidence), `curva_compuerta` (cobertura contra precisión por
umbral, con ahorro igual a cobertura) y `ece` (con `laya.ece_score` si su
firma lo permite, si no una implementación local de 10 bins, documentando
cuál se usó para que el número quede trazable). Puras justamente para poder
testearlas sin cargar el modelo.

Los contratos de los tests se importan, no se copian: los mismos
`PREGUNTA_ROUTER` y `PREGUNTA_VOTO` de nodes.py y `PREGUNTA_DESPACHO` de
supervisor.py que ya usan evals.py y las sondas, para que una copia local
no derive del contrato del fine-tune sin que ningún test lo note. El script
llama a `utils.laya.agente(setting)` con un setting propio (`SONDA_LAYA_CKPT`)
y así hereda `HF_HUB_OFFLINE` antes del import, el caché de errores y el
RLock. Un checkpoint por nombre: router, voto, supervisor y base (referencia).

### Laya: estado de la evidencia (exp/7, 2026-10-06)

| checkpoint | crudo | ECE | p50 CPU | carga fría | RSS pico |
|---|---|---|---|---|---|
| router_flow-1k | 27/30 | 0.066 | 190 ms | 9.7 s | 2.86 GiB |
| router_voto | 27/30 | 0.119 | 232 ms | 9.7 s | 2.86 GiB |
| supervisor_dispatch-1k | 14/24 | 0.209 | 500 ms | 10.1 s | 2.86 GiB |
| base multilingual | 16/30 | 0.300 | 203 ms | 9.9 s | 2.86 GiB |

- La sonda reproduce los artefactos previos: router 27/30 · ECE 0.066 =
  results.json del checkpoint y bench_router.json; supervisor 14/24 = r4;
  base 16/30 = results base. La cadena de evidencia cierra en CPU local.
- El "~0 s" heredado es en realidad ~0.2 s en CPU (supervisor ~0.5 s con
  18 opciones): órdenes de magnitud más barato que una llamada remota,
  pero ni gratis ni instantáneo.
- RSS por proceso 2.86 GiB (no los 615 MB del archivo): la ley "un
  checkpoint por proceso" ahora tiene número — dos procesos ya suman
  5.7 GiB.
- La compuerta 0.9 del supervisor es EXACTAMENTE la rodilla precisión=100%
  de la curva propia (8/24 locales, 8/8 correctos); debajo de 0.85 la
  precisión cae a 0.818. El umbral heredado de las leyes de bmo coincide
  con el punto óptimo medido.
- Router a 0.7: cobertura 0.90 / precisión 0.963; a 0.85: 0.833 / 1.000
  (mata el falso-directo "mundial", conf 0.831). La banda 0.7–0.85 es la
  sobrecargada (gap −0.32). La decisión de umbral es exp/8.
- Semántica verificada en el código del paquete: answer_confidence =
  max(p) post-temperatura (la calibrada); confidence = entropía
  normalizada (NO calibrada). Clamp de temperaturas [0.5, 5.0]: el router
  trae choice=0.5 exacto (el mínimo del clamp); el sesgo del clamp es
  conservador. Decisión: NO re-ajustar temperaturas con 54 casos.

### exp/8 — la compuerta del router, decidida por datos (2026-10-06)

La curva con semántica de producción (solo el lado "directo" se computa;
herramientas dudoso cae al lado seguro sin compuerta) y la medición del
ensamble completo (router_flow-1k + router_voto sobre las mismas 30
preguntas, `sonda_laya.py voto_en_router`) dieron el veredicto:

- **El veto CONFIRMA el falso-directo "mundial"**: responde "directo" con
  conf 0.78 (met) — las dos capas fallan juntas, el caso de eco que la
  Mesa 3 advertía como riesgo, ahora medido en un caso real del test.
- **Compuerta del router 0.7 → 0.85**: bloquea mundial ANTES de consultar
  al voto. En la banda 0.7–0.85 no hay ningún directo-correcto que lo
  pierda (t20-historia, 0.62, ya estaba bloqueado en todos los umbrales)
  — el kill es gratis. El ensamble pasa de 25/30 a 26/30 con los mismos 3
  arbitrajes.
- **El voto conserva su umbral propio** (LAYA_UNSURE_HIGH_VOTO=0.7): su
  curva da 96% de precisión con 83% de cobertura local a 0.7; heredar la
  subida del router le cortaría la cobertura a 53% sin ganar nada.
- El supervisor no se toca: 0.9 ya es exactamente la rodilla de su curva
  (exp/7).
- Caveat honesto: n=30. La curva es consistente con todo lo medido antes
  (mundial 0.83 documentado desde la curaduría), pero la banda 0.7–0.85
  tiene pocos casos; el round dirigido de "hechos actuales" del roadmap
  sigue siendo el refuerzo natural si aparecen más falsos-directos.
- Descubrimiento de activación: `_setting` lee en cascada nuestro .env y
  el de bmo (BMO_ENV) — bmo/.env trae LAYA_UNSURE_HIGH=0.7 heredado, que
  enmascara el default del código. La compuerta 0.85 se activa fijando
  LAYA_UNSURE_HIGH=0.85 en el .env del proyecto (documentado en
  .env.example).

### exp/9 — minería de errores: el triaje con Laya, descartado con el número a la vista (2026-10-06)

`minar_errores.py` minó las 108 trazas de `.runs/` (SIN torch, JSON puro;
reusa el parseo de evals). Límite honesto: la traza no guarda el texto del
error (solo tool + ok/error + segundos) — la causa es imposibilidad, no
omisión; lo medible es frecuencia, firma de duración y destino del
reintento.

- 43 errores de tools en 108 sesiones (18 sesiones con errores): frecuencia
  baja, ~0,4 por sesión.
- **Tasa de autocorrección 67,4%** (29/43): de los errores que la misma
  sesión reintentó (35), **33 terminaron bien (94%)** — el lazo
  error-como-feedback ES el triaje, y es gratis.
- edit_file concentra 27/43 (old_string que no matchea → el modelo corrige
  y reintenta, delta mediano 4 s); run_command 4/4 recuperados.
- Los 8 abandonos son mayormente timeouts de flujos largos (juez_lote,
  deep_research) donde el reintento no es decisión del modelo de todos modos.
- 4 timeouts con firma de duración ~100 s: si algo se automatiza, es un
  REINTENTO DETERMINISTA por firma (regla de código, no un modelo).

**Veredicto: el triaje con noul de Laya queda DESCARTADO por evidencia** —
a esta frecuencia y con esta autocorrección, una capa de decisión no agrega
valor; su costo (checkpoint, umbral, fallback) no se paga. Revisar si la
frecuencia de errores crece o si aparecen errores caros que el modelo no
puede autodiagnosticar.

### exp/11 — scope de aprobación por path en el banco (2026-10-06)

Riesgo operacional medido: en la sesión exp8-aplicar el harness propuso
editar el `.env` real fuera de spec y solo el timing lo frenó — el driver
del banco aprobaba TODO el HITL del turno sin mirar el objetivo.

El driver ahora parsea el objetivo de cada prompt HITL y responde con la
política solo si está dentro del alcance declarado por el escenario
(`permitir:` prefijos de rutas, `permitir_comandos:` prefijos de
comandos). Fuera de alcance → "n" automático + evento
`hitl-fuera-de-alcance` con el objetivo. Una DENYLIST DURA del conductor
aplica por encima de cualquier scope: `.env`, `.git/`, `memoria/`,
`git push`, `rm -rf` — jamás aprobables por el driver. Sin claves de
scope, todo está permitido salvo la denylist (compatibilidad).

Auto-prueba en vivo (escenario exp11-autoprueba): escribir un archivo
dentro del scope → aprobado y creado; intentar agregar un comentario a
`.env` vía edit_file → el driver rechazó solo (evento con motivo
"denylist"), el modelo reportó el rechazo como dato, y el hash del
`.env` quedó intacto. 3/3 turnos OK.

### exp/4 — presupuesto visible + protocolo de continuación (2026-10-06)

Medición que cambió el diagnóstico: el problema nunca fue "llamadas por
ronda" (87% de las rondas tiene 1-2; el outlier de 17 read_file fue UNA
ronda) sino RONDAS para la clase editar→probar→editar — 42 preguntas
históricas sobre 8 (máx. 242) y tres sesiones de aplicación muertas por
el corte. Y el hallazgo de diseño: el modelo NO veía su presupuesto (el
⚙ iba a la terminal, nunca a la conversación).

- `nota_presupuesto`: en la anteúltima ronda, la nota viaja en el
  resultado de la última tool ("la próxima es tu ÚLTIMA con tools...
  cerrá el estado y pedí continuación — un mensaje nuevo reinicia el
  presupuesto"). El reset ya existía (cada mensaje nuevo pone
  tool_rounds en 0): lo que faltaba era el aviso.
- El default 8 queda: mediana 2 rondas/pregunta; 19 min colgados en una
  pregunta es mala UX de chat — la solución es el aviso + la mano amiga,
  no un tope enorme.
- `env:` por escenario en el banco: las sesiones de aplicación pesadas
  corren con MAX_TOOL_ROUNDS=40 (así se aplicó exp/11).

Demostración (exp4-protocolo, tope 2, tarea de 3 rondas dependientes):
protocolo verificado — el presupuesto se reinicia con el mensaje nuevo.
Y UN HALLAZGO: al retirarse las tools, el modelo emitió el write_file
como TEXTO DSML y la recuperación lo ejecutó igual (recuperacion×1) —
la recuperación DSML by-pasea el presupuesto de tools: la ley L8 no es
tope duro por ese camino. Benigno acá (la tarea se completó), pero es
una interacción conocida: candidato a fix — que la recuperación
respete el retiro de tools o consuma ronda.

Las corridas de control (exp4-bajo/amplio, presupuesto 4 vs 40 con la
misma tarea) no muestran daño en defaults: 2 rondas, sin nota, sin
diferencia.

### exp/10 — edit_file con feedback rico (2026-10-06)

edit_file generaba el 63% de los errores del harness (27/43, minería
exp/9) con un feedback ciego: "old_string no aparece... releé el
archivo" — el modelo relee entero y reintenta a ciegas.

El error ahora diagnostica: (a) si el texto matchea normalizado
whitespace (tabs→4, sin trailing), NOTA explícita de indentación — la
causa clásica, incluso para old_strings de una línea; (b) top-3 de
candidatos con número de línea (difflib sobre el texto unido — sobre
listas de líneas compararía líneas enteras y toda casi-igual daría
ratio 0); (c) en ocurrencias múltiples, las líneas exactas para apuntar
con contexto.

Medición (exp10-reintento, indentación tab-vs-espacios): 2 intentos de
edit, CERO relecturas del archivo, diff correcto aprobado y verificado
— el reintento único hipotetizado. minar_errores queda como línea de
base (27 errores) para vigilar la tasa a futuro.

Primera corroboración de campo (2026-10-06, corte en el merge de exp/10):
pre-fix 116 llamadas / 11 errores (9%); post-fix 25 llamadas / 0 (0%).
Direccional — muestra chica y sesiones más simples que las de código;
el heartbeat acumulará la serie.

### exp/13 — router_prefiltro: el checkpoint del pre-filtro de contexto (2026-10-06)

La infra era no-op desde la Mesa 6 (contexto.py + settings); faltaba el
checkpoint. Fine-tune con la receta de router_voto en bmo (task yaml con
el estado de DOS campos consulta+bloque como producción, contrato
congelado por sha1):

- Datos: 1033 generados → juez ciego 530 verificados (51%) con top-up
  dirigido de la clase "no" (balance final 299/231). **Filtro anti-fuga
  aplicado** (lección de router_voto r2, donde el test entrenó dentro de
  los verificados): 0 ids del test en el entrenamiento.
- Sesgo juez=generador acotado por primera vez: releabel manual del
  conductor sobre 30 casos → acuerdo 77% (7 corregidos: trampas bien
  construidas mal etiquetadas — tema compartido, dato ausente, fecha
  equivocada). Informe en bmo/data/router_prefiltro_relabel_informe.md.
- Resultados (results.json del kernel T4x2, minutos): test 15/28 →
  **22/28** (54% → 79%), ECE 0.326 → **0.091**; banda confiable NO vacía
  (13 casos en [0.5,0.7) con 69% — la lección de voto r1 no se repite).
- **El A/B que reemplaza el claim externo "~80%"** (biblioteca de 18
  notas, max 2): poda 18→2 archivos por consulta (89%), el modelo hizo
  menos búsquedas (3 vs 6 del control) y trabajó desde lo podado; costo
  ~7 s por consulta de inferencia local (0 API). El ahorro real es de
  CONTEXTO (2 bloques vs 18 entran al prompt), no de reloj.

### exp/14 — el ranking del pre-filtro, en lote (2026-10-06)

`_puntuar` llamaba a Laya una vez por bloque (secuencial: ~1.2 s/bloque
medido con bloques largos reales). `preguntar_lote` (Agent.predict_batch,
forward compartido) lo baja a UNA llamada: micro-benchmark — secuencial
1211 ms/bloque vs lote 421 ms/bloque (~2.9×), y el camino completo
`elegir_por_laya` medido WARM: 377 ms/bloque (3.2×), decisiones idénticas
14/14 en el solapamiento. La carga en frío (~11 s) sigue siendo costo
fijo por proceso. El turno del banco NO es instrumento acá (la latencia
de DeepSeek domina con ±50% de ruido; en una corrida el modelo ni
siquiera hizo búsquedas anchas). La ley de degradación no cambia:
cualquier fallo del lote → default seguro (entran todos).

### exp/15 — pre-rank de tools: descartado por el KV-cache (2026-10-06)

La idea del brainstorm: 27 esquemas viajan en cada ronda de tools; Laya
elegiría la familia y DeepSeek vería un top-k. La sonda
`banco/probes/cache_tools.py` (API real) lo mató antes de construirlo:
los esquemas viven en el PREFIJO CACHEADO — llamada idéntica 4096/4311
tokens cacheados (miss 215 ≈ el propio mensaje del usuario), y un subset
variado en orden canónico pegó miss 161. Ahorrar tokens que cuestan
~nada a cambio de (a) arriesgar sacar la tool correcta del action space
y (b) bustear el cache si el orden varía: pérdida neta. Segundo descarte
por evidencia (con el triaje de exp/9): la sonda queda como artefacto
re-ejecutable.

### exp/16 — triaje de trazas para la auditoría nocturna (2026-10-06)

La pregunta: auditar TODAS las trazas cuesta N llamadas LLM que crece
sin techo (177 hoy). El triaje DETERMINISTA (invariantes del linter +
outliers de duración >120 s) selecciona **37/139 legibles → 73.4% de
ahorro** de la auditoría nocturna — sin checkpoint nuevo: tercera
decisión por evidencia donde Laya no corresponde (con el triaje de
errores y el pre-rank de tools). Límite honesto en el informe: el triaje
ve lo estructural; lo semántico (decisión mala sin violación) requiere
lectura LLM. `triaje_trazas.py` standalone; la integración como tarea
del heartbeat queda para cuando se quiera cablear.

Nota de proceso: la sesión del harness que lo aplicó agotó presupuesto y
emitió el segundo edit como texto DSML — y el fix de exp/12 lo IGNORÓ en
producción por primera vez (antes by-paseaba el tope): la ley sostuvo
mientras el triaje se estaba construyendo. El test a medias que dejó se
completó con la intención del edit ignorado (aserción en mixed-case
contra un haystack con .upper()).

### exp/17 — el triaje, cableado al heartbeat (2026-10-06)

El heartbeat acepta `"tipo"` en sus tareas: default = supervisor
reactivo (LLM, la noche es finita); `"tipo": "triaje"` = el script
determinista directo, **cero llamadas LLM**. Verificación en vivo con
config de una sola tarea: ✅ 0.1 s (los supervisores tardan minutos),
informe `salidas/heartbeat/triaje_trazas_<fecha>.md` escrito y logueada.
38/140 seleccionadas en la corrida real (72.9% de ahorro) — la auditoría
profunda queda disponible para la selección cuando haga falta.

### exp/19 — auditoría dirigida de modules/ y hallazgos (2026-10-06)

El harness auditó los 16 módulos dirigido por scenario (scope, inventario
y método regalados; MAX_TOOL_ROUNDS=40). Dos corridas — la primera enseñó
el hallazgo metodológico: con 19 lecturas (~130 KB) la COMPACCIÓN se
comió los módulos de las primeras tandas (informe final: 9/16); el
método corregido anota hallazgos POR TANDA antes de avanzar (inmune a la
compacción: cero en la segunda corrida, 6 rondas). La sospecha de
websearch (TOOLS `search_web` vs función `run_search_web`) se
AUTO-VERIFICÓ contra el mecanismo de despacho y se declaró "falsa alarma
mía" — la calibración de confianza del auditor mejoró de 0/2 (auditoría
1) a hallazgos verificados.

Veredicto: 6 hallazgos (1 alto, 1 medio, 4 cosméticos), los dos
sustantivos CONFIRMADOS y corregidos:
- ALTO `modules/vision.py`: la descripción de `ver_pdf` decía "vía la
  Files API" — falso desde el fix de poppler (la Files API rechaza PDFs,
  HTTP 400). El modelo leía esa mentira en cada llamada. Descripción y
  comentario de PDF_MAX_BYTES corregidos (la IMPL ya documentaba bien).
- MEDIO `modules/auditoria.py`: el default de `salida` del tool era
  `auditoria.md` mientras descripción y CLI prometen `salidas/auditoria.md`
  — alineado. (Los 4 cosméticos: naming de websearch, `rondas=None` vs
  "default 2" efectivo, comentario de PDF_MAX_BYTES, tope de páginas no
  declarado — quedan como están, documentados acá.)

- Kaggle, dos lecciones de operación: el CLI de datasets subió solo los
  archivos de primer nivel (la v1/v2 del kernel falló por eso — subida
  plana y versión nueva lo arreglaron) y el notebook copiado hereda
  referencias por nombre que hay que renombrar TODAS (contexts_router
  sobrevivió al primer reemplazo).

### exp/12 — el bypass DSML del presupuesto, cerrado (2026-10-06)

Hallazgo de exp/4: al retirarse las tools por el tope, el modelo emitía
la llamada como TEXTO DSML y la recuperación la ejecutaba igual — la ley
"todo bucle tiene presupuesto" no era tope duro por el canal de texto.

`dsml_con_presupuesto_agotado`: con tools ofrecidas, la recuperación de
siempre; con tools retiradas, el markup se corta (lo previo sobrevive) y
si no queda nada, el contenido pasa a ser el mensaje honesto "(sin
texto: emitiste tool-calls con el presupuesto agotado — decí 'seguí'
para reiniciarlo)". Terminal: "[DSML] tool calls como texto: IGNORADOS".

Re-medición del escenario que by-paseaba (exp4-protocolo, tope 2):
antes — el write_file corría tras el retiro (recuperacion×1); ahora —
dsml_ignorado×1, cero ejecución en el turno 1, y el turno de
continuación completa con su HITL. La ley vuelve a sostenerse.

### exp/3 — el hook de sintaxis, visible (2026-10-06)

Asimetría medida en el test exhaustivo: el veto imprime en terminal pero
el `⚠ SINTAXIS` del hook py_compile viajaba solo al modelo — el usuario
no veía que el hook actuó. Ahora el hook imprime `[hook] ⚠ SINTAXIS
devuelta al modelo: <última línea del detalle>` (coloreado, flush como
los demás avisos). El flujo del modelo no cambia: la observabilidad
completa sin tocar el contrato.

### exp/5 — search_files con conteo exacto (2026-10-06)

Patología medida (test exhaustivo): el conteo de ".py" quedaba "50+" y
el modelo no sabía cuántos eran; su find para cerrar el número cayó en
preguntar (hasta exp/1). Ahora el conteo EXACTO se calcula antes de
truncar la muestra: "N archivos coinciden" con N real, y al cortar el
tope agrega "... y M más (mostrando 50 de TOT; para el listado completo:
run_command 'find ...' ya es solo-lectura auto)" — la sugerencia apunta
al camino que exp/1 volvió automático.

### exp/2 — evals como tool del chat (2026-10-06)

Medido en el test exhaustivo: el modelo QUISO correr evals en vivo, no
existía la tool, su run_command fue rechazado y degradó a leer la
corrida del día anterior del disco. La spec pedía dos tools (rápida +
pesada); el harness prefirió UNA `evals` estilo run_informe (informe a
disco + ruta) — consistente con el patrón del código, y la revisión del
conductor aceptó el diseño con UNA corrección de fondo: `generar` ganó
`actualizar_baseline` (default True = CLI intacto) y la tool pasa False
— el ancla de medición no se pisa desde una conversación.

Medición (exp2-medicion): tool nativa usada (cero run_command), informe
leído y resumido en 25 s, y el baseline verificado INTACTO tras la
corrida (filecmp).

### exp/35 — la política del router, separada de la clasificación (2026-10-08)

El informe externo señaló lo que faltaba: una decisión probabilística no debe
mezclarse con la política que la aplica. Ahora Laya **estima** (opción +
probabilidades) y Python **decide** (qué ruta se ejecuta), en
`utils/laya_routing.py`:

- `decide(respuesta, config)` es **pura**: sin probabilidades usables, con
  etiqueta fuera de contrato, NaN/infinito, `bool`, texto o suma distinta de 1
  → **abstención** (herramientas). Nunca "directo" por defecto. Se EXIGEN las
  dos probabilidades: `answer_confidence` es max(p) y `confidence` es entropía
  normalizada — el wrapper viejo las mezclaba en cascada.
- Con calibración, la ruta directa exige que el **conjunto conformal colapse**
  con las probabilidades reales de cada etiqueta (exp/30/31); sin calibración,
  el umbral fijo de siempre.
- `LAYA_MODO`: `off` (no ejecuta Laya), `shadow` (registra la propuesta y
  **conserva herramientas**: mide sin cambiar la conducta y sin gastar el voto
  de DeepSeek) y `enforce` (default: aplica la propuesta). El modo sombra es la
  forma de juntar evidencia antes de apretar nada.
- Cada decisión deja una línea en `salidas/routing.jsonl` (propuesta, ruta
  aplicada, causa, p(directo), q, umbral, versión de laya). El trace no la
  tenía: registraba el nodo y la acción, no el porqué.
- `LayaRouter.exec` absorbe la guarda de exp/25 (una excepción de inferencia se
  lee como abstención) y `preguntar_detalle` conserva la respuesta completa.
- **Los dos registros se unen**: con `LAYA_LOG_PREGUNTA=1` el evento de routing
  agrega los primeros 200 caracteres de la pregunta (default 0: no guarda texto
  del usuario), así que una corrida en modo sombra deja el set completo
  (pregunta + propuesta + p(directo) + ruta aplicada) y
  `banco/probes/etiquetar_router.py --extra salidas/routing.jsonl` lo etiqueta
  para elegir alpha. Ese es el circuito para pasar de `shadow` a `enforce` con
  evidencia propia.

Costo: 0 llamadas nuevas (el modo sombra ahorra el voto); tests puros de la
política en `tests/test_laya_routing.py` (sin modelo ni red).

### exp/40 — drift de spec hallado al corroborar con fuentes oficiales (2026-10-13)

Corroboración completa de la evidencia del harness contra las fuentes
oficiales (docs de DeepSeek, spec de A2A, repo de PocketFlow, el paper de
Conformal Cascade). La mayoría confirmada al detalle (vision: imágenes
solo en user con 400 medido y documentado, límites 32/48 MiB, magic
bytes, 1024 tokens/imagen, PDFs fuera de la Files API; PocketFlow 100
líneas cero deps; el paper de conformal fiel a lo citado). Dos drifts
encontrados y cerrados:

- **A2A habla el wire format viejo**: la spec actual sirve el agent card
  en `/.well-known/agent-card.json` (el módulo usaba el legado
  `agent.json`) y exige `messageId` en el message. Fix: el cliente prueba
  el path nuevo primero y cae al legado SOLO ante 404 (un agente caído no
  merece segundo intento: doblaría el timeout de detección); el payload
  suma `messageId` (UUID) — los servers viejos lo ignoran como campo
  extra. Los `parts` siguen con `type` (legado): la spec actual usa oneOf
  sin discriminador, pero un campo extra es más seguro de tolerar que un
  part sin `type` para un server viejo. Tests: card solo-nuevo,
  solo-legado (fallback) y messageId presente.
- **La anotación A1 describía el síntoma, no la regla**: los docs
  oficiales documentan que tools+thinking SÍ son compatibles; la regla
  real es que, con `tools` en el request, el `reasoning_content` debe
  devolverse COMPLETO en todas las requests subsecuentes. Los tres
  crashes históricos eran esa regla rompiéndose (razonamiento ausente +
  tráfico agéntico tras el flip de modo) — consistente con la sonda de
  exp/38, donde el flip SOLO ya no reproducía el 400. El modo pegajoso NO
  cambia (decisión: este cliente descarta el reasoning; preservarlo
  habilitaría thinking en las rondas de tools al costo de reenviarlo en
  cada vuelta — candidato a exp futuro si el costo duele). Solo se
  corrigen las anotaciones (call_llm.py y esta doc) para que el contrato
  documentado sea el real.

## exp/41 — replay de trazas: la Mesa 1 cierra su pendiente original (2026-10-13)

`replay.py` (`python3 main.py replay`): las caminatas REALES de `.runs/`
validadas contra los grafos VIVOS del código actual. La pregunta de la
Mesa 1 desde el origen — cuando el código cambia, ¿el harness de hoy
todavía ejecuta lo que ejecutó en producción? — respondida con evidencia
de disco, no con la lista congelada del linter (que admite historia por
diseño y por eso no puede detectar drift).

**Límite honesto** (arriba en cada informe): la traza guarda la caminata
(nodo/acción/duración), no el contenido. Este replay detecta regresión
ESTRUCTURAL; la semántica (misma caminata, peor respuesta) es de los
benches con contenido. Instrumento de señal, no gate.

Cuatro niveles, funciones puras testeables sin disco:

- **A — emisibilidad**: cada (nodo, accion) histórico tiene que ser
  emisible por el código de HOY (clase viva + acción cableada). Es el
  guard de calles muertas (exp/39) generalizado a caminatas reales.
  Incluye la recursión DENTRO de los Flow/BatchFlow anidados: el flujo
  interno de auditoría (CarpetaScan/Seccion) vive en `start_node`, no en
  successors — sin recursión quedaba "desconocido" (16 falsos medidos);
  el propio guard de exp/39 tiene ese punto ciego.
- **B — adyacencia del chat**: los runs de nodos del CHAT tienen que
  seguir siendo aristas del chat actual (unión ±router). La primera
  corrida marcó 246 "rotas" — todas falsas, y el por qué es un hallazgo
  del propio instrumento: el chat despacha supervisor/debate/juez por
  tools y SUS eventos quedan en el mismo archivo (corridas de otros
  grafos intercaladas en la traza del chat). El nivel juzga solo los runs
  de nodos del chat; el resto es de nivel A.
- **C — registro de tools**: eventos de tool contra el action space VIVO
  (importado de nodes, no lista de mantenimiento).
- **D — política del router sobre tráfico real**: las decisiones de
  `salidas/routing.jsonl` (exp/35) re-evaluadas con la compuerta de HOY
  (umbral/q de config_router): apretó (un directo aprobado que hoy no
  pasaría) o aflojó (uno bloqueado que hoy pasaría). n=13 hoy; crece solo
  con el tráfico.

**Primera corrida (214 trazas, 8.827 eventos, 139 del chat)**: A=0,
A′=0, B=0, D=0, C=2 — los dos `grep` con error son artefactos de tests
del 6/10 (0.0 s). Baseline fijado (`salidas/evals/replay_baseline.json`,
patrón evals: comparar sin pisar; `--actualizar-baseline` guarda). 16
tests nuevos. El pendiente restante de la Mesa 1 (bench de decisiones
del voto como dataset permanente) sigue abierto.

## exp/42 — el residual de la trampa-delete-file, cerrado POR el harness (2026-10-13)

Primera pieza del harness aplicada por el propio harness (conductor GLM
dirigiendo por banco, 5 sesiones reales con DeepSeek). El residual:
`trampa-delete-file` (hallazgo 2 de exp/20) fallaba 3/3 — el Draft
alucinaba la tool inexistente y el Judge no podía notarlo porque nunca
vio el inventario real.

**El mecanismo** (diseño del harness, fiel a los patrones de la casa):
`_tools_alucinadas(draft, inventario)` contrasta los nombres que el
borrador menciona COMO herramienta contra el action space real
(`_inventario_tools()`, import perezoso de nodes — el ciclo de
modules/juez.py lo prohíbe a nivel de módulo). El inventario lo aporta
el CÓDIGO en `Judge.exec` (la tupla prep→exec quedó en sus 4 campos:
los tests existentes son candados y no se reescriben para acomodar un
detalle interno); la `_compuerta` existente se extendió — verdict ok +
tool inventada → retry, el mismo patrón que la cita rota.

**El ciclo medir→corregir→remedir, con el bench como vara:**
- Corrida 1: la trampa PASA (117 s: el gate fuerza el retry y el borrador
  converge a "no existe"), pero el bench marca REGRESIÓN (76,5% vs
  94,1%) — dos clases de FALSO POSITIVO medidas: segmentos de ruta
  (`fs_tools` extraído de `utils/fs_tools.py`) y funciones internas
  mencionadas como "la función X" (`call_llm_agent`, `reasoning_content`)
  porque el contexto incluía "función".
- Sesión 4 (feedback medido al harness): el contexto perdió "función", y
  las rutas/citas (`[\w./-]+\.[\w]{2,4}`) se quitan de la línea ANTES de
  matchear candidatos. Candados de regresión con los DOS casos medidos.
- Corrida 2: la trampa sigue pasando y MÁS RÁPIDA (63,6 s);
  memoria-slug y trampa-pdf-filesapi (degradados por el gate) se
  recuperan; el detector queda limpio sobre los borradores que fallan.

**Lo que NO es del fix (hallazgos nuevos, medidos):**
1. **Drift del modelo**: deepseek-flash hoy REHÚSA responder fuera del
   contexto verificado ("solo líneas 1–200 de 548; no voy a inventar") —
   compaction-chars, search-vacio y sanitizar-markers fallan por la
   ventana de 200 líneas que arma `Draft.prep` (read_file limit=200), no
   por el gate (borradores limpios). Candidato a exp: ventana más ancha
   o paginación a pedido del Draft.
2. **El caso thinking-tools envejeció con exp/40**: exigía el token
   "rechaza" que la corrección de la anotación A1 reescribió; el
   borrador citaba las líneas nuevas y explicaba la regla real. El caso
   se actualizó al ground truth vigente (["thinking",
   "reasoning_content"]).
3. Residual conocido del detector: "tool" como subcadena auto-activa el
   contexto ("tool_calls" se flaggea a sí mismo al mencionarse) — solo
   visible en borradores que discuten el tema tools; documentado, sin
   acción.

**Desempeño del harness como aplicador** (5 sesiones, 336 eventos,
~1.092 s de reloj de nodos, 120 llamadas a tools, **0 errores de tools**):
diseñó con los patrones de la casa sin que se los diera; dejó NOTA DE
MEMORIA al frenarse por presupuesto y las sesiones siguientes ARRANCARON
con memory_search (la biblioteca como handoff, funcionando tal como fue
diseñada); autodiagnosticó su propio test mal escrito ("llamador" dispara
el verbo de contexto). Dos fricciones medidas del LADO del conductor: el
tope de HITL por turno (6→12→20: dos sesiones clippeadas) y que cuando
disiente del conductor DEBATE en vez de aplicar (sesión 2: contrapropuso
reescribir los tests, que era lo que el conductor había vetado).

316 tests verdes + ruff limpio (verificado por el conductor, no por
auto-reporte). Escenarios de las 5 sesiones en `banco/escenarios/exp42-aplicar*.yaml`.

## exp/43 — la etiqueta ambiental del router: la flywheel (2026-10-13)

La revisión del harness contra el ecosistema 2026 (System One/Jev, el paper
de agentic routing) destapó la asimetría: el router produce "herramientas" en
el 100% del tráfico registrado y la calibración existente (85 casos) era todo
banco, todo "herramientas" — la clase "directo" no tenía datos propios. El
mismo hallazgo lo hizo el propio harness en la sesión 3 de aplicación (midió
44 decisiones, todas inválidas o herramientas). La pieza que faltaba no era
otro round de fine-tune: era la ETIQUETA.

**La insight**: en modo shadow la ruta aplicada es SIEMPRE herramientas, así
que DeepSeek corre con tools — y si responde SIN llamar ninguna, la pregunta
era "directo" EN LA PRÁCTICA. Esa es la etiqueta ambiental: gratis, en la
distribución exacta de producción, y crece sola con el uso. Es además la
definición OPERATIVA del objetivo del router (predecir si el bucle de tools
va a arrancar), no una opinión de oráculo. Límite honesto (declarado en el
código): mide lo que DeepSeek HIZO, no lo que la pregunta NECESITABA — un
modelo que responde de memoria una pregunta de archivos etiqueta "directo";
ruido que el volumen compensa.

**La mecánica** (4 sesiones del banco, conductor GLM): cada decisión con
probabilidades gana un `id` (`uuid4().hex[:8]`, dentro del evento de
`registrar_decision`); en shadow con `p_directo` utilizable,
`LayaRouter.post` deja `shared["_router_pendiente"]`; `AgentStep.post` al
devolver "answer" lo consume y registra la línea `{"evento": "resultado",
"id", "uso_tools", "rondas"}` en el MISMO routing log (enforce no etiqueta:
directo retira las tools y mediría la política; `GetQuestion.post` limpia
huérfanos; bookkeeping que nunca corta el chat). Terminal:
`[router] etiqueta ambiental: directo (0 rondas)` — marcador contable por el
banco. `banco/probes/etiquetar_ambiental.py` (código puro, join PURO
testeable) une decisión↔resultado por id y emite el JSONL de calibración
{conf, correcto} drop-in para `utils/conformal` — con `LAYA_LOG_PREGUNTA=1`
la fila lleva la pregunta.

**Verificado en vivo** (escenario exp43-demo, shadow, log propio): "¿cuántos
.py en utils/?" → Laya herramientas 0.0016 → 1 ronda → etiqueta herramientas
(Laya correcta, conf 0.998); "¿por qué el cielo es azul?" → Laya directo
0.998 → 0 rondas → etiqueta directo (correcta, conf 0.998). Las DOS clases
ocurren naturalmente con preguntas reales — la flywheel ya no depende del
sesgo del banco. El etiquetador emitió ambas filas sin una llamada LLM.

**El .env quedó en `LAYA_MODO=shadow` + `LAYA_LOG_PREGUNTA=1`**: el tráfico
real acumula etiquetas desde ahora. El circuito de vuelta a enforce: muestra
suficiente + balance de clases → `etiquetar_ambiental.py` → calibración →
`LAYA_CALIBRACION_ROUTER` + alpha elegido de la curva propia.

**Fricciones medidas del aplicador (4 sesiones, la saga completa en
`banco/escenarios/exp43-*.yaml`)**: (1) el tope HITL por turno volvió a
clippear una sesión (6 aprobadas, 2 rechazadas — receta conocida de exp/42:
max_hitl 20); (2) una sesión DISINTIÓ de la spec y construyó en cambio la
compuerta conformal del VOTO (`config_voto`/`decide_voto`,
`banco/probes/calibrar_voto.py`, `tests/test_voto_router.py`) — trabajo
verde, neutro por defecto (umbral 0.7 sin calibración) y coherente con la
dirección de la casa, así que QUEDA como subproducto documentado, no pedido;
(3) una sesión perdió la acción puntual por la COMPACTACIÓN (prompt largo +
5 compactaciones → el modelo investigó bien pero no editó) — la lección
operativa: specs largas VAN A DISCO y el prompt del turno queda en una
línea; (4) la cuarta sesión, con spec mecánica en disco (código literal,
precedente exp/12) y prompt corto, cerró completo. 316 → **333 tests** +
ruff limpio, verificados por el conductor en cada corte.

**La caza dirigida (exp43-caza, patrón exp/19 con hitl n — solo lee)**: el
harness auditó su propio diff nuevo con zonas de caza regaloneadas (DSML,
huérfanos, gates, unir límite, marcadores). Resultado: 2 bugs VERIFICADOS y
cerrados en sesión exp43-fix (spec `banco/specs/exp43_fix_caza.md`), 1
hallazgo refutado con honestidad (el archivo mezclado viejo/nuevo se maneja
bien — traza pública en el transcript):

- **H1 (medio)**: con `LAYA_LOG_DECISIONES=0` el pendiente se seteaba igual
  y el print corría — el banco contaba `etiqueta_ambiental×1` sin ninguna
  línea escrita (el patrón del Fix 10: medir el print, no el registro). Fix:
  el gate entra en la condición del pendiente; candado
  `test_shadow_con_log_apagado_no_deja_pendiente_ni_escribe`.
- **H2 (medio)**: el marcador matcheaba prosa ecoada — el literal vive en el
  f-string de nodes.py que las auditorías mandan leer. Fix: el patrón exige
  la forma real con dígitos `(directo|herramientas) \(\d+ rondas\)` (el
  template `{etiqueta}`/`{rondas}` no matchea) + fixture negativo en
  test_banco (lección Fix 10 aplicada de entrada esta vez).

Regresión final: demo re-corrida post-fix — 2/2 pares decisión↔resultado y
marcador exacto 1/turno. **334 tests** + ruff limpio. De paso, la caza misma
dejó 2 pares etiquetados en `salidas/routing.jsonl`: cada sesión del banco
es ahora tráfico calibrable.

## exp/44 — el juez de riesgo de acciones, en observación (2026-10-13)

El uso nº1 de la familia Jev/Laya en la wild (LangChain AutoMode): juzgar
cada ACCIÓN antes de ejecutarla. Este harness ya tenía las reglas duras
(`policy.py` auto/preguntar/confirmar_doble + denylist) — el hueco semántico
era la banda que decide SOLO un humano. exp/44 la instrumenta **sin cambiar
ninguna conducta**: en las bandas humanas (preguntar/confirmar_doble),
`run_command` consulta a Laya tres preguntas de UNA dimensión cada una
(`modifica_estado`, `danio_irreversible`, `requiere_revision` — contrato
`utils/riesgo.py`, congelado por sha1) sobre el estado `(comando, último
mensaje del usuario)` — evidencia de intención, nunca el razonamiento del
propio agente (lección del manual de Jev: se auto-aprueba) — imprime
`[riesgo] observa:` y al conocerse el s/n registra
`{"comando", "mensaje", "juicios", "aprobado"}` en `salidas/riesgo.jsonl`.
La respuesta del humano ES la etiqueta (misma jugada ambiental que exp/43).
Sin `LAYA_MODEL_RIESGO` todo es no-op. `utils/estado_sesion.py` es el
plumbing del último mensaje (lo siembra `GetQuestion.post`).

**Primera observación en vivo** (exp44-observa, checkpoint BASE sin
fine-tune): 3 comandos juzgados + etiquetados. Lecciones: el base es débil
— dijo "no requiere revisión" (0.58) para un `pip install` que el humano
RECHAZÓ, y "modifica estado" para un `python3 -c print(40+2)`; y `mkdir`
bien juzgado. La dirección es clara: el pipeline funciona, el checkpoint
necesita el fine-tune cuando el log acumule (los pares ya caen solos con el
uso del chat y del banco). Nota: el `rm -rf` del escenario nunca llegó al
gate — deepseek-flash se negó solo a ejecutarlo y ofreció alternativa
segura.

## El bench del supervisor — el veredicto medido (2026-10-13)

`banco/bench_supervisor.py` (grading dinámico en código puro: la verdad se
calcula al momento, 6 tareas reales): el supervisor reactivo (Laya elige +
mayoría 2-de-3 + args por DeepSeek) contra un agente DeepSeek PLANO con
tool-calling nativo sobre el MISMO action space y presupuesto:

| vía | calidad | llamadas remotas | reloj |
|---|---|---|---|
| supervisor | 6/6 | **65** | 358 s |
| agente plano | 6/6 | **14** | 26 s |

**4,6× llamadas y 14× tiempo por CERO ganancia de calidad** en esta clase de
tareas de búsqueda/lectura. El veredicto del bench: el despacho se
simplifica — el valor del supervisor nunca estuvo en el Choose, está en los
vetos/self-healing/presupuesto (código, no Laya). El ítem del roadmap
"Choose a escala (~2.400 casos)" queda DESCARTADO por evidencia: no hay
brecha de calidad que cerrar comprimiendo llamadas del despacho. Límite
honesto: n=6, tareas homogéneas de lookup; tareas reactivas multi-paso más
complejas podrían favorecer al bucle reactivo — si se conserva, que sea por
esa clase de trabajo, no por ahorro. Dos bugs del propio instrumento
medidos y cerrados por el conductor: el contador no veía las llamadas del
supervisor (binding: `from utils.call_llm import call_llm` directo — se
envuelve también la referencia del módulo supervisor; primera corrida
reportó 0 llamadas, imposible) y `cargar_tareas` recibía lista donde esperaba
ruta.

## exp/46 — la regla temporal: el "mundial" cerrado por regla dura (2026-10-13)

El falso-directo resistente ("¿quién ganó el último mundial?", conf 0.83
que pasa la compuerta) era un límite de FAMILIA, no de entrenamiento: estos
modelos no juzgan fechas ni recencia (manual de Jev: "no dates — extract
parts in code"). Rounds dirigidos no lo curan. La salida del runbook (regla
dura ANTES que modelo): `regla_temporal(pregunta)` en
`utils/laya_routing.py` — regex generosa (último/actual/hoy/2026/latest,
es/en, con y sin tilde; falso-herramientas es barato: el modelo con tools
responde directo si puede). En **enforce** corta antes de llamar a Laya
(centinela `regla:temporal`, decisión registrada con su causa, sin gasto);
en **shadow** NO corta — Laya corre igual para que la flywheel junte las
etiquetas de exactamente esta clase y valide la regla contra realidad.
Candados: 4 grupos de tests (la sesión cableó pero no los escribió; los
escribió el conductor — el reporte de sesión decía otra cosa, verificación
de conductor no opcional).

## Fix: el caché de errores de Laya vence (2026-10-13)

Medido en la revisión: 31/37 decisiones de producción salieron "sin detalle
de Laya" y el fallo de carga quedaba cacheado PARA SIEMPRE en el proceso —
un OOM transitorio degradaba la sesión entera sin reintento. Ahora
`_errores` guarda `(ts, msg)` y el error VENCE: pasado
`LAYA_ERROR_COOLDOWN` (default 60 s) se reintenta la carga; el acierto
limpia el residual; dentro del cooldown el raise cacheado es rápido (un
checkpoint roto permanente cuesta un reintento por minuto, aceptable). La
ley de degradación no cambia. Tests con módulo laya falso
(`tests/test_laya_cache_reintento.py`).

**Estado del turn (verificación final del conductor): 350 tests + ruff
limpio.** La sesión exp46-aplicar también dejó una lección operativa: corrió
con `USE_LAYA_ROUTER=0` y `LAYA_MODEL_RIESGO=""` por escenario — las
sesiones de ESCRITURA no cargan checkpoints (2×2.86 GiB de RAM que no
aportan); la primera corrida sin eso saturó la RAM de la máquina y mató el
banco.

## Supervisor v2 — el despacho simplificado, el bench aplicado (2026-10-13)

Decisión del dueño tras el veredicto del bench. El bucle reactivo queda; el
Choose se jubila. **Un paso = UNA llamada** que elige herramienta Y args
juntos (`call_llm_agent` con tool-calling nativo sobre `_TODAS`), y las
leyes L8 viven como GUARDAS PURAS del ejecutor (`guarda_vetada`,
`guarda_repetida` — cache de idénticas, veto sin-args, veto tras dos
fallos; testeables sin LLM). El historial VIAJA COMPLETO entre pasos (fin
de los hechos recortados a 160 chars: el modelo ve los resultados reales —
la ganancia medida del agente plano). `Sintetizar` y la sección "Pasos" del
informe se conservan; anti-recursión (L1) intacta; `supervisar`/`REGISTRO`/
`_TODAS`/`create_supervisor_flow` intactos para heartbeat, módulo y bench.
`PREGUNTA_DESPACHO` y `elegir_con_deepseek` se mudaron a
`sonda_supervisor.py` (el checkpoint jubilado se sigue midiendo como
evidencia, por args). `LAYA_MODEL_SUPERVISOR` comentado en `.env` — **los
procesos del supervisor y del heartbeat dejan de cargar 2.86 GiB**.

**Bench post-v2 (mismas 6 tareas, grading dinámico):**

| vía | calidad | llamadas | reloj |
|---|---|---|---|
| supervisor v1 (Laya+mayoría+args) | 6/6 | 65 | 358 s |
| **supervisor v2** | 6/6 | **20** | **50 s** |
| agente plano | 6/6 | 14 | 23 s |

**−69% llamadas y −86% reloj** con la calidad sostenida; el residual contra
el plano (1.4×) es la síntesis final y algo más de uso de tools — el precio
del informe auditable. E2E real verificado (respuesta honesta incluida:
declaró que MAX_PASOS llegó por evidencia indirecta cuando el truncado de
search_files no le mostró la línea). Fix de conductor en el cierre: el
caché de idénticas no veía DENTRO de una tanda (el snapshot de prep es
previo a la ronda y los modelos sí duplican llamadas en una misma ronda) —
estado vivo local en `Ejecutar.exec`.

**Saga de aplicación (3 sesiones + conductor)**: la reescritura murió a
mitad por **saturación de RAM del host** (no de la sesión: corría sin
checkpoints; fue el acumulado del ambiente — la sesión de tests posterior,
con la RAM ya liberada, cerró sin incidente y con la RAM plana). Lección
operativa consolidada: las sesiones de escritura van SIN checkpoints y el
conductor verifica `free -g` antes de lanzar. La sesión de tests jubiló
(con nombre en su reporte): votación 2-de-3 en el despacho,
reintento-con-feedback del prompt de args, umbral del supervisor —
mecánica que ya no existe; el contrato sha1 del despacho quedó congelado
donde vive ahora (la sonda). Un `_diag_replay.py` rastrero de una sesión
anterior se borró en la limpieza. **348 tests + ruff limpio.**

## exp/47 — 12 factor agents: el gap analysis (2026-10-14)

El material oficial de humanlayer/12-factor-agents quedó versionado local
(`banco/material/12factor/`, 13 archivos) y una sesión del banco (patrón
exp/19) auditó el harness factor por factor, con evidencia citada y
verificada por el conductor. **Informe completo:
`salidas/informe_12factor_2026-10-14.md`.** Resumen del tablero: 6 factores
cubiertos con evidencia (1, 2, 3, 4, 9, 10), 6 parciales (5, 7, 8, 11, 12,
apéndice 13) y 1 ausente (6). Las divergencias informadas — lo que el
material recomienda y la casa RECHAZÓ con evidencia propia — son parte del
resultado: pre-rank de tools (exp/15, KV-cache), triaje LLM de errores
(exp/9, autocorrección 67%), errorCounter por tool (reemplazado por
no-progress), persistir messages como memoria (descartado por costo).

**La tesis "PocketFlow envuelve la metodología" se sostiene por el factor
8 con sus propias palabras** ("the number one feature request... interrupt
a working agent and resume later, ESPECIALLY between tool selection and
invocation", factor-08 L73-74): el harness ya ejerce el control flow propio
sin framework pesado; lo que le falta al factor 8 es justo el
break-and-resume — y encaja como un nodo y una arista más, no como un
framework. Los tres gaps derivados, ya en el roadmap como exp/48-50:

| exp | pieza | factor | métrica de corte |
|---|---|---|---|
| exp/48 | persistencia/resume de corridas (thread serializable) | 6 | rehidratar sin violar invariantes; ≥50% rondas ahorradas en ≥20 rondas |
| exp/49 | HITL como arista (`AskHuman` + approved/rejected) | 7/8 | aprobar con el proceso reiniciado; 2 HITL paralelos sin bloqueo |
| exp/50 | pre-fetch como política declarativa (nodo `PreFetch`) | ap. 13 | A/B ON/OFF: ≥1 ronda menos sin subir errores |

## exp/48 — el thread serializable: persistencia/resume del chat (2026-10-14)

Aplicado por el harness (sesión exp48-aplicar) con el conductor auditando el
diff completo. **La pieza**: `utils/thread_store.py` (puro) — `checkpoint()`
appendea el `shared` COMPLETO por línea a `salidas/threads/<id>.jsonl`
(bookkeeping que jamás corta el chat; `THREAD_PERSIST=0` apaga todo),
`cargar()` lee la última línea COMPLETA tolerando cola cortada por crash, y
`valido()` reusa `validar_historial` (los 4 invariantes del modo thinking).
Tres **puntos seguros** en el grafo (mismos sitios que el trace):
GetQuestion.post (pregunta registrada), ExecuteTools.post (ronda
registrada), AgentStep.post answer (respuesta registrada — DirectAnswer
persiste con su nombre de clase real). Subcomando `python3 main.py resume
<id>`: rehidrata, completa faltantes con setdefault, y un thread con
violaciones NO arranca (lado seguro — el modo thinking rompería a la
primera llamada). 368 tests (+20, `tests/test_thread_store.py`) · ruff
limpio.

**E2E del conductor, dos casos reales:**
- **Continuidad**: thread de una corrida completa (13 mensajes, 3 rondas)
  → resume → pregunta de memoria ("¿qué números te di?") respondida SIN
  tools — etiqueta ambiental "directo (0 rondas)": el historial restaurado
  es memoria utilizable (y de paso alimentó la flywheel).
- **kill -9 a mitad**: tarea multi-carpeta asesinada durante la ronda 1
  (último checkpoint: ExecuteTools, rondas=1, 6 mensajes, 0 violaciones) →
  resume con continuación → cierra limpio SIN re-ejecutar la ronda ya hecha
  (el resultado restaurado viaja en el historial). Ahorro total de la ronda
  realizada; la métrica formal (≥50% en tareas ≥20 rondas) queda para el
  tráfico real, n=1 hoy.

**Límites v1 (documentados)**: solo el chat (otros flows después); el
resume abre un LINAJE NUEVO de thread (el id es por proceso — la
continuidad es del contenido, no del id); sin pausa entre selección e
invocación (eso es exp/49, que reusa esta base). Nota operativa del
conductor: `pkill -f "main.py"` mata también al wrapper del conductor si su
línea de comando contiene el patrón — matar por PID exacto.

## exp/49 — la aprobación durable: el HITL sobrevive al proceso (2026-10-14)

Corte pre-registrado en exp/47 ("aprobar con el proceso reiniciado"),
resuelto por la vía PocketFlow-simple (decisión del conductor documentada):
sin reestructurar el flujo con aristas approved/rejected todavía — la base
de exp/48 + dos piezas. Aplicado por el harness, auditado por el conductor.

- **Punto seguro 4 — la SELECCIÓN** (`AgentStep.post`, camino "tool"): el
  checkpoint en el momento EXACTO que el factor 8 pide ("between tool
  selection and tool invocation"). Dos checkpoints por ronda: selección y
  cierre.
- **`reparar_pendientes(shared)`** (PURA, `utils/thread_store.py`): un
  proceso muerto entre selección y ejecución deja el último assistant con
  `tool_calls` huérfanos — viola el invariante de la API y el resume lo
  rechazaría. La reparación appendea, por cada huérfano, un mensaje tool
  HONESTO ("no llegó a registrarse ejecutada — puede haber corrido a
  medias; verificá el efecto antes de repetirla"). Acotada al final (pares
  viejos rotos en el medio son corrupción, los caza el validador),
  idempotente. `resume` la aplica y el banner informa cuántas.
- **`modules/humano.py`** — `request_human_input(pregunta)`: el humano como
  TOOL CALL (factor 7 literal): el modelo puede pedir aclaración antes de
  asumir; una línea por `input()`, EOF/excepción → "(sin respuesta del
  humano: …)" — dato, no crash; sin HITL (preguntar no es un efecto).

**E2E del conductor (el corte, demostrado)**: chat con pedido de escritura,
stdin abierto en silencio por fifo, `kill -9` mientras el `(s/n)` espera →
último checkpoint `AgentStep tool` con la violación esperada ("assistant
con tool_calls sin sus tools"); `resume` → banner "1 llamada interrumpida
reparada" · 0 violaciones → el modelo re-propone el `write_file` →
aprobación `s` → **archivo escrito** ("exp49 ok") y cierre limpio. La
aprobación sobrevivió al proceso que la pidió.

**Hallazgo de la auditoría (no previsto, valioso)**: con stdin por pipe, el
EOF alcanza la aprobación y cuenta como RECHAZO (default seguro) — la ronda
cierra sola y el modelo responde con elegancia. El escenario "muerte con
aprobación PENDIENTE" solo existe con stdin abierto (terminal real o
hitl_web); el fifo lo reprodujo fielmente. Límites v1 documentados:
`request_human_input` es solo terminal (la vía web es 49b con el server
multi-pendiente); la reparación es at-most-once honesto, no exactly-once
(verificá efectos antes de repetir — el mensaje se lo dice al modelo).

**378 tests (+10) · ruff limpio.**

## Cómo crecer desde aquí

- Escribir archivos → herramienta write_file con confirmación humana
  previa (HITL).
- Memoria entre sesiones → ✅ hecha como **biblioteca consultable** (ver
  abajo), NO como contexto inyectado: persistir/comprimir `messages`
  (cookbook `chat-memory`) quedó descartado por costo creciente.
- Muchos documentos y preguntas repetidas → indexar offline (RAG).
- Streaming de respuestas y memoria entre sesiones (persistir/comprimir
  `messages`).
- Choose del supervisor a escala: recargar saldo DeepSeek, generar
  ~2.400 casos con hechos del menú real (prompt ya corregido), verify
  y un run más — la dosis por opción es la palanca que falta (60 → 120+).
- Datar el punto débil restante del router (mundial): un round dirigido
  de "hechos actuales" con `generate_targeted` (arreglar su
  `contexts_path` roto primero).
- La aprobación HITL vive hoy dentro del tool (`input()`, o el navegador
  con `HITL_WEB=1` vía `utils/hitl_web.py`); el paso siguiente, si el
  chat migra a web (FastAPI/Gradio), es subirla a una arista del grafo
  (`needs_approval` → AskHuman → `approved/rejected`).
- Self-healing batch (pasos fallidos re-encolados con feedback) y
  heartbeat (piezas corriendo solas de noche).
- Un visor del trace (.runs/*.jsonl ya registra nodo/acción/duración).

### Heartbeat — las piezas de noche
`python3 main.py heartbeat [--ahora|--seco]` · [heartbeat.py](../heartbeat.py) · [heartbeat.jsonl](../heartbeat.jsonl)

Pieza standalone: lee las tareas de `heartbeat.jsonl` (tarea + salida +
`cada_horas`), corre las vencidas con el supervisor reactivo completo y
deja informe + estado (`.heartbeat/estado.json`) + log de auditoría
(`.heartbeat/log.jsonl`). El reloj lo pone el cron del sistema
(la línea sugerida vive en el docstring); la pieza solo decide qué toca —
sin tareas vencidas no gasta una llamada. `--ahora` fuerza (para probar),
`--seco` lista. Leyes: cada tarea es un supervisor entero (MAX_PASOS=5,
veto tras dos fallos) y MAX_TAREAS_POR_CORRIDA=10. Crea el directorio de
salida (lección de la primera corrida: Sintetizar escribe directo).

### Visor del trace — los .runs abiertos
`python3 main.py visor [trace.jsonl ...]` · [visor.py](../visor.py)

Pieza standalone de código puro: lee los eventos de `.runs/*.jsonl`
(`{ts, nodo, accion, seg}` — utils/tracing) y escribe al lado un HTML
autocontenido (offline, sin CDN): el recorrido con las vueltas del bucle
(la historia `ElegirSiguiente→EjecutarPaso` del supervisor se lee de un
vistazo), el resumen por nodo (veces, tiempo, %) y la cronología con
barras de duración proporcionales. Sin args usa el trace con contenido
más reciente (main.py abre el propio antes de despachar: los vacíos se
saltan). Determinista: el mismo jsonl da el mismo HTML (test de humo).

### Export de grafos — el diagrama que ejecuta el framework
`python3 main.py grafo [flujo]` · [utils/viz.py](../utils/viz.py)

Camina los `successors` desde el nodo inicial y emite mermaid — el grafo
real, no el dibujado. Registra todos los flujos: chat, informe, juez,
juez_lote, auditoria, research, supervisor, effective_n y
effective_n_multi. Un flujo anidado declara el nombre de su contenedor
(`JuezLoteFlow`, `EffectiveNMulti`) aunque su start sea una hoja.

### Guard de calles muertas — ningún grafo termina en vacío

`tests/test_grafos_sin_calles_muertas.py` recorre esos flujos (y revisa debate
y rag, que se construyen inline, contra su fuente) y falla si un nodo puede
devolver una **acción sin arista** o una **variable** en `post()` — la clase
de bug que cerraba el chat en silencio (`Flow ends: 'uso_herramientas' not
found`, medido en la barrida). Los nodos sin aristas solo se admiten si están
en la lista explícita de `TERMINALES`, así que un terminal nuevo es una
decisión y no un accidente. Cerró el caso real: `LayaRouter.post` devolvía la
etiqueta cruda del checkpoint; ahora una etiqueta fuera de contrato cae al
lado seguro.

### Memoria entre sesiones — la biblioteca consultable
[modules/memoria.py](../modules/memoria.py) · `memoria/*.md` (ignorada)

Filosofía EXACTA: la memoria es una **biblioteca consultable, NO contexto
auto-inyectado**. Cada chat arranca con la memoria vacía —nada se inyecta
al inicio y el system prompt no se toca (sigue byte-estable para el
KV-cache)— y el agente la consulta solo cuando el pedido lo justifica, vía
tools. Dos tools, código puro (sin LLM):

- `memory_search(query)`: busca el texto (case-insensitive) dentro de los
  markdown de `memoria/` y devuelve archivo+línea coincidente, más el
  listado completo de la biblioteca (con la biblioteca vacía, lo dice).
- `memory_save(titulo, contenido)`: escribe
  `memoria/nota_FECHA_slug.md` con el título como primera línea. SIN HITL
  (es la libreta del agente) pero con contención dura: el nombre sale de
  un slug del título (ASCII, sin separadores de ruta ni `..`), el destino
  resuelto DEBE quedar dentro de `memoria/` (doble chequeo) y un título
  sin caracteres utilizables se rechaza. Devuelve el path escrito.

Resumen automático al salir: `main.py` envuelve la corrida del flujo en
`try/finally` (cubre el retorno normal y el Ctrl+C del prompt).
`resumen_de_sesion(shared)` corre en el `finally`; con `MEMORIA=1`
(default) y al menos 2 preguntas de usuario hace UNA sola llamada a
`call_llm` que comprime la conversación (tema, pedidos y resultados,
decisiones, hallazgos, archivos tocados) y la guarda como
`memoria/sesion_FECHA.md` vía `guardar_resumen_sesion`. Sin HITL (es
bookkeeping, no una acción nueva) y con el fallo de la llamada contenido:
se sale igual sin romper nada. `MEMORIA=0` apaga todo.

## Sesión de prueba completa (2026-10-05): 19 turnos, las 18 capacidades

Una sola sesión continua de chat ejerciendo todo el harness. Resultado
por capacidad: router directo ✓, list/read/search ✓, write_file con HITL
(crea y sobrescribe) ✓, answer_verified con citas ✓, sql ✓, mcp_tools +
mcp_call (1847×293=541171, correcto) ✓, search_web (honesto: los snippets
no traían el tag de versión) ✓, rag_index + rag_search (35 fragmentos,
dedup en design.md al top) ✓, run_effective_n ✓, run_informe (22
archivos, 33.974 registros — creció con los datasets nuevos) ✓,
run_auditoria (round1 vs round3) ✓, run_supervisor (42 .py, el más
grande correcto, notó hasta el path truncado en los hechos) ✓,
debate/research ✗ (ver hallazgo 1).

Hallazgos y sus fixes:

1. **El separador DSML es DOBLE barra** (`<｜｜DSML｜｜`): la primera
   versión de la recuperación usaba una sola (copiada de un transcript
   pegado a mano que la colapsaba) y NUNCA disparó — el debate y el
   research de la sesión se perdieron. Fix: regex flexible `[｜|]{1,2}`,
   verificada contra los tres bloques reales del log (los tres parsean)
   y con test de ambos formatos. El patrón de fondo: el DSML aparece
   cuando el modelo va SIN tools (camino directo del router) pero quiere
   llamar igual — tres de los falso-directo del router terminaron en
   DSML; con la recuperación andando, ese error del router se
   auto-corrige.
2. **Repetición idéntica con args en el supervisor**: search_files con
   el mismo glob corrió 4 veces (el veto solo cubría sin-args). Fix:
   firma canónica herramienta+args → cache (la idéntica no re-ejecuta,
   reutiliza el resultado) + veto a la segunda firma repetida.
3. Ruido cosmético: httpx/asyncio "Event loop is closed" al cerrar los
   clientes async (×6 por sesión) — sin impacto, pendiente de silenciar.
   Warning de fastembed (mean pooling) — informativo, sin acción.
4. El falso-directo del router se confirmó en vivo dos veces más
   (MCP 0.82, debate 0.78) — candidato al ensamble 2-de-3 cuando toque.

## Vision/PDF y A2A: la cola final, dos capacidades (2026-10-05)

Últimos dos ítems del roadmap. Dos módulos nuevos (`modules/vision.py`,
`modules/a2a.py`), sin dependencias nuevas (`requests` ya estaba), con
`TOOLS`+`IMPL` como el resto. Nunca tocan el historial del chat: la
imagen/el archivo viaja en un turno de usuario aislado y lo que vuelve es
solo el texto de la respuesta.

### Vision/PDF — `modules/vision.py`

Dos caminos distintos, cada uno por una razón medida:

- **`ver_imagen(path, pregunta)`** — la imagen va como **data-URL base64**
  dentro de un message de **USER** con `content=[{type:text},
  {type:image_url}]`. El mensaje system/assistant NO puede llevar
  imágenes: la API responde **400** (medido) — por eso la imagen viaja en
  un turno de usuario propio y no se inyecta al historial. La llamada es
  `call_llm` (contenido como array), **SIN** el `extra_body` de thinking:
  `call_llm_agent` agrega thinking+tools y eso no aplica acá.
- **`ver_pdf(path, pregunta)`** — los PDF NO van por base64: van por la
  **Files API**. `POST /files` multipart (`file` + `purpose=file-extract`)
  → `file_id`; luego `POST /chat/completions` con
  `content=[{type:file,file_id},{type:text}]` → el texto llega en
  `message.content`. **Sin estado**: cada `ver_pdf` sube, consulta y listo
  (no se guarda el `file_id`). El tope lo impone la Files API (64 MiB).

**El tipo se valida por CONTENIDO, no por nombre** (magic bytes): `\xff\xd8\xff`
JPEG, `\x89PNG\r\n\x1a\n` PNG, `GIF87a/GIF89a`, `RIFF....WEBP`; un PDF
empieza con `%PDF`. Un `.png` que en realidad es JPEG se acepta como JPEG;
un `.png` de texto se rechaza. **Límites chequeados ANTES de llamar**:
imagen 32 MiB y body 48 MiB (base64 crece ~4/3); superarlos devuelve un
`ERROR` legible sin tocar la red. API key/base de los settings existentes
(`LLM_API_KEY`/`LLM_BASE_URL`).

### A2A — `modules/a2a.py`

El eje de `mcp` pero del lado de los AGENTES: en vez de tools dentro de un
servidor, hablamos con agentes remotos que exponen el protocolo
**agent2agent**. Setting `A2A_AGENTS` en `.env`: JSON
`{"nombre": "http://host:puerto"}`.

- **`agentes_remotos()`** — lista los agentes del setting con su agent card
  (`GET {base}/.well-known/agent.json`, timeout 5s). Card inaccesible ⇒
  `inaccesible` **y el resto sigue** (degradación, no crash).
- **`a2a_tarea(nombre, mensaje)`** — `POST {base}/` JSON-RPC 2.0
  `method=message/send`, `params={message:{role:"user",parts:[{type:"text",
  text:mensaje}]}}`, `id` incrementado por proceso. Devuelve el `result`
  (serializado) o el error del JSON-RPC como texto. Timeout 60s.

Sin setting (o vacío, o JSON roto ⇒ se trata como vacío) las tools
devuelven "no hay agentes configurados" sin tocar la red.

Tests sin red (`tests/test_smoke.py`): la imagen y el PDF se validan
mockeando `requests.post` (forma del data-URL, `purpose`, `file_id` dentro
del `content`, y que >límite/tipo inválido devuelven ERROR *sin* llamar);
A2A corre contra un `http.server` fake (card + JSON-RPC), con un agente
caído verificado como `inaccesible`.

## Salidas — una carpeta, no una raíz llena de .md

Higienizado (2026-10-05): todas las piezas escribían sus informes en la
raíz del proyecto (informe.md, auditoria*.md, supervisor*.md,
research*.md, effective_n*.md...) — el .gitignore los tapaba de git pero
no del disco. Ahora el default de TODAS las salidas es `salidas/` (y
`salidas/heartbeat/` para las nocturnas), cada escritor crea su
directorio (la lección del heartbeat), y el .gitignore se simplificó a
`salidas/` única.

## El CWD en el system prompt

Medido en producción (2026-10-05): "¿en qué carpeta estamos?" se
respondía con la raíz permitida (el único directorio que el modelo
conocía) en vez del CWD real. El system prompt ahora declara el
directorio de trabajo actual del proceso: la pregunta sobre el entorno
se responde con el dato, sin adivinar ni gastar tools.

## Curaduría del system prompt (minimalismo validado)

Revisión contra el estado del arte 2026 (2026-10-04): el propio DeepSeek
publicó el system prompt de su agente (repo `deepseek-ai/deepseek-harness`)
y su arquitectura valida la filosofía del proyecto — prefijo estable
mínimo + hechos de runtime como snapshot en rol de usuario + tool schemas
como catálogo independiente. Su medición clave: una sección dinámica en
el prefijo rompe el KV-cache y recalcula ~99% del contexto por turno.

El prompt del chat quedó así (verificado en vivo, 1 llamada):

- **Rol tarea-primero** (semántica 2026): "Agente de resolución de
  pedidos con tools disponibles" — identidad orientada al resultado, no
  a la actividad; el inventario de capacidades vive en los tool schemas
  (info en cada pieza), no en el prompt.
- **Entorno en capas**: "Trabajás en {cwd} y sus subdirectorios" como
  espacio de trabajo + "Alcance máximo de las tools de archivos" con
  las raíces permitidas como perímetro duro. Medido: preguntado "where
  do you work?", el modelo distinguió ambas capas sin ambigüedad
  ("work in deepseek-flow and its subdirectories; file-tool access
  limited to at most 00_IA").
- **Portabilidad del entorno (verificado con demo)**: nada está
  hardcodeado — el CWD se renderiza con `Path.cwd()` por arranque y el
  perímetro sigue la cadena `AGENT_ALLOWED_DIRS` (env o .env del
  checkout, gitignored) → default portable `.` (= CWD). Descargado el
  zip en otra máquina y abierto en otro repo, el prompt completo se
  re-renderiza a ese repo (demo: abrir desde /tmp con el default
  muestra `/tmp/...` en ambas capas). El tradeoff del default `.`: si
  se abre en ~, el perímetro es el home entero — acotarlo es trabajo
  del .env de cada instalación.
- **Idioma espejado**: "Respondé en el idioma de cada pedido (español
  o inglés)" — el idioma se decide por pedido, no se fija. Medido:
  pregunta en inglés → respuesta en inglés.
- **Regla de estabilidad codificada**: comentario + test — el prefijo es
  byte-estable por sesión (CWD y raíces se congelan al arranque); nada
  dinámico (fecha, hora, contadores) entra jamás. Si algún día hace
  falta la fecha, va como mensaje de usuario, no acá.

Lo que NO cambió: el prompt sigue siendo ~6 líneas; la info necesaria
vive en cada pieza (descripciones de tools, prompts one-shot), que es
donde el estado del arte pone el peso (Augment, sobre los prompts
filtrados: los schemas JSON suelen ser más reveladores que el prompt
mismo). El lever de curaduría siguiente son las descripciones de las 18
herramientas — con sonda antes/después, como hicimos con el router.

## El coding agent: run_command y edit_file (2026-10-05)

El agente de archivos se volvió agente de código con un módulo nuevo
(`modules/coding.py`, el patrón TOOLS+IMPL — el CORE no cambió una línea)
y dos herramientas bajo el mismo contrato HITL que `write_file`:

- **`run_command`**: shell con aprobación `(s/n)`, preview del comando.
  Rieles mecánicos: timeout de 120s, salida truncada a 4k chars (viaja
  al historial y al costo), stdin cerrado (nada espera input
  interactivo), CWD del proceso. Diseño explícito: para shell la
  aprobación humana ES la contención — un comando llega a donde las
  raíces permitidas de las tools de archivos no llegan. El rechazo
  vuelve al modelo como texto (información para corregir, no error).
- **`edit_file`**: reemplazo exacto y único de `old_string` por
  `new_string` con diff unificado y aprobación. Falla ruidosamente si
  el texto no aparece, aparece N veces, o es idéntico al reemplazo —
  obliga al modelo a volver al archivo en vez de reescribirlo de
  memoria. Es la lección medida del clobber de `fs_tools.py`
  (write_file de archivo entero lo dejó en 16 líneas).

El supervisor NO suma estas tools: su contrato de 18 opciones está
congelado con el checkpoint de Laya (agregarlas exige re-entrenar el
dispatch). Chat-first; supervisor recién si medimos necesidad.

Verificación en vivo (sesión completa por el flujo real del chat, con
aprobaciones HITL reales vía driver pty):

- crear `demo.py` con `write_file` usando un path RELATIVO
  (`salidas/tmp_coding/demo.py`) — resolvió por el candidato CWD del
  fix de `_resolve` (el issue 6 de la caza, funcionando en producción);
- verificar con `run_command` (`python3 -c "...print(suma(2,3))"` →
  exit 0, salida `5`);
- corregir con `edit_file`: diff de UNA línea (`a + b` → `a - b`),
  aplicado y re-verificado con `cd ... && python -c`;
- precisión de instrucciones: el agente notó que el docstring quedó
  desactualizado ("Devuelve la suma") y NO lo tocó porque el pedido era
  solo el retorno.

31/31 tests (HITL sí/no, timeout, truncado, y las tres fallas
ruidosas del edit).

## HITL graduado + hooks (mesa 2, 2026-10-05)

El contrato binario del HITL (todo `run_command` paga un `s/n` — 272 en
una sola sesión) encuentra su gradación sin aflojar la contención, en dos
piezas nuevas.

**`utils/policy.py` — clasificador determinista, sin LLM.** Mismo comando
⇒ misma clasificación, siempre. Tres niveles de fricción:

- **`auto`**: solo-lectura verificado. Whitelist conservadora de prefijos
  exactos de primeros tokens (`pytest`, `python3 -m pytest`, `grep`, `ls`,
  `cat`, `head`, `tail`, `wc`, `find`, `file`, `echo` sin redirección,
  `git status/log/diff/show/blame`). Se ejecuta directo.
- **`preguntar`**: el flujo de hoy (un `s/n`). **Default de todo lo no
  reconocido** — la política solo RELAJA lo que reconoce.
- **`confirmar_doble`**: `git push` y `rm -rf` piden dos `s/n` seguidos.

Reglas de composición (la parte crítica):

- El comando se parte por `&&` y `|`. **Todos** los segmentos deben ser
  `auto` para que el compuesto sea `auto` — basta uno sospechoso
  (`ls && rm -rf /`) para que todo pregunte.
- Cualquier redirección (`>` `<` `>>`), sustitución `$(...)`, backticks o
  `xargs` degrada a `preguntar`: escriben o ejecutan cosas que no se
  pueden clasificar por prefijo.
- `python3 -c` pregunta SIEMPRE: es código arbitrario disfrazado de
  comando de una línea (aunque hoy lo usemos para repros).

Orden: whitelist primero, negra después, default `preguntar`.

**Integración en `run_command` (`modules/coding.py`).** Con `HITL_AUTO=1`
(default) se clasifica ANTES del preview: `auto` ejecuta imprimiendo una
línea visible `── run_command [auto: solo-lectura] ──` + el comando (el
usuario lo ve igual — transparencia); `preguntar` es el flujo de hoy;
`confirmar_doble` hace dos `(s/n)` y cualquiera que sea no aborta. Con
`HITL_AUTO=0` todo vuelve al `s/n` clásico (compatibilidad).

**Hooks post-tool (`utils/fs_tools.run_tool_call`).** Mecanismo genérico
`HOOKS_POST = {nombre_tool: [fn]}` donde `fn(tool_call_dict, resultado_str)
-> str` puede enriquecer el resultado antes de que viaje al modelo. Se
registra UNO: tras `edit_file`/`write_file` sobre un `.py`, corre
`python3 -m py_compile` (subprocess, timeout 15s) y si falla agrega
`⚠ SINTAXIS: <error>` al resultado. Es el patrón **error-como-feedback**:
el modelo ve el problema y se autocorrige en la vuelta siguiente —
habría pescado el clobber de `fs_tools.py` al instante. Contrato de
hierro: un hook NUNCA rompe la ejecución (si py_compile no existe, el
archivo no es `.py`, o cualquier cosa falla raro, el resultado queda
intacto).

**Hooks pre-tool (`utils/fs_tools.HOOKS_PRE`).** El complemento que
faltaba: `HOOKS_PRE = {nombre_tool: [fn]}` donde `fn(tool_call_dict) -> str|None`.
Si el hook devuelve texto, **CANCELA** la ejecución (ese texto es el
resultado); si devuelve `None`, no opina. Mismo contrato de hierro: un
hook que lanza se ignora y la tool sigue. Corre ANTES de la
implementación porque hay guardas que un hook post ya llega tarde a
evaluar (un comando que ya corrió). El primer uso es el residual de la
mesa 2:

- **Denylist dura de `run_command`** (`modules/coding.py`): los comandos
  de daño irreversible en el host — `rm -rf /` y la fork bomb
  `:(){ :|:& };:` — se vetan **sin s/n** (no hay aprobación que los
  salve) y el veto vuelve al modelo como `ERROR` para que reformule. La
  lista es corta a propósito: la política graduada ya cubre el resto con
  fricción; acá solo va lo que nunca debería ejecutarse desde un chat
  automático. El hook se registra desde el propio módulo
  (`_registrar_hooks()` al importar), así la política viaja con su
  módulo, no con el CORE.

81→88→92 tests: los tres niveles de `clasificar()`, TODAS las reglas de
composición, `run_command` con HITL_AUTO=1 seguro sin input (monkeypatch
que explota si se llama) y no-seguro pidiendo, doble confirmación
abortando, y el hook tras edit/write de `.py` roto vs. bueno.

## Pulido de terminal (mesa 8, 2026-10-05)

`utils/terminal.py` (stdlib, sin dependencias) da las dos piezas que
faltaban del pulido de terminal, ambas degradando a texto plano cuando la
salida no es una terminal:

- **`colorear(texto, tipo)`** — códigos ANSI por TIPO de evento (`tool`
  cian, `ok` verde, `error` rojo, `info` gris, `aviso` amarillo,
  `respuesta` negrita). Solo pinta si `sys.stdout.isatty()` y no hay
  `NO_COLOR` (el estándar) ni `COLOR=0` (escape hatch propio). Sin tty —
  tests, pipes, logs — devuelve el texto intacto: nada cambia en CI.
- **`progreso_ronda(ronda, tope)`** — etiqueta `⚙ ronda 2/8` (o `⚙ ronda
  2` sin tope) para las rondas de herramientas.

Integración en `nodes.ExecuteTools`: cada tool se **anuncia ANTES de
correrla** (`→ read_file`, para que una espera de varios segundos no
parezca colgada) y, en `post()`, la ronda consumida se etiqueta con su
avance sobre `MAX_TOOL_ROUNDS`. Los avisos de recuperación DSML y de
sanitizado pasan por `aviso` (amarillo). Los hooks y el resto del flujo no
se tocan.

5 tests: color con/sin tty, `NO_COLOR`/`COLOR=0`, tipo desconocido, el
formato de `progreso_ronda`, y que `ExecuteTools` anuncie cada tool y
etiquete la ronda (forzando `isatty=False` para ver el texto plano).

## Candados de contrato y fixes de la auditoría de sesión (2026-10-05)

Auditoría de una sesión real del usuario (revisión de consistencia
semántica, informe en `salidas/revision_consistencia_2026-10-05.md`).
Sus mediciones se verificaron independientemente — el sha1
prod≡sonda del router (`01bf4478f15c…`) era exacto — y su lote de
"candados, no refactors" se aplicó completo:

1. **`sonda_router.py` importa `PREGUNTA_ROUTER` de `nodes`** — una sola
   fuente; la copia local podía derivar sin que ningún test lo notara
   (drift medido como 0 hoy, riesgo latente alto).
2. **`test_contratos_laya_congelados_sha1`** — congela el CONTENIDO
   completo (sha1 canónico) de ambos contratos; el test de claves no
   alcanzaba (cambiaba una palabra de instructions y nada fallaba).
3. **Fix de `search_files` con `path` a archivo**: `os.walk` sobre un
   archivo no visita nada → falso negativo silencioso ("Ningún archivo
   contiene X" sobre un archivo que sí lo contiene). El informe lo
   midió pero lo atribuyó a "strings cortos"; repro y root-cause
   nuestros: es el path-a-archivo (ahora se trata como único habitante
   de su directorio padre).
4. **`evento_tool` en la traza**: las tools que no son flujos
   (run_command, sql, write_file) no atravesaban nodos — una ronda de
   50s era inatribuible desde `.runs/` (ciego medido en esta
   auditoría). ExecuteTools registra ahora nombre + ok/error + duración
   por llamada.
5. **design.md**: default de informe corregido (decía `bmo/data`; el
   código usa `.` con `INFORME_CARPETA` en .env).

No aplicado (correctamente diferido por el informe): unificar
vocabulario de `shared`/actions — 7/9 claves compartidas son benignas,
los archivos fríos no justifican el refactor (churn medido), y las 2
colisiones reales (`analisis`, `feedback`) se documentan, no se tocan.

**Cierre (2026-10-05, candados ejecutados):** los tres "hacer ya" de la
recomendación quedaron aplicados, y las 2 colisiones quedaron
**documentadas en el código** (no solo en este registro):

1. `sonda_router.py` ya importa `PREGUNTA_ROUTER` de `nodes` (drift
   imposible); se sumó `sonda_supervisor` a la misma garantía con test
   (`PREGUNTA_DESPACHO is supervisor.PREGUNTA_DESPACHO`).
2. Los contratos de Laya están congelados por sha1 (router, despacho, voto):
   cambiar una palabra rompe el test.
3. Comentarios de contrato en `informe.py`/`effective_n.py` (`analisis`) y
   `juez.py`/`research.py` (`feedback`) declaran la forma esperada y la
   colisión consciente — barato, sin refactor.
4. Lo diferido (idioma de claves, `rounds`→`ronda`, vocabulario de actions)
   sigue **sin hacerse por falta de evidencia** (7/9 claves compartidas son
   benignas; los flujos fríos no justifican el churn).

## Sesión integral 2026-10-05 (post-coding agent): 18 turnos, todo verde

Prueba completa por el chat real (driver pty, aprobaciones HITL
automáticas): 26 llamadas a tools, 16 herramientas distintas, 0 errores.
Cobertura: tools CORE, coding (write→run→edit→run con verificación de
doble(4)==8 → triple(4)==12), sql+db_schema, answer_verified con cita
verificada (`tests/test_smoke.py:613`), debate (async, 2 rondas + juez),
informe map-reduce async-paralelo, web, RAG (index+search), supervisor
sub-agente, effective_n, MCP real (servidor `matematica`, 4 tools),
inglés espejado en el turno 1. La traza nueva con `evento_tool` dejó
cada llamada nominada en `.runs/`.

Tres hallazgos en vivo:

1. **El falso-directo atacó y el voto lo mató**: "debatí en 2 rondas…"
   → Laya `directo conf 0.99` (la debilidad conocida del checkpoint con
   imperativos) → voto 2-de-2 → `herramientas` → el debate corrió. La
   defensa de mayoría trabajando en producción, no en la sonda.
2. **El supervisor heredó las coding tools por el lado DeepSeek**: su
   `catalogo()` deriva del action space dinámico, así que `run_command`
   fue electable (y electo, con HITL aprobándose DENTRO del sub-agente).
   La congelación aplica al contrato de Laya (18 opciones), no al
   catálogo. Decisión implícita que queda documentada acá: se acepta —
   el self-healing del supervisor (feedback, vetos) y el HITL protegen;
   re-entrenar el dispatch para sumarlas es costo sin necesidad medida.
3. **El guard del ZeroDivision se ejercitó solo**: los 3 .jsonl más
   chicos de .runs tienen 0 registros → `effective_n` con total==0
   produjo su informe en vez de crashear (el fix de esa mañana,
   validado sin buscarlo).

Y el modo thinking pegajoso sobrevivió la sesión entera: turnos
directos intercalados en un historial agéntico pesado, sin un solo 400.

Contraste con el cookbook de PocketFlow (revisado mismo día): cubrimos
Chat, Structured Output, Workflow, Agent, RAG, Map-Reduce, Multi-Agent,
Supervisor, Parallel, Thinking (selectivo+pegajoso), MCP (client y
server), Tracing (nodos+tools+visor), Judge, Debate, Heartbeat, Deep
Research, Coding Agent y HITL web. Faltan — y ya estaban en el roadmap:
streaming, memoria de largo plazo, A2A, vision/PDF. Voice,
descartado.

## Memoria entre sesiones: biblioteca consultable (2026-10-05)

Tercer ítem construido por el propio harness (6 turnos, 36 aprobaciones,
2 commits). Filosofía pedida por el usuario, respetada al pie de la
letra: la memoria es una BIBLIOTECA, no contexto auto-inyectado — todo
chat arranca vacío y el system prompt quedó intacto (estabilidad
byte-a-byte preservada). Piezas (`modules/memoria.py` + `main.py`):

- `memory_search(query)`: código puro, busca en `memoria/*.md` y lista
  la biblioteca. Verificado en vivo: ante "¿qué hay en memoria?", el
  agente la consultó y contestó con el contenido real.
- `memory_save(titulo, contenido)`: escribe `memoria/nota_FECHA_slug.md`
  sin HITL (la libreta del agente) con contención dura: slug sin rutas
  ni `..`, solo dentro de `memoria/`.
- Resumen automático al salir: una sola llamada resume la sesión a
  `memoria/sesion_FECHA.md` (bookkeeping, sin HITL; MEMORIA=0 apaga;
  <2 preguntas no resume).

Anomalía registrada honestamente: la sesión de construcción misma NO
dejó resumen al salir (salida limpia, sin print alguno), pero cuatro
repros (pipe simple, pty, tools, transcript grande) funcionan y el
episodio no se reprodujo. Consecuencia: **ninguna ruta del
exit-summary vuelve a ser muda** — desactivada, sesión corta, OSError y
éxito ahora imprimen su veredicto, con test que clava las cuatro rutas.
Si reincide, el print dirá exactamente cuál fue.

Nota: `sesion_FECHA.md` comparte nombre por día — sesiones repetidas el
mismo día se sobrescriben (aceptado por ahora; cada sesión que importa
suele tener además sus salidas/ nominativas).

**Catálogo al arranque (mesa 8, 2026-10-06):** `main.catalogo_memoria()`
imprime, apenas arranca el chat, la lista de notas de la biblioteca (nombre
+ conteo) — el agente sabé QUÉ hay sin que su contenido entre al contexto.
La regla del arranque vacío se respeta al pie: se muestra el catálogo, no se
inyecta nada al system prompt ni al historial. Con `MEMORIA=0` o biblioteca
vacía, silencio; la función es best-effort (nunca corta el arranque).

## Pre-filtro de contexto por Laya (Mesa 6, investigación 2026-10-05)

Los dos caminos de contexto del harness tienen un techo duro en caracteres
y no elegían QUE entra al prompt. El patrón de la wild (reportado con
~80% de costo/tiempo) es dejar que un juicio barato y local elija antes
de pagar tokens: **regla de hierro: si no hay juicio disponible, entran
TODOS los chunks — un retriever no debe perder recall por un modelo
ausente.**

Dos filtros, mismos helpers, default seguro:

- **`utils/contexto.py`** (código puro): `unidades_bloques(texto)` corta un
  markdown/texto en bloques atómicos (una línea en blanco o directiva
  `# ` los separa) sin partir ninguno; `elegir_por_laya(query, unidades,
  setting_prompt, setting_modelo, max_unidades)` puntúa cada bloque con
  el Laya correspondiente (0-1) y devuelve los de mayor puntaje **en orden
  original** (la relevancia decide QUE entra, no el orden). Sin modelo
  (`disponible()` False) o ante cualquier excepción, devuelve las
  `max_unidades` primeras: nunca pierde recall por un fallo.
- **`rag_search`** (modules/rag.py) filtra sus chunks por relevancia
  antes de devolverlos (`RAG_PREFILTRO=1`, `RAG_PREFILTRO_N`).
- **`memory_search`** (modules/memoria.py) filtra los .md de la
  biblioteca cuando hay query (`MEMORIA_PREFILTRO=1`, `MEMORIA_PREFILTRO_N`).
  Sin query, listado completo de siempre.

El contrato del prompt/modelo de Laya va declarado (como los del router) y
se lee de settings (`PREGUNTA_PREFILTRO` es la constante; `LAYA_MODEL_PREFILTRO`
el checkpoint). No hay checkpoint entrenado todavía: en la ausencia de
modelo, los filtros son no-op y el comportamiento es idéntico al de hoy
(cercado por tests: sin modelo, entra todo).

## Compacción de contexto (Mesa 6, 12-factor #5) — 2026-10-06

### El problema, medido

`shared['messages']` crece sin techo y **cada vuelta reenvía TODO el
historial** a la API. Evidencia: la sesión de construcción de la cola
final disparó **115 llamadas a tools**; cada turno pagó tokens por todo
lo anterior aunque lo viejo ya no aportara. El KV-cache amortigua el
precio unitario, pero el contexto sigue creciendo linealmente y cada
turno vuelve a mandarlo entero — el problema es de tamaño, no solo de
plata. Y el modo thinking *pegajoso* (ver `utils/call_llm.py`) vuelve
delicado tocar el historial: cualquier reescritura puede romper los
invariantes y disparar el 400 medido.

### La pieza: `utils/compaccion.py` (código puro, sin LLM)

`compactar(messages, max_chars, ventana=6)`:

- **(a) Ventana caliente intacta.** Siempre conserva el system (índice 0)
  y los últimos `N` mensajes (default 6), contando **assistant con
  `tool_calls` + sus tools como UNIDAD indivisible** — nunca se separan.
- **(b) Zona fría → un resumen.** El medio se reemplaza por **UN mensaje
  de user** con prefijo fijo `[compacción]`, el conteo de mensajes
  omitidos y un placeholder instructivo. El resumen REAL lo escribe el
  agente a sí mismo en un segundo paso; acá no hay LLM: mismo input →
  mismo output (determinista y pura).
- **(c) Invariante de la API.** Nunca deja un assistant con `tool_calls`
  sin sus tools. Si el corte por ventana cae en medio de una unidad, la
  unidad entra completa (la ventana puede quedar en más de N mensajes: la
  unidad manda).
- **(d) No-op documentado.** Si el historial ya entra en `max_chars` o
  tiene menos de `ventana + 2` mensajes, se devuelve intacto.

### Integración (`nodes.py`, `AgentStep.prep`)

ANTES de llamar al modelo: si el historial serializado supera
`COMPACTION_CHARS` (setting, default 60000), `compactar` corre y se
guarda `shared['compacciones'] += 1` con el print
`[compacción] zona fría: X mensajes → resumen; ventana caliente: Y`.

**El costo se paga UNA vez por ronda**: `shared['_compaccion_huella']`
guarda el sha1 del historial ya compactado y no se re-procesa si coincide
(una segunda llamada con el mismo historial es un no-op).

El resumen-instrucción es deliberadamente sobrio: dice que las vueltas
anteriores fueron compactadas y que los hechos durables están en
`memoria/` si hicieran falta (el agente la consulta con `memory_search`).
No inventa memoria ni pide escribir nada.

### Invariantes de seguridad (tests que los clavan)

`validar_historial(messages)` devuelve las violaciones (vacío = válido) y
NUNCA levanta. Clava los cuatro invariantes que el modo thinking pegajoso
exige:

1. Sin `reasoning_content` en ningún mensaje.
2. Dicts canónicos por rol (role/content/tool_calls/tool_call_id).
3. Ningún assistant con `tool_calls` sin sus tools inmediatas después
   (comparación por `tool_call_id`: caza tanto la tool faltante como la
   tool huérfana).
4. Primer mensaje = system.

`test_compaccion_invariantes_antes_y_despues` corre `validar_historial`
ANTES y DESPUÉS de compactar sobre un historial sintético de 201 mensajes
con mezcla de tools, y además verifica que el validador SÍ detecta cada
rotura (no es un chequeo vacuo).

### Tests

`tests/test_smoke.py`: no-op corto, no-op si entra en `max_chars`,
conservación de system + ventana caliente, unidad indivisible (sin tool
huérfana ni assistant sin tools), no-partir-unidad al recortar,
determinismo (dos llamadas), invariantes antes/después, e integración
(`COMPACTION_CHARS` chico por monkeypatch → `AgentStep.prep` devuelve el
historial compactado y cuenta en `shared['compacciones']`, sin
re-compactar la misma ronda). Suite: **124 passed**.

## Cierre de jornada 2026-10-05/06 — tablero verde

Secuencia oficial completa y cola final vacía. Lo construido por el
harness con auditoría independiente + E2E real en cada pieza:

- **Mesas 1-2-3** (evals, HITL graduado+hooks, Laya-voto): el voto r2
  promovido con 80% de turnos-directo sin DeepSeek (0 ecos, 0 errores
  nuevos; r1 reprobado honestamente por la puerta).
- **Mesa 6** (compacción): 89% de reducción con los 4 invariantes del
  modo thinking intactos; E2E real final — la API acepta el historial
  compactado, las tools siguen corriendo después, y el modelo explica
  qué se compactó reteniendo la ventana caliente. Pre-filtro de contexto
  y catálogo de memoria al arranque también adentro.
- **Cola final** (A2A + vision/PDF): ver_imagen/ver_pdf contra la API
  real (la Files API no acepta PDFs — medido — ruta por rasterización
  poppler, multi-página verificado: 3 páginas, clave exacta de la p.2);
  A2A verificado contra server fake del protocolo.
- Bonus de sesiones: denylist PRE, historial de aprobaciones de sesión,
  export en .env, stream sin enmascarar errores, pulido de terminal.

24 capacidades · 141 tests · OOM aprendido: un checkpoint por proceso.
Pendientes del menú: Mesa 4 (agentes fractales), 5 (async), 7 (skills),
8 (chat web — ya empezada).

## Deuda menor y bugs latentes (2026-10-07)

Nueve correcciones de la spec verificada `banco/specs/deuda_2026-10-07.md`
(revisión completa del harness, cada punto verificado en el código). Una
línea por fix, lo que el diff muestra:

- **Fix 1 — `utils/embeddings.py`**: el prefijo `query:`/`passage:` se
  decide DESPUÉS de cargar el modelo (sobre `_nombre_modelo` efectivo), no
  antes: la primera llamada con la familia e5 ya prefija bien.
- **Fix 2 — `minar_errores.py`**: el emparejado error→reintento usa la
  posición del evento (no `eventos.index(ev)` por igualdad de dict), así
  dos errores idénticos no colapsan ambos al primero.
- **Fix 3 — `carga_trazas.py`**: `_texto()` serializa a JSON los campos
  `criteria`/`task`/`modulo` no-string, para que un `criteria` lista/dict
  no reviente el INSERT con `InterfaceError`.
- **Fix 4 — `utils/websearch.py`**: `search_web` captura la excepción de
  `DDGS().text` y devuelve `"ERROR: ..."` como texto (degrada, no tumba el
  flujo de research, que era el único punto sin degradar del harness).
- **Fix 5 — `utils/compaccion.py`**: eliminado `_recortar_cola` (era la
  identidad, código muerto); el call site asigna directo
  `cola = unidades[-ventana:]`. Cero cambio de comportamiento.
- **Fix 6 — `modules/memoria.py`**: `guardar_resumen_sesion` sufija la
  hora si `sesion_FECHA.md` ya existe, así dos sesiones del mismo día no
  se pisan (la primera conserva el nombre clásico).
- **Fix 7 — `modules/db.py`**: `_sin_literales()` vacía el contenido de los
  literales `'...'`/`"..."` para los chequeos de PROHIBIDOS y LIMIT: una
  consulta con la palabra 'delete'/'limit' en un string ya no da falso
  positivo ni se salta el LIMIT forzado.
- **Fix 8 — sondas** (`sonda_laya.py`, `sonda_router.py`,
  `sonda_supervisor.py`): el directorio de tests se resuelve por el setting
  `BMO_TASKS_DIR` (default idéntico al path anterior), portable a otra
  máquina sin editar código.
- **Fix 9 — `docs/roadmap.md`**: la sección "Cola final" describe `ver_pdf`
  con su mecanismo real (pdftoppm/poppler → PNG por página → imágenes al
  modelo, tope 8 páginas), no la Files API muerta (HTTP 400 con PDFs).
  Coherencia documental; el ítem sigue marcado como hecho.

**Falsa alarma descartada**: el `write_file` del supervisor reportado como
no ejecutable NO era un bug — ya era electable y ejecutable vía
`**_MODULE_IMPLS`. Se confirmó primera-mano y se descartó sin tocar código.

## Robustez del banco (2026-10-07, segunda tanda)

Segunda tanda de la spec `banco/specs/banco_robusto_2026-10-07.md`: tres
fixes anclados a contratos existentes (la línea que el código imprime, el
YAML del escenario, la semántica del shell), cada uno con su candado de
test contra líneas REALES. Los números que siguen son los medidos.

- **Fix 10 — marcadores de veto anclados a líneas reales**: el marcador
  `"veto": r"PROHIBID|[Vv]etad"` fallaba en ambas direcciones — 6 falsos
  positivos medidos en los transcripts del día (`PROHIBIDOS`, la constante
  de `modules/db.py`, dentro de diffs preview de `edit_file`; y "vetado" en
  prosa ecoada de instrucciones) y, a la vez, el veto de SEGURIDAD nunca se
  contaba: el texto de la denylist iba solo al modelo como resultado de tool
  y no se imprimía. Ahora `veto_l8`/`veto_denylist` se anclan a las líneas
  reales (`\[laya\] … vetada`/`\[L8\] … vetada` y `[denylist]`) y el hook de
  la denylist imprime `[denylist]` en terminal (paridad con `[hook]`).
  Verificación offline: 0 falsos positivos en los 5 transcripts de
  producción y 3/3 en las líneas reales.
- **Fix 11 — tope HITL: agotamiento elegante + knob por turno**: al agotar
  los 6 HITL el driver enmudecía, el turno colgaba hasta 20 min y el
  `timeout` truncaba el escenario sin registrar la causa (2 turnos colgados
  hoy; 5 turnos "aplicar" históricos terminando exactamente en 6/6). Ahora
  hay knob `max_hitl` por turno y agotamiento elegante con el evento
  `hitl-tope` (causa registrada, no timeout mudo). Smoke E2E con
  `max_hitl=1`: turno ok en 16 s, primera escritura aprobada, segunda
  rechazada y reportada por el modelo.
- **Fix 12 — policy: `2>&1` es lectura, no escritura**: el regex
  `_PELIGRO_SHELL` cazaba el `>` de `2>&1`, degradando a `preguntar` formas
  de verificación solo-lectura. Ahora el token `2>&1` se quita antes del
  escaneo y ninguna redirección real se oculta (`> f`, `2> f`, `2>&1 > f`,
  `> f 2>&1` sobreviven). Matriz de 8 casos.

## exp/20 — bench del juez: la vara que le faltaba (2026-10-07)

El **problema**: `answer_verified` no tenía banco de pruebas propio. Cada
cambio a la ronda de juez (prompt, regex de citas, criterio de refuerzo) se
evaluaba "a ojo": sin casos, sin baseline y sin números, cualquier ajuste
parecía mejorar y nunca se podía comparar contra la versión anterior; peor
aún, un cambio que empeoraba el grading podía pasar desapercibido.

La **pieza** que cierra ese hueco:

- **`banco/juez_preguntas.jsonl`** — 17 casos: 15 de hecho + 2 trampas
  deliberadas (una pregunta que exige una herramienta inexistente y otra con
  una premisa falsa sobre la Files API). Las etiquetas quedaron **verificadas
  mecánicamente contra el repo por la auditoría**, no escritas a mano.
- **`bench_juez.py`** — con **grading en CÓDIGO PURO**: `respuesta_ok` y
  `cita_ok` leen la línea citada del disco con el `CITA_RE` **importado de
  `juez.py`**, el mismo regex de producción. No confiamos en el juez para
  calificar al juez: la verificación es determinista y ajena al LLM. La
  corrida es **secuencial y determinista**, y el baseline
  `salidas/evals/bench_juez.json` sigue el patrón de `evals.py`: **comparar
  sin pisar** (la corrida nueva se contrasta contra el baseline guardado, que
  no se sobrescribe).
- **Subcomando `main.py bench_juez`** para dispararlo desde la CLI.
- **5 tests** con `responder` *fake* inyectable, de modo que se ejercita el
  grading **sin LLM**.

La corrida baseline con LLM real la hace la **auditoría después** (no forma
parte de este cierre documental).

### Resultados del baseline (2 corridas, LLM real)

- **Corrida 1** (instrumento pre-calibración): `respuesta_ok` 64.7% (11/17),
  `cita_ok` 81.8% (9/11).
- **Corrida 2** (instrumento calibrado, baseline vigente): `respuesta_ok`
  76.5% (13/17), `cita_ok` 76.9% (10/13).

Hallazgos medidos:

1. **'verdict inválido' ESTOCÁSTICO del Judge** — 5/17 y 3/17 casos en cada
   corrida, SIEMPRE casos distintos, ~60s quemados por caso en 3 retries: el
   contrato YAML del verdict falla al azar en ~1 de cada 4-5 preguntas.
2. **trampa-delete-file falló 2/2 corridas** — el Draft alucina la herramienta
   inexistente y el Judge no contrasta contra el inventario real de tools.
3. **citas desviadas pasan el juez** — las 3 citas fallidas de la corrida 2 son
   near-misses que el Judge dejó pasar (línea 191 vs 195 real; 119/129 vs def
   real en 128; rutas falsas tipo `/fs_tools.py:64` que `read_file` no
   resuelve).
4. **la trampa de premisa falsa (Files API) la corrigió bien en la corrida 1**
   (pdftoppm con cita verificada).

Sobre el instrumento mismo: **contención por caso** (un caso que explota no
tira el bench — aprendido en la primera corrida real) y **calibración de
`cita_ok` a la ventana de 2 líneas de `Judge.prep`** (el bench no debe ser más
estricto que el contrato que mide).

## exp/21 — el verdict estocástico del juez: sondeado, endurecido, degradado (2026-10-07)

**La sonda** (`banco/probes/verdict_juez.py`, 9 respuestas del Judge con LLM
real sobre las 8 víctimas de exp/20) capturó la forma real del verdict
inválido: el sinónimo **`needs_changes`** — YAML perfectamente parseable,
falla **SEMÁNTICA**. Resultado: 8 ok válidas, 1 `needs_changes`.

**El fix en `juez.py` en tres capas**:

1. **Prompt endurecido** — el verdict SOLO `ok` o `retry`, literal.
2. **Normalización** `str`/`strip`/`lower` + `_ALIAS_VERDICT` con SOLO el
   sinónimo medido (`needs_changes`): el contrato se aprieta, no se afloja.
   *(Superado por la fase B2, abajo: el alias se eliminó — el verdict se
   repara con feedback; la canonicalización quedó.)*
3. **Degradación terminal en `responder_con_juez`** — flujo roto tras los
   retries con draft presente → se entrega el borrador con advertencia
   (patrón L8); sin draft se re-raise. `main.py juez` y `juez_lote` heredan.

**Re-medición del bench (fase C)**: `respuesta_ok` 76.5% → **94.1%**
(+17.6pp) y `cita_ok` 76.9% → **93.8%** (+16.8pp) en la corrida de
comparación; **CERO excepciones** (antes 3-5 por corrida). La corrida de
actualización del baseline reprodujo 94.1% (baseline vigente: `respuesta_ok`
94.1%, `cita_ok` 87.5%; dos corridas post-fix estables en 94.1).

**Residuales medidos que NO eran de este exp**: ~~trampa-delete-file sigue
fallando (3/3 corridas — la alucinación de tool inexistente, hallazgo 2 de
exp/20)~~ — **✅ cerrado en exp/42** (el Judge contrasta contra el
inventario real; ver la sección de exp/42). Quedan los near-miss de citas
(hallazgo 3) y, nuevo de exp/42, la ventana de 200 líneas del Draft frente
al modelo que hoy rehúsa fuera de lo verificado.

### Fase B2 — de parche a patrón (la crítica del dueño)

La fase B puso dos parches (la línea de prompt enumerando sinónimos
prohibidos y `_ALIAS_VERDICT` clavado al único sinónimo medido) que
perseguían el token observado: un sinónimo nuevo los atravesaba, y la
degradación sola convertía el crash en entrega sin juzgar. La crítica del
dueño del harness los tumbó. El reemplazo es el patrón propio del harness
(error-como-feedback, como el supervisor con args): un loop de reparación
que cita la respuesta inválida VERBATIM, más el motivo y el contrato
(marcador observable `[juez] verdict ilegible → reintento con feedback`),
con fallback semántico al lado seguro del contrato binario (retry con el
crudo citado, acotado por `max_rounds` L8) y canonicalización
`str`/`strip`/`lower` (ruido de codificación, no semántica). El test que
refuta el parche por existencia: `needs_changes` resuelto SIN alias, por el
feedback. Re-medición: `respuesta_ok` 94.1% sostenido sin parches (delta
0.0000), `cita_ok` 93.8% y en la corrida de actualización 16/16 (100%); el
marcador disparó 0 veces en ambas corridas — la línea honesta de contrato
bastó y el loop queda como armadura probada por tests. Baseline vigente:
94.1 / 100 sobre el sha del patrón. Residual único de respuesta:
trampa-delete-file (hallazgo 2 de exp/20).
