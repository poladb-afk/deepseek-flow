# Elegancia funcional: componer y anidar para escalar (2026-11-01)

**Qué es:** notas de diseño para la pregunta del operador — elegancia funcional
al estilo "Flow es Node" de PocketFlow, flujos anidados, piezas chicas que
compongan hasta complejidad emergente. **Método:** lectura del código y los docs
del repo (citas verificadas línea a línea), notas de investigación online que ya
viven en el repo y verificación fresca de fuentes primarias en
[elegancia_funcional_fuentes_2026-11-01.md](elegancia_funcional_fuentes_2026-11-01.md).
**No se corrió ningún experimento ni se tocó código**; lo que es lectura mía va
marcado como tal.

## 0. Respuesta corta

El mecanismo que buscás ya está en el repo y en la versión fijada del
framework: `Flow` hereda de `BaseNode`, la orquestación llama a `_run()` de
cualquier nodo, y el kernel devuelve un `Flow` que otro flujo encadena como un
paso. Lo que falta no es el mecanismo: es **(a) cerrar la clausura** —que el
chat sea una instancia del mismo loop (S9b)—, **(b) la prueba de que anidar
paga** (exp/103, pre-registrado y sin correr) y **(c) cerrar los instrumentos
en la costura**: hoy el diagrama y el guard de calles muertas no ven adentro de
un flujo anidado (hallazgo de §3). Antes de eso, sumar mecanismos de
composición nuevos es agregar casos sin medición (M4, D1).

## 1. La idea, contra los cuatro principios

Los cuatro principios del operador (`docs/principios.md:9-12`, dictados el
2026-11-01) y su fila en la capa 1:

| Principio | Fila | Qué manda sobre el anidamiento |
|---|---|---|
| Minimalismo KISS | D1 (`docs/principios.md:34`) | Pocas piezas: una primitiva que se contiene a sí misma, no un framework por escala. |
| Fractalidad | D3 (`docs/principios.md:36`) | Una definición del loop, N instancias: chat = sub-agente = supervisor = copia de sí mismo. |
| Modularidad | D2 (`docs/principios.md:35`) | Crecer es dejar un archivo: una capacidad se suma o se saca sin tocar el CORE. |
| Grafo | D4 (`docs/principios.md:37`) | El control vive en las aristas; un turno se explica leyendo `python3 main.py grafo`. |

La definición de elegancia de X116 (`docs/elegancia.md:12-19`) es exactamente
esa apuesta: "una primitiva que se contiene a sí misma (agente = Flow = Node =
Tool)", "las variaciones salen de componer y de datos, no de casos". El
principio P1 de PocketFlow ("una primitiva que se contiene a sí misma") y el P7
("elegancia por borrado") ya están tabulados en `docs/elegancia.md:25-33`.

## 2. Lo que el repo ya tiene (verificado)

| Pieza | Qué hace | Dónde |
|---|---|---|
| Una interfaz para hoja y compuesto | `Flow` hereda de `BaseNode`; `_orch` llama a `curr._run(shared)`, que todo nodo (incluido un `Flow`) implementa; `>>` y `-acción->>` cuelgan aristas del mismo `BaseNode` | `pocketflow==0.0.3` (`requirements.txt:1`), paquete instalado `__init__.py:3,13,39,46-50` |
| El loop es un `Flow` | `loop()` cablea `Paso → Actuar → Paso`, con cierre y respuesta como aristas, y devuelve `Flow(start=paso)`; el docstring lo dice: "Es un Flow, así que también es un Node" | `utils/kernel.py:174-184` |
| Flujo anidado en producción | El supervisor compone `agente = loop(...)` y lo encadena: `agente >> auditar >> sintetizar` | `supervisor.py:299-302`; corre en `tests/test_flujos.py:228-259` |
| Anidar un flujo distinto | El informe map-reduce mete un `AsyncParallelBatchNode` dentro de un `AsyncFlow` | `docs/design.md:180-186` |
| Un agente ES una tool | `agente()` envuelve el loop como `Tool`; `recursivo=True` se suma a sus propias tools | `utils/kernel.py:200-238` |
| Frenos como datos | Contexto fresco, un solo `Ledger` por árbol, efecto (lectura/escritura), profundidad acotada | `docs/design.md:928-948`; `docs/estado.md:139` (X116) |
| Modularidad medida | 21 archivos en `modules/` (31 tools, 28 impls al importar); `core_importa_modulos` = 0: borrar un módulo no rompe el chat | `docs/elegancia.md:92`; `tests/test_core_sin_modulos.py` |

Y lo que el repo ya decidió, que evita inventar de nuevo:

- **El chat todavía no es `kernel.loop`** (decisión X77: el chat queda como "el
  loop con políticas"; `docs/estado.md:126`). La instancia que lo completaría es
  S9b, hoy en el puesto 9 de la cola (`docs/handoff.md:116`; `docs/elegancia.md:53`).
- **La fractalidad como capacidad se mide, no se afirma**: `agente(..., recursivo=True)`
  existe desde X116, pero "si le conviene al chat replicarse" lo decide
  `banco/specs/exp103_fractal.md` (pre-registro: brazos, criterios, decisión
  atada; `banco/specs/exp103_fractal.md:18-66`). Es la cola #13
  (`docs/handoff.md:120`).
- **Un sub-agente entra solo si mejora algo**: el explorador se borró en H3-B
  tras 24 corridas (0 llamadas; calidad 0,50 vs 1,33; `docs/estado.md:128`); H3-H
  quedó sin objeto porque nada en producción arma agentes como tools
  (`docs/estado.md:135`). D3 lo dice: "La medición: un sub-agente entra solo si
  mejora algo".

**Lectura mía (no está escrita en el repo):** el anidamiento del repo no es
"flows anidables" como característica del framework, sino **una primitiva con
tres frenos** (profundidad, saldo, efecto) donde cada instancia decide sus
datos. Eso es más chico que la idea de "composición de flows" y más fácil de
gatear: la composición no agrega código, la política vive en los datos.

## 3. Hallazgo: los instrumentos no están cerrados bajo anidamiento

El repo presume que el grafo se explica leyéndolo (D4) y que ningún grafo
termina en vacío (`tests/test_grafos_sin_calles_muertas.py`). Pero un `Flow`
anidado tiene su pipeline en `start_node`, no en `successors`: quien camina
solo `successors` no ve adentro.

- `utils/viz.py:18-24` camina `nodo.successors` y no mira `start_node`. Medido:
  `python3 main.py grafo supervisor` imprime
  `Flow_0 -->|default| Auditar_1` y `Auditar_1 -->|default| Sintetizar_2`; el
  loop interno (`Paso/Actuar/Cerrar`) no aparece. El comando promete "el
  diagrama real que ejecuta el framework" (`utils/viz.py:3-4`).
- El guard de calles muertas camina igual: `_recorrer` (`tests/test_grafos_sin_calles_muertas.py:65-76`)
  no baja a `start_node`. A un flujo anidado lo juzga solo por sus aristas
  externas.
- `replay._nodos_alcanzables` sí recursa en `start_node` y lo deja escrito:
  "sin la recursión, las clases del flujo interno quedarían invisibles para el
  replay — el propio guard de calles muertas tiene ese punto ciego"
  (`replay.py:88-105`, la frase en `:94`).
- El test del diagrama cubre solo el chat (`tests/test_grafo_readme.py:12-20`).

**Por qué importa para la idea del operador:** si anidar flujos es la forma de
escalar, el diagrama y el guard tienen que estar cerrados bajo anidamiento, o
el instrumento que certifica "el grafo dice la verdad" miente por omisión justo
en la costura que se quiere explotar. Es la misma lección de X82 ("medí la pieza
donde decide"): el instrumento tiene que ver donde la decisión ocurre.

**Propuesta (sin cambio de conducta):** un solo caminador de grafos vivos
(el de `replay.py:88-105`, extraído) que usen `viz` y el guard; gate nuevo: un
test que afirme que los nodos internos de un flujo anidado aparecen en el
mermaid y que el guard los recorre. Si el límite es deliberado, en cambio, se
declara en F3 como límite honesto y no se toca.

## 4. Ideas de composición y anidamiento (fuentes + encaje)

| Idea | Qué aporta | Estado en el harness | Fuente |
|---|---|---|---|
| **Clausura por Composite**: hoja y compuesto comparten interfaz; componer es universal | Un mecanismo sirve a todas las escalas sin código nuevo | ✅ mecanismo (`Flow(BaseNode)`; `loop()` devuelve un `Flow`); falta el uso pleno (S9b). El README oficial ya lista un cookbook con "nested flows" y otro con "patch-as-subflow": anidar no es una rareza del harness | PocketFlow 0.0.3, `__init__.py:39-50`; README de The-Pocket/PocketFlow (verificado 2026-11-01); patrón Composite (GoF) |
| **Una primitiva + composición = universalidad** (lógica combinatoria, parser combinators) | La regla "capacidad nueva = composición, no primitiva" | ✅ práctica (módulos, hooks); sin gate propio sobre el kernel | ver `elegancia_funcional_fuentes_2026-11-01.md` |
| **Estados compuestos (statecharts)**: entry/exit definidos para el anidamiento | Le da semántica al borde: qué estado entra, qué vuelve, qué historia queda | ⚠️ leyes dispersas en `design.md:928-948`; no hay una tabla única "leyes del anidamiento" | Harel (statecharts); ver fuentes |
| **Concurrencia estructurada / supervision trees**: cada borde declara su presupuesto y su contención | Frenos heredados por construcción | ⚠️ frenos como datos ✅; el presupuesto es **compartido**, no por donación (`design.md:934-937`); el prototipo viejo donaba y devolvía el sobrante (`docs/informes/fractal_agent_mapeo_2026-10-23.md:33-36`) | ver fuentes |
| **Nido sin pila** (trampoline/CPS) | Anidar profundo sin crecer la pila | ✅ resuelto por freno: profundidad 1 por default, recursivo acotado (`design.md:942-948`); no hace falta trampolín | ver fuentes |
| **Agent-as-tool** (Claude Code, AgentScope) | El sub-agente devuelve solo su resultado, nunca su contexto | ✅ es `agente()` (`kernel.py:200-238`); la evidencia dice que no paga solo: X79 | ver fuentes; `docs/estado.md:128` |
| **Piezas chicas con contrato** (Unix, 12-factor) | Escalar por composición, no por framework | ✅ módulos + hooks; `core_importa_modulos` = 0 (`docs/elegancia.md:92`) | ver fuentes |

**Lo que NO se copia (y por qué):**

- **DBOS / durabilidad por workflow**: el prototipo del operador la usaba; el
  harness no la tiene ni la necesita para esto (`docs/informes/fractal_agent_mapeo_2026-10-23.md:71-75`).
- **Reinicio de supervisión (OTP)**: el repo eligió "los errores son
  información" (D9) y determinismo; un reinicio automático cambia conducta sin
  medición.
- **Grafo como expresión de datos serializable** (homoiconicidad): elegante,
  pero cambia la construcción de todos los flujos; sin una necesidad medida es
  YAGNI (D1). Queda como idea de segunda ronda.
- **best-of / spawn en paralelo**: el mapeo ya lo dejó registrado y recomendó
  portar solo lo puro (`fractal_agent_mapeo:83-85`); sin bench que lo justifique,
  no entra (M4).

## 5. Candidatas (costo y gate)

| # | Candidata | Cambia conducta | Costo | Gate |
|---|---|---|---|---|
| C1 | Cerrar los instrumentos en la costura: un caminador compartido para `viz` y el guard | no | chico (1 helper + test) | test nuevo de flujo anidado + `./calidad.sh` |
| C2 | Tabla "leyes del anidamiento" en `docs/design.md` (contexto fresco al entrar, solo el resultado al salir, frenos como datos, shared JSON) | no | docs | citas verificadas por R3 |
| C3 | Decidir el orden: exp/103 y S9b antes que mecanismos nuevos de composición | no (código) | decisión del operador | la decisión; después, el pre-registro manda |
| C4 | Propiedad nueva F8 "Clausura" en `docs/elegancia.md`: toda pieza anidable expone la misma interfaz que la que la anida, y los instrumentos ven adentro | no | docs + C1 como gate | C1 |
| C5 | Grafo como expresión de datos; best-of/spawn; reinicio de supervisión | **sí** | grande | no antes de una medición que lo pida (M4) |

**Recomendación:** C1 + C2, y tratar C3 como la decisión de orden. C4 solo si
C1 entra (si no, es una propiedad sin gate). C5 se descarta por ahora.

## 6. Preguntas abiertas al operador

1. ¿La "complejidad emergente" que buscás es **auto-replicación** (un loop que
   se llama a sí mismo: exp/103) o **composición heterogénea** (flujos
   distintos encadenados: supervisor, informe)? Cambia qué se mide y en qué
   orden.
2. ¿Se adelanta S9b (hoy #9) o exp/103 (hoy #13) en la cola? La cola actual
   pone primero imports, S6 y 5c (`docs/elegancia.md:112-116`).
3. ¿El diagrama tiene que mostrar adentro de un flujo anidado, o alcanza con
   declarar el límite en F3?
4. ¿La "primitiva que se contiene a sí misma" admite una regla nueva del tipo
   "capacidad nueva = composición" con gate, o queda como práctica de review
   (sin gate, como E5/E8)?

## 7. Hallazgos de la verificación de fuentes (R3)

La verificación por fetch de las 23 fuentes que citan `docs/principios.md` y
`docs/elegancia.md` quedó en
[elegancia_funcional_fuentes_2026-11-01.md](elegancia_funcional_fuentes_2026-11-01.md)
§1. Lo que afecta el contrato de docs:

| Hallazgo | Qué dice la fuente fetcheada |
|---|---|
| Parnas (DOI 10.1145/361598.361623) | No se puede abrir: `doi.org` → `dl.acm.org` da 403. La atribución de D2 queda **no verificada**. |
| *Show and Tell* (arXiv 2511.13972) | El repo le atribuye "56–70 % menos tokens"; el resumen **no da ninguna cifra** (habla de "initial compression" y "expansion discipline"). Verificado por mí el 2026-11-01. |
| SWE-agent (arXiv 2405.15793) | El repo le atribuye "el linter en la edición como guardrail medido"; el resumen habla de la interfaz agente–computadora, **no de un linter**. |
| Recursive Agent Harnesses (arXiv 2606.13643) | El repo le atribuye "profundidad acotada"; el resumen **no menciona ningún tope de profundidad**. Verificado por mí el 2026-11-01. |
| *Towards a Science of Scaling…* (DOI 10.21203/rs.3.rs-8414536/v1) | La página no entrega contenido para fetchear: solo el título. El hallazgo "más agentes dañan en secuencial" no se puede citar de esa URL. |
| 12-Factor, factor 12 | La página no tiene prosa sobre el `foldl`: son dos imágenes y un cierre. La atribución no se sostiene con el texto. |

`docs/principios.md` ya aclara que las URL de X113 "no se verificaron en línea
al escribirlas" y que el operador las confirma al aplicar. Lo que agrega esta
pasada es el detalle: **una no se puede abrir y cuatro atribuciones no están en
el resumen**. No toqué `docs/principios.md`: el arreglo (citar el PDF completo,
suavizar la fila o dejarla como pendiente declarada) es decisión del operador.

## 8. Límites de estas notas

- No corrí experimentos: todo lo de conducta es lo que dice el repo.
- Las citas de código y docs se verificaron línea a línea el 2026-11-01; las
  fuentes online se verificaron por fetch en
  `elegancia_funcional_fuentes_2026-11-01.md`.
- **Hallazgo colateral (docs):** `docs/informes/fractal_agent_mapeo_2026-10-23.md:5`
  enlaza `fractal_spawn_evidencia_2026-10-23.md`, que hoy vive en
  `docs/informes/archivo/2026-10/` (archivado en `d672d0b`): el enlace relativo
  está roto. No lo corregí: no es parte del pedido.
