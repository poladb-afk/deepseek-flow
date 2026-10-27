# F — sacar del prompt lo que la estructura reemplazó (pre-registro)

Fijado el 2026-10-27, ANTES de correr. El criterio vive en
`banco/probes/f_prompt.py::veredicto` y no se retoca.

## Primero: dónde decide cada pieza (lección X82)

Una directiva del prompt solo puede cambiar algo en las tareas donde aplica.
Medirla en otras es medir nada. Para cada candidata, la pieza que la
reemplazaría y la ventana donde las dos deciden:

| Directiva | Estructura que la reemplazaría | Dónde decide |
|---|---|---|
| CITAS: verificar archivo:línea y citar ruta relativa sin "~X" | `VerificarCitas` (X67): comprueba contra el disco y re-pregunta si no coincide | respuestas con citas: las auditorías s15–s20 de fable, que se puntúan por cita |
| ALCANCE: "acotá el alcance, no intentes leer todo" | el tope de rondas: `alcance_amplio` da 16 y en la última ronda se retiran las tools | pedidos que `alcance_amplio` clasifica amplios: s17–s20 (verificado: s15/s16 no lo son) |

Aviso sobre ALCANCE: la estructura NO hace lo mismo que la prosa. La prosa
pide contención; `alcance_amplio` da MÁS rondas. Lo único que acota es el tope.
Por eso, para ALCANCE la medida que decide es el costo.

## Fuera de F (declarado)

- "No uses cat/grep/find por run_command": no hay estructura que la
  reemplace (la policy los deja en `auto`). Cambiar la policy es R7, no F.
- Idioma, CWD y raíces: son datos o preferencias, no reemplazables.
- `DIRECTIVA_FORMA` se queda (exp/51).

## Brazos

Todos con el chat de `bench_fable` (sin prosa de fable, sin skills,
`MAX_TOOL_ROUNDS=8`, turno "salir" para leer `[tokens] sesión`):

- **base**: el prompt de producción;
- **sin_citas**: `PROMPT_CITAS=0`, en s15–s20;
- **sin_alcance**: `PROMPT_ALCANCE=0`, en s17–s20.

3 seeds. base corre en s15–s20 y cada brazo se compara con base SOLO en sus
escenarios. Total: 18 + 18 + 12 = 48 corridas.

## Medidas

- calidad: `correct_action` (0–2) de `bench_fable.puntuar`;
- citas inválidas en el informe FINAL (después de VerificarCitas);
- costo: tokens totales por corrida;
- evidencia de que la estructura decidió: líneas `[citas] N/M verificadas`
  (VerificarCitas encontró citas) y `⚙ ronda k/16` (corrió con el tope amplio);
- correcciones de VerificarCitas (`DeepSeek (citas corregidas)`).

## Criterio (cada directiva por separado)

La directiva **se borra** si se cumplen las cuatro, en su brazo contra base:

1. **cobertura**: la estructura decidió en al menos 2 de las 3 seeds de CADA
   escenario del brazo. CITAS: VerificarCitas encontró ≥1 cita. ALCANCE: la
   corrida usó el tope amplio (`/16`). Sin eso, ese escenario no midió nada;
2. **calidad**: calidad media ≥ la de base;
3. **citas**: citas inválidas finales (suma) ≤ las de base;
4. **costo**: tokens medios ≤ 1,10 × los de base.

La carga de la prueba está en el borrado: en un empate de calidad la directiva
se va (no hay peor resultado y el prompt queda más corto), pero si cualquiera
de las cuatro falla, se queda.

## Decisión atada al resultado

- CITAS gana → se borran `DIRECTIVA_CITAS` y `PROMPT_CITAS`.
- ALCANCE gana → se borran `DIRECTIVA_ALCANCE` y `PROMPT_ALCANCE`.
- No gana → la directiva se queda y su setting también se borra (el A/B ya
  respondió; el toggle no queda como perilla de producción).
