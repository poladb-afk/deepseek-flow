# exp/108 — research como composición del kernel (pre-registro del A/B)

**Estado: pre-registro, escrito ANTES de correr nada y ANTES de que exista el
código del brazo (2026-11-03).** Es un cambio de conducta: sin este documento
no se toca el producto. Si algo cambia al correrlo, va como desvío declarado
al final; los criterios no se retocan después de ver los datos.

Paso 8 del roadmap del operador (2026-11-03): "las capacidades como
composiciones del kernel: juez, auditoría, research y debate pasan a ser
`kernel.agente()` con sus tools y su prompt, en lugar de flujos propios". Es
el primero de los cuatro y el único cuyo mapeo es directo: research YA es un
loop de tools (buscar → evaluar → buscar), hoy con un grafo propio. El juez
no entra (X112 midió que el juez separado refuta 5/5 y cazó 2 bugs: volverlo
un solo agente que se auto-juzga iría contra una decisión medida), auditoría
es un map-reduce sin loop y debate es ping-pong async; cada uno, si algún día
entra, con su propio spec.

## Qué se borra y qué queda

Hoy (`research.py`, 200 líneas): `Planner → Researcher (BatchNode) →
Synthesizer`, con el loop de cobertura como arista
`Synthesizer -research-> Planner` y `Fin` de salida.

| Pieza | Dónde | Qué hace hoy | En el brazo agente |
|---|---|---|---|
| `Planner` | `research.py:30-67` | LLM → YAML de 3 consultas; el CÓDIGO recorta a `MAX_QUERIES=3` (exp/28: el modelo devolvía 20 y se buscaban las 20) | el modelo planifica en su prompt; el tope lo aplica la tool (ver abajo) |
| `Researcher` | `research.py:70-98` | por consulta: `search_web(k=4)` + UNA llamada LLM que extrae ≤5 hechos con URL; el fallo de una búsqueda es dato, no retry del lote (exp/37) | el modelo lee los resultados crudos como tool result; el fallo sigue siendo texto (lo garantiza `utils/websearch.search_web`) |
| `Synthesizer` | `research.py:101-160` | LLM decide YAML `research`/`finalize`; a `MAX_ROUNDS=2` fuerza el informe con lo reunido (L8) | el modelo decide cuándo escribir; el saldo del kernel fuerza el cierre (L8 por construcción: sin saldo, la llamada va sin tools) |
| `create_research_flow`/`Fin` | `research.py:163-181` | el grafo propio | `kernel.correr` sobre `kernel.loop` (Paso/Actuar/Cerrar), como el chat (S9b A′) y el supervisor |

**Lo que NO cambia:** `investigar(tema, salida) -> ruta` (la interfaz que
usa la tool `deep_research` del chat, `modules/research.py`), el subcomando
`main.py research`, `RESULTADOS_POR_QUERY=4`, el default de salida y el
mensaje final.

## Las dos leyes medidas, re-expresadas en el kernel

1. **exp/28 (el tope de consultas)**: hoy el código recorta la lista del
   Planner. En el brazo agente el modelo puede pedir todas las que quiera:
   el tope lo aplica el CÓDIGO dentro de la tool — a la búsqueda N+1 del run
   la tool responde `ERROR: tope de 9 búsquedas alcanzado; escribí el
   informe con el material reunido` (error-como-información, P4; el modelo
   se corrige). El tope es **9** = 3 consultas × 3 ciclos, el máximo de hoy.
2. **exp/37 (el fallo de una búsqueda es dato)**: `utils/websearch.search_web`
   ya devuelve su error como texto; en el kernel una tool que devuelve texto
   no dispara retry de ronda. La ley sobrevive sin código nuevo.
3. **L8 (informe siempre)**: hoy `Synthesizer` fuerza `finalize` a
   `MAX_ROUNDS`. En el kernel es la arista `cerrar` del loop: agotado el
   saldo, la última llamada va sin tools y el modelo cierra con lo que tiene
   (la misma ley que el chat desde X96 y el supervisor desde siempre).

`SALDO=12` rondas de tools: headroom sobre las 9 búsquedas posibles (el
modelo puede buscar de a una o agrupar); el techo real de cómputo es el tope
de búsquedas, igual que hoy.

## Brazos (dos árboles, dos worktrees, cada uno con su `.runs` desde el principio)

| Brazo | Árbol | Qué corre |
|---|---|---|
| **base** | `main` @ `0b6f857` | el research de hoy: planner → researcher → synthesizer |
| **agente** | rama `research-agente` | `kernel.correr` con `search_web` como tool y el saldo/tope de arriba |

Igualación: `LLM_MODEL=deepseek-flash` pineado en los dos (el modelo no es
la variable), mismos temas, mismas seeds (etiqueta de repetición: cada
corrida es una muestra nueva de la API, declarado como exp/104), tope de
búsquedas equivalente (9 en los dos: hoy por construction, el brazo por la
tool), `RESULTADOS_POR_QUERY=4` en los dos.

## Temas y seeds

Tres temas fijos (ampios, con respuesta en la web y verificables por URL),
seed 1 y 2 → **12 corridas** (6 por brazo):

1. "PocketFlow: el framework de agentes de 100 líneas" (nicho técnico,
   resultados escasos: mide la re-planificación).
2. "precios y modelos de DeepSeek hoy" (cambiante: mide que cite lo VISTO,
   no lo alucinado).
3. "preregistración de estudios en ciencia abierta" (conceptual amplia:
   mide el balanceo de facetas).

## El denominador (declarado y simétrico)

- **Informe**: existe y es no vacío. Sin informe, la corrida cuenta como
  fallida (no sale del denominador; ley de `AGENTS.md`).
- **URLs honestas** (determinista): las URLs del informe ⊆ las URLs
  aparecidas en los resultados que la corrida vio de verdad (el instrumento
  las captura al vuelo). Una URL citada que no estuvo en ningún resultado es
  una invención, el análogo web de la cita rota (exp/29).
- **Cobertura cruda** (dato, no criterio): cantidad de URLs citadas y
  cantidad de búsquedas distintas por corrida.
- **Costo**: USD por corrida y total con `uso_de_sesion`/`desglose_de_sesion`
  y la tarifa de `deepseek-flash`. Falta la línea → criterio de costo sin
  evaluar → no pasa.
- **Preferencia ciega del operador**: los 6 pares (mismo tema+seed, orden
  aleatorio y sin rótulo de brazo) — el operador elige mejor informe o
  declara empate. n=6 declarado: es control de regresión grosera, no
  evidencia estadística.

## Criterios (todos, o no pasa)

1. **El informe siempre**: 6/6 corridas del brazo agente terminan con
   informe no vacío (agotado el presupuesto, con lo que haya).
2. **URLs honestas**: 0 URLs inventadas en las 6 corridas del brazo agente
   (determinista; el mismo chequeo se reporta para base como dato).
3. **Costo no mayor**: USD total del brazo agente **≤ 1,25 ×** el de base.
   Predicción registrada: **menor** — hoy se pagan ~9 llamadas de extracción
   (`Researcher.exec`) que el brazo agente no hace; el margen cubre el
   contexto más largo de leer resultados crudos en vez de ≤5 hechos.
4. **El tope es del código**: ≤ 9 búsquedas por corrida en el brazo agente,
   contadas por el instrumento (no por la obediencia del modelo).
5. **Preferencia ciega**: el brazo agente gana o empata en **≥ 3 de los 6
   pares** (control de regresión; si pierde 4+, el informe empeoró y no
   pasa aunque el costo baje).
6. **La estructura se fue de verdad**: en el árbol del brazo, los nombres
   `Planner`, `Researcher`, `Synthesizer`, `create_research_flow`,
   `MAX_ROUNDS` y `MAX_QUERIES` dan **0 coincidencias** en el producto
   (`grep -rnw` sobre `research.py`, `modules/`, `main.py`);
   `./calidad.sh` verde en la rama; `tests_definidos` del ratchet no baja;
   y `research.py` corre sobre `kernel.loop` (sus nodos en la traza son
   `Paso`/`Actuar`, canónicos desde X130 — las acciones viejas de
   `evals.py` se quedan para las trazas anteriores, como X136 con
   `rondas.py`).
7. **La interfaz del chat no cambia**: la tool `deep_research` existe con el
   mismo esquema y `modules/research.py` queda intacto
   (`tests/test_smoke.py` y `tests/test_contratos.py` lo candan).

Si NO PASA: la rama se revierte (como la 5b) y el dato va a la bitácora; el
flujo de hoy no se reconstruye como parche.

## Instrumento

`banco/probes/exp108.py` (determinista, sin LLM propio): corre
`investigar(tema)` por tema×seed del árbol local, intercepta
`utils.websearch.search_web` (y los bindings de `research`/`modules.websearch`)
para contar búsquedas y capturar los resultados vistos, extrae las URLs del
informe y de lo visto, mide tokens/USD de la sesión, y deja un jsonl por
corrida; `--comparar base.jsonl agente.jsonl` aplica los siete criterios.
El veredicto se prueba con filas sintéticas antes de gastar una llamada
(mismo método que s6).
