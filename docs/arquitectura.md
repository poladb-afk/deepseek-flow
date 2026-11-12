# Arquitectura del harness

> **Estado: borrador para revisión del operador (X192, 2026-11-07).** Acordado
> en conversación; **nada de esto está implementado** salvo lo marcado *hoy*.
> Lo que se implemente, se implementa con su gate y su paso del roadmap.

## La forma, en una frase

Un **CORE mínimo** que es el núcleo del grafo y ofrece **conectores
estandarizados**; los **módulos** son las piezas que esos conectores conectan,
y también se conectan **entre sí**. El CORE conoce su catálogo (`discover()`)
sin importar ningún módulo (P3) y solo se ocupa de funcionar y de estar bien
conectado.

## Los principios, como arquitectura

Los principios son los de `docs/principios.md` (S0, P1–P4, N1–N4, EL1–EL9) y
acá **no se redefinen** (N4 también vale para los docs, X144): esta tabla dice
cómo se ve cada uno en la arquitectura y qué mecanismo de este borrador lo
sirve. El **grafo** no es un principio aparte: es la forma en que se expresan
todos (P2 lo nombra; EL2: el control es un dato). Decisión del operador
(X201, opción A).

| # | Cómo se ve en la arquitectura | Mecanismo de este borrador | Gate |
|---|---|---|---|
| S0 | **vive en el conector** (`run_tool_call` + `HOOKS_PRE`): toda composición la hereda sin que nadie tenga que acordarse; el árbol entero gasta un solo saldo | la composición validada al armar; el runner cobra cada pieza con `tracing.cobrando(ledger, …)`; X197b: la arista de `research` pasa por la fábrica (`conector_de_modulo`, el despacho único) con la misma tool y otro IMPL que devuelve el informe (D6=A): sin excepción | el de S0 en `docs/principios.md`; el saldo chat → capacidad → LLM lo cuentan los 3 tests de X202; el veto de la política llega a la composición: `test_un_veto_de_la_politica_sobre_research_corta_la_composicion_antes_de_gastar` (X197b); el supervisor sigue fuera hasta que sea `kernel.agente()` (X203/X204 NO PASA) |
| P1 | **uno por capacidad**: un módulo, un nodo, una función, nada duplicado; el contexto se gana: conocer no es mostrar | el catálogo | `bytes_primer_request`, `lineas_del_producto` |
| P2 | cada módulo es, por dentro, **una o más instancias** de `kernel.loop` (la composición de las etapas) con su prompt, sus tools y su parte del saldo **(a)**; hereda todos los frenos y, como mucho, las capacidades del padre **(c)**; la forma **(b)** sigue medida y no adoptada | el conector extiende la `Tool` del kernel (`agente=True`, `hijas`) | `test_un_hijo_no_puede_tener_tools_que_el_padre_no_tiene`; `fable_judge` con la foto de X179 (X195); el resto de los módulos, sin gate |
| P3 | **el template**: `TOOLS`, `IMPL` y `HOOKS` más un conector que declara qué consume y qué produce; el despacho y la política siguen únicos | los tipos de artefacto | `core_importa_modulos`; `tests/test_conector.py` (el contrato del template, X194) |
| P4 | **la interconexión** CORE ↔ piezas y piezas ↔ piezas; el control en las aristas, el `shared` solo con JSON, la emergencia se observa en la traza | la composición declarada por el usuario | `test_las_fallas_topologicas_se_ven_en_la_traza`; la composición con su test de contrato (X197) |

La regla de método (detalle en `docs/estrategias.md`): **un resultado negativo
cierra una estrategia, no un principio.**

## El CORE: cuatro piezas

Lo que PocketFlow pone en su núcleo son tres abstracciones (Node, Flow, Shared
Store) y deja afuera a propósito todo lo demás (el cliente del LLM, la
búsqueda, las bases vectoriales). El agente no es una pieza especial: es nodos
con un loop. Aplicado acá:

| Pieza | Hoy | Por qué es CORE |
|---|---|---|
| El grafo del loop | `utils/kernel.py` (`loop`: Paso, Actuar, Cerrar, Fin) | es el motor |
| El saldo | `Ledger` en `utils/kernel.py` | sin él ningún árbol tiene techo |
| El paso único de las tools | `run_tool_call` en `utils/fs_tools.py` (hooks PRE/POST) | **es el conector**: S0 se engancha ahí y todo lo atraviesa |
| El catálogo | `discover()` en `modules/__init__.py` | el CORE sabe qué capacidades hay |

Fuera del CORE (utilidades o módulos): el cliente del LLM, la búsqueda web, la
memoria, research y el resto de las capacidades.

## El template del módulo

**Hoy** un módulo es un archivo de `modules/` con `TOOLS` (lo que ve el modelo),
`IMPLS` (cómo se corre) y, si hace falta, `HOOKS`. El conector es solo hacia el
CORE.

**Objetivo**: el mismo archivo, más un **conector** que declara

- **qué consume y qué produce**, en tipos de artefacto (abajo);
- que su lógica interna es **una o más instancias** de `kernel.loop` (la
  composición de las etapas, lo fractal), con su prompt, sus tools y su parte
  del saldo;
- que gasta del **saldo del árbol** y corre por `run_tool_call` (hereda S0).

El conector parte de la `Tool` del kernel (`agente=True`, `hijas`): se extiende
una pieza que ya existe, no se inventa una primitiva nueva.

**Contrato negativo**: el conector **no recibe** política, validador ni
allowlist por parámetro. La herencia es por construcción: un hijo hereda los
frenos del padre y, como mucho, sus capacidades (`hijas`, `utils/kernel.py:205`;
X147 y X157). Un módulo con otra política no existe, y el gate fractal lo
verifica en los tres niveles (`tests/test_gate_fractal.py:144,483`).

**X194/X195**: el contrato existe en `utils/conector.py` y se prueba en
`tests/test_conector.py`; el registro (`discover()`) valida los `CONECTORES`
que declare un módulo al armar (tipo exacto y tool entre sus `TOOLS`/`IMPL`) y
saltea el que no cumple. `fable_judge` (X195), `debate` (X196) y `research` (X197) ya declaran el suyo
(producen `veredicto` o `borrador`); las dos etapas LLM de `fable_judge` corren
en `kernel.loop`. El resto de los módulos sigue con `TOOLS`/`IMPL` (sin paso asignado). El council en dos fases (X196) y la profundidad/N
(X199) quedan declarados.

## La compatibilidad entre módulos: tipos de artefacto

El riesgo central es el de conectar bases de datos: que lo que produce un
módulo lo entienda el siguiente. Ya pasó en chico: un card A2A que era JSON
válido con otra forma tiraba el listado (X186), y lo mismo con las trazas
(`leer_registro`, C11). Con LLMs hay además **cascada**: un dato inventado por
un módulo entra como hecho en el siguiente.

**Vocabulario inicial (5 tipos)**; crece solo cuando un módulo real lo necesita:

| Tipo | Qué es |
|---|---|
| `pregunta` | lo que hay que resolver |
| `plan` | pasos propuestos para resolverlo |
| `hallazgos` | lo encontrado, **con citas** `archivo:línea` |
| `veredicto` | un juicio sobre un trabajo (lo que produce `fable_judge`) |
| `borrador` | un trabajo intermedio |

Cada artefacto viaja con su **procedencia** (qué módulo lo produjo) y sus
**citas**, para que el siguiente pueda verificar antes de creer
(`utils/citas.py` ya verifica citas). Los tipos los **declaran** los módulos y
se enumeran como la lista blanca de comandos: no es una lista de palabras que
juzga significado (N2).

## La composición

- **La declara el usuario**, como dato (por ejemplo, research con council; X197:
  `main.py composicion research_council "tema"`). Es el mecanismo más simple;
  no hay graduador ni sugerencias del modelo hasta que la arquitectura
  funcione.
- **Se valida al armar**: si una salida no encaja con la entrada siguiente, la
  composición no arranca y no gasta ninguna llamada (X194: `componer()` en
  `utils/conector.py`; el antecedente es X147, que rechaza al armarse un hijo
  con tools fuera del padre).
- **Un adaptador entre tipos es un módulo más**, con su conector (X197: el
  puente `borrador → pregunta` de `utils/composicion.py`).
- Todo el árbol de una composición gasta **un solo saldo**: el runner crea
  un `kernel.Ledger(1)` y envuelve cada pieza en `tracing.cobrando(ledger, …)`;
  `Ctx.hijo()` comparte el saldo cuando la composición corre dentro de un
  árbol. Hereda S0.

## El catálogo: conocer no es mostrar

Hoy `discover()` carga todo y el request del chat lleva **30 tools** (medido en
X173); por eso `bytes_primer_request` (16199, la última medición en la
bitácora) pesa más que el prompt. El
objetivo es separar:

- **lo fijo del request**: las tools mínimas del CORE más una tool de
  **catálogo** (qué capacidades hay) y una de **uso** (conectar una capacidad o
  una composición);
- **el catálogo**: un manifiesto chico por módulo que viaja como resultado de
  la tool, no en el prompt (no sube `texto_de_prompt`, N3).

A medir, no a suponer: X173 mostró que el proveedor cachea el prefijo, así que
el set fijo tiene que ser **estable** entre preguntas.

## Lo que esta arquitectura todavía no incluye

- **El cookbook de recetas**: puede crecer con el uso, pero hoy no es
  necesario. Cuando exista, las recetas las **aprueba el operador**; el modelo
  puede sugerirlas.
- **El graduador**: elegir N y diferenciación según la necesidad
  (`docs/estrategias.md`).

## Las brechas, medidas hoy

| La arquitectura pide | Hoy | Brecha |
|---|---|---|
| El CORE conoce su catálogo sin mostrarlo entero | 30 tools en cada request | conocer y mostrar están mezclados |
| Conector entre módulos | X194: el contrato (`utils/conector.py`); X195: `fable_judge` y X196: `debate` ya declaran su arista (`veredicto`); X197: `research` declara la suya (`borrador`) | falta migrar el resto (sin paso asignado) |
| Composición como dato | X197: la composición research + council se declara en el CLI y se valida al armar (`utils/composicion.py`, `componer()`); research sigue importando su pieza a mano | falta el resto de las composiciones y el catálogo (X198) |
| Lógica interna acoplable (fractal) | el chat y el supervisor son `kernel.loop`; X195 migró las dos etapas LLM de `fable_judge`; `juez`, `research`, `debate`, `informe` y `auditoria` son grafos propios | 5 pipelines |
| Tipos de artefacto | X194: los 5 tipos y el artefacto con procedencia y citas verificadas; X195/X196: `fable_judge` y `debate` producen `veredicto`; X197: `research` produce `borrador` | el resto sigue viajando como texto libre hasta su migración |
| Un solo saldo por árbol (S0, P2 (c)) | **X202**: toda llamada al LLM que hace una tool la cobra el saldo del árbol (`tracing.cobrando` + el cliente); queda el supervisor con su propio `Ledger(MAX_PASOS)` | medido en X201: un `deep_research` hizo llamadas que el `Ledger` del chat no contó (hoy las cuenta); el loop del supervisor sigue fuera hasta que sea `kernel.agente()` |

## Orden de implementación

Primero el contrato, después las piezas: migrar módulos sin el template
terminaría con una interfaz por módulo. El contrato se valida con **dos
módulos de naturaleza distinta** antes de generalizarlo: un verificador
(`fable_judge`) y un swarm muy diferenciado (`debate`). La cola está en
`docs/roadmap.md` (roadmap post-X191).
