# Router de Laya: política separada + modo sombra (exp/35)

**Qué cambia.** La decisión del router deja de vivir dentro del nodo. Ahora
Laya **estima** (opción + probabilidades) y Python **decide** (qué ruta se
ejecuta), en `utils/laya_routing.py`. El nodo queda como adaptador.

## Por qué (lo que aportó el informe externo)

1. **Clasificación ≠ política.** Una probabilidad no es una autorización: la
   regla que aplica el resultado tiene que ser código propio, testeable sin
   modelo.
2. **Respuesta inválida = abstención.** Se EXIGEN las dos probabilidades,
   finitas, en [0, 1] y que sumen ~1. `answer_confidence` es max(p) y
   `confidence` es entropía normalizada: la cascada vieja podía mezclarlas.
   Sin datos usables, la ruta es herramientas — nunca "directo" por defecto.
3. **Modos para medir sin cambiar la conducta.** `shadow` registra la
   propuesta y conserva herramientas (y ahorra el voto de DeepSeek).

## Los tres modos

| `LAYA_MODO` | Ejecuta Laya | Registra | Ruta aplicada | Para qué |
|---|---|---|---|---|
| `off` | no | — | herramientas | chat previo al router |
| `shadow` | sí | sí | herramientas | juntar evidencia sin tocar nada |
| `enforce` (default) | sí | sí | la propuesta | el comportamiento de siempre |

## El registro (`salidas/routing.jsonl`)

Una línea por decisión: `ts`, `modo`, `propuesta`, `aplicada`, `causa`,
`p_directo`, `q`, `umbral`, `laya` (versión del paquete). Es lo que el trace
no tenía: el trace guarda nodo/acción/segundos, no el porqué de la decisión.
Con `shadow` activado una sesión normal ya produce la muestra para elegir α
(ver `docs/informes/calibracion_router_2026-10-08.md`).

## Verificación

- `tests/test_laya_routing.py`: 11 respuestas inválidas parametrizadas, límite
  del umbral, colapso conformal, los tres modos, el registro (escribe, se apaga
  y un destino imposible no rompe) — todo sin modelo ni red.
- Gate de la rama: ruff + **248 passed**.

## Unir los dos registros (hecho)

El registro de preguntas (exp/34) y el de decisiones (exp/35) eran dos
archivos. Ahora `LAYA_LOG_PREGUNTA=1` agrega los primeros 200 caracteres de la
pregunta al evento de routing — **default 0**, para que el registro no guarde
texto del usuario sin que el operador lo pida.

El circuito completo, en dos comandos:

```bash
LAYA_MODO=shadow LAYA_LOG_PREGUNTA=1 python3 main.py    # una semana de uso normal
python3 banco/probes/etiquetar_router.py 200 --extra salidas/routing.jsonl
```

El etiquetador ya lee JSONL con la clave `pregunta` (exp/33): no hace falta
conversión. Lo que sale de ahí es el set para elegir alpha y recién entonces
pasar a `enforce`.

## Límites declarados

- **No** implementa el estado con historial (L05 del informe): el checkpoint
  está entrenado con `{"pregunta": ...}` byte a byte y cambiarlo exige un
  fine-tune nuevo. Queda como proyecto de entrenamiento, no como parche.
- La calibración sigue siendo opt-in y el set natural recién empieza a
  juntarse (exp/34 + este registro).
- Pendiente de la comparación externa: evaluar `laya 0.4.0` y el proceso
  separado (`laya-serve`) para sacar los checkpoints del proceso del chat.

## Reproducir

```bash
LAYA_MODO=shadow python3 main.py     # una sesión normal; mirar salidas/routing.jsonl
python3 -m pytest tests/test_laya_routing.py -q
```
