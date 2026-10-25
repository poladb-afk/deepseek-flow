# Cumplimiento del patrón `prep → exec → post` en deepseek-flow

Fecha: 2026-09-23
Alcance: `/home/roquedb/Documentos/00_IA/Pocketflow/deepseek-flow` (22 archivos `.py`)
Método: lectura directa de cada archivo que define nodos.

---

## 1. Qué es el patrón

`prep` / `exec` / `post` son el **contrato de la clase `Node` de PocketFlow** (Template Method
en tres fases sobre un grafo dirigido):

| Fase | Firma | Rol |
|------|-------|-----|
| `prep(self, shared)` | lee el estado global | Preparar: extraer de `shared` lo que `exec` necesita |
| `exec(self, prep_res)` | **NO** ve `shared` | Ejecutar: lógica pura (LLM, herramienta, I/O) |
| `post(self, shared, prep_res, exec_res)` | escribe `shared` + devuelve acción | Persistir y enrutar el grafo |

La regla de oro, enunciada por el propio código:
> "El `prep` es el único tiempo del nodo que ve el estado y la llamada: el `exec` no lo toca."
> — `nodes.py:170-171`

`exec_fallback(self, prep_res, exc)` es la pata opcional de manejo de error por nodo.

---

## 2. Inventario: qué archivos definen nodos

De los 22 `.py`, **9 archivos definen nodos**; el resto son utilidades o módulos funcionales.

| Archivo | Nodo(s) | `prep` | `exec` | `post` | Cumple |
|---------|---------|:------:|:------:|:------:|:------:|
| `nodes.py` | `GetQuestion`, `AgentStep`, `ExecuteTools`, `ExitChat` | ⚠️ parcial | ✅ | ✅ | ✅ |
| `informe.py` | `ScanFiles`, `AnalizeFile` (Batch), `WriteReport` | ✅ | ✅ | ✅ | ✅ |
| `auditoria.py` | `CarpetaScan`, `Seccion`, `ReduceGlobal`, `AuditorCarpetas` (BatchFlow) | ✅ | ✅ | ✅ | ✅ |
| `juez.py` | `Draft`, `Judge`, `Entregar` | ✅ | ✅ | ✅ | ✅ |
| `debate.py` | `Proponente`, `Critico`, `FinAgente`, `JuezDebate` | ✅ | ✅ | ✅ | ✅ |
| `rag.py` | `ChunkDocs`, `EmbedChunks` (Batch), `SaveIndex` | ✅ | ✅ | ✅ | ✅ |

Sin nodos (utilidades / módulos de herramientas): `main.py`, `flow.py`, `modules/*.py`,
`utils/*.py`.

---

## 3. Evidencia del contrato

**`exec` no toca `shared`** (recibe datos ya extraídos por `prep`):
- `nodes.py:33` — `AgentStep.exec(self, inputs)` recibe `(messages, tools)`; su `prep`
  (`nodes.py:28-32`) los extrae de `shared`.
- `informe.py:118` — `AnalizeFile.exec_async(self, filepath)`.
- `rag.py:93` — `EmbedChunks.exec(self, batch)`.
- `auditoria.py:57` — `CarpetaScan.exec(self, inputs)`.

**`post` escribe `shared` y devuelve la acción de enrutado:**
- `nodes.py:44-46` — `AgentStep.post` → `"tool"` / `"answer"`.
- `nodes.py:60` — `ExecuteTools.post` → `"default"`.
- `juez.py:130-131` — `Judge.post` → `"entregar"` / `"retry"`.
- `debate.py` — `Proponente.post_async` → `"end"` / `"continue"`.

**`exec_fallback`** (manejo de error por nodo) se apoya en el motor vía parámetros:
`flow.py:9` (`AgentStep(max_retries=3, wait=5)`), `informe.py:181`, `juez.py:141`.

---

## 4. Matices (límites del contrato, no incumplimientos)

1. **Nodos parciales:** `ExitChat` (`nodes.py:63`) y `Entregar` (`juez.py:158`) solo definen
   `post`; `GetQuestion` (`nodes.py:9`) define `exec` + `post` sin `prep`. Es uso mínimo
   legítimo del contrato (heredan los no-ops de la base).
2. **BatchFlow:** `AuditorCarpetas` (`auditoria.py:89`) es un `AsyncBatchFlow` y sobrescribe
   **solo `prep_async`** (la iteración); el `exec`/`post` los hacen los nodos del flujo interno.
   Es la variante correcta del patrón.
3. **Flujos async independientes:** en `debate.py`, `Proponente` y `Critico` se auto-apuntan y
   usan `exec_async`/`post_async`; el canal es `asyncio.Queue` en vez de `shared`.
   Sigue el patrón (docstring en `debate.py:1-7`).

---

## 5. Conclusión

**Se puede afirmar que el patrón `prep → exec → post` se cumple en todos los archivos de
deepseek-flow que definen nodos.** Ningún nodo viola el contrato: no hay lógica de negocio en
`prep`/`post` más allá de leer/escribir `shared` y decidir la transición; `exec` nunca accede a
`shared`; y `post` devuelve la acción cuando el grafo la necesita.

**Matiz de interpretación:** si la vara es "todo nodo implementa las tres fases completas",
entonces **NO** se cumple al 100% (hay nodos parciales y variantes async/Batch). Si la vara es
"todo nodo respeta el *contrato* del trío donde lo usa", entonces **SÍ** se cumple.
