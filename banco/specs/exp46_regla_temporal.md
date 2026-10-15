# exp/46 — la regla temporal: recencia NO la juzga Laya (el "mundial", cerrado por regla dura)

El falso-directo "¿quién ganó el último mundial?" (conf 0.83, pasa la
compuerta) resiste desde la curaduría. El manual de Jev lo explica: la
familia NO juzga fechas ni recencia ("no dates — extract parts in code") —
es un límite del modelo, no un fallo de entrenamiento; rounds dirigidos no
lo curan. La salida del propio manual, y el orden del runbook (regla dura
ANTES que modelo): detectar la recencia en CÓDIGO y mandar la pregunta al
lado seguro sin consultar a Laya.

Asimetría que lo hace barato: un falso-herramientas ≈ gratis (DeepSeek con
tools puede responder sin llamarlas), así que la regla puede ser GENEROSA.

## 1. `utils/laya_routing.py` — la regla PURA

```python
import re

# exp/46: la recencia no la juzga Laya (límite de familia documentado en el
# manual de Jev: sin fechas). Detección en código, generosa a propósito:
# falso-herramientas es barato (el modelo con tools puede responder directo).
RE_TEMPORAL = re.compile(
    r"(?i)\b(?:últim[oa]s?|ultim[oa]s?|actual(?:es|mente)?|actuales|"
    r"hoy|ahora|recientes?|novedades?|noticias?|latest|current|today|"
    r"20[2-3]\d)\b"
)


def regla_temporal(pregunta):
    """True si la pregunta pide recencia/hechos actuales: va al lado seguro
    (herramientas) sin consultar a Laya. PURA, testeable."""
    return bool(RE_TEMPORAL.search(pregunta or ""))
```

## 2. `nodes.py` — el cableado con RESPECTO por la flywheel

En `LayaRouter.exec`, al armar el estado, ANTES de llamar a Laya:
- si `regla_temporal(pregunta)` y el modo es **enforce** → devolver el
  centinela `"regla:temporal"` (NO se llama a Laya: la regla dura es más
  barata y más confiable que el modelo en su punto ciego);
- si matchea y el modo es **shadow** → NO cortar: Laya corre igual (la ruta
  aplicada sigue siendo herramientas) y la decisión se registra con su
  p_directo — la flywheel necesita justamente las etiquetas de esta clase
  para VALIDAR la regla contra realidad.

En `LayaRouter.post`, antes de `decide()`: si `exec_res == "regla:temporal"`
→ `propuesta, causa, p_directo = "herramientas", "regla temporal (exp/46):
recencia no la juzga Laya", None` y seguir el flujo normal (registrar la
decisión con esa causa, sin pendiente — no hay p_directo).

## 3. Tests (`tests/test_laya_routing.py`, append)

1. `regla_temporal` pura: "¿quién ganó el último mundial?" True; "¿cuál es
   la capital de Francia?" False; "¿por qué el cielo es azul?" False;
   "¿qué versión de pytest hay en 2026?" True; "mi modelo actual?" True
   (generosa a propósito — el costo es una ruta herramientas); case/acentos
   (ultimO sin tilde también).
2. Nodo en enforce con fake de Laya que diría directo 0.99: con "último..."
   → "herramientas" con causa "regla temporal", el fake NO se llama
   (contador), y la línea de decisión lleva la causa.
3. Nodo en shadow con la misma pregunta: Laya SÍ corre (contador ≥ 1) y la
   decisión se registra normal (la flywheel no se ciega).
4. Pregunta sin recencia en enforce: flujo de siempre (la regla no dispara).

## 4. `.env.example`

Dos líneas junto al bloque del router: la regla temporal exp/46 manda las
preguntas con recencia al lado seguro sin gastar a Laya (en shadow sigue
consultando para juntar la etiqueta).

## Candado final

pytest verde (los tests de hoy + estos) y ruff limpio. No tocar `decide`,
`ruta_aplicada` ni los umbrales: la regla es ANTES del modelo, no otra
política.
