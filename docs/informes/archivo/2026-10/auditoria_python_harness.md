# Auditoría Python de deepseek-flow — ZIP 10-15

## Dictamen
La arquitectura PocketFlow + decisiones locales Laya es razonable. Los riesgos principales están en las fronteras: autorización de comandos, cancelación, validación, memoria y fidelidad de las métricas. No hace falta migrar de framework para corregirlos.

## Alcance y límites
- ZIP completo inventariado: 194 archivos; 74 Python; 17.219 líneas Python (11.170 fuera de tests).
- AST de todos los Python: sin errores de sintaxis.
- Se consultaron resultados web de PocketFlow y Laya. NO se descargaron ni se leyeron íntegramente los dos repositorios GitHub. No se atribuye al GitHub completo lo observado en distribuciones PyPI.
- Se contrastó la implementación publicada de PocketFlow 0.0.3 y los contratos de Laya 0.3.20.
- 28 reproducciones aisladas completadas; 0 inconclusas. NO es una ejecución de la suite pytest completa del proyecto.
- Sin inferencia Laya, sin API DeepSeek, sin modelos descargados. Shell y conexiones bloqueados. Las pruebas de escritura y enlaces usan un filesystem simulado en RAM.
- Ruff por stdin con primeras partes declaradas: 4 incidencias. Los 25 I001 de la inspección previa dependen de clasificar imports sin árbol físico; no son evidencia de bugs funcionales.

## Prioridad
P0: desactivar HITL_AUTO y corregir la clasificación shell antes de confiar acciones autónomas al harness.
P1: control efectivo de despacho/cancelación; contención de memoria y evals; prefiltro; trazabilidad y bench; fallback de supervisor; límites de SQL y conservación de tarea activa.
P2: contratos, claridad operativa, reutilización de flows y mantenimiento.

## Hallazgos reproducidos

### A01 · P0 · HITL auto acepta comandos que escriben o ejecutan código

**Código:** `utils/policy.py:51-71,115-183; modules/coding.py:162-207`

**Evidencia:**
```json
{
  "clasificaciones": {
    "find . -delete": "auto",
    "sort -o audit_marker.txt entrada.txt": "auto",
    "echo hola\ntouch audit_marker.txt": "auto",
    "echo hola & touch audit_marker.txt": "auto",
    "pytest -p plugin_local": "auto"
  },
  "subproceso_simulado": [
    {
      "shell": true,
      "command": "echo hola\ntouch audit_marker.txt"
    }
  ],
  "resultado": "exit 0\n(sin salida)",
  "comandos_reales_ejecutados": 0
}
```

**Corrección:** Desactivar AUTO por defecto; usar argv sin shell y validar opciones por herramienta. pytest requiere confianza explícita o aislamiento.

### A02 · P1 · Un stream cancelado conserva tool calls ejecutables

**Código:** `utils/call_llm.py:171-229; nodes.py:335-338`

**Evidencia:**
```json
{
  "interrupcion": "KeyboardInterrupt",
  "accion_posterior": "tool",
  "tool_conservada": "write_file",
  "archivos_escritos": 0
}
```

**Corrección:** Transportar estado de finalización; al cancelar o fallar descartar llamadas pendientes y no despacharlas. Cerrar siempre el stream con finally.

### A03 · P1 · El presupuesto retira esquemas pero no bloquea tool calls nativas

**Código:** `nodes.py:279-338,348-365; flow.py:23-30`

**Evidencia:**
```json
{
  "presupuesto_agotado": true,
  "tools_ofrecidas": null,
  "respuesta_simulada": "tool_call nativa",
  "accion": "tool",
  "alcance": "Prueba de defensa de frontera; no demuestra que DeepSeek emita esta respuesta en producción."
}
```

**Corrección:** Comprobar presupuesto y capacidades en la frontera de despacho, no solo al construir la petición al modelo; rechazar llamadas si tools=None.

### A04 · P1 · El log aplicada se escribe antes del veto del segundo voto

**Código:** `nodes.py:506-535`

**Evidencia:**
```json
{
  "aplicada_en_log": "directo",
  "accion_real": "herramientas",
  "argumento_recibido_por_voto": {
    "pregunta": "hola"
  }
}
```

**Corrección:** Registrar la ruta FINAL después del voto, incluyendo causa y resultado del veto; conservar por separado la propuesta.

### A05 · P2 · El voto recibe un dict y vuelve a envolverlo como pregunta textual

**Código:** `nodes.py:429-465,528`

**Evidencia:**
```json
{
  "esperado": {
    "pregunta": "hola"
  },
  "enviado_al_checkpoint": {
    "pregunta": "{'pregunta': 'hola'}"
  },
  "efecto_en_precision": "No medido; incompatibilidad de entrada demostrada."
}
```

**Corrección:** Pasar prep_res["pregunta"] al voto, o compartir una función de construcción del estado sin doble serialización.

### A06 · P1 · Sin Laya el prefiltro recorta y memoria anuncia que filtró con Laya

**Código:** `utils/contexto.py:65-81; modules/memoria.py:100-120`

**Evidencia:**
```json
{
  "entrada": 12,
  "salida_sin_modelo": 8,
  "memoria_marca_prefiltro_activo": true
}
```

**Corrección:** Ante ausencia/fallo devolver todas las unidades. Separar un límite determinista independiente del filtro aprendido.

### A07 · P1 · El prefiltro de memoria puntúa rutas, no contenido de notas

**Código:** `modules/memoria.py:42-46,115; utils/contexto.py:95-105`

**Evidencia:**
```json
{
  "estado_enviado": {
    "consulta": "decisión de arquitectura",
    "bloque": "/mnt/data/nota.md"
  },
  "contenido_de_la_nota_enviado": false
}
```

**Corrección:** Construir candidatos con id/ruta y contenido acotado; pasar el contenido al modelo y recuperar objetos originales por id.

### A08 · P1 · El lector de memoria sigue symlinks fuera de su raíz

**Código:** `modules/memoria.py:42-46,70-78`

**Evidencia:**
```json
{
  "read_file_bloquea": true,
  "memory_search_revela_marcador_externo": true,
  "filesystem": "simulado en RAM; ningún archivo privado real leído"
}
```

**Corrección:** Aplicar contención y política de enlaces también a memoria, tanto al enumerar como al abrir cada nota.

### A09 · P1 · La tool evals acepta salida fuera de AGENT_ALLOWED_DIRS

**Código:** `modules/evals.py:22-31; evals.py:572-576`

**Evidencia:**
```json
{
  "escritura_externa_a_raices": true,
  "resultado": "Informe de evals generado: /mnt/data/outside/evals_2026-10-15.md (bench del router + linter de trazas + costo por sesión).",
  "filesystem": "simulado en RAM"
}
```

**Corrección:** Validar salida antes de ejecutar el bench y escribir mediante escribir_salida o un directorio de artefactos autorizado.

### A10 · P1 · El bench del router no aplica la política actual de producción

**Código:** `evals.py:63-67,103-145; utils/laya_routing.py:113-146; nodes.py:495-535`

**Evidencia:**
```json
{
  "bench": "directo",
  "produccion_shadow": "herramientas",
  "otras_diferencias_estaticas": [
    "no segundo voto",
    "no q conformal",
    "entrada del bench sin truncamiento de 1000 caracteres"
  ]
}
```

**Corrección:** Reutilizar el mismo evaluador de política y la misma construcción de estado; medir voto, shadow/off y conformal por separado.

### A11 · P1 · Evals degradado falla si ya existe un baseline válido

**Código:** `evals.py:160-182,564-565`

**Evidencia:**
```json
{
  "error": "unsupported operand type(s) for -: 'NoneType' and 'float'",
  "condicion": "sin modelo/test + baseline previo con score numérico"
}
```

**Corrección:** No restar métricas None; retornar estado no evaluable conservando el baseline cuando no hubo bench.

### A12 · P1 · Fallo de inferencia Laya aborta el supervisor en vez de usar fallback

**Código:** `supervisor.py:182-206; utils/laya.py:103-112`

**Evidencia:**
```json
{
  "inferencias": 2,
  "fallback_llamadas": 0,
  "error": "inferencia simulada falló"
}
```

**Corrección:** Capturar fallos de inferencia/contrato en la frontera local del supervisor y continuar por elegir_con_deepseek; no confundir carga disponible con inferencia fiable.

### A13 · P1 · NaN en el umbral acepta directo por comparación no válida

**Código:** `utils/laya_routing.py:65-68,139-141; utils/call_llm.py:66-72`

**Evidencia:**
```json
{
  "umbral": "NaN",
  "p_directo": 0.51,
  "propuesta": "directo",
  "causa": "p(directo)=0.510 >= umbral nan",
  "nota": "El segundo voto aún podría vetar; se demuestra bypass de la primera compuerta."
}
```

**Corrección:** Validar math.isfinite y rango del umbral; configuración inválida debe fallar al iniciar o abstenerse.

### A14 · P1 · LIMIT SQL no es un tope real y fetchall puede cargar todo

**Código:** `modules/db.py:16-24,90-114`

**Evidencia:**
```json
{
  "MAX_FILAS_declarado": 50,
  "filas_devueltas": {
    "SELECT x FROM t LIMIT -1": 200,
    "SELECT x FROM t -- limit": 200
  },
  "base": "SQLite :memory:"
}
```

**Corrección:** Conectar mode=ro, usar fetchmany(MAX_FILAS+1), truncar celdas y aplicar deadline/progress_handler independiente del busy timeout.

### A15 · P2 · El esquema declara memory_search sin argumentos pero Python exige query

**Código:** `modules/memoria.py:49,181-186`

**Evidencia:**
```json
{
  "tools": 28,
  "incompatibilidades": [
    {
      "tool": "memory_search",
      "Python_requiere_pero_esquema_no": [
        "query"
      ]
    }
  ],
  "resultado": "ERROR: TypeError: memory_search() missing 1 required positional argument: 'query'"
}
```

**Corrección:** Definir memory_search(query="") y añadir prueba automática de compatibilidad esquema/firma para todos los módulos.

### A16 · P2 · ExecuteTools registra exit no cero y rechazo como éxito

**Código:** `nodes.py:362-364; modules/coding.py:183-195,214`

**Evidencia:**
```json
[
  {
    "content": "exit 1\nprueba fallida",
    "ok": true
  },
  {
    "content": "RECHAZADO por el usuario",
    "ok": true
  }
]
```

**Corrección:** Retornar ToolResult estructurado con status/error/exit_code; no inferir éxito por prefijo de texto.

### A17 · P1 · La compacción puede borrar la tarea activa sin guardar un resumen

**Código:** `utils/compaccion.py:146-157,165-201; nodes.py:258-274`

**Evidencia:**
```json
{
  "mensajes_antes": 22,
  "despues": 14,
  "objetivo_activo_conservado": false,
  "texto_insertado": "[compacción] 9 mensajes anteriores (zona fría) fueron compactados para no reenviar todo el historial. El detalle de esas vueltas ya no está en este contexto; los hechos durables están en memoria/ si hicieran falta (usá memory_search para recuperarlos). Continuá desde la ventana caliente de abajo."
}
```

**Corrección:** Preservar la petición activa y el estado de trabajo; guardar un resumen real o snapshot antes de eliminar. No afirmar que los hechos están en memoria si no se persistieron.

### A18 · P2 · Effective N no tolera JSON válido de forma inválida

**Código:** `effective_n.py:88-111; informe.py:leer_registro`

**Evidencia:**
```json
{
  "[]": "AttributeError",
  "null": "AttributeError",
  "{\"fields\": null, \"answers\": {}}": "AttributeError"
}
```

**Corrección:** Reutilizar leer_registro y distinguir JSON inválido de estructura inválida en los conteos.

### A19 · P2 · Reutilizar un flow Effective N conserva los params de la primera ejecución

**Código:** `effective_n.py:277-304`

**Evidencia:**
```json
{
  "carpetas_solicitadas": [
    "primera",
    "segunda"
  ],
  "carpetas_procesadas": [
    "primera",
    "primera"
  ],
  "alcance": "API de reutilización del mismo objeto; wrappers actuales suelen crear un flow nuevo."
}
```

**Corrección:** Eliminar monkeypatch de instancia/cierre; implementar Flow.prep o un subflujo que reciba parámetros explícitos por ejecución.

### A20 · P1 · Un pre-hook de seguridad que lanza se ignora y la tool ejecuta

**Código:** `utils/fs_tools.py:391-405`

**Evidencia:**
```json
{
  "hook": "RuntimeError",
  "implementacion_ejecutada": true,
  "efecto": "dummy sin efectos externos",
  "nota": "Diseño fail-open demostrado; no implica que el denylist actual lance normalmente."
}
```

**Corrección:** Distinguir hooks de seguridad obligatorios de observabilidad best-effort; fallo del control obligatorio debe vetar.

### A21 · P2 · Cancelación HITL web deja el pedido pendiente sin limpiar

**Código:** `utils/hitl_web.py:200-228`

**Evidencia:**
```json
{
  "KeyboardInterrupt_propagado": true,
  "pedido_pendiente_tras_interrupcion": true,
  "servidor_real_iniciado": false
}
```

**Corrección:** Limpiar _pendiente en finally y manejar cancelación como rechazo o propagarla después de limpiar.

### A22 · P2 · Las duraciones anidadas se suman como si fueran tiempo total

**Código:** `evals.py:415-426; nodes.py:357-364; utils/tracing.py:55-94`

**Evidencia:**
```json
{
  "ejemplo": "Una tool de 10 s incluida en ExecuteTools de 10 s",
  "total_reportado": 20.0,
  "tiempo_transcurrido_del_ejemplo": 10
}
```

**Corrección:** Separar wall time, tiempo inclusivo/exclusivo por span y uso real del proveedor; no llamar coste económico a segundos acumulados.

### A23 · P2 · Un tamaño de batch Laya sin límite pasa todos los estados al forward

**Código:** `utils/laya.py:126-134; utils/contexto.py:95-101; laya/agent.py:711-731 (paquete)`

**Evidencia:**
```json
{
  "llamada_simulada": {
    "n": 1000,
    "kwargs": {
      "lang": "es"
    }
  },
  "nota": "No se midió OOM; se comprueba ausencia del límite que ofrece la dependencia."
}
```

**Corrección:** Exponer batch_size y límites de candidatos/tokens; medir pico de memoria, no solo número de checkpoints retenidos.

### A24 · P2 · El tope de checkpoints se aplica después de cargar uno adicional

**Código:** `utils/laya.py:37-78`

**Evidencia:**
```json
{
  "carga_tercer_modelo": {
    "nuevo": "audit_c",
    "ya_retenidos": 2
  },
  "retenidos_al_final": 2,
  "pico_bytes": "No medido; la política permite solapar 3 cargas/objetos con tope de caché 2."
}
```

**Corrección:** Gestionar presupuesto de carga antes del nuevo modelo o aislar en proceso; gc.collect no garantiza devolución de RSS/VRAM al SO.

### A25 · P2 · El log de preguntas guarda texto por defecto aunque el log de routing sea opt-in

**Código:** `nodes.py:20-42,213; .env.example:32-37,111-114`

**Evidencia:**
```json
{
  "PREGUNTAS_LOG_no_definido": "se guarda texto",
  "LAYA_LOG_PREGUNTA_default": 0,
  "filesystem": "RAM; no datos del usuario"
}
```

**Corrección:** Unificar configuración de privacidad, documentar cada sink, minimizar/redactar datos y definir retención y permisos.

### A26 · P1 · Guardado del resumen de sesión sigue un symlink colgante

**Código:** `modules/memoria.py:145-165`

**Evidencia:**
```json
{
  "destino_externo_creado_via_symlink_colgante": true,
  "condicion": "enlace preexistente dentro de memoria",
  "filesystem": "simulado en RAM"
}
```

**Corrección:** Usar creación exclusiva y contención del destino resuelto también en guardar_resumen_sesion; compartir escritor seguro con memory_save.

### A27 · P2 · El dispatcher no contiene tool calls con envoltura incompleta

**Código:** `utils/fs_tools.py:379-415; nodes.py:356-362`

**Evidencia:**
```json
{
  "entradas_incompletas": 3,
  "excepciones_escapan": [
    "KeyError: 'function'",
    "KeyError: 'name'",
    "KeyError: 'id'"
  ]
}
```

**Corrección:** Validar envelope, id, function y argumentos antes de hooks; producir resultado de error o cancelar lote de forma explícita.

### A28 · P2 · El bench del juez excluye de cita_ok casos que lanzan excepciones

**Código:** `bench_juez.py:183-198,218-225`

**Evidencia:**
```json
{
  "casos_que_exigen_cita": 2,
  "casos_con_respuesta": 1,
  "denominador_cita_ok": 1,
  "cita_ok_reportado": 1.0,
  "respuesta_ok_reportado": 0.5
}
```

**Corrección:** Contar fallo de cita cuando el caso exigía cita y no produjo respuesta; distinguir no aplicable de no evaluable y de fallo.

## Observaciones estáticas adicionales

- `_client()` y `call_llm_async()` crean clientes por llamada sin cierre explícito ni deadline/retry propios del harness. Los reintentos del nodo pueden multiplicar los del SDK. Los presupuestos de rondas no limitan llamadas internas, bytes, tiempo total ni número de tools por respuesta.
- `run_command` usa capture_output antes del recorte y timeout sobre shell; el recorte no limita la memoria capturada y no hay terminación explícita del grupo de procesos descendientes. No se ejecutó una prueba destructiva/de procesos huérfanos.
- `read_file` lee y divide el archivo entero antes de paginar. El límite es de salida, no de lectura ni memoria.
- `utils/laya.py` modifica HF_HUB_OFFLINE y TRANSFORMERS_OFFLINE globales; `_errores` conserva los fallos de carga sin reintento/reset; un único RLock serializa todos los checkpoints. Son decisiones operativas que deben explicitarse y medirse.
- `ver_pdf` rasteriza todas las páginas antes de comprobar PDF_PAGINAS_MAX y no impone BODY_MAX_BYTES al conjunto de imágenes del PDF. Falta limitar el trabajo antes de convertir.
- El registro automático de módulos no comprueba duplicados ni esquema/firma y un import fallido puede impedir arrancar capacidades independientes. `requests` se importa directamente pero no figura como dependencia directa; `ruff` lo necesita calidad.sh pero tampoco está declarado.
- En el servidor MCP se registran implementaciones directas, no el dispatcher con hooks; si el operador expone run_command, no hereda automáticamente HOOKS_PRE. Los clientes MCP/A2A no aplican una política propia de aprobación de efectos remotos.
- El parser YAML y el supervisor aún usan assert para entrada externa: desaparecen con python -O. Validar mediante excepciones explícitas y normalización de tipos.
- Hay configuración y datos no portables: TEST_ROUTER es una ruta de otra máquina; el ZIP no incluye checkpoints ni todos los corpus de evaluación. El script de modelos no configura paths si .env ya existe y solo anuncia dos checkpoints.
- Los resultados numéricos históricos de precisión, latencia y RSS no fueron replicados. La calibración incluida usa etiquetas de árbitro y una distribución de banco; no demuestra por sí sola precisión en conversación real.

## Qué conservar
- Política de routing separada del modelo; probabilidades validadas y modo sombra.
- Grafo principal con retorno explícito de la ruta directa; no repetir como vigente el antiguo bug de arista.
- Dispatcher de supervisor pasando por run_tool_call: el bypass histórico en ese punto ya fue corregido.
- Helper escribir_salida aplicado en varios pipelines; extenderlo donde falta en vez de reemplazar toda la arquitectura.
- Transacción de recarga de SQLite, invalidación de caché RAG y guardas de citas presentes en el código actual.
- Compromiso con tests de regresión y contratos de prompts; complementarlos con pruebas negativas y de combinación, no solo con el comportamiento actual.

## Plan de trabajo
1. Corregir autorización/dispatch/cancelación y fugas de contención. Añadir regresiones que exijan el comportamiento seguro, no que celebren la reproducción del bug.
2. Corregir contrato del voto, fallback del prefiltro y contenido de memoria; validar configuración al iniciar.
3. Compartir política entre producción y bench; registrar decisión final, status de tool y métricas separadas.
4. Acotar recursos antes de leer/capturar/rasterizar; gestionar clientes y procesos con ciclo de vida explícito.
5. Ejecutar la suite original en un checkout real y entorno fijado; después una prueba integrada con checkpoints y servicios reales, midiendo falsos directos, latencia y uso.

## Artefactos
El script reproducir_auditoria.py recrea las reproducciones sobre el ZIP intacto; auditoria_resultados.json conserva evidencia y límites; el inventario y lint se entregan aparte. Las pruebas demuestran defectos actuales: no son parches ni tests de aceptación del comportamiento deseado.