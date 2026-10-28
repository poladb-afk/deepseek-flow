# Pre-registro — fase 2d de elegancia: esquema de tools fijo y cierre con `tool_choice="none"`

**Estado:** pre-registrado el 2026-10-28, ANTES de escribir el código de 2d y
de correr su brazo. No se retoca después de ver resultados (si algo cambia,
va como desvío declarado en la bitácora, con el porqué).

## Hipótesis

`Cierre` (la última llamada de una pregunta, X96) hoy manda `tools=None`: el
prefijo del request cambia en la llamada que más historial arrastra y el
KV-cache del proveedor no lo reusa. Mandar el esquema completo con
`tool_choice="none"` (probado contra DeepSeek: lo honra, oculta las tools al
modelo) deja el prefijo estable. Predicción: la llamada de `Cierre` reusa
caché; el resto de la conducta no cambia.

## Instrumento

`.runs` con `evento_llm` X98 (`cache_hit` + `llamador`), agregado con
`python3 banco/probes/tokens_runs.py`. Calidad y archivos tocados: el JSONL
de `bench_fable` (`correct_action`, `cambios`).

## Corridas

| | árbol | escenarios × seeds | brazo |
|---|---|---|---|
| base | `012b92f` + X98 (el instrumento, sin cambio de conducta) | s17 ×5, s18 ×5, s19 ×3, s20 ×3 | A |
| 2d | rama de 2d | ídem | A |

La base de `012b92f` sin X98 (16 corridas, `fase2d-linea-base`) sirve para
calidad y costo, NO para caché (sus trazas no llevan `cache_hit`): por eso
la base se corre de nuevo con el instrumento. Las 16 corridas viejas quedan
como réplica de calidad/costo.

## Criterios (todos tienen que cumplirse para que 2d entre)

**¿Sirve?** (la pregunta de la fase)
1. En la base-X98, se registra el `cache_hit` de las llamadas de `Cierre`.
   En 2d, **el hit medio de `Cierre` / prompt de `Cierre` supera al de la
   base en al menos 20 puntos porcentuales**, y al menos el 80% de los
   cierres de 2d tiene `cache_hit > 0`. Si la base ya cachea el cierre igual
   (diferencia < 20 pp), 2d no entra: no aportó lo que prometía.

**¿Rompe algo?** (por escenario, contra la base)
2. Calidad: la SUMA de `correct_action` de cada escenario no baja más de 1
   punto (pisos con la base de 012b92f: s17 ≥ 4, s18 ≥ 3, s19 ≥ 5, s20 ≥ 5;
   se recalculan con la base-X98 y vale el MENOR de los dos pisos).
3. Costo: la MEDIANA de tokens por corrida de cada escenario ≤ 1,25 × la de
   la base (umbral alto a propósito: 2d cambia UNA llamada por pregunta; si la
   mediana sube más, el modelo cambió de conducta — más rondas — y eso es lo
   que se quiere ver; 1,10× daría falsas alarmas con el ruido medido: s17
   varía 5,5× entre seeds).
4. Debris: corridas que crean archivos en la auditoría ≤ las de la base
   (la base de 012b92f tiene 1: s17-s1).
5. UX: 0 respuestas de `Cierre` que le digan al usuario que no tiene tools
   ("no tengo", "no dispongo", "no tengo acceso", "no puedo usar" + tool/
   herramienta, en el reporte final de las 16 corridas; lo revisa el operador
   sobre `*-reporte.txt`).

## Qué NO decide esto

- El subset de skill (pasa a una nota en el resultado, fiel a "guía, no
  sandbox"): con `SKILLS=0` en el brazo A no se ejercita; lo cubren los tests.
- `VerificarCitas`, que también llama sin tools: fuera de 2d (pendiente).
