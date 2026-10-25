# Spec de ejecución — exp/100: `delegar` en el ciclo de vida del chat

**Estado:** aprobada 2026-10-25 (operador: "mi uso principal es por chat. Si
algo no se activa cuando quiero iniciar el chat, durante el chat, o al cerrar
el chat, entonces no creo que lo use"). Es la señal de uso que exp/97 pedía
para el conductor — llegó antes del uso, de la boca del operador.

## Pregunta

¿El conductor de exp/99 puede vivir donde vive el operador — el chat — sin
violar la regla de que el que aprueba está fuera del alcance del modelo?

## Diseño (pre-registrado)

El conductor SIGUE siendo un proceso aparte (el que aprueba los HITL de la
tarea no puede ser el chat que los pide). Lo que cambia es la puerta: los
tres momentos del ciclo de vida del chat.

1. **Durante el chat — tool `delegar_tarea`** (`modules/delegar.py`, nueva
   tool #31): recibe el pedido (y scope opcional: `permitir`,
   `permitir_comandos` como strings separados por coma, `timeout_min`,
   `shadow`) y pide **UNA aprobación del operador** con `pedir_aprobacion`
   (exp/98: el rechazo `n <motivo>` vuelve al modelo). El prompt de
   aprobación muestra el pedido COMPLETO y el scope propuesto: el operador
   es el veto del scope que el modelo sugirió. Aprobada → lanza el conductor
   con `subprocess.Popen` **detached** (`start_new_session=True`, stdio a
   DEVNULL): la tarea sigue aunque el chat se cierre. Rechazada → no lanza
   nada y devuelve el motivo.
2. **Al arrancar el chat** (`main.py`, junto al catálogo de memoria):
   `panorama_delegadas()` — las últimas 3 corridas del conductor con su
   estado (`ok` / `timeout` / `muerto-sin-resume` / `en curso` / `murió sin
   resumen`), best-effort, nunca rompe el arranque.
3. **Al cerrar el chat** (`main.py`, en el `finally`): si hay delegadas
   ACTIVAS (pid del conductor vivo y sin `resumen.md`), un aviso de que
   siguen corriendo en background y dónde queda el resultado.

Soporte en `delegar.py`: el conductor escribe `conductor.pid` al arrancar
(estado consultable sin adivinar) y expone `panorama_delegadas()` /
`corridas_activas()` como funciones puras-de-disco. El e2e de exp/99 no
cambia (mismo CLI, mismos artefactos).

**Seguridad (declarada):** la tool NO contesta los HITL de la tarea — los
contesta el conductor (proceso aparte) con el scope que el OPERADOR aprobó
en el lanzamiento. La denylist dura corre siempre. El scope que el modelo
propone viaja visible en el prompt de aprobación; sin `permitir`, el
conductor queda en denylist-solamente (su default). `shadow="1"` fuerza
`LAYA_MODO=shadow` en el conductor (la receta de pares de la flywheel,
exp/43).

## Criterios (pre-registrados, ANTES de correr)

- **C1 (tests sin LLM):** la tool está en el action space; el rechazo de la
  aprobación NO lanza proceso y devuelve el motivo (exp/98); la aprobación
  lanza `Popen` detached con el argv completo (`main.py delegar pedido
  --permitir …`) y stdio en DEVNULL; el prompt de aprobación contiene el
  pedido y el scope; `panorama_delegadas` distingue ok / en curso (pid
  vivo) / murió sin resumen, con tope 3 y best-effort; el aviso de cierre
  solo sale con delegadas activas.
- **C2 (gate):** `./calidad.sh` verde completo (README 31 tools, smoke,
  inventario).
- **C3 (e2e real, LLM, n=1 declarado):** en el chat real (PTY sin BANCO):
  pedirle al chat que delegue una tarea chica → el chat llama la tool → el
  operador aprueba → la tool responde; CERRAR el chat (`salir`) → el
  conductor SOBREVIVE y completa la tarea; un arranque posterior del chat
  reporta la corrida con su estado.
- **C4 (docs):** README (contador + fila de capacidades), design.md
  (sección conductor: los tres momentos), bitácora exp/100, estado.md.

## Fuera de alcance (declarado)

- Cola/varias delegaciones simultáneas gestionadas (se puede lanzar más de
  una; el panorama muestra las 3 últimas); notificación push al terminar
  (el reporte es del próximo arranque); el conductor no gana HITL web; los
  sub-agentes dentro del chat (exp/97) siguen apagados — esto es lanzar el
  conductor, no anidarlo.
