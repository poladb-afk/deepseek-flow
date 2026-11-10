# S0-CITAS-EJECUCION — corrección acotada del snapshot X191

## Intención y alcance

Solicitud: corregir dos comportamientos de S0 sobre el árbol de X191: el fallback
de citas no delimitaba la búsqueda a fuentes autorizadas y pytest recibía permiso
automático. Este cambio no importa entregas documentales externas ni instala una
constitución paralela: el contrato de la casa es `AGENTS.md` (S0, R7) y la
medición es el gate de este repo.

1. Las búsquedas abreviadas de citas solo recorren bases autorizadas. El candidato
   se resuelve y autoriza antes de comprobarlo como archivo o abrir su contenido.
   Un candidato externo no participa en unicidad ni cambia el resultado visible
   de una cita abreviada por existir o no existir.
2. Pytest deja de estar en auto, incluyendo su invocación python3 -m pytest. Las
   entradas explicativas quedan sin nivel explícito: utilizan el default preguntar.
   Esto revierte A45 explícitamente. Un scope existente que autorice el comando
   puede aprobarlo; sin permiso o ante rechazo no debe llegar al ejecutor.

## Diseño

Se reutilizan _resolve y el dispatcher/aprobador actuales. No se agrega un sistema
de permisos, un helper de producción, dependencia, prompt, setting o nuevo motor.
El fallback conserva el conjunto de carpetas fuente de X175 y no recorre artefactos.
Los enlaces de archivos se aceptan solo si el destino real está permitido; los
recorridos no siguen enlaces de directorio internos (Path.rglob de Python 3.12).

La lista blanca de opciones de pytest sigue siendo necesaria para scopes sin
humano. Se conserva su contrato; retirar auto no vuelve universal su autorización.
Los tests sobre la política anterior cambian por el contrato más estricto, no para
ocultar errores. Se preservan comandos y funciones. Las fotos históricas JSONL
quedan intactas; un delta explícito registra diferencias autorizadas de nivel y explicación (incluidas explicaciones sin cambio de nivel).

## Criterios previos de verificación

- Rojo/verde: cita abreviada externa, alias externo y existencia presente/ausente.
- Conservar lecturas autorizadas, unicidad y ambigüedad; no recorrer bases externas.
- Pytest directo, vía intérprete, con envoltorios y compuestos nunca se clasifica auto.
- Rechazar impide ejecución; aprobar habilita una prueba sintética controlada.
- Los comandos irreversibles mantienen doble confirmación y el resto no cambia
  de nivel en el corpus disponible. Verificar cada delta sin descartar filas.
- Preservar tests existentes y registrar todo cambio de expectativa.
- Sintaxis, diff aplicable y limpieza de sondas.
- La suite completa y `calidad.sh` se corren en este árbol; esta spec no los
  sustituye ni certifica tipos o cobertura por su cuenta.

## Límites y consecuencia

Este patch no implementa plan versionado, aislamiento del sistema operativo,
automodificación segura, skills sin regex ni cancelación distribuida. Tampoco
resuelve carreras del filesystem entre validar y abrir (TOCTOU), hardlinks o todos
los demás comandos auto. El scope autoriza ejecución, no limita por sí mismo los
efectos internos de pytest. Se esperan más pedidos de aprobación que antes.

Si una prueba falla, se informa; no se cambia un baseline, umbral o requisito para
obtener verde. Si el ratchet de líneas rechaza código necesario para S0, se presenta
el conflicto al operador sin usar su clave ni retocar baselines automáticamente.
