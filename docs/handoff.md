# Handoff — para seguir el trabajo con contexto limpio

Documento vivo: se actualiza en cada hito (X*n*). Lo estable está en
`docs/principios.md`; el detalle, en `docs/elegancia.md`, `docs/estado.md` y
`docs/bitacora.md`. Acá va lo que hoy solo vivía en las conversaciones.
`tests/test_handoff.py` verifica que lo que cita exista.

**Al día con:** X179 (`fable_judge` recompuesto contra una foto byte a byte de 6 escenarios; `bash -m pytest` ya no pasa la allowlist del re-run y las citas del juez se verifican contra lo que el prompt mostró), X178 (los 25 `except` amplios revisados: 3 fuera con su test, uno tapaba un rechazo instantáneo del HITL web con `HITL_WEB_TIMEOUT=inf`; 22 clasificados), X177 (la política de git en una sola estructura; `fable_judge` sin dos copias, y el tope de las fuentes del modo dominio, que dejaba pasar 50k contra 9k, ahora se respeta), X175 (la vara antes de pulir: cobertura por archivo como etapa 5/5 de `calidad.sh`, con baseline por intérprete —1.053 en 3.12, 1.052 en 3.14— y la resolución por nombre suelto de citas restringida a raíces versionadas (el número ya no depende de artefactos del árbol: medido, clon limpio y árbol real con 0 diferencias por archivo); sin sección para el intérprete que corre es ROJO y se siembra con `--sembrar-entorno`— y la pasada medida sin `.env` como el CI; borrador de la aceptación v1 con 3 huecos del operador), X174 (el scope solo aprueba subcomandos de git declarados: `git config` y los que ejecutan o borran refs quedan afuera; **`lineas_del_producto` +4 aceptado por el operador con su clave**), X173 (la 4.ª medición de `tool_choice="none"` con el request real: **el prefijo no se comparte** —`none` 266 vs `base` 5.179, delta 4.913, 0 de hit en la primera `none`— y **`none` no frena la tool**: el pedido sale como markup DSML en texto y `normalizar` lo recupera y lo ejecuta; S3 no gana por esa vía, informe `docs/informes/s3_prefijo_none_2026-11-06.md`), X172 (un scope sin lista de comandos no aprueba ningún comando: `comandos: null` = `[]`; los 69 escenarios del banco sin `permitir_comandos` que aprueban algún turno ya no reproducen sus corridas con comandos, declarado), X171 (el scope de `delegar_tarea` ya no aprueba solo lo que no sabe leer: con prefijos autorizados, cada segmento necesitaba su base declarada y sus opciones en la lista blanca —`opciones_de_scope`: `cd`, `python3`, `ruff`, `git`, `ls`, `cat`, `mkdir`, `rm`—; `bash -c`, `find -delete`, `pytest -p`, `sort --compress-program`, `ruff --fix` y `tail -f` quedan `fuera-de-scope`; el chat no cambia; límite: `comandos: null` sigue sin restricción), X170 (el scope de `delegar_tarea` ya no aprueba sin humano un `git` que la política no sabe leer —`-c`, `--exec-path`, `--super-prefix` o un global desconocido: `fuera-de-scope`—; el chat sigue leyendo el subcomando detrás del global; deuda aparte: la clase amplia `bash`/`find`/`pytest` con prefijo autorizado), X168 (opción b de X167: fuera la tool `evals` del chat y la rama `triaje` del heartbeat, siguen como CLI; `producto_conoce_lab` 2 → 0), X169 (`stash drop`/`clear` y `branch -D` piden doble confirmación y el scope de `delegar_tarea` deja de aprobarlos solo; `lineas_del_producto` +7 aceptado por el operador con su clave), X165–X167 (utils de laboratorio a `instrumentos.py`, 3 funciones sin llamador borradas, `producto_conoce_lab` cuenta `LABORATORIO_RAIZ`: **0 → 2 aceptado por el operador con su clave**), X164 (relevamiento final de `utils/` y `modules/`: el mapa con candado y el índice de S0 por frontera; 3 decisiones abiertas en la deuda del roadmap), X159b (`hitl_web` valida y lee el cuerpo del POST en un solo lugar), X162 (`resume` corre el mismo ciclo de vida que una sesión nueva, `main.sesion`), X161 (`heartbeat` resuelve la salida antes de tocar el disco: una salida fuera de las raíces es un error de esa tarea), X163 (5 chequeos de S0 que ningún test cuidaba, ahora con test: cada uno en rojo contra su mutante), X160 (la ruta del trabajo en el re-run de `fable_judge` va con `shlex.quote`: se cerró una inyección por nombre de directorio y un falso REFUTED con espacios), X159a′ (las ramas con `/` o `.` —`feature/x`, `origin/main`, `v1.2.0`— vuelven a un s/n; las rutas con extensión y los dotfiles siguen en doble), X159a (lo que descarta trabajo —`git reset --hard`, `clean -f`, `checkout --`, `restore`— pide doble confirmación y el scope de `delegar_tarea` deja de aprobarlo solo; `lineas_del_producto` +27 aceptado por el operador con su clave), X158 (sonda de `tool_choice="none"` **corrida con autorización del operador (la ejecutó Chief)**: la acepta y no devuelve tool calls, así que S3 se podía pre-registrar **con la salvedad del prefijo** —el prompt pasa de 673 (con tools) a 40 (sin tools) y la caída de 633 tokens es el tamaño de las 3 tools, o sea que el proveedor no las cuenta en `none`; **X173 midió la salvedad: el prefijo no se comparte**—), X157 (no aplica: el despacho y la política ya son únicos por proceso; P3 re-expresada con la redacción aprobada), X156 completo (`nodos_largos` 3 → **0**: los dos de `effective_n` se partieron con la salida idéntica byte a byte; `lineas_del_producto` 7651 → 7646), X156, primera parte (`juez.Judge` partido en funciones de módulo con la salida idéntica; `nodos_largos` 3 → 2; faltan los dos de `effective_n`), X155 (`helpers_duplicados` 8 → 2: `_model` unificado, `_listar`/`_texto` de MCP renombrados; `_approve` duplicado a propósito por la HITL de cada módulo, R7), X154 (`settings_leidos` 50 → 47 y meta ≤ 47: se borran `CHAT_STREAM_INTERRUPT`, `MEMORIA_PREFILTRO` y `MEMORIA_PREFILTRO_N`; `PROMPT_AUDITORIA` e `INFORME_CARPETA` pasan a contrato), X153 (el prefiltro de RAG borrado: con la config documentada nunca filtraba; `settings_leidos` 52 → 50, `helpers_duplicados` 10 → 8; R2 para sus 4 tests; la baja de `tests_definidos` 1181 → 1177 quedó aceptada en `d8153bd`, el gate del tip da IGUAL), X152 (el roadmap post-X150 en `docs/roadmap.md`: de medir a achicar, X153–X158 con principio y gate; el post-X144 al historial; el prefiltro de RAG medido como no-op con los defaults), X150 (exp/110: la asimetría se midió y **no se adopta** —6 delegaciones en 24 corridas y 2 de 5 escenarios anchos contra umbral 3; calidad −0,55 con margen 0,50; costo 1,013×; y cuando la elige no rinde, post-hoc con n=5—; P2 (b) re-expresada con el dato y X151 no aplica), X149 (exp/109: primer benchmark hacia afuera — flow y pi **empatan** en calidad global 1,4286 con 28 corridas porque mini NO MONTA; flow con menos descarrilos y 0 deploys en los dos; costo medido de flow US$0,0726 + US$0,0019 de montaje), X148 (el pre-registro aprobado de exp/110, con la desviación de la Ley 1 declarada), X147 (P2 (c) por construcción: un hijo no puede tener tools fuera de su padre, con la clave del operador para el +8/+6 declarado), X146 (P4 por construcción: un solo despacho protegido) y X145b (la invocación real de mini), el roadmap post-X144 (`docs/roadmap.md`, sección "Roadmap vigente": X145–X151 con principio y gate por paso), X144 (los principios unificados en `docs/principios.md`: visión, P2 como grafo fractal asimétrico —(b) medida y no adoptada en X150—, EL1–EL9 desde `docs/elegancia.md`, fuentes fundamentales y de apoyo, P4 con la garantía en el loop), X143 (la bitácora archivada por mes: `docs/bitacora/2026-10.md` con octubre completo y el archivo vivo con el mes corriente; las citas a entradas viejas migradas), X142 (el límite producto/laboratorio explícito y `lineas_del_producto`: 7.693 líneas de código en 74 archivos, menor mejor — "minimalista" es un número que solo puede bajar; la separación física no hace falta, el producto ya corre solo), X141 (exp/108 corrido por el operador: research sobre el kernel **NO PASA** por el panel ciego —agente 2/6 gana-o-empata contra ≥3— aunque el costo dio 0,14×; la rama research-agente se revirtió sin mergear, queda el tag x139-research-agente y la evidencia en salidas/exp108/; research sigue con su flujo de siempre y el paso 8 queda cerrado para research), X140 (un solo freno de presupuesto en el chat: la fuente es `turno` y el `Ledger` del kernel su proyección, derivada en cada `PasoChat.prep` — antes dos cuentas del mismo número y el freno del Ledger era código muerto; el gate fractal gana el aviso de cierre, el candado del M4, el caso de resume, el despacho único espiado en los tres niveles y timeout: los 8 mutantes ROJO), X138 (el **gate fractal**: `tests/test_gate_fractal.py` verifica que una política agregada una vez —despacho con HITL y política de comandos, saldo, compactación— llega igual al chat, al supervisor y a una copia anidada; el pendiente de P2a queda cubierto), X137 (fase 6, I4: `informe_lote` como función de módulo —el render del lote salió del nodo del batch—; `nodos_largos` **4 → 3** y la meta de la fase 6 se cumple; los tres que quedan esperan la recomposición de P4), X136 (los instrumentos leen la traza del chat real: `banco/probes/rondas.py` contaba 0 rondas y el linter una violación por respuesta; el test de cierre ya no llama a la API), X135 (fase 6: el juez dejó de detectar herramientas inventadas por regex —vocab 4 → 3—: el inventario va al prompt, el modelo lista `tools_usadas` y el código contrasta la membresía; pre-registro exp/107 PASA 4/4 con US$0,0179 de US$0,05), X134 (fase 6: el instrumento de `nodos_largos` cuenta líneas de **código** —el texto impreso no es una arista—; el conteo físico viejo queda como diagnóstico no gateado y el número pasó de 12 a 4), X133 (S9a: la continuación la decide el estado del thread —la pregunta anterior quedó abierta por el techo— y no una lista de palabras; `vocabulario_hardcodeado` 5 → 4, delta declarado), X126 (S9b A′: el chat corre sobre `kernel.loop`; `AgentStep`/`ExecuteTools`/`Cierre` borrados, 22 tests reescritos 1:1 y mapa de compatibilidad para trazas/checkpoints viejos; caracterización 12/12 sin tocar), X132 (S6: un solo techo de 16 por pregunta con el saldo en `turno`; el A/B pre-registrado **PASA** — calidad +0,167 con margen −0,25, costo 0,958×, descarrilos 6 → 4, 0 deploys en s9, US$0,2307), X131 (el exp/105: la réplica del exp/103 con `deepseek-v4-pro` tampoco adopta `dividir`, 0/72; la fractalidad conductual no aparece con los dos modelos medidos), X130 (el linter conoce el loop del kernel: 0 violaciones falsas en las trazas del supervisor), X129 (el exp/104: una tool inerte en el menú no cambia la calidad; la diferencia del exp/103 no se replicó), X128 (la verificación de X127: el gate de nuevo verde en un checkout limpio y el pre-registro del exp/104), X127 (el exp/103: NO PASA por adopción, 0/72; la rama se borró como ata el spec), X126 (S9b: el primer paso y el bloqueo medido), X125 (los imports perezosos: 79 → 14, con `python -X importtime` como gate del arranque), X124 (los instrumentos: bytes del primer request, líneas del loop, D y las fallas de DIG sobre la traza), X123 (la medición honesta: "sin datos" ≠ 0 y denominador simétrico), X114, X115 y X121 (pytest en lista blanca, su configuración vigilada y las comillas del shell), X120 (el exp/103 con el cómputo igualado), X119 (cada copia descuenta del saldo) y X118 (los principios S0, P1–P4, N1–N4), sobre X116 (la definición de elegancia y el kernel fractal) sobre X113, aplicado sobre X112 sobre `cca1f28`, más la auditoría del
operador sobre ese árbol (2026-10-31): dos hallazgos de seguridad abiertos
(X114 y X115 en `docs/estado.md`) y cuatro de orden, todos en la cola.

## 0. Mensaje de arranque para la sesión nueva

> Leé `docs/handoff.md`, `docs/principios.md` y `AGENTS.md`. Te paso el zip
> del HEAD con su sha256: verificalo. Corré `./calidad.sh` y decime si el
> estado coincide con la sección 4 del handoff. No escribas código hasta que
> confirmemos el próximo paso de la cola (sección 7).

## 1. Para qué es el harness

**Qué es.** Un harness de agente minimalista en el que un solo grafo se compone
consigo mismo: el chat, el supervisor y cada capacidad son el mismo loop con
otros datos. La complejidad emerge de piezas mínimas interconectadas, no de
mecanismos agregados; el núcleo no conoce sus módulos y un módulo es una
capacidad.

**Quién lo usa.** El operador, solo, con este equipo de bots como ejecutores.

**Para qué.** Programar y auditar repos con HITL, y experimentar sobre
arquitecturas de agentes.

**Qué es funcionar bien.** La tarea termina con evidencia y sin ninguna acción
no autorizada, a un costo medido; cada pieza nueva entra solo si una medición
la justifica.

Definido el 2026-11-02 sobre la intención del operador: cierra el
`[PENDIENTE: operador]` que abrió X113. Lo que dice el README hoy: un agente
de terminal sobre PocketFlow con DeepSeek, para pedidos sobre tus archivos y
tu código, con CORE + módulos.

**Objetivo final** (operador, 2026-11-02, textual): "harness minimo, de
composición grafo fractal autoreplicante, en donde partes minimas -modulos-
interconectados generan complejidad emergente."

**Aclaración del mismo día** (operador, 2026-11-02, textual; tildes y guiones
normalizados): "grafo fractal asimétrico — el modelo lleva el harness a donde
lo necesita generando patrones; ahí está lo fractal". La fractalidad es
**asimétrica y conductual**: quien lleva el harness a donde lo necesita es el
modelo, no una regla del código. Esto contesta la pregunta de estructural vs
conductual.

`[CERRADO: operador, 2026-11-02 — opción (c)]` La fractalidad es
**estructural**: una instancia es parte de sí misma y no depende de que el
modelo la elija. La conductual queda como capacidad **medida y no perseguida**:
la división se ofreció y no la eligió ningún modelo —0/72 con `deepseek-flash`
(exp/103) y 0/72 con `deepseek-v4-pro` (exp/105)—; antes, el explorador en 0
llamadas y las skills por descripción en 5 de 12. Con eso: la opción (a),
cambiar de modelo, quedó **descartada por medición en dos modelos**; la (b), un
disparo por dato del código, queda como idea **pre-registrable** (tendría que
reformular N1), no como trabajo en curso.

`[REABIERTO: operador, 2026-11-04 — X144]` Lo que (c) cerró fue la
replicación **simétrica**: exp/103 y exp/105 ofrecieron copias iguales
(`recursivo`) y ninguna se eligió. La **asimétrica** —instancias
especializadas, árbol desparejo, hijos con menos poder que el padre— **se midió
en X150 (exp/110) y tampoco se adopta**: se elige más que la simétrica (6
delegaciones en 24 corridas contra 0 de 144, casi todas con `barrido`), pero no
alcanza el umbral pre-registrado (2 de 5 escenarios anchos, pedía 3) y la
calidad cae 0,55 con margen 0,50; `s19`/`s18` cayeron sin delegar, así que con
4 seeds el A/B no separa daño de ruido. Desde X144, P2 es "grafo fractal
asimétrico": especialización y jerarquía son principio (estructurales) y la
forma desigual que decide el modelo queda **medida y no perseguida** (X150). El
dato en contra que hay que honrar: exp/108 —una capacidad recompuesta como
agente— perdió el panel.

## 2. Principios

En `docs/principios.md` (fuente única desde X144): la visión, S0, los de
diseño P1–P4, los de elegancia EL1–EL9 (lo común a PocketFlow, 12-Factor
Agents y Laya), las prohibiciones N1–N4 y las fuentes (tres fundamentales y
las de apoyo). Las reglas de proceso viven en `AGENTS.md`. Acá no se repiten.
La redacción de la visión y de P2 fue **aprobada por el operador el
2026-11-04**; P2 incluye el dato de exp/110: (b) medida y no adoptada.

## 3. Arquitectura

| Pieza | Qué hace | Dónde |
|---|---|---|
| Grafo del chat | `GetQuestion → PreFetch → Skills → Contexto → kernel.loop` (`PasoChat ⇄ ActuarChat`, con `Observar`/`Contexto` como políticas); `CierreChat` por presupuesto; `VerificarCitas` antes de volver a preguntar | `flow.py`, `nodes.py` |
| Kernel fractal | `Ctx`, `Ledger` (un saldo), `Tool`, `loop`, `agente`: el supervisor **y el chat** (S9b A′) son instancias de `kernel.loop` | `utils/kernel.py`, `supervisor.py`, `flow.py` |
| Registro de módulos | `discover()` arma `TOOLS` e `IMPL`; `ganchos()` recorre los `HOOKS` | `modules/__init__.py` |
| Skills | YAML con `condicion` regex (la 5b no la pudo reemplazar) | `utils/skills.py`, `skills/revision.yaml` |
| Política de comandos | Mecanismo en código, listas como datos, falla cerrada | `utils/policy.py`, `utils/politica_comandos.json` |
| HITL | s/n graduado, scope headless, web | `utils/aprobaciones.py`, `modules/coding.py`, `utils/hitl_web.py` |
| Log de riesgo | Cada s/n de comando: las etiquetas de un juez futuro | `utils/riesgo.py`, `banco/probes/estado_riesgo.py` |
| Laya | Juicios locales opcionales: prefiltro de memoria y RAG, juicio MCP | `utils/laya.py`, `utils/contexto.py` |
| Memoria | Biblioteca consultable por tools | `modules/memoria.py` |
| Threads y resume | Checkpoint del `shared` completo; `resume` lo rehidrata | `utils/thread_store.py`, `resume.py` |
| Trazas | nodo/acción/segundos, sin contenido | `utils/tracing.py` |
| Juez de trabajo | La parte de fable que funciona | `fable_judge.py`, `modules/fable.py` |

## 4. Estado al cierre

| ratchet | fase 0 | hoy | meta |
|---|---|---|---|
| `settings_leidos` | 89 | 47 (X154) | ≤ 47 (X154: lo que queda es contrato del operador o seam de prueba usado) |
| `imports_perezosos` | 137 | 14 (X125) | ≤ 40 ✅ |
| `nodos_largos` | 15 (físicas) | **0** (X156: `Judge`, `WriteReport` y `HashFile` recompuestos). Antes **3** (X137/I4: el render del informe del lote salió del nodo; quedan `Judge` 72, `WriteReport` 50 y `HashFile` 47 para la recomposición de P4) | ≤ 3 (definición de X134) ✅ |
| `vocabulario_hardcodeado` | 8 | **3** (X135: el juez ya no detecta por regex) | ≤ 2 → **piso honesto 3** (2 regex de `skills/*.yaml` + `YES` del HITL; se re-expresa en X136) |
| `texto_de_prompt` | 2748 | 1542 | 1542 ✅ |
| `core_importa_modulos`, `funciones_complejas`, `codigo_muerto_privado` | — | 0 | 0 ✅ |
| `producto_conoce_lab` | 10 | **0** (X168; la métrica ve los imports de `LABORATORIO_RAIZ` desde X167) | 0 ✅ |

**Fases.**
- Cerradas: 0, 1 (y su deuda, X109), 2a, 2b-1, 2b-2, 3b, 4b-mín, 4a, 5a, **6 (X134–X137)**, X112, S9a y S9b A′ (X133/X126; de la fase 2 queda solo S3, **medido en X173: no gana por la vía de `none`** —el prefijo no se comparte y `none` no frena la tool—; re-expresarlo es una decisión nueva).
- Cerradas con veredicto negativo: 3a, S1, S2, S7 (5b, revertida).
- Pendientes: la cola de la sección 7.

## 5. Decisiones tomadas (no se reabren sin un dato nuevo)

| Decisión | Por qué | Dónde |
|---|---|---|
| El router sale del chat | 3b: 12/12 directas sin tools, 0,65× USD | `banco/specs/fase3b_4a.md` |
| Thinking con tools, no | 3a: 2,2×–6,9× USD y peor en s17/s18 | `docs/bitacora/2026-10.md` (X105) |
| La 5b se revierte | Disparo 1/2/2 de 4; la regex vuelve con el revert y queda como deuda medida | `banco/specs/fase5b.md` |
| La prosa de fable se borra; el juez se queda | 3 A/B sin lift; el juez refutó 5/5 y cazó 2 bugs reales | X112 |
| La forma es fija | exp/51: −77 % SLOC con este modelo | `main.py` |
| El checklist de auditoría es opción del operador | Único texto con lift donde había margen (s18) | `PROMPT_AUDITORIA` |
| El juez de riesgo observador se borra; `RIESGO_LOG=1` | Lo que se entrena es la decisión humana | X109 |
| La continuación, por estado del thread | Saca la lista de palabras de `GetQuestion`: el estado (la pregunta anterior abierta por el techo) decide, no los sinónimos; delta declarado | X133 (S9a) |
| Imports perezosos ≤ 40 | De 81, la mayoría no rompe ningún ciclo | X112 |
| Meta de `texto_de_prompt` 1542 | Lo fijo + la forma + el checklist; no se recorta para el número | X112 |

**Abiertas.** `HITL_SCOPE` y `HUMANO_RESPUESTA` como contrato con un nombre
neutro. F2 de fable (compuertas en código) solo si un dato lo pide. X114 decidió
la lista blanca de pytest y que `pyproject.toml` cuenta entero; el operador
puede ajustarla (es un dato de `utils/politica_comandos.json`).

## 6. Lo aprendido (una línea por veredicto)

- **3a** (thinking con tools): más caro y peor en las auditorías. El modo lo
  elige el código, no Laya (S2 cerrado).
- **3b**: el modelo decide solo cuándo usar tools; el router costaba más que
  lo que ahorraba (el árbitro del voto).
- **4b-mín**: la regex de palabras no decidía nada (0 cambios en 36 preguntas reales).
- **5a**: pasar las listas a datos con 0 diferencias se prueba con la foto
  real, casos por entrada y fuzz; la duplicación desaparece por construcción.
- **5b**: con este modelo, la activación por descripción no dispara (5 de 12) y
  cuando dispara no mejora. Que algo sea elegante no quiere decir que funcione.
- **Fable**: la prosa no transfiere el método; el juez sí. Lo que falta medir
  son las compuertas (F2).
- **Skill `revision`**: baja el ruido (−40 % y −59 %), no detecta más (exp/56, exp/56b).
- **Checklist de auditoría**: +1,33 en s18; techo en s19 y s20; creó un temporal en 1 de 3 (exp/80).
- **s9 en la 5b**: el 0 venía de tareas sin terminar (5 de 6), no de un deploy: es un dato para S6.
- **Auditoría del operador (X113)**: la contención de rutas, el HITL web y el MCP aguantaron; la lista
  negra de flags de pytest no (tercera vez que una lista negra de flags pierde: E1, E2, X114).

## 7. Cola de trabajo

| # | Paso | Cambia conducta | Depende de | Dato de entrada |
|---|---|---|---|---|
| 1 | Aplicar X112 + X113; la clave por vocabulario 3 → 5 | no | — | — |
| 2 | ✅ **X114, seguridad (S0):** hecho el 2026-11-01 con X115 y X121 (ver `docs/estado.md`) | **sí**, solo sube fricción | 1 | ver "X114 en detalle" abajo |
| 3 | ✅ **X115-orden hecho (2026-11-02):** los `.patch` y el test viejo se borraron (quedan en la historia de git), el candado de higiene es `tests/test_higiene_repo.py` (X122) y las dependencias quedaron separadas: `requirements.txt` (runtime), `requirements-dev.txt` (`-r requirements.txt` + pytest + ruff) y `requirements-opcionales.txt`; el CI instala `requirements-dev.txt` | no | 1 | hecho |
| 4 | ✅ **X125 hecho (2026-11-02):** imports perezosos **79 → 14** (11 stdlib, 2 obligatorias y los internos al tope del archivo que los usa); quedan 8 opcionales y de los 6 internos los dos ciclos reales (`hitl_web` y `juez`→`nodes` vía `discover()`), el de inicialización parcial `modules/supervisor`→`supervisor`, `modules/delegar` (driver PTY) y `fable_judge` (aislamiento del producto), con motivo declarado. Gate: `python -X importtime -c "import main"` (840–935 ms antes, 859–903 ms después) y `tests/test_imports.py` | no | 1 | hecho |
| 5 | ✅ **A/B de S6 hecho (X132): PASA** — un solo techo de 16 con saldo por pregunta; calidad dentro del margen, costo 0,958×, descarrilos 6 → 4 y 0 deploys | **sí** | 1 | s9: 5 de 6 sin terminar, 0 deploys |
| 6 | 5c-a → **X153** del roadmap vigente (`docs/roadmap.md`); acá no se repite (N4) | — | — | `docs/roadmap.md` |
| 7 | 5c-b → deuda abierta del roadmap vigente (`docs/roadmap.md`) | — | — | `docs/roadmap.md` |
| 8 | ✅ **S9a hecho (X133):** la continuación la decide el estado del thread (la pregunta anterior abierta por el techo), no una lista de palabras; `vocabulario_hardcodeado` 5 → 4 y delta declarado en la bitácora | mínimo | 9 | hecho |
| 9 | ✅ **S9b A′ hecho (X126):** el chat corre sobre `kernel.loop`; los 22 tests que nombraban `AgentStep`/`ExecuteTools`/`Cierre` reescritos 1:1 (R2 autorizada), y mapa de compatibilidad para trazas/checkpoints viejos | mínimo | 5 | hecho |
| 10 | ✅ **S3 medido (X173):** `tool_choice="none"` no comparte el prefijo con las tools (`none` 266 vs `base` 5.179, delta 4.913) y no frena la tool (el pedido sale como markup DSML en texto y `normalizar` lo recupera); no gana por esa vía, ver `docs/roadmap.md` e informe `docs/informes/s3_prefijo_none_2026-11-06.md` | — | — | `docs/roadmap.md` |
| 11 | ✅ **Fase 6 completa (X137/I4):** `informe_lote` como función de módulo — el render del informe del lote salió de `JuezLoteFlow` (53 → 29 de código) —; `nodos_largos` **4 → 3**, meta cumplida (quedan `Judge` 72, `WriteReport` 50 y `HashFile` 47 para la recomposición de P4). Antes: ✅ instrumento (X134), ✅ split de `effective_n.WriteReport` (X134a) y ✅ juez sin regex de contexto (X135) | no | — | `nodos_largos` 3 sobre código, `vocabulario_hardcodeado` 3 |
| 12 | ✅ **Archivada por mes (X143):** `docs/bitacora/2026-10.md` (octubre, 6.230 líneas) y el archivo vivo con el mes corriente; las 4 citas a entradas de octubre migradas al archivo | no | 11 | hecho |
| 13 | exp/103: el loop fractal contra el loop solo, con el presupuesto igualado. Su diferencia de calidad sin adopción la midió el exp/104 (X129): **no se replica** (F0 − A = −0,062, p ≈ 0,67). **Corrido el 2026-11-02 (X127): NO PASA** por adopción (0/72 llamadas a `dividir`; las otras tres condiciones ✅); `recursivo` queda como primitiva sin uso y la rama se borró (consecuencia pre-registrada del spec); el registro queda en el spec y la bitácora | **sí** | 1 (con el desvío declarado: el saldo único llega con 9). A+ corregido en X120: el mismo techo que F | `banco/specs/exp103_fractal.md` |
| 14 | ✅ **X144 hecho (2026-11-04):** principios unificados (solo docs) | no | — | hecho |
| 15 | **El orden de lo que sigue (X152–X158), los opcionales y la deuda abierta** viven en `docs/roadmap.md` (sección "Roadmap vigente"); el post-X144 cerrado quedó en su historial. Acá no se repiten (N4) | — | 14 | `docs/roadmap.md` |

### X114 en detalle (lo que la sesión nueva escribe primero)

**Reproducido sobre X113** con `utils.policy.clasificar`: dan `auto`
`pytest --pastebin=all` (también por `python3 -m pytest`), `--junitxml` y
`--junit-xml` (las dos: no es un alias que se escapó, falta la familia),
`--report-log`, `--debug[=ruta]` y `--cache-clear`. Hoy los vetados de pytest
son solo `-p`, `--basetemp`, `--rootdir`, `-c`, `--confcutdir`, `-o` y
`--override-ini` (`utils/politica_comandos.json`).

**Por qué no alcanza sumar los 5 flags** (N1): es la tercera vez que una
lista negra de flags se queda corta (E1 `sort --compress-program`, E2
`pytest -o`, ahora esta). pytest y sus plugins agregan opciones; una lista
negra pierde contra eso por construcción.

**Lo que se recomienda** (decisión del operador al aplicarlo):
- **Opciones de pytest en lista blanca para `auto`** (falla cerrada, S0):
  `-q`, `-v`, `-x`, `-k`, `-m`, `-s`, `--lf`, `--ff`, `--co`/`--collect-only`,
  `--tb`, `-r…`, `--maxfail`, `--durations`, `-W`, `--no-header`, rutas y
  `nodeid`. Cualquier otra opción pregunta. Va en
  `utils/politica_comandos.json` como datos, sin vocabulario.
- **La configuración de pytest editada sube la fricción** (X115): después de
  una escritura o edición aprobada sobre `tests/conftest.py` (o cualquier conftest), `pytest.ini`,
  `setup.cfg`, `tox.ini` o `pyproject.toml`, el siguiente `pytest` de la
  sesión pregunta. Determinista; los nombres son archivos de configuración,
  no lenguaje del usuario.
- Las alternativas descartadas: sumar los 5 (parche) y `pytest` siempre
  pregunta (fricción alta: el agente corre pytest todo el tiempo).

**Gate**: `tests/test_policy_bypass.py` y `tests/test_policy.py` intactos
más un caso por cada flag de arriba (R7); la foto real
(`banco/fixtures/policy_comandos.jsonl`, solo la tiene el operador) se vuelve
a clasificar y **cada `pytest` que pase de `auto` a `preguntar` se lista y se
explica**. Si alguno es de uso común, entra a la lista blanca con su motivo.
Los casos por entrada de la 5a se regeneran: cambian a propósito y se
declara. Cambia conducta solo en fricción, nunca la relaja: no hace falta un
A/B del chat, pero sí la foto.

**No es criterio, es dato**: la auditoría dijo que `--junitxml` estaba
bloqueado y que los `except` amplios eran 36; los dos están mal (no estaba
bloqueado; el ratchet cuenta 27 en el harness, 36 incluye tests).

**Decisión del operador, 2026-11-02: S9b A′ aprobado.** El chat pasa a ser una
instancia de `kernel.loop` y se autoriza reescribir los 22 tests que nombran
`AgentStep`, `ExecuteTools` y `Cierre` (la excepción de R2 que pedía la fila
X126). La cola queda: **S6 ✅ → S9b A′ ✅ → S9a ✅ → fase 6**, y archivar la
bitácora al final; 5c-a y S3 quedan como estaban.

## 8. Cómo trabajamos

- **Roles.** El autor escribe sobre **el zip del HEAD del operador**, nunca
  sobre su propio árbol, y entrega patch + zip con sha256. El operador
  aplica, reconcilia, corre los A/B, da la clave y manda el zip nuevo.
- **Patch.** `diff -ruN a/ b/` desde la raíz del repo, se aplica con
  `patch -p1`. Antes de entregar: el patch reproduce el árbol, más la suite,
  `ruff`, C901 de las fronteras y el ratchet.
- **Cada X lleva:** pre-registro en `banco/specs/` si cambia conducta;
  entrada en `docs/bitacora.md`; fila en `docs/estado.md` con sus tests;
  `docs/elegancia.md` y este handoff al día.
- **Lo que cambia conducta va en una rama hasta su A/B**, cada brazo en su
  worktree con su `.runs` desde el principio.

## 9. Errores del autor a vigilar

- Dar una estimación como si fuera medición (805 contra 807; 83 contra 81).
- Concluir por un puntaje sin leer los `checks` (s9: "deploy" cuando era tarea sin terminar).
- Cambiar algo y no lo que depende de eso (`--brazos`, `TOOLS_CONOCIDAS`).
- Escribir un criterio que puede fallar con el mecanismo andando (criterio 4 de la 5b).
- Atribuirle al operador decisiones que no tomó ("decidiste `main`").
- Prometer un entregable y postergarlo (el pre-registro de S6).
- Escribir sobre el árbol propio en vez del HEAD del operador.
- Afirmar qué mide un ratchet sin correrlo (la 5a "bajaba el vocabulario").
- Tomar los números de una auditoría sin reproducirlos: en X113 dos estaban mal.

## 10. Trampas del entorno

- El ratchet necesita `ruff==0.17.1` en el PATH.
- Sin git, Laya o `trazas.db`, hay tests que se saltean: los conteos difieren
  entre la máquina del operador y la del autor.
- `.runs/` y `salidas/` no viajan en el zip: el replay, la foto real de la 5a y
  la evidencia de los A/B (`salidas/ab111/`) solo los ve el operador.
- A `tests/inventario_tests.txt` solo se le sacan los tests borrados.
- El patch de X107 tiene un prefijo de más (se aplica con `-p2`).

## 11. Instrumentos del laboratorio y sus límites

| Instrumento | Qué mide | Límite conocido |
|---|---|---|
| `banco/banco.py` | El chat real por PTY: turnos, marcadores, HITL por scope | Solo lo que imprime la terminal |
| `banco/probes/bench_fable.py` | Trampas y auditorías con scoring determinista | s9 da 0 por deploy **o** por tarea sin terminar: leer los `checks` |
| `banco/probes/ab_skills.py` | Revisión con issues plantados | Keywords, no calidad absoluta |
| `banco/probes/tokens_runs.py` | Tokens y USD desde `.runs` | La traza no guarda argumentos ni contenido |
| `banco/probes/comandos_reales.py` | Los comandos reales de `run_command` | Descarta largos y posibles secretos |
| `replay.py` | Que las caminatas viejas sigan siendo ejecutables | Estructural, no semántico |
| `evals.py` | Linter de trazas y costos | Hay que mantener `TOOLS_CONOCIDAS` |
| `ratchet.py` | Métricas por AST | Lo que no es `.py` no lo ve, salvo los YAML de skills |

## 12. Glosario

- **X*n***: hito del refactor (un patch, un commit). **exp/*n***: experimento con medición.
- **S1–S10**: síntomas de la auditoría X91. S1 `reasoning_content`; S2 Laya
  elige el modo; S3 esquema de tools fijo; S4 hooks; S5 el producto lee el
  banco; S6 presupuesto por novedad; S7 skills por descripción; S8
  directivas; S9 el chat como loop del kernel; S10 la política como datos.
- **F1–F7 / C1–C7**: propiedades de elegancia funcional y de código (`docs/elegancia.md`).
- **S0 / P1–P4 / EL1–EL9 / N1–N4**: seguridad, diseño, elegancia y prohibiciones (`docs/principios.md`). D / E / M eran las capas de X113, reemplazadas en X118.
- **Brazo, base, criterio**: cada árbol de un A/B, el de referencia y la
  condición pre-registrada. **Desvío declarado**: un cambio al plan escrito
  antes de correr.
- **Ratchet, baseline, clave**: la métrica, su valor versionado en
  `ratchets/baseline.json` y el permiso del operador para empeorarla.
- **Banco, fable, probes**: escenarios del chat real, trampas y auditorías,
  sondas del laboratorio.
- **Orgánico / scope**: una decisión HITL de un humano o de un archivo de scope.
- **Techo**: un fixture donde la base ya saca el máximo y no hay margen para medir.
