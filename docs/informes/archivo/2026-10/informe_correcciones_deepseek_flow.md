# Informe de correcciones — deepseek-flow

**Fecha:** 2026-10-08  
**Fuente:** `deepseek-flow-main.zip`  
**Alcance:** 35 archivos Python y documentación técnica.  
**Estado:** diagnóstico y plan de corrección. Ningún cambio está aplicado.
**SHA-256 del ZIP:** `4f485bd1f0e2cd63ab5fad5e88eb651e14b8579f91d6d962b94f99a2181f6d9a`

## 1. Alcance y evidencia

Este informe convierte los hallazgos de la revisión en tareas de implementación. Cada tarea incluye la causa, la solución y pruebas de aceptación.

Los identificadores C01 a C22 sirven para crear tareas y relacionarlas con sus pruebas. Las mejoras adicionales propuestas no se presentan como fallos reproducidos.

La revisión anterior incluyó pruebas con Python 3.12 y PocketFlow 0.0.3. Las pruebas sustituyeron las respuestas de los modelos y las operaciones externas.

Las pruebas de archivos usaron un sistema simulado o sustituyeron las escrituras. Este informe no demuestra el comportamiento de DeepSeek o Laya con inferencia real.

Los 35 archivos Python tienen sintaxis válida. No se ejecutó la suite completa ni una prueba integral con todos los servicios.

El ZIP no incluye checkpoints, índices, bases de datos ni conjuntos de trazas. Las referencias de línea corresponden a esa copia del código.

### Términos usados

| Término | Significado |
|---|---|
| JSON | JavaScript Object Notation. Formato de datos. |
| YAML | YAML Ain’t Markup Language. Formato usado por las respuestas estructuradas. |
| SQL | Structured Query Language. Lenguaje de consultas. |
| LLM | Modelo de lenguaje de gran tamaño. |
| MCP | Model Context Protocol. Protocolo para exponer y consumir herramientas. |
| URI | Identificador uniforme de recurso. |
| STE | Simplified Technical English. Reglas de redacción técnica. |

### Tipos de evidencia

| Marca | Significado |
|---|---|
| R | Comportamiento reproducido durante la revisión anterior, con dependencias externas simuladas cuando correspondía. |
| E | Hallazgo por lectura del código. No implica una reproducción integral. |
| H | Riesgo pendiente de una prueba con el entorno o los modelos reales. |

Las soluciones y los fragmentos de código son propuestas. No son cambios aplicados ni soluciones con pruebas integrales terminadas.

### Prioridades

| Prioridad | Criterio |
|---|---|
| P0 | Protección de archivos y permisos. Resolver antes de habilitar escrituras automáticas o acceso externo. |
| P1 | Fallos de ejecución, resultados incorrectos o controles que no cumplen su contrato. |
| P2 | Robustez, calidad y coherencia de la documentación. |

## 2. Índice de correcciones

| ID | Prioridad | Corrección | Evidencia |
|---|---|---|---|
| C01 | P0 | Unificar los permisos y la aprobación de escrituras. | R |
| C02 | P0 | Comprobar cada archivo y sus enlaces simbólicos. | R / E |
| C03 | P1 | Crear el semáforo dentro de cada ejecución asíncrona. | R |
| C04 | P1 | Corregir la transición de `DirectAnswer`. | R |
| C05 | P1 | Eliminar la importación circular del supervisor. | R |
| C06 | P1 | Definir esquemas de respuesta y separar los reintentos. | R |
| C07 | P1 | Corregir el contrato del juez y su refinamiento. | R / E |
| C08 | P1 | Entregar resultados reales al supervisor y resolver dependencias. | R / E |
| C09 | P1 | Aplicar controles efectivos sobre SQLite. | R / E |
| C10 | P1 | Invalidar la caché y proteger la consistencia del índice. | R / E |
| C11 | P1 | Comprobar la estructura de cada registro JSON. | R / E |
| C12 | P1 | Separar el muestreo del informe de la carga completa de datos. | E |
| C13 | P1 | Aplicar presupuestos locales y globales. | R / E |
| C14 | P1 | Manejar fallos de inferencia y respuestas inválidas de Laya. | R / E |
| C15 | P2 | Dar contexto suficiente al router y medir sus errores. | E / H |
| C16 | P2 | Aislar la configuración local de Laya. | E / H |
| C17 | P2 | Aclarar el alcance de research y conservar la evidencia. | E |
| C18 | P1 | Registrar errores y controlar la integración de tracing. | R / E |
| C19 | P2 | Aclarar el estado compartido del debate y evitar bloqueos. | E |
| C20 | P1 | Separar las instrucciones al modelo de los controles del programa. | E / H |
| C21 | P1 | Crear pruebas portables que cubran las garantías reales. | E |
| C22 | P2 | Corregir opciones, comandos y promesas de la documentación. | E |

## 3. Correcciones de seguridad y ejecución

### C01. Unificar los permisos y la aprobación de escrituras

**Prioridad:** P0. **Evidencia:** R.

**Dónde:** `informe.py:173–175`, `auditoria.py:97–99`, `research.py:121–122`, `supervisor.py:126–128` y `modules/escritura.py:52–89`.

**Problema:** `write_file` comprueba la ruta y pide aprobación. Los flujos de informes llaman directamente a `Path.write_text()`.

Una salida suministrada al flujo puede apuntar fuera de los directorios permitidos. El proceso puede sobrescribirla si sus permisos del sistema lo permiten.

**Solución propuesta:** crear un servicio único de escritura. El chat, los subcomandos y los módulos deben usar ese servicio.

Distinguir dos clases de escritura:

- **Documento del usuario:** requiere aprobación vinculada a la ruta y al contenido exactos.
- **Artefacto interno:** permite escritura automática solo en una ubicación configurada por el operador.

Esta distinción evita pedir aprobación por cada evento de traza. También evita que una salida elegida por el modelo eluda la aprobación.

Pasos de implementación:

1. Crear `utils/storage_policy.py` con una política explícita de escritura.
2. Incorporar la comprobación de rutas y el flujo de aprobación existente.
3. Sustituir las escrituras directas de los cuatro flujos.
4. Guardar mediante un archivo temporal y un reemplazo atómico en el mismo sistema de archivos.
5. Devolver un resultado estructurado cuando el usuario rechace la escritura.

La aprobación debe quedar invalidada si cambia el contenido o la ruta. Una comprobación previa con `Path.resolve()` no elimina las carreras del sistema de archivos.

Si otro proceso puede cambiar enlaces durante la operación, usar aislamiento del sistema operativo o apertura segura mediante descriptores.

**Pruebas de aceptación:**

- Una salida externa no crea ni modifica archivos.
- Un rechazo no modifica el archivo anterior.
- Un cambio después de la aprobación exige otra aprobación.
- Los informes respetan la misma política que `write_file`.
- Los artefactos automáticos quedan dentro de su ubicación autorizada.

**Parche a evitar:** agregar cuatro preguntas `input()` independientes. Eso duplica la política y deja otras escrituras sin control.

### C02. Comprobar cada archivo y sus enlaces simbólicos

**Prioridad:** P0. **Evidencia:** R para la búsqueda y la selección del índice. E para otros recorridos.

**Dónde:** `utils/fs_tools.py:65–90,147–167`, `rag.py:43–82` e `informe.py:39–46`.

**Problema:** comprobar la carpeta inicial no comprueba cada archivo encontrado. Un enlace puede apuntar fuera de las raíces permitidas.

La prueba mostró que `read_file` rechazó un enlace externo, pero `search_files` devolvió su contenido. El recorrido del índice también seleccionó ese enlace.

**Solución propuesta:** centralizar el recorrido autorizado y la apertura de archivos.

La política debe cubrir los archivos y los directorios intermedios. La opción inicial más simple es rechazar enlaces simbólicos durante los recorridos.

Si se permiten enlaces, comprobar el destino real de cada candidato antes de abrirlo. Aplicar la política también a informes, auditorías e indexación.

La consulta del índice debe respetar los permisos actuales. Reducir los permisos no debe dejar accesible una copia anterior del contenido indexado.

**Pruebas de aceptación:** enlace a un archivo externo, enlace a una carpeta externa, enlace roto y ciclo entre carpetas. Ninguno debe filtrar contenido ni bloquear el recorrido.

Para cambios concurrentes de enlaces, usar el aislamiento descrito en C01. No presentar la comprobación de rutas como un aislamiento completo del proceso.

### C03. Crear el semáforo dentro de cada ejecución asíncrona

**Prioridad:** P1. **Evidencia:** R.

**Dónde:** `informe.py:35–36,110–118`. También afecta a los módulos que llaman varias veces a `asyncio.run()`.

**Problema:** `_SEMAFORO` vive en el módulo. Cuando debe esperar, puede quedar asociado al bucle de eventos de esa ejecución.

La prueba ejecutó dos mapas de nueve tareas, con concurrencia ocho. El segundo falló con `is bound to a different event loop`.

**Solución propuesta:** crear el semáforo dentro de la función asíncrona que inicia cada ejecución. Pasarlo a los nodos mediante sus entradas o un contexto de ejecución.

Ejemplo conceptual para el nodo de mapa:

```python
class AnalizeFile(AsyncParallelBatchNode):
    async def prep_async(self, shared):
        return [
            (path, shared["map_semaphore"])
            for path in shared["files"]
        ]

    async def exec_async(self, item):
        path, semaphore = item
        async with semaphore:
            stats = stats_de(path)
            summary = await interpretar(path, stats)
            return {"file": path, **stats, "resumen": summary}
```

El punto de entrada asíncrono crea `shared["map_semaphore"]`. La auditoría debe recibirlo también, porque reutiliza el nodo.

Mantener `asyncio.run()` solo en entradas síncronas sin un bucle activo. Dentro de un entorno asíncrono, llamar a una función asíncrona mediante `await`.

**Pruebas de aceptación:** dos informes consecutivos con más tareas que permisos disponibles. Ambas ejecuciones terminan y nunca exceden la concurrencia configurada.

**Parche a evitar:** modificar globalmente el comportamiento del bucle para permitir llamadas anidadas a `asyncio.run()`.

### C04. Corregir la transición de `DirectAnswer`

**Prioridad:** P1. **Evidencia:** R.

**Dónde:** `flow.py:21` y `nodes.py:42–47,107–111`.

**Problema:** `DirectAnswer` hereda un `post()` que devuelve `answer`. La conexión usa la acción `default`.

**Cambio puntual:**

```python
# Actual
directo >> ask
```

Reemplazarla por:

```python
directo - "answer" >> ask
```

**Prueba de aceptación:** activar Laya, simular una decisión `directo` y enviar dos preguntas. El chat procesa ambas sin avisos de transición inexistente.

El defecto pertenece al grafo. No requiere cambiar el prompt ni el umbral de Laya.

### C05. Eliminar la importación circular del supervisor

**Prioridad:** P1. **Evidencia:** R.

**Dónde:** `supervisor.py:28`, `modules/supervisor.py:5` y `modules/__init__.py:14–20`.

**Problema:** importar `supervisor` inicia el descubrimiento de módulos. Ese descubrimiento importa `modules.supervisor`, que intenta importar `supervisar` antes de su definición.

Importar primero `nodes` evita el fallo en el recorrido habitual. Eso no elimina la dependencia circular.

**Corrección mínima:** mover la importación al cuerpo del adaptador.

```python
def run_supervisor(tarea, salida="supervisor.md"):
    from supervisor import supervisar

    ruta = supervisar(tarea, salida)
    return f"Síntesis del supervisor escrita: {ruta}. Lee el archivo con read_file."
```

Esta corrección rompe el ciclo inmediato. La solución estructural consiste en construir el registro al iniciar la aplicación, no al importar los módulos.

El supervisor debe recibir el registro como dependencia. El registro debe rechazar nombres duplicados y discrepancias entre `TOOLS` e `IMPL`.

**Pruebas de aceptación:** importar `nodes`, `supervisor` y `modules.supervisor` en procesos nuevos e independientes. El resultado no depende del orden de importación.

## 4. Contratos de datos y resultados

### C06. Definir esquemas de respuesta y separar los reintentos

**Prioridad:** P1. **Evidencia:** R.

**Dónde:** `utils/estructura.py:17–24`, `juez.py:113–127`, `research.py:109–122` y `supervisor.py:74–80`.

**Problemas reproducidos:**

- `python -O` elimina los `assert` usados como controles de producción.
- El supervisor aceptó seis pasos con `-O`, aunque el máximo es cinco.
- `verdict: retry` sin `problems` supera `Judge.exec` y falla en `Judge.post`.
- `content: 42` supera la comprobación de research, aunque la escritura requiere texto.
- Un reintento por formato repite el mismo prompt, sin el error ni la respuesta anterior.

**Solución propuesta:** mantener `assert` para pruebas internas, no para comprobar entradas externas. Definir esquemas explícitos para cada respuesta.

Se puede usar Pydantic 2 con modo estricto, o comprobadores equivalentes. Si se usa Pydantic directamente, declararlo como dependencia del proyecto.

Contrato propuesto:

| Respuesta | Comprobaciones obligatorias |
|---|---|
| Juez | `verdict` permitido, listas de cadenas y problemas no vacíos si solicita corrección. |
| Plan de búsqueda | Entre una y tres consultas no vacías, sin duplicados. |
| Decisión de research | Variante `research` con feedback o variante `finalize` con contenido textual no vacío. |
| Plan del supervisor | Uno a cinco pasos, herramientas existentes y argumentos comprobados contra su esquema. |
| Debate | Ganador permitido y síntesis textual no vacía. |

Definir un contrato de serialización que preserve el contenido completo. El `split()` actual puede cortar texto cuando encuentra delimitadores dentro del contenido.

Si el proveedor ofrece salida estructurada compatible, usarla y mantener la comprobación local. No asumir esa compatibilidad sin probarla.

Separar los fallos:

| Fallo | Tratamiento |
|---|---|
| Red o límite temporal del proveedor | Reintento acotado con espera creciente. |
| Respuesta con estructura inválida | Reparación acotada con la respuesta anterior y errores concretos. |
| Permiso rechazado o argumento imposible | Resultado de error para el flujo, sin repetición automática. |
| Error de programación | Registro del error y fallo explícito. |

Los reintentos deben consumir el presupuesto global. Evitar multiplicar sin control los reintentos del cliente y los de PocketFlow.

PocketFlow 0.0.3 reintenta `exec`, no `prep` ni `post`. Los datos deben salir de `exec` con tipos correctos.

Las operaciones de escritura necesitan su propia política de error. Repetir un nodo completo puede repetir efectos ya ejecutados.

**Pruebas de aceptación:** respuestas incompletas, tipos incorrectos, texto con delimitadores y planes bajo `python -O`. Ninguna entrada inválida llega a la ejecución de herramientas.

### C07. Corregir el contrato del juez y su refinamiento

**Prioridad:** P1. **Evidencia:** R / E.

**Dónde:** `juez.py:22–36,39–62,69–128` y `modules/juez.py:25–30`.

**Problema de aceptación:** una cita inexistente no impone el rechazo. La prueba suministró una cita con error y un `verdict: ok` simulado. El flujo entregó la respuesta.

**Problema de refinamiento:** el nuevo borrador recibe los problemas, pero no el borrador anterior. Tampoco recibe las `suggestions`.

La revisión actual examina hasta cinco citas y reúne contexto de hasta tres archivos. El resultado no debe implicar una comprobación completa fuera de ese alcance.

**Solución propuesta:** separar la comprobación de referencias de la evaluación semántica.

1. Representar las citas como datos con ruta y rango de líneas.
2. Comprobar existencia, permisos y límites de cada referencia en código.
3. Bloquear la aprobación si existen errores objetivos en las referencias.
4. Entregar al refinamiento el borrador anterior y todos los problemas pertinentes.
5. Devolver un estado explícito cuando se agoten las rondas sin aceptación.

El resultado puede incluir `status`, `answer`, `reference_checks`, `review` y `warnings`.

Una referencia válida no demuestra que una afirmación sea verdadera. La evaluación semántica debe conservar su condición de juicio del modelo.

Si el presupuesto impide examinar todas las citas, devolver una revisión parcial. No convertir una muestra aceptada en una garantía sobre toda la respuesta.

**Pruebas de aceptación:** cita inexistente con `verdict: ok`, línea fuera de rango, ruta prohibida y respuesta sin citas cuando son necesarias.

El refinamiento debe recibir exactamente el borrador evaluado. Al alcanzar el límite, el resultado debe distinguir `not_approved` de una revisión aceptada.

**Parche a evitar:** reforzar únicamente frases como `las citas DEBEN coincidir`.

### C08. Entregar resultados reales al supervisor y resolver dependencias

**Prioridad:** P1. **Evidencia:** R / E.

**Dónde:** `supervisor.py:55–64,90–123` y los adaptadores de informes, auditoría y research.

**Problema:** varias herramientas devuelven solamente la ruta de un informe. El supervisor pasa ese mensaje a la síntesis sin leer el contenido.

El modelo puede recibir `Informe generado: informe.md` y una solicitud de explicar los hallazgos. El contenido necesario no está en su entrada.

Además, todos los argumentos quedan fijados antes de ejecutar el primer paso. No existe una referencia general a resultados anteriores.

**Solución propuesta:** separar el resultado interno de su representación para el chat.

Ejemplo de contrato propuesto:

```json
{
  "status": "ok",
  "data": {
    "files_analyzed": 12,
    "total_records": 240,
    "summary": "Resumen calculado o generado durante el flujo"
  },
  "artifacts": [
    {"path": "informe.md", "media_type": "text/markdown"}
  ],
  "warnings": []
}
```

Los números son ilustrativos. No son resultados del conjunto de datos del usuario.

El supervisor consume `data`. El adaptador del chat transforma el resultado en un mensaje legible. Una ruta no reemplaza los datos necesarios para la síntesis.

Para dependencias, usar uno de estos diseños:

- **Inicial:** ejecutar un paso y planificar el siguiente con el resultado disponible.
- **Posterior:** plan completo con referencias tipadas entre pasos y un orden de dependencias comprobado.

No usar `eval()` para resolver referencias. Un resultado fallido debe bloquear o marcar los pasos que dependen de él.

Conservar la exclusión de `run_supervisor` del registro local. Si se permite delegación externa, aplicar también el presupuesto y la profundidad globales.

**Pruebas de aceptación:** una herramienta genera un hallazgo conocido y la síntesis recibe ese hallazgo. Un paso posterior recibe una ruta realmente devuelta por el anterior.

Una dependencia fallida no produce una síntesis que afirme una tarea completa.

**Parche a evitar:** pedir que la síntesis final razone una dependencia que nunca se ejecutó.


## 5. Datos, consultas y presupuestos

### C09. Aplicar controles efectivos sobre SQLite

**Prioridad:** P1. **Evidencia:** R para los filtros y los resultados. E para la configuración de conexión.

**Dónde:** `modules/db.py:16–24,42–68`.

**Problema:** buscar palabras dentro de la consulta no equivale a interpretar su estructura. El código agrega un límite solo si no encuentra `limit`.

Resultados reproducidos sobre una tabla de 120 filas:

| Consulta | Resultado actual |
|---|---|
| `SELECT n FROM datos` | 50 filas. |
| `SELECT n, 'limit' AS marca FROM datos` | 120 filas. |
| `SELECT n FROM datos LIMIT 100` | 100 filas. |
| `SELECT 'update' AS evento` | Rechazo de una consulta inocua. |

Cincuenta es un límite por defecto, no un máximo efectivo. La conexión tampoco usa el modo de solo lectura de SQLite.

`timeout=5` limita la espera por bloqueos. No limita la duración total de la consulta.

**Solución propuesta:** aplicar controles separados en el motor y en la entrega del resultado.

1. Abrir la base mediante una URI SQLite con `mode=ro` y `uri=True`.
2. Aplicar una política de autorización que rechace escrituras, adjuntos y operaciones administrativas no permitidas.
3. Ejecutar una sola sentencia mediante `execute()`.
4. Recuperar como máximo 51 filas mediante `fetchmany()` para devolver 50 e indicar truncamiento.
5. Interrumpir consultas largas mediante `set_progress_handler()` y un plazo basado en `time.monotonic()`.

Construir la URI desde la ruta autorizada. Codificarla correctamente.

La política debe comprobar funciones y tablas permitidas. No habilitar extensiones que puedan producir efectos externos.

Si el contrato exige exclusivamente `SELECT`, comprobar el tipo de sentencia con un analizador compatible. Esa comprobación no reemplaza los permisos del motor.

`fetchmany()` limita la entrega, no todo el trabajo interno de SQLite. El presupuesto de ejecución sigue siendo necesario.

Cerrar siempre la conexión. El contexto transaccional de una conexión SQLite no implica necesariamente su cierre.

**Pruebas de aceptación:** las cuatro consultas anteriores, sentencia múltiple, escritura, adjunto de base y consulta costosa.

Una consulta permitida devuelve como máximo cincuenta filas. El resultado indica si existen más filas. La base conserva su contenido.

**Parche a evitar:** ampliar la lista de palabras prohibidas para cubrir cada nuevo caso.

### C10. Invalidar la caché y proteger la consistencia del índice

**Prioridad:** P1. **Evidencia:** R para la caché. E para los riesgos de persistencia.

**Dónde:** `rag.py:107–120,155–170,202–223` y `utils/embeddings.py`.

**Problema reproducido:** el disco contenía el índice nuevo, pero la búsqueda de la misma sesión devolvió el contenido anterior.

**Solución inmediata:** invalidar `_indice_cache` después de completar correctamente la escritura del índice.

No invalidarla como sustituto de una escritura consistente. El índice usa archivos separados que pueden pertenecer a versiones distintas si una escritura falla.

**Solución estable:** introducir una versión del índice y un manifiesto. Publicar la versión nueva solo cuando sus archivos estén completos.

El manifiesto debe incluir el modelo, su revisión, la dimensión vectorial, el modo de búsqueda y el número de fragmentos.

Al cargar, comprobar que los vectores corresponden a los fragmentos. El modelo de consulta debe coincidir con el modelo de indexación.

Un índice semántico vacío debe abrir sin requerir un archivo de vectores inexistente. Una consulta sin coincidencias no debe presentar resultados irrelevantes como evidencia.

Aplicar también C02: los fragmentos recuperados deben respetar los permisos actuales.

**Pruebas de aceptación:** indexar A, consultar, indexar B y consultar sin reiniciar. La segunda consulta usa B.

Agregar casos de índice vacío, cambio de modelo y escritura interrumpida. Un fallo no reemplaza el índice válido anterior por una versión incompleta.

**Parche a evitar:** pedir al usuario que reinicie el chat después de cada indexación.

### C11. Comprobar la estructura de cada registro JSON

**Prioridad:** P1. **Evidencia:** R en `stats_de`. E en el cargador.

**Dónde:** `informe.py:49–71` y `carga_trazas.py:44–66`.

Que un texto sea JSON válido no implica que tenga la estructura del registro esperado.

`[]`, `null` y `{"answers": null}` provocaron `AttributeError` en `stats_de`.

**Solución propuesta:** definir un esquema para las trazas de decisiones antes de acceder a sus campos.

Distinguir como mínimo:

- JSON ilegible.
- JSON legible con estructura incorrecta.
- Registro compatible y válido.
- Registro de otra versión o de otro tipo.

Comprobar `answers`, `fields`, `steps`, `next` y los tipos utilizados por SQLite. Definir cómo representar campos opcionales ausentes.

No transformar cualquier dato incorrecto en un diccionario vacío. Eso convierte errores de calidad en ausencias aparentemente válidas.

Compartir el lector entre el informe y el cargador. Conservar el archivo de origen, el número de línea y la causa del rechazo.

**Pruebas de aceptación:** registro válido, objeto vacío, lista, `null`, campos nulos, `steps` incorrecto y JSON roto.

Un registro incorrecto no cancela todo el lote. Los conteos distinguen cada categoría y permiten reconstruir el total.

### C12. Separar el muestreo del informe de la carga completa de datos

**Prioridad:** P1. **Evidencia:** E.

**Dónde:** `informe.py:30,39–46` y `carga_trazas.py:18–42`.

**Problema:** `collect_files()` devuelve solamente los primeros treinta archivos ordenados. El cargador de SQLite reutiliza esa función.

El límite puede tener sentido para una demostración del informe. No debe excluir datos de una carga completa sin aviso.

Además, el cargador ejecuta `DROP TABLE IF EXISTS trazas` antes de procesar los archivos. Una carga fallida puede dejar de conservar la tabla anterior.

**Solución propuesta:** separar el descubrimiento de archivos del presupuesto de análisis.

La función de descubrimiento debe informar todos los archivos elegibles. El informe puede seleccionar un subconjunto, pero debe mostrar encontrados, procesados y omitidos.

La carga debe procesar todos los archivos elegibles por defecto. Un límite opcional debe marcar la base resultante como parcial.

Antes de una recarga, comprobar la carpeta y la compatibilidad de los registros. No reemplazar automáticamente una base válida cuando la entrada está vacía.

Cargar en una tabla o base temporal. Reemplazar la versión anterior solo después de completar y comprobar la carga.

**Pruebas de aceptación:** una carpeta con 31 archivos procesa 31 durante una carga completa. Un informe limitado muestra que omitió un archivo.

Un error a mitad de la carga conserva la base válida anterior. Una carpeta inexistente no provoca una recarga vacía.

**CAUTION:** confirmar la sustitución antes de ejecutar una recarga destructiva. El cargador actual puede eliminar la tabla anterior.

Este informe no ejecuta esa operación.

### C13. Aplicar presupuestos locales y globales

**Prioridad:** P1. **Evidencia:** R / E.

**Dónde:** `research.py:21,47–50,77–125`, `nodes.py:33–35,57–59`, `supervisor.py:26,74–80` y los clientes externos.

**Problemas:** el prompt pide tres consultas, pero el código aceptó veinte. `MAX_ROUNDS = 2` permite la búsqueda inicial y dos repeticiones.

Las ocho rondas del chat cuentan lotes de herramientas. No limitan el total de llamadas que ejecutan sus flujos internos.

**Solución propuesta:** conservar límites locales y agregar un presupuesto compartido por ejecución.

Contrato propuesto para el presupuesto:

| Campo | Propósito |
|---|---|
| `max_tool_calls` | Máximo total de llamadas a herramientas. |
| `max_model_calls` | Máximo total de llamadas al modelo, incluidos reintentos. |
| `max_searches` | Máximo total de consultas al buscador. |
| `deadline` | Plazo global medido con reloj monotónico. |
| `max_output_bytes` | Máximo de datos que vuelve al contexto. |
| `max_depth` | Máxima profundidad de delegación. |

Comprobar y reservar el presupuesto antes de cada operación. Las tareas paralelas no deben superar el límite por una carrera entre contadores.

Una operación denegada no llama al servicio externo. El resultado debe indicar `budget_exhausted` y conservar el trabajo ya terminado.

Para research, elegir una semántica explícita:

- `MAX_RESEARCH_CYCLES = 2`: máximo de dos ciclos totales.
- `MAX_RESEARCH_RETRIES = 2`: ciclo inicial y hasta dos repeticiones.

Elegir una opción, no mantener ambos nombres para el mismo contador.

Los límites de tokens del proveedor, cuando existan, complementan el presupuesto. Registrar el consumo real para medir los costos.

**Pruebas de aceptación:** veinte consultas propuestas, muchos tool calls en una respuesta, flujos anidados y reintentos repetidos.

El límite global se cumple aunque ningún límite local se haya agotado.

## 6. Laya y calidad de las respuestas

### C14. Manejar fallos de inferencia y respuestas inválidas de Laya

**Prioridad:** P1. **Evidencia:** R para el error de inferencia. E para el contrato incompleto.

**Dónde:** `nodes.py:86–104` y `utils/laya.py:60–85`.

**Problema:** `disponible()` maneja errores de carga. La llamada posterior a `preguntar()` puede fallar sin seleccionar una ruta alternativa.

El código también supone una clave existente, una elección válida y una confianza numérica utilizable.

**Solución propuesta:** definir una frontera de integración que produzca siempre una decisión válida o un error controlado.

Comprobar:

- La existencia de `necesita_herramientas`.
- Una elección entre `directo` y `herramientas`.
- Una confianza numérica, finita y comprendida entre cero y uno.
- Umbrales configurados válidos y ordenados.

Si falla la carga, la inferencia o la estructura, usar `herramientas`. Registrar la causa sin ocultar el fallo técnico.

La ruta de herramientas no es una garantía de seguridad. Solo mantiene disponibles las capacidades del agente. C01 y C02 siguen siendo obligatorias.

**Pruebas de aceptación:** excepción de carga, excepción de inferencia, campo ausente, elección desconocida, confianza textual y valor no finito.

Ningún caso crea una transición inexistente ni cierra el chat.

### C15. Dar contexto suficiente al router y medir sus errores

**Prioridad:** P2. **Evidencia:** E / H.

**Dónde:** `nodes.py:86–87` y `docs/design.md`, sección sobre Laya.

**Problema:** el router solo recibe los primeros mil caracteres del último mensaje. No recibe las referencias necesarias de una conversación anterior.

Una petición como “comparalo con el segundo” puede depender del historial. El modelo no puede recuperar información que no recibe.

La documentación registra cinco casos de prueba. Esa muestra no demuestra precisión general ni una confianza calibrada.

**Solución propuesta:** definir una entrada compacta que incluya la solicitud actual y el estado relevante de la tarea.

No recortar silenciosamente una condición importante. Si el contexto necesario no cabe o no está disponible, seleccionar herramientas.

Antes de activar el router por defecto, preparar un conjunto fijo de evaluación. Incluir hechos actuales, archivos, cálculos, referencias previas y mensajes largos.

Medir por separado los falsos directos: casos que necesitan herramientas, pero reciben una respuesta directa. Definir el umbral aceptable antes de evaluar.

Ajustar el modelo solo después de comprobar la entrada, las etiquetas y el conjunto de evaluación. Comparar contra el agente sin router.

**Prueba de aceptación:** ejecutar el conjunto independiente con el checkpoint real y registrar decisiones, confianza, latencia y errores.

**Parche a evitar:** mover el umbral repetidamente para mejorar cinco ejemplos conocidos.

### C16. Aislar la configuración local de Laya

**Prioridad:** P2. **Evidencia:** E / H.

**Dónde:** `utils/laya.py:29–48`.

**Problema:** `setdefault()` agrega `HF_HUB_OFFLINE` y `TRANSFORMERS_OFFLINE` si no existen. Estas variables afectan al proceso, no solo a Laya.

Otras bibliotecas pueden leerlas antes o después de la carga. El efecto depende del orden de importación y de la configuración previa.

**Solución propuesta:** establecer la política de red una vez, al iniciar la aplicación.

Si Laya necesita una política distinta, usar un proceso separado. Configurar su entorno antes de importar sus bibliotecas.

Si la biblioteca ofrece una opción local equivalente, comprobarla con la versión instalada antes de adoptarla.

Definir también cuándo reintentar la carga. `_error` conserva el primer fallo durante toda la sesión actual.

**Prueba de aceptación:** Laya carga desde archivos locales sin cambiar la política de red de los embeddings ni de otros componentes.

Esta interacción requiere una prueba de integración real. No quedó demostrada por las pruebas simuladas.

**Parche a evitar:** restaurar variables después de importar la biblioteca y asumir que sus valores internos también cambian.

### C17. Aclarar el alcance de research y conservar la evidencia

**Prioridad:** P2. **Evidencia:** E.

**Dónde:** `utils/websearch.py:14–20` y `research.py:61–68,81–113`.

**Problema:** research usa extractos del buscador de hasta trescientos caracteres. No descarga el contenido completo de las páginas.

Después solicita hechos y una evaluación de cobertura. Esa evaluación depende de extractos y resúmenes, no de una revisión completa de las fuentes.

**Solución inicial:** describir el resultado como investigación preliminar basada en extractos. Conservar esa limitación dentro del informe generado.

**Ampliación posterior:** agregar recuperación de páginas, extracción de contenido y referencias vinculadas a fragmentos.

Cada afirmación debe conservar la dirección de su fuente y el fragmento utilizado. La síntesis debe distinguir evidencia disponible de inferencias.

Si se descargan direcciones elegidas por el modelo, aplicar límites de tamaño, plazo y redirecciones. Bloquear destinos privados, locales y servicios de metadatos.

**Pruebas de aceptación:** extracto insuficiente, página inaccesible, fuentes contradictorias y ausencia de resultados. Ningún caso produce una cobertura completa por defecto.

**Parche a evitar:** aumentar solamente la insistencia del prompt sobre completitud o veracidad.


## 7. Observabilidad, integración y pruebas

### C18. Registrar errores y controlar la integración de tracing

**Prioridad:** P1. **Evidencia:** R / E.

**Dónde:** `utils/tracing.py:14–62`.

**Problema:** el código reemplaza métodos internos de PocketFlow. El evento se escribe después de ejecutar el nodo.

Si el nodo lanza una excepción, no se registra el evento. La prueba registró el nodo exitoso, pero no el nodo fallido.

Los contenedores `Flow` tienen implementaciones propias. El parche no describe necesariamente todo el recorrido compuesto.

**Solución propuesta:** establecer un contrato de observabilidad por ejecución.

El evento debe incluir identificador de ejecución, identificador del paso, nodo, estado, duración y error, cuando corresponda.

Usar un bloque `finally` para registrar el cierre. Conservar y propagar la excepción original. Un fallo al registrar no debe sustituirla silenciosamente.

Medir las duraciones con un reloj monotónico. Mantener la hora civil solamente para ubicar eventos en el tiempo.

Crear nombres de archivo únicos. El nombre actual tiene resolución de segundos y puede colisionar entre ejecuciones.

Cerrar el destino de trazas al terminar. Evitar registrar claves, contenido sensible o argumentos completos sin una política explícita.

Para integrar PocketFlow, elegir clases instrumentadas o un adaptador mantenido y probado. Si se conserva el parche interno, fijar su compatibilidad y probar todos los tipos utilizados.

No presentar el reemplazo de métodos como incorrecto por definición. El problema actual es su cobertura incompleta y su dependencia de detalles internos.

**Pruebas de aceptación:** nodo exitoso, nodo fallido, cancelación, nodo asíncrono y flujo compuesto. Los eventos identifican el estado real y conservan la causa del fallo.

### C19. Aclarar el estado compartido del debate y evitar bloqueos

**Prioridad:** P2. **Evidencia:** E.

**Dónde:** `debate.py:28–93,129–148`.

**Problema semántico:** ambos agentes reciben el mismo `shared`. También leen y escriben `transcript`. No se comunican exclusivamente mediante colas.

**Problema de integración:** las llamadas síncronas a `call_llm()` bloquean el bucle de eventos. Que el debate sea por turnos no elimina ese bloqueo.

**Solución propuesta:** elegir y documentar un modelo de estado.

- **Estado común:** conservarlo, pero eliminar la afirmación de aislamiento por colas.
- **Estado separado:** dar un estado propio a cada agente y enviar mensajes por colas. Un coordinador conserva el historial global.

Usar `await call_llm_async()` dentro de los nodos asíncronos. Definir plazos, cancelación y terminación si un agente falla.

El cierre de una tarea debe liberar o cancelar a la otra. No depender exclusivamente de que el marcador `FIN` llegue por una cola.

**Pruebas de aceptación:** un agente falla antes de responder, otro espera en la cola y el usuario cancela. La ejecución termina sin tareas pendientes.

**Parche a evitar:** mantener una llamada bloqueante porque solo un agente genera texto a la vez.

### C20. Separar las instrucciones al modelo de los controles del programa

**Prioridad:** P1. **Evidencia:** E / H.

**Dónde:** `main.py:10–15`, `utils/call_llm.py:67–104` y los prompts de juez, research y supervisor.

DeepSeek cumple el papel de LLM en este proyecto.

El mensaje de sistema del chat es breve. Las instrucciones de los flujos viajan principalmente como mensajes con `role="user"`.

El problema no es usar prompts. El problema es tratar una instrucción textual como una garantía de ejecución.

| Necesidad | Responsabilidad del código | Responsabilidad del modelo |
|---|---|---|
| Permisos de archivos | Autorizar rutas y operaciones. | Proponer una operación pertinente. |
| Formato de respuesta | Comprobar tipos y campos. | Producir la estructura solicitada. |
| Presupuesto | Contar y detener operaciones. | Priorizar el trabajo disponible. |
| Citas | Comprobar referencias y alcance. | Evaluar el apoyo semántico de la evidencia. |
| Dependencias | Resolver entradas y resultados. | Proponer un plan compatible. |
| Veracidad | Conservar evidencia y declarar límites. | Interpretar sin presentar inferencias como datos observados. |

**Solución propuesta:** usar mensajes separados para instrucciones estables, solicitud y evidencia externa. Identificar el contenido externo como datos no confiables.

Esa separación no elimina la inyección de instrucciones. La protección depende también de permisos mínimos, aprobaciones y comprobaciones antes de ejecutar herramientas.

Las herramientas deben exponer solamente las capacidades necesarias para la tarea. Los servidores externos no heredan automáticamente la política local de archivos.

Las llamadas MCP necesitan una política por servidor y herramienta, además del presupuesto global.

**Pruebas de aceptación:** archivos y resultados web con instrucciones falsas para ignorar permisos o ejecutar acciones adicionales.

El programa conserva los límites aunque el modelo proponga una acción prohibida. Medir también el comportamiento con el modelo real.

**Parche a evitar:** resolver una falta de control agregando “nunca hagas X” al mensaje de sistema.

### C21. Crear pruebas portables que cubran las garantías reales

**Prioridad:** P1. **Evidencia:** E.

**Dónde:** `tests/test_smoke.py:8–11,28–34,47–68`.

**Problema:** algunas pruebas dependen de una ruta concreta de la computadora del autor. Otra prueba espera exactamente `15595` registros.

La prueba de SQL prohibido acepta cualquier resultado que empiece con `ERROR`. Puede pasar porque falta la base, sin probar el rechazo de la consulta.

**Solución propuesta:** construir datos y configuración dentro de cada prueba.

1. Usar `tmp_path` para archivos y bases temporales.
2. Configurar las raíces permitidas mediante `monkeypatch`.
3. Sustituir las respuestas de modelos con casos deterministas.
4. Probar las importaciones en procesos nuevos.
5. Separar pruebas unitarias, integración local y evaluación con modelos reales.

No usar el conjunto personal de trazas como requisito de las pruebas unitarias. La prueba debe crear sus filas y comprobar sus resultados exactos.

Las pruebas bajo `python -O` deben comprobar el rechazo real. No usar solamente `assert` dentro del subproceso optimizado, porque también desaparece.

Para los límites asíncronos, probar dos bucles independientes. Una sola ejecución no detecta C03.

**Pruebas de aceptación:** la suite pasa en una copia limpia, sin la base personal y sin la estructura de carpetas del autor.

Un servicio externo ausente no convierte una prueba de permisos en un falso éxito.

### C22. Corregir opciones, comandos y promesas de la documentación

**Prioridad:** P2. **Evidencia:** E.

**Dónde:** `juez.py:155–163`, `README.md`, `docs/design.md` y `docs/informes/patron-prep-exec-post.md`.

Correcciones concretas:

| Elemento | Cambio requerido |
|---|---|
| `juez --rondas` | Usar el argumento como configuración del flujo o eliminar la opción. Hoy el código no la utiliza. |
| `python3 main.py carga_trazas.py` | Documentar `python3 carga_trazas.py`, o agregar un subcomando real. |
| Comunicación exclusiva por colas | Ajustar la descripción al diseño elegido en C19. |
| Escritura siempre aprobada | Limitar la afirmación a la implementación actual hasta completar C01. |
| Trazas propias y trazas de decisiones | Documentar sus esquemas diferentes y sus lectores. |
| Cumplimiento de `prep → exec → post` | Actualizar el informe histórico. Hay lectura de archivos en `prep` y escritura de archivos en `post`. |
| Funcionamiento independiente | Probar cada entrada después de resolver C05. |
| Rendimiento y precisión de Laya | Mantener fecha, entorno, muestra y límites de cada medición. |

No hace falta trasladar mecánicamente toda operación de entrada y salida a `exec`. Primero definir sus efectos, reintentos y condiciones de idempotencia.

Los nodos parciales son válidos. El problema no es omitir un método sin trabajo, sino prometer garantías que el flujo no cumple.

## 8. Plan de implementación

### Etapa A. Proteger los archivos

**Objetivo:** impedir lecturas y escrituras fuera de la política autorizada.

**Incluye:** C01 y C02.

**Condición de cierre:** todas las rutas de acceso a archivos pasan las pruebas de permisos, enlaces y rechazo de aprobación.

Hasta completar esta etapa, evitar datos sensibles y deshabilitar las herramientas que escriben sin control.

### Etapa B. Estabilizar la ejecución

**Objetivo:** eliminar fallos independientes de la calidad del modelo.

**Incluye:** C03, C04, C05, C14 y C18.

**Condición de cierre:** conversación continua, importaciones independientes, dos informes consecutivos y trazas de errores completas.

### Etapa C. Corregir contratos y datos

**Objetivo:** impedir resultados formalmente aceptados pero funcionalmente incorrectos.

**Incluye:** C06, C07, C08, C09, C10, C11, C12 y C13.

**Condición de cierre:** las entradas inválidas no llegan a herramientas. Los resultados conservan datos, evidencia, límites y estados parciales.

### Etapa D. Medir calidad y actualizar la interfaz

**Objetivo:** ajustar las capacidades declaradas a la evidencia disponible.

**Incluye:** C15, C16, C17, C19, C20 y C22.

**Condición de cierre:** evaluación independiente de Laya, alcance explícito de research y pruebas de integración de configuración y cancelación.

### Pruebas durante todas las etapas

**Incluye:** C21.

Cada corrección debe incorporar una prueba que falle con la implementación anterior. No esperar al final para crear la suite.

No se asignan tiempos de implementación sin medir el entorno y la compatibilidad de las dependencias.

## 9. Matriz mínima de pruebas

Los nombres siguientes son propuestas para nuevas pruebas. No indican archivos existentes ni pruebas ya incorporadas al proyecto.

| Prueba propuesta | Resultado obligatorio | Correcciones |
|---|---|---|
| `test_report_rejects_outside_path` | No modifica una salida externa. | C01 |
| `test_write_rejection_preserves_content` | Conserva el archivo cuando se rechaza la escritura. | C01 |
| `test_approval_is_bound_to_content` | Un cambio de contenido exige otra aprobación. | C01 |
| `test_search_rejects_external_symlink` | No devuelve contenido externo. | C02 |
| `test_index_rejects_external_symlink` | No indexa contenido externo. | C02 |
| `test_retrieval_respects_current_roots` | No entrega fragmentos fuera de los permisos actuales. | C02, C10 |
| `test_report_runs_in_two_event_loops` | Termina dos mapas con concurrencia limitada. | C03 |
| `test_direct_answer_returns_to_question` | Recibe una segunda pregunta. | C04 |
| `test_imports_in_fresh_processes` | No depende del orden de importación. | C05 |
| `test_judge_requires_problems_for_retry` | Rechaza la estructura incompleta antes de `post`. | C06 |
| `test_research_requires_text_content` | Rechaza números como contenido final. | C06 |
| `test_plan_limits_survive_optimized_python` | Rechaza seis pasos también con `-O`. | C06, C13 |
| `test_invalid_reference_blocks_approval` | Un `verdict: ok` no elude una referencia inválida. | C07 |
| `test_refinement_receives_previous_draft` | Incluye el borrador exacto y los problemas. | C07 |
| `test_supervisor_receives_report_data` | La síntesis recibe los hallazgos, no solo una ruta. | C08 |
| `test_failed_dependency_blocks_step` | No ejecuta un paso con entradas ausentes. | C08 |
| `test_sql_result_cap_is_effective` | Devuelve como máximo cincuenta filas. | C09 |
| `test_sql_literal_is_not_keyword` | No rechaza una cadena inocua como operación SQL. | C09 |
| `test_sql_deadline_interrupts_query` | Interrumpe una consulta que supera el plazo. | C09 |
| `test_reindex_refreshes_search` | Usa el índice nuevo sin reiniciar. | C10 |
| `test_interrupted_index_keeps_previous_version` | Conserva el índice válido anterior. | C10 |
| `test_invalid_record_shape_is_counted` | Registra la estructura inválida sin cancelar el lote. | C11 |
| `test_loader_processes_more_than_thirty_files` | La carga completa no hereda el muestreo. | C12 |
| `test_failed_reload_preserves_database` | Conserva la base anterior si falla la carga. | C12 |
| `test_research_cycle_budget` | Respeta la semántica elegida para el contador. | C13 |
| `test_global_budget_covers_nested_calls` | Cuenta herramientas, modelos y reintentos internos. | C13 |
| `test_laya_inference_failure_uses_tools` | Conserva una ruta válida ante fallos. | C14 |
| `test_router_receives_task_context` | Incluye el contexto necesario de la tarea. | C15 |
| `test_laya_network_policy_is_isolated` | No cambia la configuración de otros componentes. | C16 |
| `test_research_reports_insufficient_evidence` | No afirma cobertura completa con material insuficiente. | C17 |
| `test_failed_node_is_traced` | Registra y propaga el error original. | C18 |
| `test_debate_cancels_peer_on_failure` | No deja una tarea esperando en la cola. | C19 |
| `test_untrusted_text_cannot_authorize_tools` | Una instrucción externa no cambia los permisos. | C20 |
| `test_cli_rounds_affects_execution` | La opción cambia el límite o deja de existir. | C22 |

## 10. Ejemplos de pruebas de regresión

Estos ejemplos prueban comportamientos concretos sin llamar al modelo. Requieren las dependencias locales necesarias para importar el proyecto.

Son propuestas para integrar en la suite. No se ejecutaron como archivos de prueba completos durante la generación de este informe.

### Ruta directa del chat

```python
from types import SimpleNamespace


def test_direct_answer_returns_to_question(monkeypatch):
    import nodes
    from flow import create_agent_flow

    monkeypatch.setenv("USE_LAYA_ROUTER", "1")
    questions = iter(["Hola", "salir"])
    received = []

    def fake_input(prompt=""):
        text = next(questions)
        received.append(text)
        return text

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(
        nodes.LayaRouter,
        "exec",
        lambda self, state: ("directo", 0.95),
    )
    monkeypatch.setattr(
        nodes,
        "call_llm_agent",
        lambda messages, tools=None: SimpleNamespace(
            content="Hola.",
            tool_calls=None,
        ),
    )

    create_agent_flow().run({"messages": [], "tool_rounds": 0})

    assert received == ["Hola", "salir"]
```

### Importación independiente

El comando debe ejecutarse desde la raíz del proyecto, después de instalar sus dependencias.

```python
import subprocess
import sys
from pathlib import Path


def test_supervisor_imports_independently():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", "import supervisor"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
```

### Referencias fuera de los directorios permitidos

```python
import pytest


def test_search_rejects_external_symlink(tmp_path, monkeypatch):
    from utils.fs_tools import search_files

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("EXTERNAL_MARKER_123", encoding="utf-8")
    link = allowed / "link.txt"

    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("El entorno no permite enlaces simbólicos.")

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(allowed))
    result = search_files(query="EXTERNAL_MARKER_123", path=str(allowed))

    assert "L1: EXTERNAL_MARKER_123" not in result
```

La prueba no debe fallar solamente porque el resumen repite la consulta. Por eso comprueba la línea de contenido, no cualquier aparición del marcador.

## 11. Criterios para aceptar cada corrección

Una corrección queda completa cuando cumple estos puntos:

1. Reproduce el defecto con una prueba que falla antes del cambio.
2. Corrige la causa mediante un contrato o una regla explícita.
3. Supera la prueba y los casos límite relacionados.
4. Conserva los permisos y los presupuestos de la ejecución.
5. Actualiza la documentación y los resultados que recibe el usuario.

Un prompt puede orientar al modelo. No reemplaza una autorización, un límite, un dato ausente ni una prueba de aceptación.

## 12. Control editorial y límites del documento

El linter oficial de `asd-ste100` no está disponible en este entorno. No se informa una puntuación STE automática ni una certificación.

Este documento usa español claro y adapta las reglas de forma, no el diccionario normativo inglés.

Se aplicó una revisión manual y un control auxiliar de estructura. Los ejemplos Python y JSON superaron una comprobación sintáctica.

Esa comprobación no ejecuta los ejemplos ni demuestra la corrección técnica de las soluciones.

Las soluciones requieren implementación y pruebas en el entorno objetivo. El proyecto original permanece sin cambios.
