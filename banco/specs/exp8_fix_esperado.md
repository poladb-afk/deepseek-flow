# exp/8 parte 1b — corrección: la clave de la respuesta esperada

## Bug

`sonda_laya.py voto_en_router` revienta con `KeyError: 'confirma_herramientas'`:
el test del router guarda la verdad de terreno en `answers["necesita_herramientas"]`
(misma etiqueta semántica: herramientas|directo), pero `correr()` lee
`caso["answers"][spec["pregunta"]]` con la pregunta del VOTO.

## Fix exacto (2 toques)

1. En la entrada `voto_en_router` de ESPECIFICACIONES, agregar la clave:
   `"esperado_de": "necesita_herramientas",`
2. En `correr()`, cambiar la línea:
   `esperado = caso["answers"][spec["pregunta"]]`
   por:
   `esperado = caso["answers"][spec.get("esperado_de", spec["pregunta"])]`
   con un comentario de una línea: la verdad de terreno vive en la clave de
   la pregunta ORIGINAL cuando la sonda mide una segunda capa sobre el test
   de otra.

Nada más. No correr la sonda (la corre el conductor).
