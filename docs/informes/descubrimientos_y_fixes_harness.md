# Descubrimientos y fixes propuestos — deepseek-flow

## Documento de decisión e implementación basado en evidencia

**Versión:** 1.0 · **Fecha de referencia:** 14 de octubre de 2026 · **Estado:** propuestas, sin aplicar cambios al proyecto.

**Alcance:** el ZIP aportado por el usuario. No se consultaron repositorios remotos ni se asume que esta copia coincida con ramas posteriores.



## 1. Resumen ejecutivo

El harness tiene una base modular útil y controles existentes que conviene conservar. La prioridad no es sustituir PocketFlow ni añadir herramientas: es hacer coherentes la autorización de efectos, la continuidad del estado y la semántica de las métricas.

Los fixes inmediatos respaldados por reproducciones son: retirar el auto inseguro de shell; fallar cerrado en hooks PRE; unificar el acceso MCP al dispatcher; cancelar acciones pendientes; validar el presupuesto antes del efecto; contener las salidas; corregir el fallback de memoria, el límite SQL y los estados de evaluación/telemetría. Cada propuesta tiene su prueba de aceptación más abajo.

No se presentan todos los puntos como bugs: la suma de Effective N por carpeta, el límite de citas y heartbeat --ahora contienen decisiones deliberadas. Se distinguen de defectos reproducidos y se propone primero aclarar el contrato cuando corresponde.

**Decisión de uso recomendada:** trabajo local supervisado con datos reemplazables y controles provisionales; no autonomía confiada sobre el host principal hasta cerrar los controles de ejecución. No es una certificación de seguridad ni de producción.



## 2. Evidencia, procedencia y límites

### 2.1 Snapshot y fuentes

- Archivo fuente: `deepseek-flow-main (1).zip`. SHA-256: `425991fd6d77bd1802b57d4c05c87cae0461b157497ae8568ceda0ae1bb7079a`.
- Inventario contrastado: 194 archivos; 74 Python; 17,219 líneas Python; 270 funciones de prueba en 7 archivos; 28 tools descubiertas en la evidencia original.
- Referencias de este documento: rutas relativas y símbolos del ZIP; los rangos de línea se recalcularon contra esta copia. No se reutilizan ubicaciones de auditorías sobre ZIPs anteriores.
- R01–R23: resultados del JSON de evidencia recibido. No se reejecutaron en esta entrega y no se presentan como mediciones nuevas.
- R24–R26: reejecutados en esta entrega extrayendo por AST únicamente constantes y decision_hitl. Sin Chat, PTY, shell, red ni cleanup. Sus entradas y salidas completas quedan en la evidencia consolidada.
- El JSON recibido contiene 23 comprobaciones y 20 grupos de hallazgos, aunque respuestas posteriores mencionaban 26 y 21. Se cerró esa diferencia reejecutando los tres casos del banco y reconstruyendo H21; no se asumió que el nombre del archivo garantizara ser la última versión.
- Se conservaron intactos el ZIP y los informes/evidencias de entrada. Los archivos entregados son un documento nuevo y su evidencia consolidada, no parches aplicados.

### 2.2 Leyenda de evidencia

| Tipo | Qué sostiene | Qué no sostiene |
|---|---|---|
| R | Reproducción aislada registrada; se especifica si usa mocks o datos sintéticos. | No implica ejecución contra proveedor, checkpoint o host real. |
| S | Lectura directa del código y verificación de la rama/llamada indicada. | No demuestra frecuencia ni impacto operativo real por sí sola. |
| D | Conteo o propiedad de los datos/documentos incluidos. | No equivale a precisión medida nuevamente. |
| M | Límite metodológico de la auditoría o plan de validación. | No es una falla demostrada del proyecto. |

**Prioridades:** P0 = contención inmediata en el escenario indicado; P1 = cerrar antes de confiar en autonomía o datos importantes; P2 = robustez, contratos o medición adicional. La prioridad es juicio técnico condicionado al uso, no una puntuación CVSS calculada.

### 2.3 Pruebas y herramientas de calidad

- Evidencia previa: 17 casos originales de `test_laya_routing.py` pasados, exitcode=0; cuatro funciones dependientes de fixtures de archivos no se ejecutaron. No hubo suite completa de 270 funciones ni cobertura porcentual.
- Entorno registrado de esa revisión: Python 3.12.7 | packaged by Anaconda, Inc. | (main, Oct  4 2024, 13:27:36) [GCC 11.2.0]; PocketFlow 0.0.3; Ruff 0.17.0. No equivale al entorno del autor o de producción.
- Ruff no se reejecutó en esta entrega porque el paquete no está disponible. La primera pasada guardada contiene 23 I001 y no reconocía los imports propios del ZIP; la conversación registra una segunda pasada con first-party explícito y cero incidencias, pero ese resultado no está en el JSON recibido. No se usa la primera pasada para afirmar que el gate de estilo está roto ni se certifica el gate completo.
- Sin pruebas reales de DeepSeek, modelos Laya, fastembed, MCP/A2A, búsquedas web, chat integral o instalación completa. No se ejecutaron comandos peligrosos ni pruebas de agotamiento de recursos.

### 2.4 Matices que corrigen afirmaciones demasiado amplias

- Effective N multicarpeta suma intencionadamente; el problema es atribuir a esa suma el significado de unión global. R12 solo probó el agregador de resúmenes.
- Una tool call nativa tras agotamiento fue simulada; no prueba un comportamiento indebido de la API.
- MCP omite hooks compartidos al registrar funciones crudas; no por ello desaparecen las aprobaciones internas de run_command.
- Tiempo inclusivo acumulado no es necesariamente una métrica inútil; es incorrecto presentarlo como pared sin distinguir anidamiento.
- --ahora está documentado para ejecutar todas las tareas; fijar un máximo absoluto exige una decisión de contrato, no solo un parche.
- 24 capacidades y 28 herramientas pueden contar unidades distintas; se pide inventario claro, no se afirma un error aritmético por esa diferencia.
- La suite no ejecutada es un límite de esta auditoría, no evidencia de suite fallida.



## 3. Índice de descubrimientos y decisión recomendada

| ID | Prioridad / condición | Evidencia | Descubrimiento |
|---|---|---|---|
| H01 | P0 si HITL_AUTO=1 sobre un host con datos importantes | R01, R02 | La clasificación auto no garantiza solo lectura |
| H02 | P1 | R06, R07 | Las salidas automáticas pueden modificar archivos fuera de su propósito |
| H03 | P1 | R03, R22 | Los hooks de seguridad permiten continuar al fallar y MCP no los usa |
| H04 | P1 | R04 | Cancelar el stream conserva acciones pendientes |
| H05 | P1 | R05 | Retirar herramientas del request no impide su ejecución local |
| H06 | P1 cuando los permisos cambian o el índice se comparte | R10 | La recuperación de RAG y memoria necesita comprobar el ámbito |
| H07 | P1 para fiabilidad de recuperación | R08, R09, R23 | La memoria pierde coincidencias al fallar el prefiltro y tiene un schema inconsistente |
| H08 | P1 para límites de salida; endurecimiento de CPU separado | R11 | El tope SQL se puede omitir y se materializan todas las filas |
| H09 | P1 para métricas usadas al decidir datasets | R12, R13, R14 | Effective N mezcla agregación local con un rótulo global y tiene bordes de datos |
| H10 | P1 para evaluación y baseline | R15 | El benchmark no reproduce toda la política actual y falla al faltar métricas |
| H11 | P1 para veracidad del estado; P2 para instrumentación adicional | R16, R17, R18 | Éxito, ruta aplicada y duración se registran con semánticas ambiguas |
| H12 | P1 en tareas largas; P2 para historial defensivo | R20, R21 | La compacción elimina hechos y el validador admite tools huérfanas |
| H13 | P2; P1 si se procesan entradas hostiles sin aislamiento | S | Los límites de presentación se aplican después del trabajo pesado |
| H14 | P2; condicionado a concurrencia/interrupciones | S; varias decisiones de producto | Publicación no atómica, caché entre procesos y semántica de heartbeat |
| H15 | P1 para validación de datos; P2 para cambios de routing | R19 | Calibración permissiva y evidencia limitada para el router |
| H16 | P2; límite deliberado que debe hacerse visible | S | El juez comprueba evidencia parcial, no toda la veracidad de una respuesta |
| H17 | P2; P1 si se delegan efectos sin autorización | S | Research y delegación externa necesitan contratos de evidencia y confianza |
| H18 | P2 | S | El registro y la instalación necesitan contratos explícitos |
| H19 | P2; riesgo de privacidad según datos tratados | S + D | Privacidad, inventario y setup necesitan describir el comportamiento real |
| H20 | Trabajo de aceptación, no fallo de ejecución confirmado | M | La validación disponible no equivale a un gate integral del proyecto |
| H21 | P1 cuando se usa hitl: s fuera de un workspace desechable | R24, R25, R26 | El banco autoaprueba por prefijos y permite prompts no reconocidos |



## 4. Hallazgos, fixes mínimos y pruebas de aceptación

**Estado de todas las pruebas T-Hxx:** especificaciones propuestas, no implementadas ni ejecutadas en esta entrega. El hecho de que una prueba original falle no demuestra que una corrección propuesta funcione: cada parche necesita su validación posterior.

### H01. La clasificación auto no garantiza solo lectura

**Prioridad:** P0 si HITL_AUTO=1 sobre un host con datos importantes. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; R01, R02.

**Código contrastado:** `utils/policy.py:151–183` (clasificar); `utils/policy.py:115–131` (_segmento_es_auto); `modules/coding.py:162–214` (run_command).

**Observado:** R01 clasifica como auto cadenas con salto de línea o &, find con acciones, sort -o, git diff --output y pytest con plugin. R02 verifica que el dispatcher invoca subprocess simulado sin pedir aprobación. El clasificador separa &&, | y ;, pero no todas las formas de composición; además, los programas admitidos tienen opciones con efectos.

**Límite de la evidencia:** No se ejecutó ningún comando peligroso. R01 es clasificación y R02 observa el límite del ejecutor con mock. cat fuera de las raíces ilustra ausencia de aislamiento del shell, no una escritura. No se atribuye malicia al usuario.

**Impacto condicionado:** La etiqueta «solo lectura» reduce la intervención humana sin garantizar ausencia de escritura o ejecución de código. El impacto depende de permisos del proceso, contenido del workspace y configuración.

**Fix que aplicaría:**

- F01.1 — Contención: cambiar el default de run_command a HITL_AUTO=0 y alinear README/.env.example. Mientras el clasificador no sea seguro, el modo automático debe ser opt-in explícito y advertido, no el default.
- F01.2 — Mantener la doble confirmación de operaciones reconocidas como peligrosas incluso al desactivar auto: el código actual fuerza todo a preguntar cuando HITL_AUTO=0. Desactivar auto no debe disminuir otra confirmación ya existente.
- F01.3 — Para una política garantizada, run_command con shell arbitrario siempre requiere autorización. Reservar ejecución automática para herramientas tipadas con ejecutable y argumentos restringidos; preferir las tools de lectura existentes. argv sin shell evita composición de shell, pero no convierte pytest, find o git en operaciones inocuas por sí solo.
- F01.4 — Ejecutar tests y código de repositorios no confiables en un workspace aislado, sin credenciales heredadas innecesarias. Documentar que AGENT_ALLOWED_DIRS no restringe al proceso shell.

**Pruebas de aceptación que exigiría:**

- T-H01-a — Parametrizar todas las cadenas de R01 y comprobar que no obtienen permiso automático con efectos. No ejecutarlas: mock en la frontera de subprocess.
- T-H01-b — Con HITL_AUTO=0, toda llamada shell solicita autorización; rechazo => cero invocaciones al ejecutor.
- T-H01-c — Una operación de doble confirmación conserva ambas; una herramienta de lectura tipada conserva su funcionamiento permitido.

**Qué no haría:** No ampliaría una regex o agregaría otra lista negra como única corrección. Tampoco llamaría sandbox a la aprobación humana.



### H02. Las salidas automáticas pueden modificar archivos fuera de su propósito

**Prioridad:** P1. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; R06, R07.

**Código contrastado:** `utils/fs_tools.py:120–138` (escribir_salida); `modules/evals.py:22–37` (evals); `evals.py:555–577` (generar).

**Observado:** R06 observa write_text sobre un destino simulado con nombre de código fuente dentro de las raíces, sin HITL. R07 observa que salida se pasa a generar sin _resolve. En generar, el directorio se crea y se escribe directamente. El helper común contiene algunas escrituras, pero no diferencia artefactos de archivos de trabajo.

**Límite de la evidencia:** Las escrituras se simularon; no se sobrescribió código ni se escribió fuera del entorno. Que los flujos no pidan aprobación es una decisión deliberada para CLI/cron. La corrección propuesta protege el ámbito de esa capacidad automática, no exige interacción en cron.

**Impacto condicionado:** Una ruta seleccionada por el modelo puede reutilizar la capacidad de generar informes para tocar código, configuración o un destino externo en evals.

**Fix que aplicaría:**

- F02.1 — Extender el helper compartido con una raíz de artefactos fijada por el operador y un modo de escritura explícito. Validar que el destino resuelto pertenezca a esa raíz; no basta pertenecer al conjunto general de archivos legibles/editables.
- F02.2 — Hacer que evals use el mismo resolvedor y escritor tanto al validar anticipadamente como al publicar. Validar antes de llamadas caras y volver a comprobar antes del efecto.
- F02.3 — Para artefactos nuevos, crear sin sobrescribir o usar un identificador único. Si cron necesita actualizar un informe fijo, permitirlo mediante configuración del operador dentro de su raíz de artefactos y publicación atómica. No exponer ese privilegio como argumento libre del modelo.
- F02.4 — Una escritura sobre el workspace debe usar la ruta de edición/aprobación. No insertar input() en todos los flujos. Contemplar enlaces y cambios de destino entre validación y escritura en el modelo de amenaza.

**Pruebas de aceptación que exigiría:**

- T-H02-a — Destino fuera de raíz, ruta de código fuente, .env y enlace hacia fuera: denegados sin escribir.
- T-H02-b — Informe nuevo permitido; colisión rechazada por defecto. Actualización de cron expresamente autorizada funciona sin TTY y no puede modificar otro destino.
- T-H02-c — Evals rechaza una salida inválida antes de llamar al benchmark; fallo al publicar no deja un informe anterior truncado.

**Qué no haría:** No forzaría HITL universal ni confiaría en comprobar solo la extensión .md.



### H03. Los hooks de seguridad permiten continuar al fallar y MCP no los usa

**Prioridad:** P1. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; R03, R22.

**Código contrastado:** `utils/fs_tools.py:372–415` (run_tool_call); `mcp_server.py:46–75` (main); `modules/coding.py:60–83` (_vetar_comando_prohibido).

**Observado:** R03: un hook PRE lanza y la implementación se invoca. R22: el servidor MCP simulado recibe la función original run_command, no un adaptador del dispatcher. El catch del dispatcher convierte la excepción en veto=None.

**Límite de la evidencia:** No hubo transporte MCP real. Registrar la función cruda omite hooks, pero no elimina los controles internos de esa función: run_command conserva su propia aprobación. El supervisor actual sí usa run_tool_call.

**Impacto condicionado:** La seguridad depende de la entrada usada y de que las comprobaciones no fallen. El veto duro y los hooks post no son uniformes entre chat y MCP.

**Fix que aplicaría:**

- F03.1 — Tratar los hooks PRE de autorización como fail-closed: excepción => resultado de error de política y retorno inmediato; nunca invocar la implementación. Validar el envelope y los argumentos antes de pasarlos a hooks.
- F03.2 — Revisar los catches internos de hooks de seguridad: un error de parsing no debe presentarse como autorización. Separar ese comportamiento del best-effort permitido para hooks informativos.
- F03.3 — Registrar en MCP wrappers que llamen al ejecutor común, preservando nombre, descripción y contrato de parámetros. Devolver al transporte el contenido apropiado; no hacer que el cliente pueda decidir qué controles se omiten.
- F03.4 — Probar paridad de chat, supervisor y MCP. No exponer run_command por MCP como mitigación temporal.

**Pruebas de aceptación que exigiría:**

- T-H03-a — Hook PRE que lanza, que veta y que permite: 0, 0 y 1 efectos respectivamente.
- T-H03-b — La misma solicitud recibe el mismo veto en chat, supervisor y wrapper MCP; se ejecutan los mismos hooks post pertinentes.
- T-H03-c — Los esquemas MCP siguen siendo invocables tras envolver las funciones; integración real de transporte pendiente.

**Qué no haría:** No suprimiría los errores de política para que «el agente no se caiga»: se puede devolver un error sin ejecutar el efecto.



### H04. Cancelar el stream conserva acciones pendientes

**Prioridad:** P1. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; R04.

**Código contrastado:** `utils/call_llm.py:146–229` (call_llm_agent_stream); `nodes.py:289–333` (AgentStep.exec); `nodes.py:335–345` (AgentStep.post).

**Observado:** Un stream simulado emite una tool call completa y después KeyboardInterrupt; R04 conserva run_command en la respuesta. AgentStep.post enruta cualquier tool_calls presente a ejecución. La recuperación de acciones desde DSML es una segunda vía que debe respetar la cancelación.

**Límite de la evidencia:** Se reprodujo la conservación de la acción en el retorno, no una ejecución destructiva posterior ni una cancelación real contra la API.

**Impacto condicionado:** El usuario puede creer que abortó una acción que todavía se despachará. También puede intentarse ejecutar una acumulación parcial tras un fallo de transporte.

**Fix que aplicaría:**

- F04.1 — Hacer explícito el estado del resultado: completed, cancelled o failed. Conservar texto parcial para visualización, pero descartar el lote de acciones si la generación no terminó válidamente.
- F04.2 — Usar el cierre del proveedor y validar id, nombre y argumentos de las tool calls; JSON válido por sí solo no demuestra que la generación haya concluido.
- F04.3 — En AgentStep, bloquear tanto tool_calls nativas como recuperación DSML cuando el estado no sea completed; no registrar acciones ejecutables incompletas en el historial.
- F04.4 — Cerrar el stream en finally y preservar el comportamiento explícito de CHAT_STREAM_INTERRUPT=0. No convertir cancelación del usuario en reintento automático.

**Pruebas de aceptación que exigiría:**

- T-H04-a — Interrupción antes de argumentos, durante JSON, tras JSON completo y tras contenido DSML: cero llamadas a tools.
- T-H04-b — Fallo de red tras un fragmento no ejecuta el lote parcial; finalización normal ejecuta una sola vez.
- T-H04-c — El historial sigue siendo válido tras cancelar y permite una pregunta nueva.

**Qué no haría:** No bastaría con stream.close(); eso no borra las acciones ya reconstruidas.



### H05. Retirar herramientas del request no impide su ejecución local

**Prioridad:** P1. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; R05.

**Código contrastado:** `nodes.py:250–287` (AgentStep.prep); `nodes.py:335–345` (AgentStep.post); `nodes.py:352–366` (ExecuteTools.exec); `modules/juez.py:52–57` (answer_verified); `modules/debate.py:26–28` (debate).

**Observado:** R05 entrega una respuesta simulada con tool_calls después de que prep devolviera tools=None por agotamiento. La transición resultante es tool. ExecuteTools recorre el lote sin verificar presupuesto por efecto. Los límites locales tampoco limitan automáticamente todos los subflujos.

**Límite de la evidencia:** No se ha observado a la API devolver herramientas cuando no se ofrecieron. Se demuestra ausencia de una comprobación local ante esa entrada, no un bypass real del proveedor. No se midió gasto excesivo.

**Impacto condicionado:** Una respuesta inesperada o una ruta interna puede ejecutar pese al estado de agotamiento. Una sola ronda puede multiplicar acciones y llamadas internas.

**Fix que aplicaría:**

- F05.1 — Guardar el conjunto de tools autorizado para el paso y rechazar acciones nativas o DSML fuera de ese conjunto antes de ejecutar. DirectAnswer y presupuesto agotado deben tener reglas explícitas.
- F05.2 — Aplicar el presupuesto en el ejecutor por acción, con un contador del turno. Una acción denegada debe tener una respuesta coherente si ya se historió su tool_call; nunca dejar mensajes tool huérfanos.
- F05.3 — Mantener el límite de rondas, añadir un tope de calls por turno y validar rondas de juez/debate con mínimos/máximos fijados por operador. Definir si rechazos y fallos consumen intento y probarlo.
- F05.4 — Solo para autonomía prolongada, extender después a deadline, llamadas LLM y profundidad compartidos. No es necesario introducir esa infraestructura completa para cerrar R05.

**Pruebas de aceptación que exigiría:**

- T-H05-a — Presupuesto 0 y respuesta nativa simulada => cero efectos; DSML también bloqueado.
- T-H05-b — Lote mayor que el presupuesto => solo las acciones autorizadas, historial consistente y sin reejecutar las ya completadas.
- T-H05-c — Rondas fuera de rango se rechazan antes del LLM; los máximos no pueden ampliarse por argumentos del modelo.

**Qué no haría:** No confiaría solo en retirar schemas, añadir instrucciones al prompt o contar rondas después del lote.



### H06. La recuperación de RAG y memoria necesita comprobar el ámbito

**Prioridad:** P1 cuando los permisos cambian o el índice se comparte. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; R10.

**Código contrastado:** `rag.py:227–248` (buscar); `rag.py:170–195` (_cargar); `modules/memoria.py:42–46` (_archivos_md); `modules/memoria.py:49–97` (memory_search).

**Observado:** R10 sustituye la carga del índice por un chunk sintético con ruta externa y el buscador devuelve su contenido. buscar no revalida las raíces actuales. Por lectura, _archivos_md usa is_file sin excluir symlinks y memory_search lee esos candidatos.

**Límite de la evidencia:** No se extrajeron datos privados. La prueba usa contenido sintético; no demuestra un ataque remoto ni mide un symlink real. La memoria tiene una raíz configurable propia, que puede ser deliberadamente distinta de AGENT_ALLOWED_DIRS.

**Impacto condicionado:** Datos indexados en un ámbito amplio pueden reaparecer después de reducir permisos. Un enlace presente en la biblioteca puede ampliar la lectura fuera de ella.

**Fix que aplicaría:**

- F06.1 — Al recuperar, comprobar cada ruta de origen contra las raíces autorizadas actuales y el ámbito del índice. Excluir chunks de fuentes no autorizadas y comunicar omisiones; validar primero los candidatos, luego formar el top-k.
- F06.2 — Tratar un cambio de permisos o de índice como motivo de invalidación de caché. El archivo de índice no es una autorización permanente.
- F06.3 — En memoria, excluir enlaces y resolver candidatos contra MEMORIA_DIR canónico, preservando que esa raíz es una capacidad explícita del operador. No ampliar el acceso automáticamente por coincidir un nombre.
- F06.4 — Si hay escritores locales adversariales concurrentes, la validación de rutas sola no elimina carreras: requerir workspace aislado o acceso por descriptores con garantías del sistema.

**Pruebas de aceptación que exigiría:**

- T-H06-a — Índice creado bajo raíz A; sesión permitida solo en B: ningún chunk de A aparece.
- T-H06-b — Fuente borrada, movida o revocada: comportamiento definido y sin devolver silenciosamente contenido no autorizado.
- T-H06-c — Nota normal se lee; enlace a fuera y enlace cambiado se rechazan en un entorno de prueba aislado.

**Qué no haría:** No usaría una ruta almacenada en chunks.json como prueba suficiente de permiso.



### H07. La memoria pierde coincidencias al fallar el prefiltro y tiene un schema inconsistente

**Prioridad:** P1 para fiabilidad de recuperación. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; R08, R09, R23.

**Código contrastado:** `utils/contexto.py:65–81` (elegir_por_laya); `modules/memoria.py:100–120` (_prefiltrar); `modules/memoria.py:49–97` (memory_search).

**Observado:** R09 configura nueve notas sintéticas, coincidencia solo en la novena y puntuación de Laya ausente. Se obtiene «no aparece» y «prefiltro Laya: 9 → 8». R08/R23: query no es required en el esquema, pero la función no tiene valor por defecto. El prefiltro recibe objetos Path, cuyo texto usado para puntuar es la ruta.

**Límite de la evidencia:** R09 fuerza _puntuar=None, que es el camino documentado de ausencia/fallo; no hubo inferencia de checkpoint. No se midió la calidad del ranking cuando sí funciona.

**Impacto condicionado:** Una búsqueda puede producir una negación falsa y atribuir a Laya una selección inexistente. Una invocación válida según schema produce TypeError.

**Fix que aplicaría:**

- F07.1 — En elegir_por_laya, cuando puntajes is None, devolver unidades completas, no unidades[:max_unidades]. Comunicar explícitamente si hubo ranking o fallback cuando haga falta distinguirlos.
- F07.2 — Definir memory_search(query="") para preservar la consulta de catálogo ya anunciada. Añadir comprobación automática de parámetros obligatorios entre TOOLS e IMPL.
- F07.3 — Para la búsqueda textual, determinar coincidencias reales antes de cualquier ranking que reduzca candidatos. Paginar o truncar la presentación con aviso, no declarar ausencia por no haber buscado una parte.
- F07.4 — Si se conserva ranking semántico de notas, puntuar extractos acotados de contenido, no solo nombres. Medirlo aparte; no convertirlo en requisito del parche de fallback.

**Pruebas de aceptación que exigiría:**

- T-H07-a — Repetir R09: se devuelve la coincidencia de la nota 9 y no se afirma que Laya filtró.
- T-H07-b — memory_search({}) devuelve catálogo; query textual conserva búsqueda exacta.
- T-H07-c — Prefiltro desactivado, fallo por excepción y retorno None conservan candidatos; ranking válido conserva orden y límites de presentación declarados.

**Qué no haría:** No reduciría el alcance silenciosamente para aparentar eficiencia ni interpretaría «no buscado» como «no existe».



### H08. El tope SQL se puede omitir y se materializan todas las filas

**Prioridad:** P1 para límites de salida; endurecimiento de CPU separado. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; R11.

**Código contrastado:** `modules/db.py:16–24` (_con); `modules/db.py:93–129` (sql).

**Observado:** R11 usa SQLite en memoria con 80 filas. SELECT n FROM t -- LIMIT devuelve 80 con MAX_FILAS=50. La detección de LIMIT es textual y fetchall materializa el resultado entero. _con abre la base sin mode=ro.

**Límite de la evidencia:** No se demostró modificación de la base, carga de extensiones ni agotamiento de CPU. fetchmany acota filas recuperadas, no el coste de ejecutar la consulta ni el tamaño de una celda.

**Impacto condicionado:** Una consulta válida puede inflar el contexto y la memoria por encima de lo anunciado. La garantía de solo lectura depende hoy del filtro de entrada, sin refuerzo en la conexión.

**Fix que aplicaría:**

- F08.1 — Usar fetchmany(MAX_FILAS+1), presentar como máximo MAX_FILAS y marcar truncación. No depender de encontrar o insertar la palabra LIMIT para imponer el límite de salida.
- F08.2 — Abrir la ruta configurada mediante URI correctamente escapada con mode=ro y uri=True; activar query_only como defensa adicional. Preservar el cierre en finally.
- F08.3 — Limitar bytes/caracteres de la salida y de las celdas. Mantener validaciones de una sentencia/SELECT, pero no describirlas como control de coste.
- F08.4 — Si se exige deadline de SQL, incorporar progress handler e interrupción, respaldados por una prueba de consulta costosa en una base sintética. Es endurecimiento adicional, no evidencia de un ataque ya ocurrido.

**Pruebas de aceptación que exigiría:**

- T-H08-a — Comentario con LIMIT, LIMIT -1, límite enorme y LIMIT solo en subconsulta: como máximo 50 filas mostradas, con aviso si sobran.
- T-H08-b — Una celda grande no supera el presupuesto de salida.
- T-H08-c — La conexión rechaza escrituras por su configuración y una consulta interrumpida cierra recursos.

**Qué no haría:** No cambiaría solo la regex ni prometería que fetchmany limita CPU o RAM interna de SQLite.



### H09. Effective N mezcla agregación local con un rótulo global y tiene bordes de datos

**Prioridad:** P1 para métricas usadas al decidir datasets. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; decisión explícita en multicarpeta; R12, R13, R14.

**Código contrastado:** `effective_n.py:43–49` (huella); `effective_n.py:67–68` (ScanFiles.exec); `effective_n.py:88–122` (HashFile.exec); `effective_n.py:143–241` (WriteReport.exec); `effective_n.py:375–386` (resumen_conjunto); `informe.py:41–53` (collect_files).

**Observado:** R12 pasa dos resúmenes con total=1 y efectivo=1; obtiene Effective N 2. El docstring declara explícitamente deduplicación POR CARPETA: la suma es deliberada, no un cálculo de unión global. R13 da hashes distintos a objetos iguales con diferente orden de claves anidadas. R14: un JSON [] produce AttributeError. Por lectura, ScanFiles hereda el tope de 30 de collect_files; los conflictos de etiquetas se examinan dentro de cada archivo.

**Límite de la evidencia:** R12 no ejecutó dos carpetas reales con el mismo registro; demuestra suma de cardinalidades y la lectura del código confirma la semántica. Una carpeta sí une las huellas de los archivos analizados. No se ha medido el efecto de estos bordes sobre un entrenamiento real.

**Impacto condicionado:** El rótulo «Effective N conjunto» puede interpretarse como número de ejemplos únicos globales cuando es una suma de únicos locales. Orden JSON y muestreo pueden distorsionar el conteo que sí se pretende exacto.

**Fix que aplicaría:**

- F09.1 — Fix inmediato sin cambiar la operación deliberada: renombrar el agregado a «suma de únicos por carpeta; no deduplicado entre carpetas» y distinguir sus duplicados locales de duplicados globales.
- F09.2 — Si el producto necesita N global, transportar conjuntos de huellas al agregador y calcular la unión explícita. Publicar ambas métricas; no sumar cardinalidades para inferir una unión.
- F09.3 — Canonizar la serialización de los campos elegidos con sort_keys=True de forma recursiva, preservando orden de listas y distinción de tipos que el contrato considere relevante. Versionar la definición de huella e invalidar comparaciones antiguas si cambia.
- F09.4 — Reutilizar validación de JSON/forma en HashFile. Recorrer todos los archivos para conteos exactos con max_files=None; si se ofrece muestreo, declarar ámbito y cantidad omitida.
- F09.5 — Si se anuncia contradicción global de etiquetas, unir el mapa contenido-sin-etiqueta → etiquetas entre archivos/carpetas, sin confundirlo con la huella que incluye la etiqueta.

**Pruebas de aceptación que exigiría:**

- T-H09-a — Dos carpetas con un registro idéntico: suma local=2 y unión global=1, con rótulos separados. Con una carpeta se preserva la unión actual.
- T-H09-b — Reordenar claves anidadas mantiene la huella; cambiar valor, tipo u orden de lista significativo la cambia.
- T-H09-c — 31 archivos se contabilizan completos; [], null y answers inválido se registran como forma incorrecta sin abortar.
- T-H09-d — El mismo contenido con etiquetas distintas en dos archivos produce un conflicto si esa es la métrica publicada.

**Qué no haría:** No llamaría bug aritmético a una suma deliberada ni cambiaría su significado silenciosamente. Tampoco confundiría deduplicación exacta con tamaño muestral efectivo estadístico.



### H10. El benchmark no reproduce toda la política actual y falla al faltar métricas

**Prioridad:** P1 para evaluación y baseline. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; R15.

**Código contrastado:** `evals.py:63–67` (_decision); `evals.py:103–157` (correr_bench); `evals.py:160–185` (comparar_baseline); `evals.py:555–577` (generar); `nodes.py:495–535` (LayaRouter.post).

**Observado:** R15 resta score=None a un baseline numérico y obtiene TypeError. _decision usa elección + veredicto(conf), mientras producción usa probabilidades, config de modos, decisión conformal y voto. El código del benchmark se describe como compuerta exacta. El dataset por defecto depende de una ruta personal; generar permite actualización del baseline por defecto.

**Límite de la evidencia:** No se ejecutaron modelos ni se midió discrepancia de precisión. El benchmark del clasificador sigue siendo útil, pero no demuestra calidad de toda la cascada. La tool del chat ya pasa actualizar_baseline=False; no atribuirle sobrescritura del baseline.

**Impacto condicionado:** Una ejecución degradada puede romper el informe y una comparación puede mezclar definiciones o datasets diferentes. Se puede atribuir al sistema una métrica que solo evalúa una parte.

**Fix que aplicaría:**

- F10.1 — Si las métricas nuevas no existen o no son finitas, devolver NO_EVALUABLE con causa; no restar, no etiquetar OK y no actualizar baseline.
- F10.2 — Separar métricas de clasificador, compuerta y ruta final. Reutilizar decide/ruta_aplicada y extraer el arbitraje final como lógica testeable con voto inyectable; no duplicar una aproximación bajo el nombre «producción».
- F10.3 — Permitir dataset explícito y proporcionar un fixture portable. Guardar identidad del dataset, política, checkpoint y schema de métricas antes de comparar.
- F10.4 — Cambiar actualización del baseline a opt-in también en CLI; exigir estado evaluable y referencia compatible. Migrar baselines viejos sin sobrescribirlos por defecto.

**Pruebas de aceptación que exigiría:**

- T-H10-a — Baseline existente + nuevo score=None => NO_EVALUABLE, sin excepción ni modificación de disco.
- T-H10-b — Misma entrada y configuración => mismas decisiones en benchmark de política y producción, incluidos shadow, off, conformal y voto contrario.
- T-H10-c — Dataset ausente o diferente produce estado explícito; ninguna ejecución normal cambia baseline sin flag.

**Qué no haría:** No reemplazaría None por cero ni publicaría métricas de una política simplificada como si fueran del sistema completo.



### H11. Éxito, ruta aplicada y duración se registran con semánticas ambiguas

**Prioridad:** P1 para veracidad del estado; P2 para instrumentación adicional. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; R16, R17, R18.

**Código contrastado:** `nodes.py:352–366` (ExecuteTools.exec); `nodes.py:495–535` (LayaRouter.post); `utils/tracing.py:24–35` (evento_tool); `utils/tracing.py:38–98` (activar); `evals.py:415–426` (costo_traza).

**Observado:** R17: RECHAZADO y exit 1 producen ok=True. R18: aplicada=directo se registra antes de que un voto lleve a herramientas. R16 suma dos eventos sintéticos de 10 segundos y da total=20; si uno contiene al otro, esa suma no es tiempo de pared. costo_traza devuelve segundos, no tokens o dinero.

**Límite de la evidencia:** R16 no fue una corrida cronometrada: demuestra la operación de suma, y el tracing de nodo y tool permite tiempos anidados. Sumar tiempo inclusivo por componente puede ser útil si se etiqueta como tal. No se midió coste monetario real.

**Impacto condicionado:** Las tasas de éxito, rutas ejecutadas y duración pueden no corresponder al comportamiento que se quiere evaluar. No se puede reconstruir con certeza todo el tiempo exclusivo a partir de logs sin relaciones de anidamiento.

**Fix que aplicaría:**

- F11.1 — Introducir un resultado interno pequeño con status: ok/error/rejected/cancelled/timeout, content y exit_code cuando corresponda. Conservarlo hasta tracing; no convertir inmediatamente todo a str. Migrar primero run_command, escritura y edición.
- F11.2 — Mantener el formato válido del mensaje role=tool al hablar con el proveedor: status es metadato interno, no una clave arbitraria enviada al API. Evitar clasificar éxito exclusivamente por prefijos del texto.
- F11.3 — Registrar la ruta final después del voto, y propuesta/voto como campos distintos. Fallo de log informativo no autoriza acciones ni cambia el resultado.
- F11.4 — Renombrar la suma actual a tiempo inclusivo acumulado. Añadir inicio/fin de sesión o tarea con reloj monotónico para duración real; para datos viejos no reconstruibles, indicar no disponible.
- F11.5 — Solo si se necesita atribución detallada, añadir ids padre/hijo y medir solapamientos. Para dinero, registrar usage/modelo y versión de tarifa; nunca inferir tokens a partir de segundos.

**Pruebas de aceptación que exigiría:**

- T-H11-a — Rechazo, exit no cero, timeout y cancelación no cuentan como éxito; salida textual que contenga ERROR sin fallo no modifica el estado estructurado.
- T-H11-b — Voto contrario: aplicada coincide con la ruta devuelta.
- T-H11-c — Tool de 10 s contenida en nodo de 10 s: duración de tarea 10 s; suma inclusiva 20 s solo bajo ese rótulo. Paralelismo tampoco se suma como pared.

**Qué no haría:** No reemplazaría un prefijo frágil por varios prefijos frágiles ni convertiría los logs incompletos en cifras exactas.



### H12. La compacción elimina hechos y el validador admite tools huérfanas

**Prioridad:** P1 en tareas largas; P2 para historial defensivo. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; R20, R21.

**Código contrastado:** `utils/compaccion.py:165–201` (compactar); `utils/compaccion.py:146–158` (_resumen); `utils/compaccion.py:69–111` (validar_historial); `main.py:51–98` (resumen_de_sesion).

**Observado:** R21 elimina una decisión de la zona fría y la sustituye por un marcador fijo que remite a memoria. No hay persistencia automática de esos hechos antes del recorte. El resumen de salida usa el historial restante. R20: un mensaje tool sin llamada previa no genera fallas del validador.

**Límite de la evidencia:** Se demostró pérdida de texto del historial, no que el modelo necesariamente incumpla una restricción después. No existe garantía de poder extraer todas las decisiones de lenguaje natural con código puro. Preservar cada bloque assistant+tools es una fortaleza actual.

**Impacto condicionado:** El agente puede perder el pedido activo y restricciones al prolongarse una tarea. El usuario recibe una promesa de recuperación que no está asegurada. Un historial inválido puede pasar el validador local.

**Fix que aplicaría:**

- F12.1 — Fix mínimo: llamar al mecanismo truncación/recorte y retirar la afirmación de que los hechos ya están en memoria. Informar qué se perdió y conservar el pedido activo y el estado de tarea explícito.
- F12.2 — Mantener un registro de hechos estructurados conocidos por el programa: acciones, resultados, aprobaciones y objetivos/restricciones que el usuario haya fijado explícitamente. No fabricar un «resumen factual» ni inferir que está completo.
- F12.3 — Si se necesita resumir prosa libre, guardar el transcript recuperable bajo política de privacidad o resumir con validación y procedencia; marcar incertidumbre y no elevar texto del modelo a instrucciones de autoridad.
- F12.4 — Validar el historial mediante llamadas pendientes y respuestas correspondientes: ids presentes y únicos, tool con llamada previa, ausencia de respuestas duplicadas y lote completo antes del siguiente turno. Conservar unidades atómicas.
- F12.5 — Si la ventana caliente sola excede el presupuesto, detener/solicitar reducción o aplicar paginación controlada; no presentar COMPACTION_CHARS como techo duro si no lo es.

**Pruebas de aceptación que exigiría:**

- T-H12-a — Tras varios recortes, pedido activo y restricciones explícitamente registradas siguen presentes o recuperables; no se promete persistencia inexistente.
- T-H12-b — Tool huérfana, id duplicado, id vacío y respuesta faltante se detectan; un lote válido pasa.
- T-H12-c — Ventana caliente enorme produce un estado claro y no destruye pares de llamadas/respuestas.

**Qué no haría:** No sustituiría hechos por un texto fijo que asegure que fueron guardados ni usaría un resumen generado como nueva política del sistema.



### H13. Los límites de presentación se aplican después del trabajo pesado

**Prioridad:** P2; P1 si se procesan entradas hostiles sin aislamiento. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** S; sin reproducción dinámica asociada.

**Código contrastado:** `modules/coding.py:162–214` (run_command); `utils/fs_tools.py:187–212` (read_file); `modules/vision.py:147–216` (ver_pdf).

**Observado:** run_command usa capture_output y recorta después; read_file lee todo el texto y luego selecciona líneas. ver_pdf ejecuta pdftoppm para todo el documento y solo después cuenta las páginas; no comprueba el total codificado del lote PDF como hace con una imagen individual.

**Límite de la evidencia:** No se ejecutaron pruebas de OOM, PDFs maliciosos o procesos descendientes. El impacto de timeout sobre un árbol depende de SO y del proceso; no se afirma que todo comando deje hijos vivos.

**Impacto condicionado:** Archivo, proceso o PDF grandes pueden consumir memoria, disco y tiempo antes de producir una salida pequeña. Timeout y truncación de texto no son aislamiento.

**Fix que aplicaría:**

- F13.1 — Capturar stdout/stderr incrementalmente con presupuesto en bytes y drenaje que evite bloqueo; al superar el presupuesto, aplicar una política definida de truncación/terminación. Gestionar y limpiar el grupo de procesos según la plataforma.
- F13.2 — Leer archivos de texto incrementalmente para offset/limit y con máximo de bytes/longitud de línea. Declarar si obtener el total exacto requiere recorrer el archivo; no cargarlo entero solo para contar.
- F13.3 — Comprobar o acotar páginas antes de rasterizar. Si se limita la conversión, detectar truncación y decirlo; no afirmar que el documento completo tenía solo esas páginas. Limitar dimensiones de raster y body agregado.
- F13.4 — Probar con fixtures pequeños y límites artificialmente bajos antes de ensayos de estrés aislados. Un grupo de procesos no es una barrera contra procesos hostiles que intenten escapar.

**Pruebas de aceptación que exigiría:**

- T-H13-a — Proceso de prueba con salida mayor al techo no infla el buffer sin límite; timeout/cancelación limpia los procesos que el runner controla.
- T-H13-b — Archivo de muchas líneas y línea individual muy larga respetan el presupuesto.
- T-H13-c — PDF de más de 8 páginas no se rasteriza completo; tamaño agregado excesivo se rechaza antes del API.

**Qué no haría:** No validaría estos riesgos lanzando cargas destructivas en el host real ni diría que truncar a 4.000 caracteres limita la RAM.



### H14. Publicación no atómica, caché entre procesos y semántica de heartbeat

**Prioridad:** P2; condicionado a concurrencia/interrupciones. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** S; varias decisiones de producto; sin reproducción dinámica asociada.

**Código contrastado:** `modules/coding.py:280–346` (edit_file); `modules/escritura.py:59–100` (write_file); `rag.py:110–125` (SaveIndex.exec); `rag.py:170–195` (_cargar); `modules/memoria.py:123–142` (memory_save); `heartbeat.py:89–116` (main).

**Observado:** write/edit leen y luego sobrescriben sin verificar cambios posteriores al preview. El índice se publica en dos archivos y se cachea en memoria. memory_save usa fecha+slug, que puede repetirse. heartbeat --ahora usa todas las tareas; la ayuda declara «correr todas», y solo vencidas aplica el máximo.

**Límite de la evidencia:** No se reprodujeron carreras ni pérdida por interrupción. --ahora es una opción explícita del operador y su comportamiento coincide con la ayuda: no se clasifica por sí solo como bug. La política sobre reemplazar una nota del mismo título debe decidirse.

**Impacto condicionado:** Bajo concurrencia se puede aplicar un diff sobre contenido distinto del aprobado o leer un índice mezclado. No se puede vender el máximo de heartbeat como absoluto si existe la excepción deliberada.

**Fix que aplicaría:**

- F14.1 — Antes de aplicar edit/write a un archivo existente, verificar que sigue coincidiendo con el contenido/hashes usados en el preview; si cambió, regenerar diff y pedir nueva aprobación. Usar publicación atómica cuando se autorice reemplazo y preservar permisos relevantes.
- F14.2 — Para RAG, publicar una generación completa y cambiar atómicamente una referencia a ella; o empaquetar los datos en un único artefacto transaccional. Sustituir dos ficheros por separado con replace no hace atómico el par.
- F14.3 — Incluir versión de generación/modelo en la caché y invalidarla al cambiar. No exigir un sistema distribuido para una aplicación local.
- F14.4 — Decidir si guardar una nota de igual título significa nueva versión o actualización; comunicarlo y probarlo. Si se quieren ambas, diferenciarlas explícitamente.
- F14.5 — Documentar que --ahora ignora el máximo o separar elegibilidad temporal y máximo de ejecución con una opción distinta. Si se cambia, actualizar ayuda y tests. Añadir lock de heartbeat solo si se permite o se observa solapamiento de corridas.

**Pruebas de aceptación que exigiría:**

- T-H14-a — Modificar un archivo entre aprobación y aplicación provoca conflicto, no pérdida silenciosa.
- T-H14-b — Interrupción entre componentes del índice deja visible la generación anterior completa; otro proceso detecta reindexado.
- T-H14-c — Colisión de nota sigue la política elegida. --ahora y ejecuciones solapadas cumplen la semántica documentada.

**Qué no haría:** No llamaría atómico a un par de os.replace ni trataría una opción «correr todas» como violación accidental sin revisar el contrato.



### H15. Calibración permissiva y evidencia limitada para el router

**Prioridad:** P1 para validación de datos; P2 para cambios de routing. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S + D; R19.

**Código contrastado:** `utils/conformal.py:71–97` (leer_calibracion); `utils/conformal.py:100–103` (q_de_calibracion); `nodes.py:478–479` (LayaRouter.prep); `utils/laya.py:46–78` (agente); `utils/laya_routing.py:57–82` (config_router).

**Observado:** R19 acepta conf=1.5 y convierte correcto="false" en True. El router recibe solo el último mensaje truncado a 1.000 caracteres. q infinito se transforma en None y se vuelve a umbral fijo. El dataset incluido contiene 85 registros: 84 herramientas, 1 directo y 77 campos correcto=True.

**Límite de la evidencia:** No se ejecutaron checkpoints ni se midió precisión o ahorro en esta entrega. correcto refleja acuerdo con la etiqueta del dataset, no verdad independiente garantizada. Volver a umbral fijo está documentado y no conserva automáticamente una garantía conformal. No se demostró un fallo de continuación con un modelo real.

**Impacto condicionado:** Entradas de calibración incorrectas pueden alterar la política. Un conjunto casi sin directos no permite estimar bien ese lado del tráfico; afirmaciones sobre cobertura necesitan distinguir garantía teórica y observación empírica.

**Fix que aplicaría:**

- F15.1 — Validar cada fila con número finito conf en [0,1], sin bool como número, y correcto booleano real. Rechazar strings en lugar de convertirlos implícitamente. Informar fila y causa; no calibrar silenciosamente con datos reinterpretados.
- F15.2 — Registrar si se usó conformal o umbral fijo y por qué. Si la operación exige garantía conformal, datos insuficientes => abstener a herramientas; si se permite fallback fijo, indicarlo sin garantía conformal.
- F15.3 — Mantener identificador de dataset, checkpoint y política para comparar. No retocar umbrales con el mismo set utilizado para declarar calidad.
- F15.4 — Medir continuaciones dependientes del historial antes de cambiar el contrato de entrada del checkpoint; añadir contexto compacto solo con compatibilidad y evaluación. No alterar un contrato de entrenamiento por intuición.
- F15.5 — Definir recuperación explícita de errores de carga y validar settings numéricos; no prometer que una descarga o inferencia está acotada sin prueba.

**Pruebas de aceptación que exigiría:**

- T-H15-a — Rechazar conf fuera de rango, NaN, infinito, True, strings y correcto="false"; aceptar booleanos y probabilidades válidas.
- T-H15-b — Calibración insuficiente distingue abstención de fallback fijo y lo registra.
- T-H15-c — Conjunto independiente con continuaciones: medir falso-directo, uso innecesario de tools y latencia total, separando clasificador de voto.

**Qué no haría:** No usaría los 77 acuerdos como precisión del sistema ni cambiaría modelos/umbrales sin una medición nueva.



### H16. El juez comprueba evidencia parcial, no toda la veracidad de una respuesta

**Prioridad:** P2; límite deliberado que debe hacerse visible. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** S; sin reproducción dinámica asociada.

**Código contrastado:** `juez.py:147–159` (Judge.prep); `juez.py:161–250` (Judge.exec); `bench_juez.py:49–57` (respuesta_ok); `bench_juez.py:78–104` (cita_ok).

**Observado:** Judge examina hasta MAX_CITAS=5, mediante regex de rutas y fragmentos de dos líneas. Una cita rota fuerza retry; coincidencia semántica y falta de citas dependen del LLM. El benchmark utiliza presencia de tokens y comprobaciones de citas.

**Límite de la evidencia:** No se reprodujo un falso veredicto con API real. Un límite de cinco citas no es un bug por sí mismo. El grading por tokens detecta propiedades parciales y no debe equipararse a evaluación semántica exhaustiva.

**Impacto condicionado:** El usuario puede interpretar «verificada» como cobertura de todas las afirmaciones, aunque solo se haya examinado un subconjunto de referencias.

**Fix que aplicaría:**

- F16.1 — Publicar número de citas reconocidas, comprobadas, rotas y no revisadas; advertir cuando se alcance el presupuesto. No aumentar MAX_CITAS a ciegas ni suprimir el tope.
- F16.2 — Validar explícitamente líneas >=1 y formatos soportados; añadir casos de rutas con espacios según el contrato elegido.
- F16.3 — Si el modo exige citas, convertir ausencia en estado de verificabilidad insuficiente, separado del juicio semántico. Mantener el borrador y advertencia al agotar rondas.
- F16.4 — Añadir contraejemplos al grading: negación que contiene palabras esperadas, cita correcta para afirmación distinta y menciones irrelevantes. No presentar acierto de tokens como verdad completa.

**Pruebas de aceptación que exigiría:**

- T-H16-a — Seis citas con tope cinco => una declarada no verificada; línea 0 rechazada.
- T-H16-b — Respuesta sin citas cuando son requeridas no se presenta como totalmente verificada.
- T-H16-c — Casos negativos que contienen tokens esperados prueban la limitación y mejoran el grading con condiciones explícitas.

**Qué no haría:** No prometería verificación factual completa con regex y dos líneas de contexto, ni eliminaría el juez solo por no ofrecer esa garantía.



### H17. Research y delegación externa necesitan contratos de evidencia y confianza

**Prioridad:** P2; P1 si se delegan efectos sin autorización. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** S; sin reproducción dinámica asociada.

**Código contrastado:** `research.py:74–87` (Researcher.exec); `utils/websearch.py:8–28` (search_web); `utils/mcp_client.py:85–97` (mcp_call); `modules/a2a.py:95–138` (a2a_tarea); `debate.py:35–50` (Proponente.exec_async); `debate.py:70–85` (Critico.exec_async).

**Observado:** Research interpreta extractos de búsqueda, sin leer documentos completos. search_web devuelve errores como texto, que Researcher puede pasar al LLM. MCP/A2A permiten invocar destinos configurados sin una política local por efecto. Debate usa call_llm síncrono dentro de métodos async.

**Límite de la evidencia:** No se ejecutaron búsquedas, protocolos ni una cancelación real. Los endpoints los configura el operador: no se demuestra SSRF por una URL arbitraria suministrada por el modelo. La secuencia por turnos del debate puede ser deliberada.

**Impacto condicionado:** Se puede confundir una síntesis de extractos con investigación de fuentes completas, o un error de búsqueda con material. Delegar a un servidor configurado no garantiza que su herramienta sea de lectura.

**Fix que aplicaría:**

- F17.1 — Titular el resultado como síntesis preliminar basada en extractos, conservar URLs/extractos utilizados y distinguir búsqueda fallida de búsqueda sin resultados. Si no hay evidencia, no pedir al LLM que la transforme en hechos.
- F17.2 — Añadir allowlist de servidor/herramienta y tratamiento de efectos antes de delegar; configurar límites de tamaño/tiempo. No confiar en descripciones remotas como autorización.
- F17.3 — Probar compatibilidad MCP/A2A con versiones y servidores reales antes de afirmar conformidad. No cambiar schemas de protocolo basándose solo en nombres.
- F17.4 — Para respuesta a cancelación, migrar el I/O a cliente async o aislarlo con cuidado. to_thread evita bloquear el loop, pero cancelar la espera no mata automáticamente el trabajo del hilo.

**Pruebas de aceptación que exigiría:**

- T-H17-a — Búsqueda ERROR no se convierte en evidencia factual; sin resultados se informa la limitación.
- T-H17-b — Herramienta externa fuera de allowlist no se invoca; timeout y resultado enorme se acotan.
- T-H17-c — Cancelar debate/llamada externa no deja tareas pendientes controladas por el harness; integrar luego con transportes reales.

**Qué no haría:** No añadiría descarga web ni infraestructura anti-SSRF como parche automático de un comportamiento deliberadamente basado en extractos.



### H18. El registro y la instalación necesitan contratos explícitos

**Prioridad:** P2. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** S; sin reproducción dinámica asociada.

**Código contrastado:** `modules/__init__.py:14–20` (discover); `utils/call_llm.py:43–51` (_setting).

**Observado:** discover importa los módulos y combina IMPL con update sin detectar colisiones. _setting consulta también un .env de otro proyecto en el home. requirements no declara directamente requests aunque el código lo importa, ni ruff aunque calidad.sh lo usa; casi todas las versiones son rangos abiertos. pyproject no declara metadata requires-python.

**Límite de la evidencia:** No se ensayó instalación limpia completa ni una colisión real. Una dependencia transitiva puede hacer que requests esté disponible hoy; eso no constituye un fallo de importación demostrado. El target py312 de Ruff no certifica compatibilidad con todas las versiones de Python.

**Impacto condicionado:** Un módulo roto puede impedir descubrir otros y un nombre duplicado sustituye implementación. La configuración heredada y dependencias variables dificultan reproducir resultados.

**Fix que aplicaría:**

- F18.1 — Validar nombres únicos en CORE + módulos, correspondencia TOOLS/IMPL y parámetros obligatorios al arrancar. Fallar con diagnóstico claro ante colisiones; no elegir la última función importada.
- F18.2 — Si se soportan capacidades opcionales, declararlas y cargarlas de forma selectiva. Un módulo requerido roto debe impedir arrancar con un mensaje claro, no desaparecer silenciosamente.
- F18.3 — Hacer explícito y opt-in el fallback al .env de otro proyecto. Mostrar procedencia de settings sin valores secretos y fijar una configuración coherente por sesión.
- F18.4 — Declarar dependencias directas y separar herramientas de desarrollo. Fijar un entorno reproducible/lock y versión mínima de Python comprobada con instalación limpia, sin presentar una versión no probada como soportada.

**Pruebas de aceptación que exigiría:**

- T-H18-a — Nombre duplicado o implementación ausente se detecta antes de aceptar pedidos.
- T-H18-b — Capacidad opcional ausente y requerida rota producen los estados definidos.
- T-H18-c — Instalación limpia ejecuta calidad.sh y entradas CLI; configuración ajena no se hereda salvo opt-in.

**Qué no haría:** No añadiría un framework de plugins o Pydantic solo para comprobar unicidad, ni confundiría deuda de empaquetado con un crash ya observado.



### H19. Privacidad, inventario y setup necesitan describir el comportamiento real

**Prioridad:** P2; riesgo de privacidad según datos tratados. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** S + D; sin reproducción dinámica asociada.

**Código contrastado:** `nodes.py:20–44` (registrar_pregunta); `main.py:51–98` (resumen_de_sesion).

**Observado:** PREGUNTAS_LOG=1 persiste preguntas en claro. El README anuncia 24 capacidades y el registro tiene 28 herramientas; «capacidad» y «tool» no son necesariamente la misma unidad. La tabla describe PDF como Files API, pero ver_pdf usa pdftoppm e imágenes. descargar_modelos.sh solo configura rutas de checkpoints al crear .env si no existe.

**Límite de la evidencia:** No se inspeccionaron conversaciones privadas ni se produjo exfiltración. No se presenta el contraste 24/28 como error de conteo inequívoco; exige definir qué se cuenta. La ausencia de secretos en un barrido por patrones no certifica ausencia total.

**Impacto condicionado:** El usuario puede conservar texto sensible sin advertirlo o seguir un setup que descarga modelos sin configurar su uso. La documentación puede crear expectativas que el código no cumple.

**Fix que aplicaría:**

- F19.1 — Avisar al arrancar si se guardan preguntas/resúmenes, con destinos lógicos y política de retención; ofrecer modo privado explícito. Para nuevas instalaciones, considerar logging de contenido opt-in y captura de calibración separada con consentimiento.
- F19.2 — Limitar permisos y retención según SO, evitar imprimir secretos y documentar qué se envía a proveedores. .gitignore evita versionar por accidente, no protege backups o lectura local.
- F19.3 — Generar inventario de herramientas desde el registro y definir aparte «capacidades». Actualizar PDF/Poppler, fallback de memoria y descripción de compacción.
- F19.4 — Si .env ya existe, no sobrescribirlo: detectar settings de modelos ausentes y ofrecer agregarlos o imprimir instrucciones precisas. Comprobar el flujo Quickstart completo.

**Pruebas de aceptación que exigiría:**

- T-H19-a — Modo privado no persiste preguntas ni resumen; logging opt-in avisa y respeta la retención configurada.
- T-H19-b — Quickstart con .env ya existente permite activar checkpoints sin perder otros settings.
- T-H19-c — Catálogo generado coincide con TOOLS; documentación PDF y compacción corresponde al recorrido actual.

**Qué no haría:** No certificaría privacidad por usar .gitignore ni pondría cifras de capacidades sin definir la unidad.



### H20. La validación disponible no equivale a un gate integral del proyecto

**Prioridad:** Trabajo de aceptación, no fallo de ejecución confirmado. **Naturaleza:** límite de validación y plan de aceptación. **Evidencia:** M; sin reproducción dinámica asociada.

**Código contrastado:** `modules/__init__.py:14–20` (discover).

**Observado:** La evidencia registra 270 funciones test, pero solo 17 casos parametrizados de test_laya_routing fueron ejecutados en la revisión; cuatro funciones con fixtures de archivos quedaron fuera. Todos esos 17 pasaron. AST y Ruff cubren otras propiedades, no comportamiento de todos los flujos.

**Límite de la evidencia:** Que esta revisión no ejecutara la suite completa es un límite de la auditoría, no prueba de que la suite falle ni de que el autor no la haya ejecutado. No hay porcentaje de cobertura medido.

**Impacto condicionado:** Aceptar fixes solo por revisión o por unos tests verdes puede dejar regresiones de interfaces, permisos, cron o transporte.

**Fix que aplicaría:**

- F20.1 — Para cada fix, crear primero el test de regresión que reproduzca el comportamiento previo con fixture controlado; después aplicar el parche y comprobar que pasa por el motivo correcto.
- F20.2 — Ejecutar la suite completa en checkout limpio, con versiones declaradas y logs de fallos/skips. Fijar Ruff y ejecutar calidad.sh en ese mismo entorno.
- F20.3 — Separar pruebas deterministas de integración opt-in con API, checkpoints y transportes; no hacer que una suite aparentemente offline descargue modelos silenciosamente.
- F20.4 — Organizar nuevos tests por subsistema si facilita mantenimiento. Descomponer el smoke monolítico es refactor opcional, no condición previa para corregir un P0.

**Pruebas de aceptación que exigiría:**

- T-H20-a — CI adjunta comandos, versiones, resultados y skips; no confunde 270 funciones con 270 casos ejecutados.
- T-H20-b — Cada hallazgo R corregido tiene regresión antes/después y un caso positivo de compatibilidad.
- T-H20-c — Integraciones no ejecutadas quedan marcadas pendientes, no pasadas por mocks.

**Qué no haría:** No vendería el análisis AST, Ruff o los 17 casos como una suite completa, ni como una nota porcentual de calidad.



### H21. El banco autoaprueba por prefijos y permite prompts no reconocidos

**Prioridad:** P1 cuando se usa hitl: s fuera de un workspace desechable. **Naturaleza:** defecto/garantía incompleta. **Evidencia:** R + S; R24, R25, R26.

**Código contrastado:** `banco/banco.py:52–93` (decision_hitl); `banco/banco.py:210–349` (correr).

**Observado:** Las tres pruebas puras se reejecutaron: permitir /workspace/proyecto admite /workspace/proyecto_evil; permitir echo permitido admite echo permitido; touch marcador_sintetico; un prompt no parseable devuelve dentro=True. correr responde s cuando dentro=True y la política del turno es s. La limpieza usa RAIZ/path sobre scratch.

**Límite de la evidencia:** No se inició Chat, PTY o cleanup y no se ejecutó ningún comando. Los escenarios son configuración del operador, no una entrada remota demostrada. Una función de alcance permisiva no ejecuta nada por sí sola; el riesgo aparece al conectarla a autoaprobación.

**Impacto condicionado:** El banco puede aprobar acciones fuera del alcance que aparenta imponer. HITL_AUTO=0 en el chat no basta si el banco responde sí. Un scratch erróneo puede apuntar fuera del workspace; ese último punto es estático.

**Fix que aplicaría:**

- F21.1 — Fallar cerrado si no se reconoce el tipo de aprobación o no se obtiene un objetivo completo. Para autoaprobación, ausencia de allowlist debe significar denegación; si se conserva modo legado permisivo, exigir opt-in inequívoco y workspace desechable.
- F21.2 — Comparar rutas canónicas por componentes/pertenencia real, no startswith. Rechazar hermanos con igual prefijo, escapes .. y enlaces hacia fuera según la política.
- F21.3 — Como parche mínimo para comandos, permitir coincidencia exacta contra comandos completos preautorizados y rechazar composición no autorizada. A medio plazo, emitir solicitudes HITL estructuradas con id, acción y objetivo íntegro; el texto de terminal no debe ser la frontera de autorización.
- F21.4 — Validar scratch antes de iniciar: solo descendientes estrictos de un directorio desechable, nunca raíz del repo, padre ni destino externo. Limpiar recursos en finally sin ampliar ámbito.
- F21.5 — Diferenciar turno finalizado de tarea correcta. Añadir asserts de resultado/archivos esperados a los escenarios en vez de usar solo marcadores como verificación semántica.

**Pruebas de aceptación que exigiría:**

- T-H21-a — R24, R25 y R26 deben devolver dentro=False tras el fix; ruta hija legítima y comando completo autorizado siguen pasando.
- T-H21-b — Comando ausente, multilinea incompleta y aprobación doble no se autoaprueban por un texto parcial.
- T-H21-c — scratch externo se rechaza antes del arranque y cleanup nunca toca archivos ajenos. Un turno terminado sin el resultado esperado no obtiene tarea_correcta=True.

**Qué no haría:** No trataría prefijos de terminal como una autorización fuerte ni ejecutaría escenarios desconocidos contra el repositorio principal.



## 5. Plan de aplicación en cambios pequeños

El orden evita reescribir el harness. Los grupos son unidades de revisión propuestas, no estimaciones de esfuerzo ni commits existentes.

| Cambio | Contenido mínimo | Dependencias / cierre |
|---|---|---|
| PR-01 — Contención shell y banco | H01 y H21: default manual; permisos exactos/canónicos; parsing desconocido denegado; scratch restringido. | Tests de clasificación y decisión puros; cero shell real en regresiones peligrosas. |
| PR-02 — Política única | H03: PRE fail-closed, validación del envelope, wrappers MCP que usan el dispatcher. | Paridad de controles y schemas; no requiere reescribir PocketFlow. |
| PR-03 — Cancelación y autorización por paso | H04–H05 y R20 de H12: estado de stream, bloqueo de nativas/DSML, presupuesto en punto de efecto e historial consistente. | Probar lotes parciales, agotamiento, rechazo y continuación. |
| PR-04 — Salidas con ámbito | H02: helper de artefactos + evals, creación sin colisión y actualización cron explícita. | Preservar modo no interactivo; conflictos y rutas inválidas no modifican archivos. |
| PR-05 — Recuperación y SQL | H06–H08: revalidación RAG/memoria, fallback sin recorte, firma query y límite fetchmany/salida. | Regresiones de nota 9, root revocada y LIMIT en comentario. |
| PR-06 — Métricas exactas | H09–H11: rótulos locales/globales, huellas canónicas, lector completo, baseline evaluable, estados y ruta final. | Recalcular/reversionar métricas afectadas; no comparar contra definiciones antiguas sin advertencia. |
| PR-07 — Contexto y calibración | H12 y validación de H15: truncación honesta, estado explícito de tarea y tipos estrictos de calibración. | No cambiar umbrales o contrato del checkpoint sin evaluación independiente. |
| PR-08 — Endurecimiento y documentación | H13–H19 según prioridad de uso; H20 como gate de todos los PR. | Reproducir riesgos estáticos relevantes antes de incorporar infraestructura mayor. |

### 5.1 Compatibilidad y migración

- Cambiar el default de auto modifica UX: anunciarlo y mantener controles más estrictos existentes. La ejecución automática de cron debe depender de capacidades delimitadas, no de respuestas s indiscriminadas.
- Cambiar huellas, política de routing o definición de duración invalida comparaciones directas con métricas viejas; guardar versión y mantener la evidencia anterior.
- El nuevo resultado interno de herramientas debe conservar el contrato externo role=tool. No introducir campos no admitidos en requests del proveedor.
- Fallback de memoria sin recorte puede aumentar I/O; compensarlo con búsqueda incremental/paginación, no con falsos negativos silenciosos.
- Para atomicidad y locks, definir sistemas operativos soportados; no prometer portabilidad de una técnica específica sin probarla.

### 5.2 Criterio de cierre por fix

1. Test que reproduce la condición anterior con datos controlados y causa identificada.
2. Cambio mínimo en el punto responsable, con comportamiento positivo y negativo especificado.
3. Regresión anterior corregida; caso permitido sigue funcionando; no nuevas rutas que eviten la política.
4. Suite determinista completa y lint en checkout limpio con versiones registradas.
5. Integración real cuando el fix afecta transporte/modelo, declarando las comprobaciones que siguen pendientes.
6. Documentación y métricas actualizadas; evidencia antes/después. Un test omitido no cuenta como pasado.



## 6. Registro resumido de las 26 comprobaciones

Las entradas y resultados completos registrados quedan en `evidencia_descubrimientos_fixes_harness.json`. Para R01–R23 se conserva exactamente el resultado previo; cuando aquel archivo no contiene entradas completas, no se inventan. Las fixtures descritas en los tests propuestos son criterios de validación futura, no un script ya ejecutado.

| Evidencia | Resultado y alcance | Procedencia |
|---|---|---|
| R01 | Clasificador: comandos con efectos obtienen auto; solo se clasificaron. | JSON de revisión previa |
| R02 | Ejecutor simulado invocado=True; aprobación solicitada=False; shell real=False. | JSON de revisión previa |
| R03 | Excepción de hook PRE; implementación simulada invocada=True. | JSON de revisión previa |
| R04 | KeyboardInterrupt tras una tool call: run_command continúa en el retorno. | JSON de revisión previa |
| R05 | tools ofrecidas=None; respuesta nativa simulada => transición tool. | JSON de revisión previa |
| R06 | write_text simulado invocado sobre destino de código; escritura real=False. | JSON de revisión previa |
| R07 | Directorio externo pasado a generar mock sin validarlo; escritura real=False. | JSON de revisión previa |
| R08 | memory_search({}) => TypeError por query obligatorio. | JSON de revisión previa |
| R09 | Coincidencia sintética solo en nota 9 => «no aparece»; se recorta 9→8. | JSON de revisión previa |
| R10 | Chunk sintético fuera de las raíces actuales aparece en la respuesta RAG. | JSON de revisión previa |
| R11 | SQLite en memoria: 80 filas devueltas con máximo anunciado de 50. | JSON de revisión previa |
| R12 | Dos resúmenes locales de efectivo=1 => agregado 2; no es prueba de unión global. | JSON de revisión previa |
| R13 | Objetos iguales con orden distinto de claves anidadas => huellas distintas. | JSON de revisión previa |
| R14 | JSON válido [] => AttributeError en HashFile. | JSON de revisión previa |
| R15 | score nuevo=None y baseline numérico => TypeError al restar. | JSON de revisión previa |
| R16 | Dos eventos sintéticos de 10 s => total inclusivo 20; no mide pared. | JSON de revisión previa |
| R17 | RECHAZADO y exit 1 registrados con ok=True. | JSON de revisión previa |
| R18 | Log aplicada=directo; ruta final devuelta=herramientas. | JSON de revisión previa |
| R19 | conf=1.5 aceptada; correcto="false" convertido en True. | JSON de revisión previa |
| R20 | Historial con tool huérfana => lista de errores vacía. | JSON de revisión previa |
| R21 | Decisión antigua ausente tras recorte; reemplazo por marcador fijo. | JSON de revisión previa |
| R22 | MCP simulado registra función original; no se inicia transporte. | JSON de revisión previa |
| R23 | 28 tools descubiertas; query de memory_search obligatorio en firma pero no en schema. | JSON de revisión previa |
| R24 | Ruta hermana con mismo prefijo => dentro=True; reejecutado sin I/O. | Esta entrega, función pura |
| R25 | Comando compuesto con prefijo permitido => dentro=True; no ejecutado. | Esta entrega, función pura |
| R26 | Prompt no parseable => dentro=True; reejecutado sin I/O. | Esta entrega, función pura |



## 7. Datos incluidos: qué permiten afirmar

- Calibración: 85 registros parseables; herramientas=84, directo=1; correcto=True=77, False=8. Son propiedades del archivo, no un ensayo nuevo del modelo.
- Banco del juez: 17 registros. Su existencia no demuestra robustez fuera de esos casos ni que cada métrica mida verdad semántica.
- El informe de calibración del propio proyecto identifica el sesgo de escenarios dirigidos. No se recomienda elegir un umbral nuevo sin datos representativos, etiquetas revisadas y una prueba independiente.



## 8. Hallazgos históricos que no se reabren sin prueba

- DirectAnswer ya tiene transición de answer al chat en flow.py; no se propone repetir el arreglo antiguo.
- El supervisor actual usa run_tool_call; el bypass confirmado en esta revisión es la exposición directa de implementaciones en MCP.
- La caché de RAG ya se invalida en SaveIndex.post dentro del proceso. H14 se refiere a publicación consistente y cambios desde otros procesos, no a negar ese fix existente.
- El juez ya fuerza retry ante citas rotas y pasa el borrador anterior al refinamiento. H16 delimita cobertura, no afirma que esos controles falten.
- La documentación incluye una sonda posterior que no reprodujo el error de cambio de thinking. Sin nueva API real, no se recomienda cambiar esa política por una acusación histórica.
- No se infiere un bug actual de semáforos globales antiguos ni de importación circular ya corregida sin una reproducción contra esta copia.



## 9. Conclusión

Aplicaría primero fixes locales verificables en autorización, cancelación, escritura y exactitud. Mantendría la arquitectura y sus helpers compartidos; no introduciría frameworks adicionales para resolver lo que puede cerrarse con una validación, una política de ámbito y un test.

Los cambios de mayor alcance —aislamiento fuerte, presupuestos globales completos, spans, versionado transaccional de índices, cambios de checkpoint— se justifican por el escenario de uso y pruebas específicas. No se presentan como correcciones ya demostradas o aplicadas.

**Estado final de esta entrega:** documento y evidencia producidos; proyecto sin modificaciones; fixes propuestos y pendientes de implementación y validación.