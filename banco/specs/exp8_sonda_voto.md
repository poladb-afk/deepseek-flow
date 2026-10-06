# Spec exp/8 — parte 1: extender sonda_laya.py con la medición del ensamble

## Objetivo

Agregar UNA entrada al diccionario ESPECIFICACIONES de sonda_laya.py para
medir la segunda capa del ensamble: el checkpoint `router_voto` respondiendo
PREGUNTA_VOTO sobre el MISMO test del router (las 30 preguntas del router
test pasadas por el checkpoint del voto). Con eso se puede computar el
veredicto del ensamble completo (gate del router + voto) caso por caso.

## Cambio exacto

En `sonda_laya.py`, agregar a ESPECIFICACIONES esta clave (después de
"voto", mismo estilo):

```python
    "voto_en_router": {
        "checkpoint": ".modelos/router_voto",
        "test": TAREAS / "router_flow_test.jsonl",
        "pregunta": "confirma_herramientas",
        "contrato": PREGUNTA_VOTO,
        "estado": lambda f: {"pregunta": f["pregunta"]},
    },
```

Y actualizar el docstring de uso del módulo agregando la línea:

    python3 sonda_laya.py voto_en_router  # .modelos/router_voto sobre el test del router (ensamble)

NADA más: no tocar funciones, no tocar las otras entradas, no correr nada
(la medición la corre el conductor después).

## Contexto (para el comentario, si querés agregar uno breve)

La pregunta del voto ("confirma_herramientas") fue diseñada como segunda
opinión sobre los directos del router: correrla sobre el test del router
mide si la segunda capa cazaría los falsos-directos que pasan la compuerta
(hoy: "mundial" a 0.831).
