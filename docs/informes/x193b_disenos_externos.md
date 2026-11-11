# X193b — Revisión de los cuatro diseños fractales externos

> **Estado:** informe de revisión, 2026-11-11. Es la entrada del paso **X194**
> (el template del módulo) y de X196/X197/X199. No cambia producto; además de
> este informe, el paso aplica las dos correcciones a los docs de contrato
> (al final). La arquitectura que se revisa está en
> `docs/arquitectura.md` y las estrategias en `docs/estrategias.md`.

## Qué se leyó y hasta dónde

Las cuatro fuentes se bajaron por HTTP el 2026-11-11. Tres se leyeron
completas; de FRACTAL sólo el abstract de arXiv (v1). **Ninguna se ejecutó y
ningún número de ninguna se reprodujo.**

| Fuente | URL | Qué se leyó | ¿Trae mediciones? |
|---|---|---|---|
| FRACTAL-MAS, *Divide, Conquer, and Standardize* (ICLR Blogposts 2026) | https://iclr-blogposts.github.io/2026/blog/2026/fractal-mas/ | blog completo (secciones, diagramas y conclusiones) | **no**: "our immediate focus is to empirically evaluate this cost-benefit trade-off" |
| FRACTAL, *A Self-Similar Multi-Agent Orchestration Architecture with Formal Communication, Convergence, and Depth Bounds* (arXiv 2610.22561, 2026-10-15) | https://arxiv.org/abs/2610.22561 | **abstract** (v1) | **no**: "we do not report quantitative performance claims in this paper"; "Empirical validation … left to future work" |
| Lár, *Recursive Graph Composition* (docs del producto, snath-ai/lar) | https://docs.snath.ai/core-concepts/11-fractal-agency/ | página de *Core Concepts* completa (validator inheritance, budgets, compliance gap) | **no**: documentación de producto |
| FractFlow (repositorio, EnVision-Research) | https://github.com/EnVision-Research/FractFlow | README completo | **no**: "The project is still under development" |

**Consecuencia de método.** Ninguna de las cuatro sirve como evidencia: sirven
para decidir **forma**, no para abrir un A/B. Eso está alineado con la regla de
`docs/estrategias.md:8-19`: un principio no se cierra ni se abre por una
arquitectura sin medición. FRACTAL lo dice en sus propias palabras —usa
"fractal" como "an architectural metaphor for self-similarity, not a measured
mathematical property"— y es la misma disciplina con la que el repo midió la
asimetría y la dejó no adoptada (`docs/estrategias.md:42-54`).

## Veredicto en una tabla

| Fuente | Se adopta | No se adopta (y por qué) |
|---|---|---|
| **FRACTAL-MAS** | un **solo despacho polimórfico**: la misma arista decide tool o hijo por el flag `agente`; el verificador existe **sólo** donde hay artifact verificable (`veredicto`/`hallazgos`) | **memoria procedimental (CBR)**: no hay planes que recuperar (`utils/tracing.py:59-77` guarda nodo/acción/segundos, un discriminador corto y un hash de los argumentos, **sin contenido**), `memoria` es biblioteca y no banco de planes, y es un mecanismo nuevo sin medición (N1) |
| **FRACTAL** | **protocolo de dos fases** (propuesta ciega → *stress test*) para el council (X196); **profundidad y N como datos**, con un tope duro; **saturación de diversidad** como señal a pre-registrar (X199) | **escalado bayesiano** entre capas; **convergencia por supermayoría** como código (la del repo es voto de 3 con desempate y el paper asume evaluador fijo); **los cinco componentes en cada nodo** (contradice P1 y `docs/estrategias.md:132-134`) |
| **Lár** | **la evidencia por rama sobrevive al reduce y llega a la puerta humana** (no una puerta por rama: *una* puerta, antes del agregado, con las filas); **el conector no acepta política/validador por parámetro** | **que el LLM diseñe el grafo** (`AdaptiveNode`): acá la composición la declara el operador (`docs/arquitectura.md:100-102`) y la decisión del modelo ya se midió y no se adoptó (exp/103–110); **tope de nodos** (`max_nodes`), porque el autor del spec acá es el operador, no el modelo; **HMAC, PII y EU AI Act**, que no son principios de este harness |
| **FractFlow** | **una sola descripción por módulo**: el catálogo (X198) lee `TOOLS[i].function.description`, no un manifiesto paralelo | **tres modos de corrida** (el repo ya tiene `main.py` + `mcp_server`), **entornos `uv` por tool** y **config por tool**: comodidad, no necesidad medida (P1, dependencias mínimas) |

## 1. FRACTAL-MAS — la forma recursiva y el agente como herramienta

**Qué propone.** Que "the structure of the MAS must be isomorphic to the
structure of an individual agent": en cada nivel, un agente básico con memoria
procedimental, planner, orquestador **determinista**, ejecutor (cliente MCP) y
supervisor que verifica antes de dar por cerrada la subtarea. En el nivel de
sistema, el ejecutor usa A2A para delegar a otros agentes, que a su vez usan MCP
para sus tools; de ahí "**Agent-as-a-Tool**" y la posibilidad de pasar de una
jerarquía rígida a una red descentralizada.

**Qué confirma del repo.** Tres cosas que ya son verdad y no hay que inventar:

1. **El isomorfismo es de ejecución, no de archivos.** El repo ya lo tiene en
   `utils/kernel.py:193` (`loop`) y `:243` (`agente`): el chat, el supervisor y
   una capacidad son la misma instancia con otros datos (`docs/arquitectura.md:28`).
2. **El agente como herramienta ya es una pieza del kernel**: `Tool(..., agente=True, hijas=...)`
   (`utils/kernel.py:60-69`, `:281-284`). No hace falta una primitiva nueva.
3. **Los dos protocolos existen como módulos separados**: `mcp_server.py` y
   `modules/a2a.py`; pero la arista del grafo **no** los distingue hoy: un hijo
   es una `Tool` in-process.

**Se adopta (para X194).** Una sola arista para las dos cosas: el conector
declara **qué consume y qué produce** y el despacho elige tool o hijo por el
flag `agente`, sin un "nodo hijo" aparte. Es la parte que el repo puede tomar
sin sumar mecanismo: `docs/arquitectura.md:58-71` ya dice que el conector
extiende la `Tool` del kernel, y esto lo cierra: **una forma de conectar, dos
implementaciones detrás**.

**Se adopta con recorte.** El "supervisor dentro de cada agente" del post no
entra al contrato como paso obligatorio: entra como **declaración**. Un módulo
que produce `veredicto` o `hallazgos` declara su verificación (el repo ya tiene
la compuerta de `fable_judge` y el juez de respuestas); uno que produce
`borrador` no la necesita. Obligarla en todos sería el "cinco componentes en
cada nodo" que `docs/estrategias.md:132-134` rechaza por P1.

**No se adopta: memoria procedimental (CBR).** El post la pone como el
componente que más reduce alucinaciones: recuperar trazas de ejecución exitosas
(estado, plan, recompensa) para guiar al planner. Acá choca con cuatro hechos:
(1) el repo **no guarda planes** en sus trazas —`utils/tracing.py:59-77`: nodo,
acción, segundos, un `codigo` corto y una `huella` que es un hash de
(nombre, argumentos); el contrato del archivo dice "sin contenido"—; (2) `modules/memoria.py`
es una biblioteca que el modelo consulta, no un banco de casos con recompensa;
(3) es un mecanismo nuevo y por N1 no entra sin medición que lo justifique;
(4) es la clase de feature que engorda cada módulo (P1, EL7). Si alguna vez se
quiere, es un pre-registro propio: qué se guarda, qué se recupera, contra qué
se mide.

**Caveat de la fuente.** El propio post dice que la recursión "inherently
introduces a higher computational overhead" y que el siguiente paso es medirlo.
Es exactamente el estado del repo: la forma está escrita y el costo no.

## 2. FRACTAL — el protocolo del concilio y los límites

**Qué propone.** El mismo patrón de cinco componentes en cada nivel
(Orchestrator, Ensemble, Knowledge Ledger, Decision Maker, Meta-Observer) y
cuatro aportes formales: (1) cota de comunicación **lineal O(kr)** con un
protocolo de dos fases —propuesta ciega y *stress test*— contra el costo
cuadrático del debate libre, **bajo el supuesto declarado de evaluador fijo**;
(2) criterio de dos modos (generativo vs. evaluativo) con un **umbral medible de
saturación de diversidad**; (3) convergencia por supermayoría con cotas de
probabilidad y **cota formal de profundidad** según una medida operacionalizada
de complejidad del objetivo; (4) **escalado bayesiano** entre capas.

**Qué confirma del repo.** Que la diversidad es el eje: la fuente que el repo
ya citaba desde X144 —dos agentes diversos igualan o superan a 16 iguales— es la
versión empírica de la saturación que acá aparece como umbral formal. También
confirma que la asimetría medida en exp/110 (diferenciación real, no copias
iguales) es la variable correcta; lo que faltó fue el régimen.

**Se adopta (para X196).** El **protocolo de dos fases** en el council. Hoy
`debate.py:136-156` corre dos roles en paralelo con colas y un juez final; con
k miembros, el costo sólo queda en O(kr) si cada ronda separa **propuestas
ciegas** (nadie ve las de los demás) de la **refutación** (todos ven todas). Es
una decisión de interfaz, no una promesa de rendimiento: el estado del council
lleva las dos fases y el tamaño de cada ronda es acotado por construcción.

**Se adopta (para X199).** **Profundidad y N como datos declarados, con tope
duro.** El repo ya tiene el tope duro —la **Ley 1** (`docs/principios.md:53`:
llamadas ≤ 2R + 1 con cualquier abanico y profundidad) y la forma de la
herencia (`hijas`, `utils/kernel.py:205`)— y ya tiene la forma de declarar
(`docs/arquitectura.md:100-102`). Lo que FRACTAL
agrega es que el número **dependa de una medida de complejidad**, y ahí el repo
todavía no tiene esa medida: la cota de profundidad queda **declarada y
bounded por el tope duro**, y atarla a una señal medida es el pre-registro de
X199, no código de X194.

**Se adopta como pre-registro.** **Saturación de diversidad** y **dos modos**
(generativo vs. evaluativo) son las dos preguntas que X199 tiene que contestar
antes de correr: qué señal dice "más copias no ayudan" y en qué fase del flujo
está parado el swarm. No se implementan ahora.

**No se adopta.** (a) **Escalado bayesiano**: mecanismo nuevo, sin problema
medido en el repo (N1). (b) **Convergencia por supermayoría como código**: el
voto del repo es de 3 con desempate y las cotas del paper asumen un número fijo
de evaluadores; cambiarlo es un pre-registro, no un ajuste. (c) **Los cinco
componentes por nodo**: el nodo del repo es el loop mínimo y lo demás es módulo
opcional (`docs/estrategias.md:132-134`); cinco componentes por nodo es la
forma contraria.

**Caveat de la fuente.** No reporta resultados cuantitativos y declara que
"fractal" es metáfora. Las cotas son sobre protocolo, no sobre calidad: sirven
para **estructurar** el concilio, no para afirmar que gana.

## 3. Lár — la evidencia por rama y la herencia de validadores

**Qué propone.** Combinar `AdaptiveNode` (un manager hace **una** llamada al LLM
que diseña el grafo como spec JSON) con `BatchNode` (ramas en paralelo), un
`TopologyValidator` que valida ciclos, allowlist de tools, `max_nodes` y
`max_depth`, y **herencia del validador**: el mismo validador y los mismos
límites bajan a cada hijo. El presupuesto se comparte entre ramas y se
reconcilia después del merge. Y el hallazgo central: **la brecha de
cumplimiento** —la "jury" humana ve el puntaje consolidado y no la rama que
disparó la alerta, así que aprueba sin saber por qué—. Su arreglo es un nodo
que escribe las conclusiones **por rama** en el estado y **adelanta la puerta
humana antes del reduce**, para que el humano vea el desglose y no el agregado.

**Qué confirma del repo.** Dos de las tres piezas ya son contratos:

1. **Herencia de validadores** es `hijas` (X147): al armar el loop se rechaza un
   hijo con tools que el padre no tiene (`utils/kernel.py:205`), y el gate
   fractal verifica que una política agregada una vez llega igual al chat, al
   supervisor y a una copia (`tests/test_gate_fractal.py:144,483`). El conector
   de `docs/arquitectura.md:26` dice lo mismo: S0 vive en el conector.
2. **Saldo compartido y reconciliado después del merge** es exactamente lo que
   el repo acaba de medir en X201/X202: una capacidad hizo llamadas que el
   `Ledger` del chat no contaba; hoy las cobra (`utils/tracing.py`, X202) y falta
   el supervisor (`docs/arquitectura.md:143`). Lár vende como diseño lo que acá
   ya es un hallazgo medido.

**Se adopta (para X194/X197).** **La evidencia por rama sobrevive al reduce.**
Con dos precisiones que corrigen la tabla de `docs/estrategias.md:125-130`:

- **No es "una puerta por rama"**: el diseño de Lár deja **una** puerta y la
  corre **antes del agregado**, con las filas por rama en el contexto de la
  decisión. Una puerta por rama multiplicaría la fricción (S0 sube sin ganar
  información); una puerta con evidencia no.
- El repo ya tiene el precedente en lote: `juez_lote.informe_lote` arma **una
  sección por ítem** con su veredicto y su motivo (`juez_lote.py:118-140`). Lo
  que el template tiene que hacer es que eso sea **contrato del artifact**
  (`hallazgos`/`veredicto` con filas por rama), no una decisión de cada módulo.

**Se adopta como contrato negativo.** El conector **no acepta** validador,
política ni allowlist por parámetro: la herencia es por construcción. El repo ya
se negó a abrir esa puerta en X157 (sumar `politica` a `Ctx` habría permitido un
hijo con otra política que su padre); Lár confirma que la herencia es la
propiedad y no un detalle.

**No se adopta.** (a) **Que el LLM diseñe el grafo**: acá la composición la
declara el operador (`docs/arquitectura.md:100-102`) y "el modelo decide" ya se
midió tres veces sin adopción (`docs/estrategias.md:44-54`). (b) **`max_nodes`**:
el riesgo que cubre es que un LLM genere un subgrafo arbitrariamente grande; acá
el autor del spec es el operador y los topes son de presupuesto (L8), no de
cantidad de nodos. (c) **HMAC de trazas, redacción de PII y cumplimiento del EU
AI Act**: es el encuadre normativo del producto, no un principio de este
harness; traerlo sería cambiar el alcance sin decisión del operador.

**Caveat de la fuente.** Documentación de producto con encuadre normativo; las
afirmaciones son de diseño, no medidas.

## 4. FractFlow — el molde del tool y la descripción como interfaz

**Qué propone.** `ToolTemplate`: `SYSTEM_PROMPT`, `TOOL_DESCRIPTION`, `TOOLS`
(dependencias) y `create_config`; tres modos de corrida (servidor MCP,
interactivo, consulta única); composición por anidamiento (una tool compuesta
llama a las de abajo); y la regla que importa: **`TOOL_DESCRIPTION` es el manual
que lee el agente de arriba** para decidir cuándo y cómo llamar. Suma entornos
`uv` aislados por tool para conflictos de dependencias.

**Qué confirma del repo.** Que la forma ya es la del repo: un módulo es un
archivo con `TOOLS` (lo que ve el modelo) e `IMPL` (cómo se corre)
(`docs/arquitectura.md:54-56`, `docs/estrategias.md:115`), y el `discover()` es
el catálogo. FractFlow es la versión con clase y runner de lo que acá es un
contrato de datos.

**Se adopta (para X194/X198).** **Una sola descripción por módulo.** El catálogo
(X198) tiene que leer `TOOLS[i].function.description` —la misma que ya viaja en
el request— y no inventar un manifiesto paralelo: dos textos que describen la
misma capacidad derivan (es la clase de deriva que el repo ya caza con
`tests/test_docs_sin_deriva.py`). También entra la idea de que la descripción
tiene un lector distinto del prompt: **lo lee el de arriba**, no el propio
módulo (N3: nada por prompt).

**No se adopta.** (a) **Los tres modos de corrida** como requisito del template:
el repo ya tiene `main.py` por subcomando y `mcp_server`; sumarlos al contrato es
comodidad (P1). (b) **Entornos `uv` por tool**: el repo es deliberadamente
mínimo (stdlib + dependencias pinneadas); un mecanismo de entornos por pieza
necesita un conflicto medido. (c) **Configuración por tool**
(`max_iterations`, `timeout`): el presupuesto es del árbol (L8), no de la pieza.

**Caveat de la fuente.** README de un proyecto en desarrollo, sin mediciones;
es el más útil de los cuatro como **molde de archivo** y el menos útil como
evidencia.

## Lo que esto le deja a X194 (la entrada del template)

Lo que el contrato del template tiene que decir, con su origen y su evidencia
en el repo. Ocho ítems: siete obligaciones y un contrato negativo (el 3).

| # | Ítem del contrato | Origen | Evidencia en el repo | Puerta |
|---|---|---|---|---|
| 1 | consume/produce en tipos de artifact, con **procedencia** y **citas** | FRACTAL-MAS (interfaces estandarizadas) + Lár (evidencia por rama) | `docs/arquitectura.md:58-63,92-96`; `utils/citas.py` ya verifica | test de contrato (X194) |
| 2 | la lógica interna es una instancia de `kernel.loop`, con su saldo | FRACTAL-MAS (loop unificado) | `utils/kernel.py:193,243`; `docs/arquitectura.md:61-62` | P2 (a) |
| 3 | hereda S0 y el saldo **sin parámetro**: no se le pasa política ni validador | Lár (validator inheritance) | `utils/kernel.py:205`; `tests/test_gate_fractal.py:144,483`; X157 | el de S0 (`docs/principios.md`) |
| 4 | una sola arista: tool o hijo por el flag `agente` | FRACTAL-MAS (agent-as-a-tool, ejecución polimórfica) | `utils/kernel.py:60-69,281-284`; `utils/fs_tools.py` (despacho único) | gate fractal |
| 5 | **una descripción por módulo**, y la lee el de arriba | FractFlow | `modules/__init__.py` (`discover()`); `TOOLS[i].function.description` | `tests/test_docs_sin_deriva.py` (no dos textos) |
| 6 | filas por rama en `hallazgos`/`veredicto`, visibles en la puerta humana **antes** del agregado | Lár (la brecha de cumplimiento) | `juez_lote.py:118-140` (una sección por ítem) | el de S0 + el de X194 |
| 7 | el council separa **propuesta ciega** de **refutación** | FRACTAL (O(kr) vs cuadrático) | `debate.py:136-156` (dos roles con colas hoy) | X196 |
| 8 | profundidad y N **declarados**, con tope duro; la señal de saturación es pre-registro | FRACTAL | `docs/principios.md:53` (Ley 1); `utils/kernel.py:205` (`hijas`); `docs/arquitectura.md:100-102` | X199 |

**No entra al contrato**, y conviene que quede escrito para no reabrirlo:
memoria procedimental/CBR y supervisión obligatoria en todos los módulos
(FRACTAL-MAS); escalado bayesiano y supermayoría como código (FRACTAL); que el
LLM diseñe el grafo y `max_nodes` (Lár); tres modos de corrida, entornos `uv` y
config por tool (FractFlow).

## Dos correcciones a los docs (aplicadas en este paso)

Aplicadas junto con este informe: las dos son docs de contrato y cierran la
revisión.

1. `docs/estrategias.md:127-130` — la tabla ya dice lo que dicen las fuentes:
   Lár pide **una** puerta **antes del reduce, con las filas por rama** (no una
   por rama); FRACTAL-MAS aporta la **uniformidad de la arista** (MCP y A2A ya
   existen); FractFlow, **una descripción sola**; FRACTAL, **dos fases y una
   señal medible** (su cota de profundidad necesita una medida que el repo no
   tiene todavía).
2. `docs/arquitectura.md:68-71` — el template nombra el **contrato negativo**:
   el conector no recibe política ni validador por parámetro porque la herencia
   es por construcción (X157 y el gate fractal ya lo sostenían; ahora está
   escrito en el template).

## Límites declarados

- **FRACTAL por abstract**: no se leyó el PDF; las cuatro contribuciones se
  citan como las enuncia el abstract (v1, 2026-10-15), no verificadas.
- **Ninguna fuente trae resultados**: las cuatro se usan para forma. Cualquier
  afirmación de rendimiento de este informe sería inventada.
- **Ninguno de los cuatro se ejecutó** ni se reprodujo su código; FractFlow y
  Lár son implementaciones, pero revisarlas en ejecución es otro paso.
- Las citas al repo se escribieron contra `5da6178` y se verificaron sobre el
  árbol de este commit: las líneas de `utils/`, `tests/` y `docs/` existen como
  se citan.
