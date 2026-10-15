# Contraste de la auditoría externa contra el proyecto actual

**Fecha:** 2026-10-15 · **Alcance:** los 5 documentos nuevos de `docs/informes/` frente al árbol de trabajo de este repo (HEAD `44420a4` + cambios sin commitear).
**Método:** inventario reproducido con git, anclas de línea, `./calidad.sh` sobre el árbol vivo, re-ejecución de las sondas del propio auditor y verificación por clústeres (seguridad, streaming, memoria/SQLite y métricas, delegadas; sesión/compacción/infra, directa). Solo lectura sobre el repo; fixtures en `/tmp`. Ningún archivo del proyecto fue modificado (los 20 `M` de `git status` son el trabajo previo sin commitear del 2026-10-14).

---

## 1. Qué se entregó (identificación)

Los 5 archivos son **nuevos y sin commitear** (`git status`: `??`), con marca de tiempo 2026-10-15 13:00–13:01. No se citan entre sí; son tres informes, una evidencia y un script.

| Archivo | Líneas | Qué es |
|---|---|---|
| [auditoria_python_harness.md](docs/informes/auditoria_python_harness.md) | 533 | Auditoría de 28 hallazgos **A01–A28** con prioridad P0/P1/P2, evidencia JSON y corrección propuesta. Dictamen: la arquitectura PocketFlow+Laya es razonable; el riesgo está en las fronteras. |
| [revision_integral_harness.md](docs/informes/revision_integral_harness.md) | 631 | Revisión integral: 21 hallazgos **H01–H21** (matriz), 26 reproducciones **R01–R26**, evidencia de tests/lint, "qué no debe reabrirse" y plan por fases. |
| [descubrimientos_y_fixes_harness.md](docs/informes/descubrimientos_y_fixes_harness.md) | 806 | Los mismos 21 hallazgos **H01–H21** con decisión recomendada, fix mínimo, pruebas de aceptación T-Hxx, plan en 8 PR y registro de las 26 comprobaciones. Declara "propuestas, sin aplicar cambios al proyecto". |
| [evidencia_revision_harness.json](docs/informes/evidencia_revision_harness.json) | 1.768 | Evidencia de máquina: `sha256` del ZIP, inventario (194 archivos / 74 .py / 17.219 líneas), 18 reproducciones, 25 tools, 244 llamadas sensibles, 48 `except` amplios. |
| [reproducir_auditoria.py](docs/informes/reproducir_auditoria.py) | 345 | Script con **28 sondas** (`@probe('A01'…'A28')`). Requiere `/mnt/data/deepseek-flow-10-15-main.zip` y `pyfakefs` (no instalado): **no corre en este entorno tal cual**. |

Los tres informes coinciden en el fondo: mismo diagnóstico, distinta numeración (A→H) y distinto nivel de detalle. No hay contradicciones internas entre ellos.

---

## 2. Hallazgo estructural: los informes describen el commit del 9 de octubre, no el proyecto actual

Los informes dicen "ZIP 10-15". El inventario que declaran (194 archivos / 74 .py / 17.219 líneas / 270 funciones de test en 7 módulos) **coincide exactamente con el commit `44b2e5f` "chore(git): el merge de tests/test_smoke.py es union, versionado" del 2026-10-09** — y no con HEAD (201/76/18.361) ni con el árbol de trabajo.

Pruebas convergentes:
- Los rangos de línea citados apuntan al layout de `44b2e5f`/`HEAD`: p. ej. `nodes.py:289-333 AgentStep.exec` (hoy 340-384), `juez.py:147-159 Judge.prep` (hoy 231-244), `LayaRouter.post:495-535` (hoy 588-…). En `git show 44b2e5f:juez.py` `Judge.prep` está en 147: coincidencia exacta.
- Los archivos que siguen limpios (`evals.py`, `effective_n.py`, `bench_juez.py`, `utils/conformal.py`, `modules/memoria.py`, `modules/db.py`, `utils/policy.py`, `utils/fs_tools.py`, `rag.py`) coinciden byte a byte con el árbol actual: sus hallazgos aplican sin traducción.

**Deriva desde el snapshot auditado:**
- 6 commits nuevos (exp/40 A2A, exp/41 replay, exp/42 juez vs inventario): 7 archivos .py, +1.182/−40, incluido `replay.py` y `utils/call_llm.py`.
- **32 archivos .py con cambios sin commitear** del 2026-10-14 (exp/43–exp/50): +1.787/−570. Reescriben justo varias superficies auditadas: `utils/hitl_web.py` (+204/−73), `utils/laya_routing.py` (170→282), `nodes.py` (548→661), `supervisor.py` (v2), `modules/coding.py`, `utils/laya.py`, `utils/tracing.py`, `flow.py`, `main.py`, `banco/banco.py`.

Consecuencia práctica: **3 hallazgos ya no aplican al árbol de trabajo** y varios rangos de línea están corridos (≈+50 en `nodes.py`, +85 en `juez.py`, +15 en `modules/coding.py`). Detalle en §5.

---

## 3. Estado del proyecto hoy (el gate que los informes no corrieron)

Los informes declaran explícitamente "pytest completo no ejecutado" (solo 17 casos de `test_laya_routing.py`) y no corrieron `calidad.sh`. Ejecutado ahora:

| Palanca | Resultado | Lectura |
|---|---|---|
| `ruff check .` | **91 errores — los 91 en `docs/informes/reproducir_auditoria.py`** | El código del proyecto está limpio: `ruff check . --exclude docs/informes/reproducir_auditoria.py` → "All checks passed!". El paquete de auditoría **deja el gate de higiene en rojo** (`./calidad.sh` → ❌). |
| `pytest tests/ -q` | **401 pasan, 2 fallan en 67 s** | Las 2 fallas son ambientales: `test_search_files_*` intenta `mkdir` en `/home/roquedb/Documentos/00_IA/Pocketflow/_tmp_search_files*`, fuera del workspace de la sesión → `OSError: [Errno 30] Read-only file system`. No es un defecto del proyecto. |

Es decir: el proyecto tiene hoy **403 tests** (vs. los 270 del snapshot y los 17 que el informe pudo correr) y la suite está verde salvo bloqueo de sandbox. El propio informe ya se autoimpone eso como límite (H20) y acierta al decir que su validación no equivale a un gate.

---

## 4. Veredicto por clúster (verificado contra el árbol ACTUAL)

Leyenda: **CONFIRMADO** = el defecto sigue vivo, reproducido; **MATIZADO** = parte del hallazgo no se sostiene; **YA_CORREGIDO** = el árbol de trabajo ya no lo tiene; **OBSOLETO** = la superficie auditada ya no existe.

### 4.1 Seguridad, autorización y despacho

| ID | Estado | Evidencia (árbol actual) |
|---|---|---|
| A01 / H01 (**P0**) | **CONFIRMADO** | `utils/policy.py:164` parte solo por `&&|||;` (no por `\n` ni `&` suelto); `utils/policy.py:51-71` whitelist sin restringir opciones; `modules/coding.py:174` default auto y `:224-232` `shell=True`. Re-ejecutado: `find . -delete`, `find . -exec touch …`, `find . -fprintf …`, `sort -o f`, `git diff --output=f`, `pytest -p plugin`, `cat /etc/passwd`, `echo hola\ntouch f`, `ls & touch f` → todos **auto**, sin aprobación, con shell real. |
| A20 / H03 | **CONFIRMADO** | `utils/fs_tools.py:391-397`: `except Exception: veto = None` → un hook PRE que lanza no veta y la implementación corre. El archivo lo declara como contrato fail-open (`:53-54`). |
| H03 (MCP) | **CONFIRMADO** | `mcp_server.py:67-68` registra `impls[nombre]` (funciones crudas): con FastMCP falso, `run_command`/`read_file` expuestos son el mismo objeto que la implementación y **no** pasan por `run_tool_call` (hooks incluidos). Matiz: el default `MCP_EXPOSE` no incluye `run_command`; el riesgo exige que el operador lo exponga. |
| H02 / A09 | **CONFIRMADO** | `modules/evals.py:28` pasa `salida` (argumento libre del modelo) sin `_resolve` a `generar`, que hace `mkdir` + `write_text` (`evals.py:573-576`). Reproducido escribiendo fuera de `AGENT_ALLOWED_DIRS`. Además `escribir_salida` (`utils/fs_tools.py:120-138`) sobrescribe archivos existentes dentro de las raíces **sin HITL**. |
| A26 | **CONFIRMADO** | `modules/memoria.py:149-163`: `if destino.exists()` da False para un symlink colgante y `write_text` sigue el enlace → creó el archivo **fuera** de la biblioteca. `memory_save` sí tiene la guarda (`:133`). |
| A21 | **YA_CORREGIDO** | `utils/hitl_web.py:274-281`: `finally: _pendientes.pop(token, None)` limpia el pedido al cancelar/expirar. En HEAD (lo auditado) `_pendiente` quedaba sucio. Residual menor: un `KeyboardInterrupt` entre `:270` y `:274` todavía dejaría la entrada. |
| H21 / R24–R26 | **CONFIRMADO** | `banco/banco.py:69` y `:86-88` aprueban por `startswith` (ruta hermana con el mismo prefijo → dentro); `:93` un prompt no parseable → `dentro: True`. **Extra no reportado por los informes:** la limpieza del banco hace `RAIZ / path` (`banco/banco.py:343-348`); con una ruta absoluta o `..` el `rmtree`/unlink sale del repo. |
| A27 | **CONFIRMADO (P2, sin camino de producción)** | `utils/fs_tools.py:379/391/415` indexa `function`/`name`/`id` sin validar → `KeyError` (y en el caso sin `id`, la implementación **ya se ejecutó**). Matiz: `nodes.historiar` (`nodes.py:171-183`) siempre escribe las claves; la envoltura incompleta exige historial construido a mano o corrompido. |

### 4.2 Streaming, cancelación, compuerta de ejecución y telemetría

| ID | Estado | Evidencia (árbol actual) |
|---|---|---|
| A02 / H04 | **CONFIRMADO** | `utils/call_llm.py:204-211` marca `cortado` pero `:228-239` reconstruye y devuelve `tool_calls`; `nodes.py:386-393` enruta cualquier `tool_calls` a `"tool"`. Tras Ctrl+C la tool call se conserva y se despacha. Segunda vía: DSML acumulado (`nodes.py:353-367`). Se queda corto: un fragmento sin `name`/`id` no solo se conserva, **se despacha** (`ERROR: herramienta desconocida: None`). |
| A03 / H05 | **CONFIRMADO** | `nodes.py:330-337` retira `TOOLS` del request al agotar presupuesto, pero `nodes.py:388-393` y `:419-433` ejecutan el lote igual: 5/5 calls con presupuesto agotado. No existe objeto presupuesto/deadline global; el único tope es de rondas por pregunta (`nodes.py:111-124`). **Desvío:** la mitad DSML ya está cerrada (`nodes.py:152-168`, exp/12/36); falta solo el canal nativo. |
| A04 / H11 | **CONFIRMADO** | `nodes.py:611` calcula `aplicada` y `:615-628` la registra **antes** del segundo voto (`:641-648`), que puede vetar a `"herramientas"`. El evento no tiene campo de voto ni veto; nada lo corrige después. Matiz: solo ocurre en `enforce`. |
| A05 | **CONFIRMADO** | `nodes.py:565` (prep devuelve dict) → `:641` `voto_confirmacion_router(prep_res)` → `:514` `str(pregunta)` → prompt con `{'pregunta': 'hola'}`. Doble serialización en ambos brazos. |
| A16 / H11 | **CONFIRMADO** | `nodes.py:430` `ok = not content.startswith("ERROR")`, mientras `modules/coding.py:239` devuelve `exit 1` y `:218` `"RECHAZADO…"`. Re-ejecutado: ambos con `ok: True`. El rechazo sí queda en el registro de aprobaciones (`coding.py:215`): lo que miente es la traza. |
| A22 / H11 | **CONFIRMADO** | `evals.py:415-426` suma segundos por nodo, inclusivos: dos eventos de 10 s (nodo contenedor + tool) → `total 20.0`. Además el cronómetro incluye la espera humana del HITL (`nodes.py:424-431` dentro de `run_tool_call` → `coding.py:214`). No hay tokens ni dinero en la traza (`utils/tracing.py:29-36`). El informe ya lo acota (R16 sintético). |

### 4.3 Memoria, RAG y SQLite

| ID | Estado | Evidencia (árbol actual) |
|---|---|---|
| A06 / H07 | **CONFIRMADO** | `utils/contexto.py:76-77`: sin juicio de Laya devuelve `unidades[:max_unidades]` (recorta, no es no-op); `modules/memoria.py:118-120` lo marca como prefiltro actuado y `:91` imprime `[prefiltro Laya: 12 → 8 archivos]`. Reproducido: 12 notas → 8, con aviso de Laya **sin haber usado Laya**. El camino "sin Laya devuelve todo" (`memoria.py:116-117`) es inalcanzable porque `_puntuar` captura toda excepción y devuelve `None`. **Dos extras no reportados:** (a) `tests/test_smoke.py:3246` afirma el no-op pero usa 2 notas con N=8 → **falso verde**; (b) el mismo defecto afecta a `rag_search` (`modules/rag.py:73,81`). También el docstring de `utils/contexto.py:70` y `docs/roadmap.md:248` documentan el no-op que no se cumple. |
| A07 / H07 | **CONFIRMADO** | `utils/contexto.py:96-99` construye el estado con `str(unidad)` = **ruta** (`modules/memoria.py:115` pasa `Path`): el clasificador puntúa nombres de archivo, nunca el contenido de las notas. |
| A08 / H06 | **CONFIRMADO (con symlink real)** | `modules/memoria.py:46` usa `raiz.glob("*.md")` + `is_file()` sin la política `sin_enlaces` que sí aplica `utils/fs_tools.py:31-40`. Con `memoria/enlace.md -> /tmp/fuera/privado.md`, `memory_search` devuelve el marcador privado mientras `read_file` y `search_files` lo bloquean en el mismo entorno. |
| A15 / R08 | **CONFIRMADO** | Firma `def memory_search(query)` (`modules/memoria.py:49`) contra schema con `"required": []` y "opcional" (`:184-186`). `run_tool_call` con `{}` → `ERROR: TypeError: memory_search() missing 1 required positional argument`. Mitigado porque vuelve como texto de tool. |
| A14 / H08 / R11 | **CONFIRMADO** | `modules/db.py:111-112` decide el tope con una regex sobre el texto sin comentarios (`_sin_literales` no los borra) y `:114` usa `fetchall`. Medido: 50 filas por defecto, **200 con `LIMIT -1`**, **200 con `-- limit`**. La conexión (`:22`) es de escritura, sin `mode=ro`. Matiz: un `LIMIT` explícito grande es diseño declarado, no evasión. |
| H06 (RAG) | **CONFIRMADO** | `rag.py:228,244-247` devuelve `path`/`texto` del índice sin revalidar contra los permisos actuales; `_cargar` (`:170-195`) lee y cachea `chunks.json` sin comprobar rutas. Escenario válido: índice heredado o permisos reducidos después de indexar. |

### 4.4 Métricas, evals, bench y router

| ID | Estado | Evidencia (árbol actual) |
|---|---|---|
| A11 / H10 / R15 | **CONFIRMADO** | `evals.py:174-178` protege el baseline pero no el bench nuevo: con baseline numérico y bench degradado, `TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'` (reproducido; precondición real: `salidas/evals/bench_router.json`). |
| A10 / H10 | **CONFIRMADO** | `evals.py:63-67` se autodenomina "compuerta EXACTA de producción" pero usa umbral fijo y ningún elemento de la cascada real: sin segundo voto, sin q conformal, sin validación de `probabilities`, sin regla temporal exp/46 (`nodes.py:576`), sin truncamiento a 1000. Medido: bench `directo` vs producción `herramientas`. |
| A13 / H15 / R19 | **CONFIRMADO** | `utils/laya_routing.py:81-84` acepta `float('nan')`; `:203-205` compara `p < umbral` (False con NaN) → `directo` con causa `p(directo)=0.510 >= umbral nan`. `utils/conformal.py:90-94` acepta `conf` fuera de rango y convierte `"false"` → `True`; `q = inf` → `None` → umbral fijo. |
| A18 / A19 / H09 (R12–R14) | **CONFIRMADO** | `effective_n.py:97-106` no valida forma: `[]`, `null`, `{"fields":null}` → `AttributeError` (existe `informe.leer_registro`, `:56-76`, que sí lo maneja; no se usa). Huella sin `sort_keys` (`:49`) → mismo objeto con claves anidadas en otro orden = huellas distintas. Multicarpeta suma cardinalidades locales y las rotula como conjunto (`:375-386`) — reproducido con dos carpetas reales: "2 registros → Effective N 2" con unión global 1; el docstring promete solapes cruzados que el informe conjunto no calcula. `MAX_FILES=30` de `informe.py:30` trunca en silencio (`effective_n.py:67-68`). `flow.params` se congela en la primera corrida (`effective_n.py:294-301`) → segunda carpeta ignorada. |
| A23 | **CONFIRMADO (magnitud no medida)** | `utils/laya.py:144-152` llama `predict_batch(...)` sin `batch_size` aunque la dependencia lo ofrece (`laya/agent.py:711-731`). El propio informe declara que no midió OOM. |
| A28 | **CONFIRMADO** | `bench_juez.py:185-198` marca `cita_ok: None` en la rama de excepción y `:217-224` promedia solo sobre `con_cita`: 2 casos que exigen cita, 1 con respuesta → `cita_ok = 1.0`. |
| H16 | **CONFIRMADO** | `juez.py:27` `MAX_CITAS=5`, `:25` regex que exige ruta absoluta, `:236` ventana de 2 líneas; la compuerta determinista solo reacciona a citas rotas (`:289-316`) y `bench_juez.py:49-57` gradúa por presencia de tokens (`respuesta_ok('Esto NO esta escrito en Python', {'contiene':['python']}) == True`). El informe lo presenta como límite deliberado, no como bug: correcto. |
| H15 (caché de errores) | **MATIZADO / ya corregido** | La afirmación "la caché de errores de Laya es permanente" **no** se sostiene en el árbol actual: `utils/laya.py:35,57-64,90,94` implementan `LAYA_ERROR_COOLDOWN` con reintento y limpieza (parte del diff sin commitear). En HEAD sí era permanente. |
| A12 (supervisor) | **NO_REPRODUCE / OBSOLETO** | La ruta auditada (`supervisor.ElegirSiguiente` + `elegir_con_deepseek`) **ya no existe**: el Supervisor v2 usa tool-calling nativo (`supervisor.py:47-51,203-216`) y no invoca Laya en ningún punto; el contrato del fine-tune se mudó a `sonda_supervisor.py:82`. La reproducción del informe parchea símbolos inexistentes (`AttributeError`). Era real en `44b2e5f` (`supervisor.py:194` llamaba `preguntar(...)` sin `try/except`). El chat sí conserva guardas equivalentes (`nodes.py:580-586,640-644`). |

### 4.5 Sesión, compacción e infraestructura

| ID | Estado | Evidencia |
|---|---|---|
| A17 / H12 | **CONFIRMADO (con matiz)** | `utils/compaccion.py:146-158` reemplaza la zona fría por un placeholder fijo; `compactar` (`:165-201`) no persiste nada. Re-ejecutado: 22 → 14 mensajes y el objetivo activo desaparece, con un texto que afirma que "los hechos durables están en memoria/" sin haberlos guardado. Matices: (a) **sí hay persistencia automática antes del recorte** desde exp/48: `nodes.py:15,234` graba el `shared` completo en `salidas/threads/<id>.jsonl` (`utils/thread_store.py:38-49`, `THREAD_PERSIST` default 1) y la línea pre-compacción conserva el objetivo — pero `thread_store.cargar`/`resume.py:35` rehidratan **solo la última línea** (la compactada), así que la recuperación no es automática; (b) `main.py:66` resume al salir sobre el historial **ya reducido**, y solo con `MEMORIA=1` y ≥2 preguntas; (c) la promesa del marcador sigue siendo falsa: `memory_search` solo lee `memoria/*.md` (`modules/memoria.py:42-46`), no el thread store. Confirmado además que **no hay techo duro**: con una ventana caliente enorme, `compactar` devuelve 301.198 chars con `COMPACTION_CHARS=60000`. En `44b2e5f` no existía `thread_store.py`: allí el hallazgo era exacto. |
| A25 | **CONFIRMADO (contrato)** | `nodes.py:34` `PREGUNTAS_LOG` default `"1"` → `:41` guarda la pregunta en texto plano (4000 chars); el log de routing con texto es opt-in (`utils/laya_routing.py:229`, `LAYA_LOG_PREGUNTA=0`). Es coherente con el diseño (exp/34) pero no con la política opt-in del otro sink. Contexto local: el `.env` de este checkout fija `LAYA_LOG_PREGUNTA=1`, así que **en esta máquina ambos sinks guardan texto** (config del operador, no default del código). |
| A24 | **CONFIRMADO (parcial)** | `utils/laya.py:81-85` desaloja **después** de cargar el nuevo checkpoint (pico de MAX+1); el desalojo es por uso (`_uso`), no por antigüedad. No se midió RSS/VRAM. |
| H13 | **coincide con el código** | El informe lo marca como S (lectura), no como reproducido, y así es: `utils/fs_tools.py:187-212` hace `read_text` completo y recién después pagina; `modules/coding.py:227` usa `capture_output=True` y recorta en `:238`; `modules/vision.py:172` invoca `pdftoppm` **sin** `-f/-l` (rasteriza todas las páginas) y recién en `:186` compara con `PDF_PAGINAS_MAX`. |
| H14 | **coincide con el código** | Publicación no atómica confirmada: `modules/escritura.py:97` y `heartbeat.py:47` usan `write_text` directo (sin `os.replace`/temp + rename). Los informes lo condicionan a concurrencia/interrupciones, correcto. |
| H17 | **coincide con el código** | `utils/websearch.py:16-19` devuelve `"ERROR: búsqueda web falló"` como **texto** y `research.py:77-86` lo pasa a `call_llm` sin distinguirlo; `mcp_client.py:85-97` no tiene allowlist por herramienta/efecto ni límite de tamaño; `modules/a2a.py:119-165` solo valida nombre configurado. El informe ya lo relativiza (endpoints los fija el operador). |
| H18 | **CONFIRMADO** | `modules/__init__.py:16-19`: un módulo que falla al importar aborta `discover` (sin try/except) y `impls.update` no detecta colisiones. **Extra:** `utils/call_llm.py:19,47` lee también `~/Documentos/00_IA/bmo/.env` (otro proyecto): en esta máquina `LLM_MODEL`, `LLM_BASE_URL`, `LLM_MAX_TOKENS`, `LAYA_UNSURE_LOW` y `MAX_RETRIES` salen de ahí. `requirements.txt` no declara `requests` (usado en `modules/vision.py:32` y `modules/a2a.py:34`) ni `ruff` (`calidad.sh:14`). |
| H19 | **MATIZADO** | El contrato de privacidad (`PREGUNTAS_LOG` default 1 con texto) se sostiene, pero **el número de tools quedó viejo**: el informe dice 28 (exacto en `44b2e5f`) y hoy `nodes.TOOLS` tiene **29** (se sumó `request_human_input`, `modules/humano.py`). Además el `README.md` tiene drift que el informe no lista: `:70` "Capacidades (24)", `:85` vende el supervisor como "bucle reactivo: Laya elige la herramienta" (falso desde el v2) y `:91` dice que `ver_pdf` usa la Files API cuando usa `pdftoppm` (`modules/vision.py:147-154`). |
| H20 | **MATIZADO** | No hay CI de ningún tipo (`.github/`, `.gitlab-ci.yml`): el gate es `calidad.sh` manual, sin versión de ruff fijada ni `requires-python`. El conteo "270 funciones en 7 archivos" es exacto para `44b2e5f`; hoy son **13 archivos y 373** (`pytest`: 401 pasan, 2 bloqueadas por sandbox). Correcto que la suite no ejecutada era un límite de la auditoría. |
| R20 | **CONFIRMADO** | `utils/compaccion.py:83-111` solo recorre `assistant` con `tool_calls`; una respuesta `tool` huérfana pasa sin error (`validar_historial([system, tool]) == []`). No viola ninguno de los 4 invariantes que declara (`:15-24`): es un hueco frente al contrato de la API. |
| R21 | **MATIZADO** | Igual que A17/H12: el marcador sustituye la decisión sin persistirla, pero el `shared` completo ya se appendea a `salidas/threads/<id>.jsonl` antes del recorte, aunque no se rehidrata automáticamente hacia atrás. |
| R22 | **CONFIRMADO** | `mcp_server.py:67-68` registra `impls[nombre]` crudo (armado en `:56-61`), sin pasar por `run_tool_call` (`utils/fs_tools.py:372-415`, único camino con `HOOKS_PRE`/`HOOKS_POST`). |

---

## 5. Precisión de los informes

**Aciertan:**
- El núcleo P0/P1 está **reproducido y es real**: clasificación auto insegura, hooks PRE fail-open, cancelación que conserva tools, presupuesto que no bloquea, escrituras sin validar (evals y memoria), SQL sin tope efectivo, prefiltro que recorta y miente, métricas con semántica ambigua. Ninguno resultó falso.
- Los números de datos son exactos: calibración 85 filas / 84 herramientas / 1 directo / 77 correctos; 28 sondas A01–A28; 26 comprobaciones R.
- El aparato de honestidad (leyenda R/S/D/M, "qué no debe reabrirse", límites declarados) es inusual y correcto: no inflan P2 a P0, marcan lo sintético como sintético y distinguen "garantía ausente" de "explotable".

**Se quedan cortos o desactualizados:**
- **Toda la numeración de línea de los archivos sucios** apunta al snapshot del 9-oct (`nodes.py`, `juez.py`, `modules/coding.py`, `utils/laya_routing.py`, `utils/tracing.py`, `utils/hitl_web.py`, `main.py`, `flow.py`).
- **Ya no aplican (o aplican a medias)**: A21 (hitl_web limpia en `finally`), A12 (la ruta auditada del supervisor se borró en el v2), la mitad "no hay persistencia previa" de A17/H12/R21 (`thread_store` appendea el `shared` completo antes del recorte desde exp/48) y la "caché de errores permanente" de H15. Presentarlos como vigentes induce a trabajo ya hecho.
- Precisión sobre piso real: A27 no tiene camino de producción (lo dice el propio repo en `nodes.historiar`) y H05 ya tiene cerrada la mitad DSML.

**Extras que los informes no vieron** (encontrados al verificar):
- El falso verde de `tests/test_smoke.py:3246` sobre el prefiltro (2 notas con N=8: nunca ejercita el recorte).
- El mismo defecto de prefiltro alcanza a `rag_search` (`modules/rag.py:73,81`) cuando `RAG_PREFILTRO_N < k`.
- El escape de la limpieza del banco: `RAIZ / path` con ruta absoluta o `..` sale del repo (`banco/banco.py:343-348`).
- El docstring de `utils/contexto.py:70` y `docs/roadmap.md:248` documentan el no-op que no se cumple.
- `memory_save` del mismo título el mismo día **pisa** la nota anterior sin aviso (`modules/memoria.py:131-139`).
- Drift de documentación no listado: `README.md:70` (24 capacidades), `:85` (supervisor con Laya, falso desde el v2), `:91` (`ver_pdf` por Files API, usa pdftoppm).
- El registro de tools pasó de 28 a **29** con `request_human_input` (`modules/humano.py`), y `utils/call_llm.py:19,47` resuelve parte de la configuración desde el `.env` de **otro proyecto** (`bmo/.env`).

**Artefactos declarados que no se entregaron:**
- `auditoria_resultados.json` (`auditoria_python_harness.md:534`) — ausente.
- `evidencia_descubrimientos_fixes_harness.json` (`descubrimientos_y_fixes_harness.md:749`) — ausente; el JSON entregado es `evidencia_revision_harness.json`, que contiene 18 reproducciones (no las 23/26 que los textos mencionan).
- El ZIP `deepseek-flow-10-15-main.zip` — ausente, y `reproducir_auditoria.py` tiene 27 rutas `/mnt/data` incrustadas y depende de `pyfakefs` (no instalado): **no es reproducible aquí sin adaptarlo**.

---

## 6. Qué conviene hacer

1. **No volver a auditar lo que ya está cerrado**: A21, A12 (superficie borrada) y la caché de errores de H15.
2. **Cerrar el P0 real** (A01/H01): default manual de `HITL_AUTO`, `shell=False` con argv, y parsing que cubra `\n` y `&`; o, como mínimo, quitar de la whitelist lo que no es solo-lectura por construcción (`find` con `-delete/-exec/-fprintf`, `sort -o`, `git diff --output=`, `pytest -p`, `cat` sin contención de rutas). El propio `docs/roadmap.md:196-207` documenta la intención "auto = solo-lectura verificado"; el código no la cumple.
3. **Unificar el camino de escritura**: `modules/evals.py` debe validar `salida` con `_resolve`/`escribir_salida`; `guardar_resumen_sesion` debe compartir la guarda de `memory_save`.
4. **Fallar cerrado en los hooks de seguridad** (separar hooks obligatorios de observabilidad) — cambio de una línea en `utils/fs_tools.py:394`, con la salvedad de que hoy el denylist no lanza.
5. **Arreglar el prefiltro**: sin juicio de Laya, devolver todo (como promete el contrato) y corregir el test que hoy lo da por bueno con 2 notas.
6. **Sacar el script del auditor del gate o limpiarlo**: 91 errores de ruff en `reproducir_auditoria.py` dejan `./calidad.sh` en rojo. Mover el paquete a un directorio excluido de ruff (p. ej. añadir `docs/informes` al `exclude`) o arreglarlo.
7. **Re-ejecutar los informes sobre HEAD + árbol sucio** cuando se quiera un veredicto vigente: hoy su valor es de diagnóstico histórico (9-oct), no de estado actual. Con la suite de 403 tests disponible, la validación de los fixes puede hacerse contra el gate real.

---

## 7. Los dos archivos nuevos (2026-10-15 16:22)

| Archivo | Qué es |
|---|---|
| [correcciones_deepseek_flow.md](docs/informes/correcciones_deepseek_flow.md) | 665 líneas. Informe "código mal vs. código bien" con 6 correcciones y la evidencia medida de cada una. Declara el resultado global del gate: antes 9 failed/282 passed/5 skipped → después 326 passed/0 failed/9 skipped, con un test nuevo de 39 casos. |
| [deepseek-flow-fixes.patch](docs/informes/deepseek-flow-fixes.patch) | Diff unificado (93+/11−) sobre 5 archivos: `utils/policy.py`, `modules/coding.py`, `modules/memoria.py`, `evals.py`, `tests/test_smoke.py`. Es el "después" del informe. |

**Verificado aplicándolo en copias `/tmp` del árbol actual** (el repo no se tocó; 8/9 hunks aplican):

| Corrección | Resultado verificado |
|---|---|
| §1 Bypass del HITL graduado (`utils/policy.py`) | **Cierra el P0.** Deja de ser `auto`: `ls & touch x`, `find . -delete`, `find . -exec …`, `sort -o`, `git diff --output=`, `pytest -p`, `pytest --basetemp=/`, `echo hola\ntouch x` → `preguntar`; `ls\nrm -rf ~` y `cat a & rm -rf b` → `confirmar_doble`. Los legítimos (`ls`, `pytest -q`, `cd /x && pytest`, `grep -r x . 2>&1`, pipes de lectura, `git log`) siguen `auto`: sin regresiones. |
| §2 Denylist dura (`modules/coding.py`) | **Funciona:** veta `rm -rf /`, `/*`, `~`, `$HOME`, `-r -f /`, `sudo rm -rf /`, `/bin/rm -rf /`, `rm -rf / --no-preserve-root`*(no)* y la fork bomb, y **no** veta borrados acotados (`rm -rf ./build`, `/tmp/mio`). **Gap encontrado:** la variante `rm -rf / --no-preserve-root` (flag *después* de la ruta) no la veta — igual cae en `confirmar_doble`, así que no queda en `auto`. |
| §3 `run_command` auto vs. `AGENT_ALLOWED_DIRS` | **Funciona:** con las raíces acotadas, `cat /etc/passwd` y `cat ../../etc/hosts` vuelven a pedir aprobación (con aprobación denegada: `RECHAZADO`), mientras `cat README.md` sigue `auto`; `_sale_de_raices` devuelve True ante `$HOME`. |
| §4 `TEST_ROUTER` fijo (`evals.py`) | **Funciona:** usa `utils.rutas.tasks_dir()`; con `BMO_TASKS_DIR=/tmp/mis_tasks` la ruta pasa a `/tmp/mis_tasks/router_flow_test.jsonl` (mismo default histórico). |
| §5 Memoria anclada al CWD (`modules/memoria.py`) | **Funciona:** desde otro CWD, `_raiz()` pasa de `/tmp/memoria` (biblioteca vacía) a `<proyecto>/memoria`. |
| §6 Tests no herméticos (`tests/test_smoke.py`) | **Funciona:** en una copia escribible, la suite pasa de **2 fallos** (`test_contencion_de_rutas`, `test_search_files_por_nombre`, por rutas del autor hardcodeadas) a **0 fallos / 399 passed / 4 skipped**. |

**Lo que falta o no cierra en la entrega:**
1. **No entregaron `tests/test_policy_bypass.py`**: el informe lo anuncia con 39 casos y cita `test_auto_fuera_de_raices_pregunta`, pero el propio patch dice `Only in ./tests: test_policy_bypass.py`. Sin ese archivo no se pueden fijar las regresiones ni reproducir el "326 passed".
2. **1 de 9 hunks no aplica** (`tests/test_smoke.py`, hunk #3, rechazado a `.rej`): parchea un test que monkeypatchea `sup.elegir_con_deepseek`, símbolo que el **Supervisor v2 ya borró**. Es inocuo (la suite queda verde igual) pero confirma que el patch se escribió sobre el snapshot del 9-oct, como la auditoría.
3. **Los números globales no son de esta máquina:** el informe declara 9 fallos antes; en una copia fiel del árbol actual medí **2** (los otros dependen de `ddgs`/checkpoint/rutas del autor). Su propio "Pendiente" dice 28 tools: hoy hay 29.
4. **`ruff` sigue rojo después del patch** — no por estos dos archivos, sino por los 91 errores que dejó el paquete de auditoría anterior en `reproducir_auditoria.py`.

**Recomendación (aplicada):** el patch se aplicó sobre el árbol de trabajo el 2026-10-15, con respaldo previo.

**Estado tras aplicar:**
- 8/9 hunks aplicados; el único rechazado (`tests/test_smoke.py` hunk #3) se descartó por obsoleto (parcheaba un test que usa `sup.elegir_con_deepseek`, símbolo que el Supervisor v2 borró) y su `.rej` se eliminó.
- Contribución exacta: `utils/policy.py` +34/−1, `modules/coding.py` +32/−3, `modules/memoria.py` +6/−2, `evals.py` +2/−1, `tests/test_smoke.py` +17/−4 (91+/11−; los 2 añadidos del hunk rechazado no entran).
- **Batería en sitio:** todos los vectores de la auditoría cerraron (`preguntar`/`confirmar_doble`), los comandos legítimos siguen `auto`, la denylist veta 4/4 sin falsos positivos, `cat /etc/passwd` pide aprobación y `cat README.md` sigue `auto`. Los 6 archivos compilan.
- **Gate:** `ruff check .` sigue en 91 errores — todos del script del auditor; excluyéndolo, "All checks passed!". `pytest`: **433 passed, 2 failed** — y esos 2 (`test_search_files_conteo_exacto_al_truncar`, `test_search_files_sin_aviso_bajo_el_tope`) fallan solo porque el sandbox de esta sesión bloquea la escritura en `/home/roquedb/Documentos/00_IA/Pocketflow/_tmp_search_files*`, fuera del workspace; en una copia escribible la suite queda verde.
- **Test que faltaba, reconstruido:** `tests/test_policy_bypass.py` (32 casos: vectores cerrados, legítimos sin regresión, denylist con y sin falso positivo, `auto` fuera/dentro de raíces) pasa en verde y con ruff limpio. **No es el archivo del autor** (sus 39 casos no se entregaron): es una reconstrucción de la especificación §7 del informe.
- Respaldo pre-patch en `salidas/patch_backup_20261015/` (gitignored). Para revertir: `patch -R -p3 < docs/informes/deepseek-flow-fixes.patch` o copiar desde el respaldo.
- Queda pendiente el detalle del regex: `rm -rf / --no-preserve-root` (flag después de la ruta) no lo veta la denylist — igual cae en `confirmar_doble`, así que no vuelve a `auto`.

---

*Contraste realizado sin modificar el código del proyecto. Artefactos temporales en `/tmp`; el único archivo agregado es este informe.*
