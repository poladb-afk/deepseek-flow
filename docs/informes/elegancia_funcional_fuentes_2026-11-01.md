# Elegancia funcional: mecanismos de composición y anidamiento en fuentes primarias

Qué mecanismos existen, en fuentes primarias, para que poquísimas primitivas que se contienen a sí mismas den complejidad emergente; y qué límites declara cada fuente. Fecha: 2026-11-01.

Método: cada URL se abrió con `web_fetch` el 2026-11-01. Las citas son literales de la página fetcheada. Lo que la fuente no dice, se marca como no dicho.

## 1. Fuentes que el repo ya cita — verificación

| # | URL | Estado | Cita literal |
|---|---|---|---|
| 1 | https://github.com/The-Pocket/PocketFlow | OK | "Just 100 lines. Zero bloat, zero dependencies, zero vendor lock-in." |
| 2 | https://github.com/humanlayer/12-factor-agents | OK | "Rather than building monolithic agents that try to do everything, build small, focused agents that do one thing well." |
| 3 | https://www.anthropic.com/engineering/building-effective-agents | OK (redirige a `/research/building-effective-agents`) | "the most successful implementations weren't using complex frameworks or specialized libraries" |
| 4 | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | OK (redirige a `/research/…`) | "engineers hardcoding complex, brittle logic in their prompts" |
| 5 | https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus | OK | "avoid dynamically adding or removing tools mid-iteration" |
| 6 | https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills | OK (redirige a `/research/…`) | "Progressive disclosure is the core design principle that makes Agent Skills flexible and scalable." |
| 7 | http://www.incompleteideas.net/IncIdeas/BitterLesson.html | OK | "general methods that leverage computation are ultimately the most effective, and by a large margin." |
| 8 | https://github.com/SWE-agent/mini-swe-agent | OK | "Just some 100 lines of python for the agent class" |
| 9 | https://arxiv.org/abs/2405.15793 | OK | "SWE-agent's custom agent-computer interface (ACI) significantly enhances an agent's ability to create and edit code files" |
| 10 | https://arxiv.org/abs/2511.13972 | OK | "Combined prompts produced the strongest initial compression and greatest expansion discipline." |
| 11 | https://doi.org/10.1145/361598.361623 | **No se pudo fetchear** | Sin cita. `doi.org` redirige cross-origin a `dl.acm.org`; esa página devuelve HTTP 403 con "Just a moment...". |
| 12 | https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html | OK | "This rule says that source code dependencies can only point inwards." |
| 13 | https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell | OK | "This functional core is surrounded by a shell of imperative code" |
| 14 | https://martinfowler.com/bliki/Yagni.html | OK | "you shouldn't build it until it's necessary" |
| 15 | https://github.com/monk-eee/git-agent-ratchet | OK | "The rule didn't change. The cost of breaking it did." |
| 16 | https://github.com/NandhaKishorM/laya | OK | "Laya evaluates typed questions (`choice`, `score`, `noul`) over any state" |
| 17 | https://arxiv.org/abs/2605.06639 | OK | "agents that can spawn and delegate sub-tasks to new instantiations of themselves recursively" |
| 18 | https://arxiv.org/abs/2606.13643 | OK | "the recursive unit is a full agent harness with filesystem tools, code execution, and planning rather than a model call with no tools" |
| 19 | https://arxiv.org/abs/2512.24601 | OK | "allows the LLM to programmatically examine, decompose, and recursively call itself over snippets of the prompt" |
| 20 | https://doi.org/10.21203/rs.3.rs-8414536/v1 | **Parcial** | Sin cita del resumen. El DOI redirige cross-origin; en `researchsquare.com/article/rs-8414536/v1` responde HTTP 200 con el cuerpo vacío: solo se lee el título "Towards a Science of Scaling Agent Systems". |
| 21 | https://doi.org/10.48550/arxiv.2604.02460 | OK (reintento en `https://arxiv.org/abs/2604.02460`) | "SAS consistently match or outperform MAS on multi-hop reasoning tasks when reasoning tokens are held constant." |
| 22 | https://github.com/DietrichGebert/ponytail | OK | "write only what the task needs, and never cut validation, error handling, security, or accessibility." |
| 23 | https://www.cos.io/initiatives/prereg | OK | "you're simply specifying your research plan in advance of your study and submitting it to a registry" |

Citas marcadas con fuente distinta de la URL del repo (mismo proyecto, otro host, fetcheadas OK):

- #1: https://raw.githubusercontent.com/The-Pocket/PocketFlow/main/README.md
- #8: https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/README.md
- #15: https://raw.githubusercontent.com/monk-eee/git-agent-ratchet/main/README.md
- #16: https://raw.githubusercontent.com/NandhaKishorM/laya/main/README.md
- #22: https://raw.githubusercontent.com/DietrichGebert/ponytail/main/README.md
- #2: https://raw.githubusercontent.com/humanlayer/12-factor-agents/main/content/factor-10-small-focused-agents.md
- #11: sin fuente.

### Hallazgos de la verificación

- **R3 roto en un caso y flojo en cuatro.** El DOI de Parnas no entrega contenido (403). No se puede probar la atribución del repo a esa URL.
- **#10 no dice el número que el repo le atribuye.** El repo cita "56–70 % menos tokens"; el resumen no da ninguna cifra de tokens, solo "initial compression" y "expansion discipline". El número no está en la fuente fetcheada.
- **#9 no menciona el linter.** El repo le atribuye "el linter en la edición como guardrail medido"; el resumen habla de la ACI y de editar código, no de un linter.
- **#18 no declara "profundidad acotada".** `docs/elegancia.md` y `docs/principios.md` se lo atribuyen a RAH; el resumen no menciona ningún tope de profundidad.
- **Factor 12 no tiene prosa.** La página `factor-12-stateless-reducer.md` son dos imágenes y un "mostly just for fun"; el `foldl` que el repo le atribuye aparece solo en el nombre de archivo de una imagen (`1c5-agent-foldl.png`), no en el texto.
- **Otros dos DOIs redirigen cross-origin.** #20 y #21 no se pueden leer en `doi.org`; #21 se verificó en `arxiv.org/abs/2604.02460`, #20 no tiene versión legible.

## 2. Ideas de composición y anidamiento

### a) PocketFlow: `Flow` hereda de `Node`, y un flujo se ejecuta donde va un nodo

- **Fuente primaria.** https://raw.githubusercontent.com/The-Pocket/PocketFlow/main/pocketflow/__init__.py (fetcheado OK).
- **Cita.** `class Flow(BaseNode):` … `def _run(self,shared): p=self.prep(shared); o=self._orch(shared); return self.post(shared,p,o)`.
- **Qué permite.** Un `Flow` es un `BaseNode`: expone `run`, `prep`, `post`, `_run`. El anidamiento sale gratis: `_orch` recorre sucesores y llama `curr._run(shared)`; si `curr` es otro `Flow`, adentro corre su propio `_orch`. La contención también está declarada al revés: `BaseNode.run` avisa "Node won't run successors. Use Flow.", y `Flow.post` devuelve `exec_res`, que es la última acción del grafo interno. Además `AsyncFlow(Flow, AsyncNode)` muestra la misma primitiva en la variante async.
- **Límites.** El código no declara tope de profundidad: `_orch` corta cuando no hay sucesor (`while curr`). La fuente no dice qué pasa con un ciclo que nunca cambia de acción. Costo visible: cada nodo se `copy.copy` antes de correr, y los `params` se setean por paso (`curr.set_params(p)`), así que el estado mutable del nodo no se comparte entre ejecuciones.

### b) Composite (GoF): hoja y compuesto con la misma interfaz

- **Fuente primaria.** Capítulo Composite del libro de GoF, copia HTML en https://www.cs.unc.edu/~stotts/GOF/hires/pat4c.htm (fetcheado OK; la portada `pat4cfso.htm` es solo un frameset).
- **Cita.** "Compose objects into tree structures to represent part-whole hierarchies. Composite lets clients treat individual objects and compositions of objects uniformly."
- **Qué permite.** Es el patrón exacto de "un flujo es un nodo": un `Component` declara la interfaz, `Leaf` la implementa sin hijos, `Composite` la implementa reenviando a sus hijos. La fuente lo dice: "Picture implements Draw to call Draw on its children… Picture objects can compose other Pictures recursively".
- **Límites.** "can make your design overly general… it makes it harder to restrict the components of a composite. Sometimes you want a composite to have only certain components." Con Composite "you can't rely on the type system to enforce those constraints for you. You'll have to use run-time checks instead." Es el costo directo de uniformar hoja y compuesto.

### c) Statecharts de Harel: estados compuestos y anidados

- **Fuente.** El paper de 1987 no se pudo fetchear: la copia de Weizmann da 404 y `sciencedirect.com/science/article/pii/0167642387900359` devuelve 403. Se usa el doc que lo describe y lo cita: W3C SCXML, https://www.w3.org/TR/scxml/ (OK).
- **Cita.** "a <state> element may contain nested <state> elements. Such a state is called a compound state".
- **Qué permite.** Anidar sin límite ("The child states may themselves have nested children and the nesting may proceed to any depth"), con dos propiedades que sirven para un harness: la transición de un ancestro es el default de sus descendientes ("transitions in ancestor states serve as defaults that will be taken if no transition matches in a descendant state"), y el estado compuesto encapsula su interior ("The presence of default initial states provides a form of encapsulation, since a transition may select a compound state as its target without understanding its internal substate structure").
- **Límites.** La semántica no es barata: el spec necesita el "Least Common Compound Ancestor", conjuntos de salida/entrada y un algoritmo entero (Apéndice D). El paralelismo es simulado: los hijos de `<parallel>` "process the event in a defined, serial order, so no conflicts or race conditions can occur". La fuente no fija un tope de profundidad.

### d) Erlang/OTP: worker y supervisor son el mismo tipo de hijo

- **Fuente primaria.** https://www.erlang.org/doc/system/sup_princ.html (OK).
- **Cita.** "A supervisor is responsible for starting, stopping, and monitoring its child processes."
- **Qué permite.** Una sola especificación de hijo (`type => worker | supervisor`) hace que un supervisor sea hijo de otro supervisor: la jerarquía es la misma estructura repetida. `one_for_one`, `one_for_all` y `rest_for_one` son datos de configuración, no código nuevo.
- **Límites.** El freno es explícito y numérico: "If more than `MaxR` number of restarts occur in the last `MaxT` seconds, the supervisor terminates all the child processes and then itself." Y anidar multiplica el presupuesto: "the total number of restarts (before the top level supervisor gives up and terminates the application) will be the product of the intensity values of all the supervisors above the failing child process." Costo extra: "the supervisor process will be blocked while it is performing any of those operations" (start, restart, terminate).

### e) Parser combinators: pocas primitivas que componen gramáticas

- **Fuente.** El paper de Hutton & Meijer no se pudo leer: `https://people.cs.nott.ac.uk/pszgmh/monparsing.pdf` responde pero con `application/pdf`, que la herramienta no decodifica. Se usa la doc oficial de `Text.ParserCombinators.ReadP` (base de GHC, Koen Claessen): https://hackage-content.haskell.org/package/base-4.21.0.0/docs/Text-ParserCombinators-ReadP.html (OK).
- **Cita.** "choice :: [ReadP a] -> ReadP a — Combines all parsers in the specified list."
- **Qué permite.** La página separa "Primitive operations" (`get`, `look`, `(+++)`, `(<++)`, `pfail`) de todo lo demás, y todo lo demás se define combinando: `many`, `sepBy`, `between`, `chainl1`, `manyTill`. Un parser es un valor (`ReadP a`) que se pasa, se compone y se corre con `readP_to_S`.
- **Límites.** "Note that this kind of backtracking parser is very inefficient; reading a large structure may be quite slow." Y `readS_to_P` "introduces local backtracking in the resulting parser, and therefore a possible inefficiency". La fuente no dice que las gramáticas arbitrarias entren sin costo.

### f) Lógica combinatoria: dos combinadores dan universalidad, incluida la auto-aplicación

- **Fuente primaria.** Stanford Encyclopedia of Philosophy, "Combinatory Logic": https://plato.stanford.edu/entries/logic-combinatory/ (OK).
- **Cita.** "he established that S and K suffice to define all the other combinators."
- **Qué permite.** Todo término se arma aplicando `S` y `K`; de ahí salen `I = SKK`, `B`, `C`, `W` y el punto fijo `Y`, que resuelve toda ecuación recursiva. La fuente también marca lo que el repo busca: "pure untyped CL does not exclude the self-application of functions", y "its mathematical models showed that a theory in which functions can become their own arguments is completely sensible".
- **Límites.** Dos, declarados. (1) El tipado: "no self-application is typable in a Church-style typing system" — si las decisiones se vuelven datos tipados, la auto-aplicación se pierde. (2) La potencia se paga: "CL is susceptible to Gödel-type incompleteness theorems", "the problem of the equality of combinatory terms is undecidable", y la abstracción de corchetes puede devolver términos mucho más largos (el texto muestra que sin la cláusula η sale "a much longer term").

### g) Concurrencia estructurada: árbol de tareas con cancelación heredada

- **Fuente primaria.** Doc oficial de Kotlin: https://kotlinlang.org/docs/coroutines-basics.html (OK).
- **Cita.** "A parent coroutine waits for its children to complete before it finishes. If the parent coroutine fails or gets canceled, all its child coroutines are recursively canceled too."
- **Qué permite.** La jerarquía no es una convención: "new coroutines can only be launched in a `CoroutineScope`" que define y administra su ciclo de vida. `coroutineScope()` crea la raíz de un subárbol y espera a que termine; el contexto (dispatcher, cancelación) se hereda.
- **Límites.** La página no declara un tope de profundidad ni de cantidad de hijos: "la fuente no lo dice". El único costo que menciona es de otra capa: los hilos (no las corrutinas) consumen memoria, y por eso 50 000 corrutinas caben donde 50 000 hilos no.

### h) Llamada de cola / trampolín: anidar sin crecer la pila

- **Fuente primaria.** Especificación R7RS de Scheme, §3.5: https://standards.scheme.org/corrected-r7rs/r7rs-Z-H-5.html (OK).
- **Cita.** "A Scheme implementation is properly tail-recursive if it supports an unbounded number of active tail calls."
- **Qué permite.** Una recursión que se llama a sí misma en posición de cola no acumula marcos: "no space is needed for an active tail call because the continuation that is used in the tail call has the same semantics as the continuation passed to the procedure containing the call". Es el mecanismo que hace que un loop que se contiene a sí mismo no dependa de la profundidad.
- **Límites.** Solo vale en "tail position", y la spec tiene que enumerar los contextos de cola uno por uno (`if`, `cond`, `let`, `do`, `and`, `or`, …). Fuera de esa posición el anidamiento vuelve a crecer. El documento no promete nada sobre el costo en tiempo.

### i) Filosofía Unix: programas chicos y composición por streams

- **Fuente primaria.** *The Art of Unix Programming*, cap. 1, "Basics of the Unix Philosophy": http://www.catb.org/esr/writings/taoup/html/ch01s06.html (OK), citando a McIlroy.
- **Cita.** "Write programs that do one thing and do it well. Write programs to work together."
- **Qué permite.** El contrato de composición es un formato común (texto), no una interfaz rica: por eso cualquier programa puede ser entrada de cualquier otro. La regla del libro: "Rule of Composition: Design programs to be connected to other programs."
- **Límites.** "To make programs composable, make them independent. A program on one end of a text stream should care as little as possible about the program on the other end." El precio es explícito: "accept a little parsing overhead in return for being able to hack the data stream with general-purpose tools". La fuente no da un criterio de cuándo el pipe deja de convenir.

### j) Agentes recursivos (RAO, RAH, RLM): qué anidan y qué declaran

- **Fuentes.** https://arxiv.org/abs/2605.06639 · https://arxiv.org/abs/2606.13643 · https://arxiv.org/abs/2512.24601 (las tres OK).
- **Citas.** RAO: "agents that can spawn and delegate sub-tasks to new instantiations of themselves recursively". RAH: "A parent agent generates and runs an executable script that spawns subagent harnesses in parallel for fine-grained workloads and uses structured function calls for small subtasks." RLM: "treats long prompts as part of an external environment and allows the LLM to programmatically examine, decompose, and recursively call itself over snippets of the prompt".
- **Qué permite.** RAO: la política se entrena para decidir cuándo delegar. RAH: la unidad recursiva es el harness completo (herramientas de filesystem, ejecución de código, planning), no la llamada al modelo; la ganancia "attributable to the harness rather than the model". RLM: el padre no arrastra el contexto completo; el hijo devuelve un resumen (el repo lo usa así en `docs/principios.md`).
- **Límites.** RLM declara escala ("up to two orders of magnitude beyond model context windows") y costo "comparable", no gratis. RAH y RAO no declaran tope de profundidad en el resumen: **la fuente no lo dice**. Ninguno de los tres resúmenes habla de un presupuesto de anidamiento por nivel; el freno que nombran es contexto/cómputo.

## 3. Ideas descartadas o no verificables

- **Parnas, *On the criteria…* (DOI 10.1145/361598.361623).** No se pudo fetchear (403 Cloudflare). Además no es un mecanismo de anidamiento: su idea es ocultar una decisión de diseño por módulo. Queda como fuente no verificada, no como fuente del mecanismo.
- ***Towards a Science of Scaling Agent Systems* (DOI 10.21203/rs.3.rs-8414536/v1).** Página vacía para el fetcher: solo el título. No se puede citar el hallazgo ("más agentes dañan en tareas secuenciales") sin inventarlo.
- **Paper de statecharts de Harel (1987).** No legible: la copia de Weizmann da 404 y ScienceDirect 403. Se reemplazó por SCXML, que describe la notación y la atribuye a Harel; el paper en sí queda no verificado.
- **Hutton & Meijer, *Monadic Parser Combinators*.** El PDF responde pero la herramienta no decodifica `application/pdf`. Se reemplazó por la doc de `ReadP`; el paper queda no verificado.
- **`statecharts.org`.** Redirige a `itemis.com`, sitio comercial. Descartado como fuente.
- **`c2.com` (Composite).** Wiki de la comunidad, secundaria: resume el libro. Descartado; se usó el capítulo del libro.
- **Factor 12 de 12-Factor Agents como "foldl".** La página no tiene prosa sobre `foldl`: son dos imágenes y un cierre. La atribución del repo no se sostiene con el texto.
- **El sitio de docs de PocketFlow.** No se localizó una página de docs que explique el anidamiento; el mecanismo se prueba en el código (`__init__.py`) y en el README. La doc online queda no verificada.

## 4. Lectura de conjunto

1. (lectura mía) Las diez fuentes convergen en una sola operación: un tipo que puede contener instancias de sí mismo —`Flow(BaseNode)`, `Component`/`Composite`, `<state>` dentro de `<state>`, `type => supervisor`, `ReadP`, `S`/`K`, `CoroutineScope`.
2. (de las fuentes) En seis el cierre está escrito: el compuesto se declara del mismo tipo que la hoja, y el cliente no los distingue ("Composite lets clients treat individual objects and compositions of objects uniformly").
3. (lectura mía) Las que tienen freno lo declaran con un número o con una regla sintáctica: intensidad de reinicios (OTP), posición de cola (Scheme), contextos válidos (SCXML), presupuesto de contexto (RLM/RAH).
4. (lectura mía) Ninguna promete "complejidad emergente" con esas palabras; prometen uniformidad y un límite.
5. (lectura mía) El "poco código" no viene de la cantidad de líneas sino de que el mecanismo no distingue hoja de compuesto: PocketFlow lo consigue con una clase, OTP con un átomo en la spec de hijo.
6. (lectura mía) El costo se paga siempre en el mismo lugar: sin tope, la composición no termina o se come el presupuesto; cambia la moneda —reinicios, pila, contexto, tokens.
7. (lectura mía) El filo que las fuentes marcan y el repo todavía no: "decisiones como datos tipados" y "agente = Flow = Node = Tool" tiran para lados distintos; en CL, tipar a la Church elimina la auto-aplicación que hace universal al cálculo.
8. (lectura mía) La lógica combinatoria es el límite teórico del programa: dos primitivas alcanzan para todo, incluida la recursión; el precio es que el término se vuelve ilegible y la igualdad indecidible.
9. (lectura mía) Los papers de agentes recursivos son los que hablan de costo por nivel y los que menos declaran sobre profundidad: el freno lo pone el contexto, no la arquitectura.
10. (lectura mía) Para el harness, el freno de la fractalidad no es un `if` de profundidad sino un presupuesto que se hereda, como `intensity/period` en OTP o el contexto en RLM.

2026-11-01 — fuentes verificadas por fetch el 2026-11-01; las que no se pudieron fetchear quedan marcadas.
