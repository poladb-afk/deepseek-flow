# H3-B — ¿el explorador paga cuando el contexto pesa? (pre-registro)

Fijado el 2026-10-26, ANTES de correr nada. El script
(`banco/probes/h3b_swarm.py`) no lo retoca.

## Pregunta

En H2 PR 2 el explorador corrió 0 veces en `bench_supervisor` (tareas de un
solo objetivo; con el saldo compartido delegar no ahorra rondas). Su ventaja
es el contexto FRESCO: tiene que aparecer donde el contexto pesa. Las
auditorías amplias de fable (s17–s20: 20 módulos, código real) lo cargan.

## Brazos

- **chat**: el chat de siempre (`bench_fable`, brazo A: sin prosa ni skills),
  `MAX_TOOL_ROUNDS=8`, con el turno "salir" para leer `[tokens] sesión`.
- **supervisor+explorar**: `supervisor.supervisar` con `EXPLORAR=1`
  (`MAX_PASOS=5`, saldo único para el árbol). Mismo fixture, misma tarea,
  mismo scope HITL que el chat (escrituras solo dentro de la copia, mismos
  prefijos de comando) por `HITL_SCOPE`.

Asimetría declarada: el chat tiene 8 rondas y el supervisor 5 compartidas
con sus exploraciones. Es la configuración de producción de cada uno.

## Medidas

- calidad: `correct_action` de `bench_fable.puntuar` (0–2) por corrida;
- costo: tokens totales (prompt + completion) por corrida;
- adopción: llamadas a `explorar` por corrida (sección "Pasos" del informe).

## Criterio

El brazo supervisor+explorar **gana** si se cumplen las tres:

1. **adopción**: `explorar` corrió al menos una vez en CADA escenario (sumando
   seeds). Si en un escenario corrió 0 veces, ese escenario no midió nada.
2. **calidad**: la calidad media es MAYOR que la del chat.
3. **calidad por token**: calidad media / tokens medios es MAYOR que la del
   chat ("la calidad sube más que el costo").

## Decisión atada al resultado

- Gana → el explorador se queda y se evalúa ofrecerlo en el chat.
- No gana (cualquiera de las tres) → el explorador se borra: `explorador.py`,
  la tool `explorar`, el setting `EXPLORAR` y sus tests. El kernel se queda
  (lo usa el supervisor).
