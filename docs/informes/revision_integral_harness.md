# Revisión integral de deepseek-flow

## Dictamen ejecutivo

El proyecto tiene una arquitectura modular aprovechable y una cultura de experimentación poco habitual: límites locales, hooks, evaluaciones, trazas y documentación de correcciones. Sin embargo, el snapshot revisado no debe tratarse como un entorno seguro para ejecución autónoma sobre el host. La prioridad es endurecer la ejecución y las escrituras, después corregir las métricas y la memoria, y solo entonces ampliar capacidades. No se modificó el ZIP.

Esta revisión distingue reproducción aislada (R) de evidencia estática (E). R no significa prueba contra API/modelos reales: las acciones peligrosas, las escrituras externas y los transportes se simularon. Las afirmaciones históricas de docs no cuentan como pruebas nuevas.

## Alcance y método

- Inventario: 194 archivos, 74 Python, 17,219 líneas Python, 270 funciones de prueba en 7 módulos de tests y 28 herramientas descubiertas.
- Todos los Python se parsearon mediante AST, sin errores de sintaxis en el intérprete de esta revisión. Se realizó inventario y análisis AST de todos los Python, revisión funcional selectiva del núcleo, módulos y utilidades, e inspección de entradas CLI, soporte experimental, documentación y datasets. Esto no equivale a ejecución integral ni a demostrar corrección de todas las líneas o ramas.
- SHA-256 del ZIP: `425991fd6d77bd1802b57d4c05c87cae0461b157497ae8568ceda0ae1bb7079a`.
- Comprobaciones aisladas ampliadas: 26; además se conserva la evidencia de la primera revisión.
- Pytest parcial sobre código original de test_laya_routing: 17 casos pasados y 0 fallidos; exitcode=0. Se excluyeron las funciones que requieren fixtures de archivos. La suite completa de 270 funciones no se ejecutó.
- Ruff 0.17.0: la primera pasada por stdin señaló 23 I001; no se consideran fallos confirmados porque Ruff no podía reconocer el árbol de imports propio dentro del ZIP. Una segunda pasada con esos módulos declarados first-party obtuvo 0 incidencias y 0 errores de ejecución. Ambas procesaron los 74 Python con las reglas del proyecto; ninguna sustituye ejecutar calidad.sh en un checkout y entorno reproducible.
- Sin llamadas reales a DeepSeek, servidores MCP/A2A, buscadores ni descarga/inferencia de checkpoints. No se ejecutaron comandos peligrosos, el chat interactivo completo o la instalación completa del proyecto.

## Arquitectura observada

`GetQuestion → LayaRouter → AgentStep/DirectAnswer → ExecuteTools → AgentStep`, con herramientas CORE y módulos descubiertos al importar. Los módulos conectan flujos de juez, research, supervisor, informes y RAG. El dispatcher compartido es una buena base, pero hoy no gobierna todas las entradas y efectos. Los presupuestos se aplican por pieza, no de forma transaccional a la sesión.

## Fortalezas que conviene conservar

- Separación entre esquemas TOOLS e implementaciones IMPL y herramientas deterministas para leer/contar.
- `_resolve`, rechazo de symlinks en varios recorridos y límites de presentación ya existentes.
- `edit_file` con coincidencia exacta/única, diff y aprobación, mejor que reescrituras completas indiscriminadas.
- Juez con validación del veredicto, feedback y advertencia al agotar rondas; supervisor usando actualmente el dispatcher.
- Política de routing separada, modos off/shadow/enforce, validación de probabilidades y fallback a herramientas.
- Semáforos por instancias de flujo, pruebas de grafos y documentación que registra hallazgos descartados, no solo éxitos.
- Lectura común de registros en informe/carga_trazas y transacción de SQLite que protege una carga fallida.

## Matriz de hallazgos

| ID | Prioridad | Evidencia | Hallazgo |
|---|---|---|---|
| H01 | P0 | R | La política auto permite operaciones con efectos |
| H02 | P1 | R/E | Las escrituras de informes no respetan una política única |
| H03 | P1 | R | Los controles PRE son fail-open y MCP los evita |
| H04 | P1 | R | Cancelar streaming no cancela las herramientas pendientes |
| H05 | P1 | R/E | El presupuesto no es una barrera de ejecución global |
| H06 | P1 | R/E | RAG y memoria no comparten todas las garantías de rutas |
| H07 | P1 | R | La memoria puede devolver falsos negativos y tiene un contrato roto |
| H08 | P1 | R/E | SQLite no impone un límite de recursos real |
| H09 | P1 | R/E | Effective N puede informar cifras incorrectas o truncadas |
| H10 | P1 | R/E | Las evaluaciones no miden exactamente la política de producción |
| H11 | P1/P2 | R/E | La telemetría mezcla éxito, duración y decisión |
| H12 | P1/P2 | R/E | La compacción descarta hechos sin persistirlos |
| H13 | P2 | E | El runner limita la salida después de capturarla y no controla todo el árbol |
| H14 | P2 | E | Persistencia no atómica y condiciones de carrera |
| H15 | P2 | R/E | Laya necesita contratos y medición más estrictos |
| H16 | P2 | E | El juez verifica un subconjunto de citas, no la verdad completa |
| H17 | P2 | E | Research y protocolos externos necesitan límites explícitos |
| H18 | P2 | E | El registro de módulos y la configuración tienen acoplamiento evitable |
| H19 | P2 | E | Privacidad y documentación no corresponden a todas las garantías actuales |
| H20 | P2 | E | La calidad necesita puertas de aceptación por contrato, no solo smoke |

| H21 | P1 en banco con autoaprobación | R/E | El banco no debe tratarse como una frontera segura de aprobación |

P0: detener la exposición del comportamiento inseguro. P1: corregir antes de autonomía o datos importantes. P2: robustez, exactitud, portabilidad o calidad. La severidad depende del escenario de uso: CLI personal confiable no equivale a servicio multiusuario.

### H01 — La política auto permite operaciones con efectos

**Prioridad:** P0. **Evidencia:** R. **Código:** utils/policy.py:51–71,115–180; modules/coding.py:162–207.

Saltos de línea y & no son separadores del clasificador. La allowlist admite find con acciones, sort -o, git diff --output y pytest, que ejecuta código. El dispatcher llegó a subprocess sin pedir aprobación en la reproducción; subprocess estaba simulado.

**Corrección recomendada:** Cambiar el default a HITL_AUTO=0. Para auto, usar herramientas tipadas y argv sin shell, con argumentos permitidos; ejecutar código/tests solo en un entorno aislado. No ampliar regex como única defensa.

**Aceptación:** Ningún comando con efecto sale como auto; cada escritura requiere autorización o una capacidad de salida estrictamente delimitada.

### H02 — Las escrituras de informes no respetan una política única

**Prioridad:** P1. **Evidencia:** R/E. **Código:** utils/fs_tools.py:120–138; modules/evals.py:22–37; evals.py:555–577.

escribir_salida restringe raíces, pero acepta cualquier archivo dentro de ellas y lo sobrescribe sin aprobación. La tool evals pasa salida a generar sin _resolve; allí se crea el directorio y escribe directamente. La prueba de evals verificó el argumento pasado sin escribir fuera del entorno.

**Corrección recomendada:** Crear un servicio de escritura común: directorio exclusivo de artefactos, creación sin sobrescritura por defecto, aprobación para destinos de trabajo, resolución y validación antes del gasto en LLM.

**Aceptación:** Intentar destinos fuera de raíz, código fuente, .env, archivo existente y symlink; comprobar ausencia de escritura y, cuando corresponda, solicitud de aprobación.

### H03 — Los controles PRE son fail-open y MCP los evita

**Prioridad:** P1. **Evidencia:** R. **Código:** utils/fs_tools.py:391–397; mcp_server.py:60–68; modules/coding.py:60–95.

Una excepción en un hook PRE se convierte en veto=None y se ejecuta la implementación. MCP registra la función original, no run_tool_call. El supervisor sí usa el dispatcher en este ZIP; no repetir la acusación histórica ya corregida.

**Corrección recomendada:** Separar hooks de seguridad de hooks informativos: seguridad falla cerrada; telemetría puede ser best-effort. Hacer que chat, supervisor y MCP usen un ejecutor común.

**Aceptación:** Un hook que lanza debe impedir la acción en todas las entradas; comprobar paridad de políticas y de hooks post.

### H04 — Cancelar streaming no cancela las herramientas pendientes

**Prioridad:** P1. **Evidencia:** R. **Código:** utils/call_llm.py:194–228; nodes.py:302–338.

Tras Ctrl+C se reconstruyen y devuelven tool_calls acumuladas. Una tool call completa sigue presente; AgentStep.post dirige cualquier tool_call al ejecutor. La recuperación DSML también exige una compuerta de cancelación.

**Corrección recomendada:** Devolver estado explícito completed/cancelled/failed. Si no hubo cierre válido, conservar texto parcial solo para mostrar y descartar acciones, incluido DSML.

**Aceptación:** Interrumpir antes, durante y después de los argumentos de una acción; ninguna debe llegar a ExecuteTools.

### H05 — El presupuesto no es una barrera de ejecución global

**Prioridad:** P1. **Evidencia:** R/E. **Código:** nodes.py:279–287,335–365; modules/juez.py:52–57; modules/debate.py:26–28; utils/call_llm.py:86–104.

Se retiran las tools del request al agotar rondas, pero una respuesta nativa con tool_calls sigue a ejecución. ExecuteTools no limita el número de calls por ronda. Los límites locales no acotan coste total de subflujos, tokens ni duración; rondas del juez/debate requieren máximos de operador.

**Corrección recomendada:** Revalidar permiso y presupuesto justo antes de cada acción. Propagar un objeto Budget de sesión con deadline, llamadas LLM, tokens, tool calls y profundidad; topes del operador no ampliables por el modelo.

**Aceptación:** Probar presupuesto 0, tool_calls inesperadas con tools=None, lotes grandes, subflujos anidados y una respuesta que solicita miles de rondas.

### H06 — RAG y memoria no comparten todas las garantías de rutas

**Prioridad:** P1. **Evidencia:** R/E. **Código:** rag.py:170–195,227–248; modules/memoria.py:42–46,49–97.

RAG devuelve texto cacheado sin revalidar las raíces actuales; se reprodujo con un índice sintético externo. memory_search enumera archivos .md con is_file, sin sin_enlaces: puede seguir un symlink preexistente a un archivo fuera de la biblioteca. Esto último es estático, no se creó un enlace real.

**Corrección recomendada:** Validar cada documento al recuperar; incluir ámbito y versión de permisos en el índice. No seguir symlinks en memoria. Tratar los permisos del shell por separado: AGENT_ALLOWED_DIRS no es un sandbox del proceso.

**Aceptación:** Indexar en un ámbito y consultar desde otro más reducido; probar symlinks sintéticos y revocación de permisos.

### H07 — La memoria puede devolver falsos negativos y tiene un contrato roto

**Prioridad:** P1. **Evidencia:** R. **Código:** modules/memoria.py:49,100–120,169–211; utils/contexto.py:65–81,84–101.

Sin puntuación de Laya, elegir_por_laya devuelve solo las primeras N unidades. La nota 9 con la coincidencia desaparece al usar el default 8. Además, se pasan rutas, no contenido, al clasificador. El esquema permite memory_search({}), pero la implementación exige query. No-op y ausencia de pérdida de recall no son ciertos para ese fallback.

**Corrección recomendada:** Usar filtro léxico determinista antes de truncar; no reducir candidatos si el prefiltro falla; puntuar contenido/extractos si se usa semántica. Definir query="" o hacer el argumento requerido.

**Aceptación:** Coincidencia en la novena nota sin Laya; nombres irrelevantes con contenido relevante; llamada vacía conforme al esquema.

### H08 — SQLite no impone un límite de recursos real

**Prioridad:** P1. **Evidencia:** R/E. **Código:** modules/db.py:16–24,90–129.

La consulta SELECT n FROM t -- LIMIT devolvió 80 filas con MAX_FILAS=50. Un LIMIT explícito grande también queda libre. fetchall materializa todo; la conexión no usa mode=ro ni query_only ni progress handler. No se afirma un bypass de escritura SQL: no fue demostrado.

**Corrección recomendada:** Conexión URI mode=ro, query_only y authorizer cuando corresponda. Límite independiente con fetchmany(N+1), tamaño máximo de celdas, deadline/cancelación mediante progress handler.

**Aceptación:** Comentarios, LIMIT en subconsulta y límites enormes; consultas costosas deben interrumpirse sin bloquear el harness.

### H09 — Effective N puede informar cifras incorrectas o truncadas

**Prioridad:** P1. **Evidencia:** R/E. **Código:** effective_n.py:43–49,60–72,88–120,175–182,375–386; informe.py:41–53.

El resumen multicarpeta suma efectivos locales: no deduplica entre carpetas. El hash no canoniza claves anidadas: objetos iguales pueden tener huellas diferentes. Un registro [] rompe HashFile. ScanFiles hereda MAX_FILES=30 de collect_files y no contabiliza el resto. Las contradicciones se buscan por archivo, no globalmente.

**Corrección recomendada:** Unión global de huellas, JSON canónico, lector común con validación de forma, recorrido completo para métricas exactas, detección de etiquetas contradictorias entre archivos.

**Aceptación:** Mismo caso en dos carpetas => N global 1; orden de claves distinto => misma huella; >30 archivos; JSON válido con forma inválida; conflicto de etiqueta repartido entre archivos.

### H10 — Las evaluaciones no miden exactamente la política de producción

**Prioridad:** P1. **Evidencia:** R/E. **Código:** evals.py:38,63–67,103–157,160–185,555–568; nodes.py:495–535.

El benchmark usa _decision/veredicto, no la política decide con off/shadow/enforce, probabilidades, conformal y voto. TEST_ROUTER apunta a una ruta personal no incluida. Con un baseline anterior y score=None, comparar_baseline lanza TypeError. generar actualiza baseline por defecto en CLI, a diferencia de bench_juez.

**Corrección recomendada:** Compartir una función de decisión final entre producción y evaluación, distinguir benchmark del clasificador y del sistema, dataset portable versionado, estado no_disponible antes de comparar y actualización explícita de baseline.

**Aceptación:** Comparar mismas entradas y decisiones con producción; sin dataset y con baseline previo no debe fallar; no modificar baseline salvo opt-in.

### H11 — La telemetría mezcla éxito, duración y decisión

**Prioridad:** P1/P2. **Evidencia:** R/E. **Código:** nodes.py:363–364,506–535; utils/tracing.py:17–35,55–98; evals.py:415–426; visor.py:47–54.

RECHAZADO y exit 1 se registran como ok. El log del router puede decir aplicada=directo cuando el voto termina en herramientas. costo_traza suma los tiempos del contenedor y de sus tools, duplicando duración, y puede incorporar tiempo de espera del usuario. No mide dinero ni tokens.

**Corrección recomendada:** ToolResult tipado con estados ok/error/rejected/cancelled/timeout; registrar ruta final y cada etapa; spans con run_id/span_id/parent_id, reloj monotónico, tiempo exclusivo y de pared; usage de API para costes.

**Aceptación:** Rechazo no equivale a éxito; tool de 10 s dentro de ExecuteTools de 10 s no implica 20 s de pared; voto final debe coincidir con aplicada.

### H12 — La compacción descarta hechos sin persistirlos

**Prioridad:** P1/P2. **Evidencia:** R/E. **Código:** utils/compaccion.py:146–201; main.py:51–98.

El supuesto resumen es un marcador fijo, no un resumen de hechos. El contenido frío desaparece; se afirma que los hechos durables están en memoria, pero no se guardan automáticamente antes de compactar. El resumen al salir trabaja sobre el historial ya reducido. Se respeta la unidad assistant+tools, lo cual es positivo; no hay techo duro si la ventana caliente es enorme.

**Corrección recomendada:** Llamarlo truncación si esa es la decisión. Antes de eliminar contexto, persistir un journal factual de objetivos, restricciones, cambios y evidencias; preservar el pedido activo y el plan; límites por mensaje y presupuesto en tokens.

**Aceptación:** Una restricción y una decisión de un turno antiguo deben poder recuperarse tras varias compactaciones; ventana caliente grande y tool calls huérfanas.

### H13 — El runner limita la salida después de capturarla y no controla todo el árbol

**Prioridad:** P2. **Evidencia:** E. **Código:** modules/coding.py:198–214; modules/vision.py:147–201; utils/fs_tools.py:187–211.

capture_output acumula stdout/stderr completos antes de truncarlos. Con shell=True, un timeout del proceso directo no es una garantía sobre todos sus descendientes. read_file carga el archivo entero antes de paginar. ver_pdf rasteriza todas las páginas antes de revisar el máximo de 8 y no aplica al lote PDF el límite agregado de body.

**Corrección recomendada:** Lectura incremental con techo de bytes; proceso/grupo aislado con terminación de descendientes; controles de CPU/RAM/disco. Contar o limitar páginas antes de rasterizar y limitar dimensiones/tamaño del request.

**Aceptación:** Salida masiva, descendientes persistentes, archivo de texto enorme, PDF de muchas páginas o dimensiones grandes; hacerlo en sandbox, no sobre el host real.

### H14 — Persistencia no atómica y condiciones de carrera

**Prioridad:** P2. **Evidencia:** E. **Código:** modules/coding.py:293–343; modules/escritura.py:59–97; rag.py:106–125,170–195; heartbeat.py:39–47,89–116.

write/edit usan read-modify-write sin comprobar cambios tras la aprobación ni escritura atómica. El índice se guarda en dos archivos y la caché solo se invalida en el proceso indexador. memory_save puede sobrescribir título/fecha iguales. Heartbeat carece de lock entre ejecuciones y --ahora evita MAX_TAREAS_POR_CORRIDA.

**Corrección recomendada:** Comprobar hash antes de aplicar; temporales y replace atómico; versionar índice con modelo/dimensiones/fuentes, invalidar por versión; nombres únicos. Lock de heartbeat y mismo máximo en todas sus opciones.

**Aceptación:** Edición concurrente, interrupción entre archivos del índice, reindexado desde otro proceso, dos heartbeats simultáneos y --ahora con >10 tareas.

### H15 — Laya necesita contratos y medición más estrictos

**Prioridad:** P2. **Evidencia:** R/E. **Código:** nodes.py:478–479,527–531; utils/conformal.py:71–103; utils/laya.py:34,46–86; utils/laya_routing.py:57–82.

El router solo recibe el último mensaje truncado a 1000 caracteres: continuaciones como "continúa" carecen de referencia. La calibración admite conf=1.5 y correcto="false" => True. Ausencia de datos suficientes vuelve a umbral fijo: no conserva por sí misma una garantía conformal. La caché de errores es permanente y hay settings int/float sin validación uniforme.

**Corrección recomendada:** Validar tipos/rangos, identificador inmutable de checkpoint/dataset y resultado de carga. Incluir contexto mínimo de continuación. Separar fallo de carga de fallo transitorio de inferencia, con recarga explícita. Mantener shadow hasta medir datos representativos.

**Aceptación:** Tráfico real con elipsis y contexto, entradas corruptas, NaN/inf, fallo de inferencia, recuperación de checkpoint; medir falso-directo, cobertura, latencia y coste total.

### H16 — El juez verifica un subconjunto de citas, no la verdad completa

**Prioridad:** P2. **Evidencia:** E. **Código:** juez.py:25–28,146–214,252–269; bench_juez.py:49–57,78–104.

Solo se examinan cinco citas, con rutas reconocidas por regex y ventanas de dos líneas. Cita ausente o discrepancia semántica depende del LLM; solo cita rota fuerza retry determinista. El grading por presencia de palabras puede aceptar respuestas que mencionen tokens sin afirmar lo correcto. Los checkpoints reales y el comportamiento de API no se verificaron aquí.

**Corrección recomendada:** Resultado estructurado por afirmación y cita, cobertura explícita de citas no verificadas y advertencia cuando se agota presupuesto; grading negativo y relacional además de tokens.

**Aceptación:** Más de cinco citas, línea 0, rutas con espacios, afirmación falsa que contiene palabras esperadas, respuesta sin citas donde son obligatorias.

### H17 — Research y protocolos externos necesitan límites explícitos

**Prioridad:** P2. **Evidencia:** E. **Código:** research.py:70–155; utils/mcp_client.py:38–97; modules/a2a.py:95–138; debate.py:35–50,70–85.

Research resume extractos de buscador, no descarga ni contrasta documentos completos; una respuesta ERROR textual puede alimentar el siguiente LLM. MCP y A2A permiten delegar a capacidades externas configuradas sin política por efecto local. Debate llama un cliente síncrono dentro de exec_async; asyncio no lo vuelve no bloqueante.

**Corrección recomendada:** Describir research como síntesis preliminar de extractos y conservar evidencia/URLs. Política de confianza y egress por servidor/herramienta; errores y tamaños acotados. Cliente async real o to_thread cuando se requiera cancelación/concurrencia; validar los protocolos con servidores reales.

**Aceptación:** Búsqueda fallida sin síntesis ficticia, tool externa con efecto, respuesta enorme, timeout remoto, cancelación de debate y compatibilidad MCP/A2A.

### H18 — El registro de módulos y la configuración tienen acoplamiento evitable

**Prioridad:** P2. **Evidencia:** E. **Código:** modules/__init__.py:14–20; nodes.py:185–186; utils/call_llm.py:19–51; requirements.txt; pyproject.toml.

discover importa todos los módulos y pisa implementaciones duplicadas sin validación. La configuración puede heredar valores de otro proyecto en el home. Hay requests importado directamente sin dependencia directa declarada, ruff requerido por calidad.sh pero no instalado por requirements, versiones casi todas abiertas y sin metadata requires-python. El objetivo de ruff es py312, pero no hay matriz de compatibilidad ejecutada.

**Corrección recomendada:** Registro con validación de esquemas, colisiones y capacidades habilitadas; imports perezosos por capacidad. Config tipada resuelta una vez y procedencia visible sin claves. Separar extras y dependencias de desarrollo; lock reproducible y declarar la versión mínima realmente probada.

**Aceptación:** Módulo roto no debe inutilizar capacidades independientes; nombres duplicados fallan al arrancar; instalación limpia y entradas CLI en procesos separados.

### H19 — Privacidad y documentación no corresponden a todas las garantías actuales

**Prioridad:** P2. **Evidencia:** E. **Código:** nodes.py:20–44; .env.example; README.md:18–43,70,96–115; descargar_modelos.sh:23–29.

PREGUNTAS_LOG=1 guarda preguntas en claro por defecto; .gitignore no limita permisos, retención o backups. README anuncia 24 capacidades, pero el registro actual contiene 28 tools. El README habla de Files API para PDF, mientras el código usa pdftoppm e imágenes. Si .env ya existe, descargar_modelos.sh no configura los checkpoints. No se encontraron secretos con los patrones acotados del barrido previo, lo que no certifica su ausencia.

**Corrección recomendada:** Consentimiento/opt-out visible, rotación y retención, permisos de archivos, redacción de secretos y política de egress. Generar catálogo de tools desde registro. Documentar Poppler y actualizar setup de checkpoints sin pisar .env.

**Aceptación:** Verificar sesión privada sin texto persistido; instalación siguiendo Quickstart con .env preexistente; inventario documental generado.

### H20 — La calidad necesita puertas de aceptación por contrato, no solo smoke

**Prioridad:** P2. **Evidencia:** E. **Código:** tests/test_smoke.py; tests/test_laya_routing.py; calidad.sh; pyproject.toml.

Hay una base de 270 funciones de prueba y pruebas específicas útiles, pero no se ejecutó la suite completa en un entorno real. Los fallos reproducidos exigen tests adversariales sobre las garantías. Las pruebas existentes de router ejecutadas aquí son solo un subconjunto sin fixtures de archivos.

**Corrección recomendada:** CI reproducible con pytest completo, Ruff versionado, contract tests, fixtures portables y pruebas de integración opt-in. Descomponer el smoke monolítico por subsistema; separar pruebas de transporte/modelos de las deterministas.

**Aceptación:** Gate P0/P1 independiente; incluir todas las reproducciones R y declarar versiones, skips y alcance. Nunca convertir un análisis AST en un porcentaje de cobertura.

### H21 — El banco no debe tratarse como una frontera segura de aprobación

**Prioridad:** P1 en banco con autoaprobación. **Evidencia:** R/E. **Código:** banco/banco.py:52–109,210–349.

decision_hitl usa startswith para rutas y comandos: una ruta hermana con el mismo prefijo queda permitida, y un comando autorizado puede llevar un segundo comando fuera del alcance. Un prompt no parseable devuelve dentro=True incluso con listas permitidas vacías. correr convierte dentro=True en aprobación cuando la política del turno es s. Además, la limpieza une RAIZ/path y puede eliminar destinos externos si un escenario confiado incluye rutas absolutas o ..; esta última observación es estática, no se ejecutó cleanup. El banco mide finalización de turnos y marcadores, no corrección semántica de la tarea.

**Corrección recomendada:** Para escenarios confiados de desarrollo, ejecutar el banco en un workspace desechable y describir el alcance real. Si se usa como control de seguridad, fallar cerrado en parsing desconocido, resolver rutas con pertenencia por componentes y no autorizar shell compuesto por prefijo. Preferir eventos estructurados de aprobación sobre texto de terminal. Restringir scratch a un directorio de pruebas y añadir assertions de resultados esperados.

**Aceptación:** Rutas hermanas y .. rechazados; cadenas con comandos adicionales rechazadas; prompt desconocido o comando ausente nunca aprobado automáticamente; scratch externo rechazado antes de iniciar; distinguir turno terminado de tarea correcta.

## Reproducciones de esta revisión

### R01: La allowlist no garantiza solo lectura

```json
[
  {
    "comando": "ls\ntouch audit_marker",
    "clasificacion": "auto"
  },
  {
    "comando": "ls & touch audit_marker",
    "clasificacion": "auto"
  },
  {
    "comando": "find . -delete",
    "clasificacion": "auto"
  },
  {
    "comando": "find . -exec touch audit_marker \\;",
    "clasificacion": "auto"
  },
  {
    "comando": "sort README.md -o audit_marker",
    "clasificacion": "auto"
  },
  {
    "comando": "git diff --output=audit_marker",
    "clasificacion": "auto"
  },
  {
    "comando": "pytest -p arbitrary_plugin",
    "clasificacion": "auto"
  },
  {
    "comando": "cat /etc/passwd",
    "clasificacion": "auto"
  }
]
```

### R02: Despacho de shell sin aprobación con subprocess simulado

```json
{
  "ejecutor_invocado": true,
  "aprobacion_solicitada": false,
  "shell_real_ejecutado": false
}
```

### R03: Los hooks PRE fallan permitiendo la ejecución

```json
{
  "implementacion_invocada": true,
  "resultado": {
    "role": "tool",
    "tool_call_id": "a",
    "content": "efecto simulado"
  }
}
```

### R04: Ctrl+C conserva acciones pendientes del stream

```json
{
  "tool_calls_tras_ctrl_c": [
    "run_command"
  ]
}
```

### R05: El límite de rondas retira tools, pero no bloquea una tool call nativa devuelta

```json
{
  "tools_ofrecidas": null,
  "transicion_con_tool_call_nativa": "tool"
}
```

### R06: El escritor de informes acepta sobrescribir un archivo dentro de las raíces sin HITL

```json
{
  "write_text_invocado": true,
  "error": null,
  "destino_elegido_por_llamador": "modules/coding.py",
  "escritura_real": false
}
```

### R07: La salida de la tool evals no se valida con _resolve

```json
{
  "directorio_pasado_sin_resolver": "/fuera/no_permitido",
  "resultado": "Informe de evals generado: /fuera/evals.md (bench del router + linter de trazas + costo por sesión).",
  "escritura_real": false
}
```

### R08: memory_search se anuncia sin argumentos requeridos, pero exige query

```json
{
  "role": "tool",
  "tool_call_id": "a",
  "content": "ERROR: TypeError: memory_search() missing 1 required positional argument: 'query'"
}
```

### R09: Sin Laya, el prefiltro de memoria omite la nota relevante número 9

```json
{
  "coincidencia_real_en_nota_9": true,
  "resultado": "'CANARIO' no aparece en la biblioteca.\n\nBiblioteca de memoria:\n- nota_1.md\n- nota_2.md\n- nota_3.md\n- nota_4.md\n- nota_5.md\n- nota_6.md\n- nota_7.md\n- nota_8.md\n- nota_9.md\n[prefiltro Laya: 9 → 8 archivos]"
}
```

### R10: RAG devuelve contenido indexado fuera de los permisos actuales

```json
"1 fragmentos indexados (modo lexico); top 1:\n\n--- /fuera/privado.txt (score 0.288) ---\nCANARIO DE DATOS SINTÉTICOS"
```

### R11: Un LIMIT en comentario evita el límite de filas de SQLite

```json
{
  "tope_declarado": 50,
  "filas_devuelta": 80,
  "consulta": "SELECT n FROM t -- LIMIT"
}
```

### R12: Effective N multicarpeta suma cardinalidades locales en vez de unir huellas

```json
{
  "dos_carpetas_con_el_mismo_registro": "N global esperado 1",
  "resultado_funcion": "2 carpetas · 2 registros → Effective N 2 (0 duplicados)"
}
```

### R13: La huella de contenido depende del orden de claves anidadas

```json
{
  "objetos_equivalentes": true,
  "huellas_iguales": false
}
```

### R14: Effective N no tolera un JSON válido de forma incorrecta

```json
{
  "registro": "[]",
  "resultado": "AttributeError: 'list' object has no attribute 'get'"
}
```

### R15: Evals falla con baseline previo si el bench ya no está disponible

```json
{
  "resultado": "TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'"
}
```

### R16: Evals suma tiempos inclusivos duplicados

```json
{
  "total": 20.0,
  "por_nodo": {
    "read_file": 10.0,
    "ExecuteTools": 10.0
  },
  "tools": 1,
  "dominante": "read_file"
}
```

### R17: Rechazos y exit distinto de cero se registran como éxito

```json
[
  {
    "resultado": "RECHAZADO por el usuario",
    "registrado_ok": true
  },
  {
    "resultado": "exit 1\nfalló",
    "registrado_ok": true
  }
]
```

### R18: El router registra la ruta aplicada antes de que el segundo voto la cambie

```json
{
  "ruta_final": "herramientas",
  "aplicada_registrada": "directo"
}
```

### R19: La calibración acepta conf fuera de rango y convierte "false" a True

```json
[
  {
    "conf": 1.5,
    "correcto": true
  }
]
```

### R20: El validador de historial acepta una respuesta tool huérfana

```json
[]
```

### R21: La compacción elimina información, no construye un resumen de hechos

```json
{
  "antes": 12,
  "despues": 8,
  "decision_conservada": false,
  "marcador": "[compacción] 5 mensajes anteriores (zona fría) fueron compactados para no reenviar todo el historial. El detalle de esas vueltas ya no está en este contexto; los hechos durables están en memoria/ si hicieran falta (usá memory_search para recuperarlos). Continuá desde la ventana caliente de abajo."
}
```

### R22: La exposición MCP registra la implementación cruda, sin dispatcher ni hooks

```json
{
  "registra_funcion_original": true,
  "pasa_por_run_tool_call": false,
  "transporte_real_iniciado": false
}
```

### R23: Contratos de las herramientas descubiertas

```json
{
  "numero": 28,
  "problemas": [
    {
      "tool": "memory_search",
      "parametros_obligatorios_no_declarados": [
        "query"
      ]
    }
  ]
}
```

### R24: El scope de rutas usa prefijos, no pertenencia a un directorio

```json
{
  "tipo": "escritura",
  "objetivo": "/workspace/proyecto_evil/archivo.md",
  "dentro": true,
  "motivo": "ok"
}
```

### R25: El scope de comandos acepta un segundo comando por prefijo

```json
{
  "tipo": "comando",
  "objetivo": "echo permitido; touch marcador_sintetico",
  "dentro": true,
  "motivo": "ok"
}
```

### R26: Un prompt no reconocido se considera dentro del scope

```json
{
  "tipo": "desconocido",
  "objetivo": null,
  "dentro": true,
  "motivo": "no-parseable"
}
```

## Evidencia de tests y lint

### Pytest parcial

```text
.................                                                        [100%]
17 passed in 0.01s

```

Tests con fixtures de archivos excluidos: test_registrar_decision_escribe_y_no_rompe, test_registrar_decision_no_guarda_texto_por_default, test_registrar_decision_con_pregunta_opt_in, test_el_nodo_pasa_la_pregunta_al_registro.

### Ruff

Ruff 0.17.0: la primera pasada por stdin señaló 23 I001; no se consideran fallos confirmados porque Ruff no podía reconocer el árbol de imports propio dentro del ZIP. Una segunda pasada con esos módulos declarados first-party obtuvo 0 incidencias y 0 errores de ejecución. Ambas procesaron los 74 Python con las reglas del proyecto; ninguna sustituye ejecutar calidad.sh en un checkout y entorno reproducible.

No se reporta un gate de estilo roto a partir del primer resultado.

## Qué no debe reabrirse como fallo confirmado

- El ZIP ya incorpora la transición de DirectAnswer al ciclo del chat y usa el dispatcher en el supervisor.
- La limitación de semáforos antiguos a nivel de módulo no debe extrapolarse a instancias actuales sin reproducción.
- La sonda histórica de thinking (docs/informes/sonda_thinking_flip_2026-10-08.md) degrada el fallo a no reproducido. Esta revisión no consultó la API y no afirma que el flip siga fallando.
- No se midieron precisión, ahorro de tokens, latencia de checkpoints ni compatibilidad actual del alias del modelo. Tampoco se asigna una nota porcentual arbitraria al proyecto.

## Datos de evaluación incluidos

El JSONL de calibración contiene 85 registros bien formados: 84 etiquetas herramientas y 1 directo; 77 acuerdos y 8 desacuerdos según el campo correcto. El banco del juez contiene 17 registros. Estos son conteos del archivo, no mediciones nuevas de modelos. La propia documentación reconoce que la calibración está sesgada al trabajo dirigido: hace falta tráfico representativo e independiente antes de extrapolar fiabilidad del lado directo.

## Plan de trabajo propuesto

### 1. Contención inmediata

1. Usar HITL_AUTO=0 hasta corregir H01; no presentarlo como aislamiento de proceso.
2. No ejecutar repositorios ajenos ni prompts/documentos no confiables sobre el host; usar workspace aislado, mínimos permisos y sin credenciales heredadas innecesarias.
3. Restringir las salidas a un directorio dedicado con no-clobber y no exponer run_command por MCP.
4. Desactivar logging de preguntas si se tratan datos sensibles y hacer visible el alcance de la memoria.

### 2. Unificar ejecución y datos

Introducir un ejecutor común y un ToolResult estructurado. Validar schemas, capacidad habilitada, permisos y presupuesto antes del efecto. Separar seguridad fail-closed de observabilidad best-effort. Añadir cancelación transaccional, escrituras atómicas y límites de recursos.

### 3. Corregir exactitud y recuperación

Arreglar Effective N, SQL, prefiltro de memoria, revalidación RAG, baseline no disponible y route logging. Diferenciar tiempos de pared/exclusivos y métricas de coste. Sustituir la compacción engañosa por truncación explícita o un journal factual persistido.

### 4. Medición y liberación

Ejecutar pytest completo en instalación limpia y CI, fijar dependencias, integrar regresiones de H01–H12 y luego correr pruebas opt-in de API/modelos/protocolos. Validar routing sobre un conjunto independiente de tráfico real. No añadir más herramientas antes de estabilizar estas garantías.

## Adecuación a la filosofía del proyecto

No hace falta introducir Pydantic, OpenTelemetry ni reemplazar PocketFlow para corregir los fallos demostrados. Las prioridades pueden resolverse con helpers comunes, dataclasses si aportan claridad y pruebas de aceptación. El cron puede mantener escrituras sin preguntas si se le concede una capacidad restringida a un directorio de artefactos: la alternativa no es insertar input() en todos los flujos. Un presupuesto global completo, trazas con spans y manifiestos más elaborados son opciones de endurecimiento para autonomía/concurrencia, no requisitos para cada uso local supervisado.

## Decisión de uso

- **Desarrollo local supervisado:** viable con controles provisionales y datos reemplazables.
- **Agente autónomo sobre el equipo principal:** no recomendado con este snapshot.
- **Servicio compartido o exposición remota:** requiere aislamiento real, identidad/autorización, control de egress y validación de integración adicional.

La mejora prioritaria no es cambiar PocketFlow ni aumentar el system prompt: es convertir las políticas y promesas en controles comunes que se verifiquen en el punto exacto de ejecución.
