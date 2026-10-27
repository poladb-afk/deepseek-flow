# Reentreno de `router_voto` para c01/c02 (pre-registro)

Fijado el 2026-10-27, ANTES de escribir el control y ANTES de generar datos.
El criterio vive en `banco/probes/bench_voto.py::veredicto_reentreno` y no se
retoca.

## Pregunta

H3-G2 (X83) no gana porque el voto local confía en directo en c01 ("debatí en
2 rondas…", 0,94) y c02 ("¿quién ganó el último mundial…?", 0,76). ¿Un
checkpoint reentrenado con imperativos de capacidad y recencia los frena sin
volverse un voto que dice siempre herramientas?

## Dónde decide la pieza (lección X82)

El voto solo decide cuando Laya propone directo. `bench_voto.py` lo pone ahí
en cada caso (corre la cascada siempre), así que el bench mide la pieza donde
decide. El riesgo propio de un reentreno es otro: que el gate mida MEMORIA.
Los 18 casos del bench son conocidos; si entran al entrenamiento, el bench da
0 falsos directos sin que el voto haya aprendido nada.

## Tres defensas, fijadas antes

1. **Anti-fuga** (`banco/probes/voto_antifuga.py`): ningún caso del bench ni
   del control entra al entrenamiento, tampoco reescrito de cerca (misma
   bolsa de palabras normalizada, Jaccard ≥ 0,6). Precedente: exp/13. Límite
   declarado: una paráfrasis con palabras distintas pasa el filtro; por eso
   existe la defensa 2.
2. **Control fuera de muestra** (`banco/voto_control.jsonl`, vacío hasta que
   lo escriba el operador): al menos **10 casos herramientas** (imperativos
   de capacidad y recencia, grupo `correccion`) y **4 trampas inversas**
   (creativos o conocimiento estable, grupo `directo`), con etiqueta humana,
   escritos y commiteados **antes** de generar el dataset de entrenamiento.
   El commit del control tiene que ser anterior al del checkpoint: el orden
   de la historia es la prueba.
3. **Ahorro**: el grupo directo del bench sigue 6/6 (ya en H3-G2) y las
   trampas inversas del control, todas bien.

## Criterio

El checkpoint nuevo **se promueve** (y H3-G2 queda ganado) si se cumplen las
cinco, con el checkpoint real en `LAYA_MODEL_VOTO`:

1. **h3g2**: gana H3-G2 en el bench (0 falsos directos, directo 6/6);
2. **control_tamano**: el control tiene ≥10 herramientas y ≥4 directos;
3. **control_seguridad**: 0 falsos directos del voto en el control;
4. **control_ahorro**: todas las trampas inversas del control, bien;
5. **antifuga**: 0 fugas entre el entrenamiento y bench + control.

Sin el anti-fuga corrido (`--entrenamiento`), no hay veredicto.

## Decisión atada al resultado

- Gana → el checkpoint pasa a producción y se aplica el borrado aparcado de
  las reglas (`docs/informes/h3g_borrar_reglas.patch`, con sus bloques de
  docs regenerados); el operador acepta la baja del ratchet con su clave.
- No gana → el checkpoint de producción no cambia y las reglas se quedan. El
  bench dice qué falló (c01/c02, el control o el ahorro).

## Fuera de este repo (declarado)

Generar y verificar el dataset y correr el fine-tune pasa por el tooling de
bmo/Laya y el contrato congelado `PREGUNTA_VOTO`
(`tests/test_contratos.py::test_pregunta_voto_congelada_sha1`): el
reentreno no puede cambiar la pregunta.

## Cómo se corre

    python3 banco/probes/voto_antifuga.py RUTA_ENTRENAMIENTO.jsonl
    LAYA_MODEL_VOTO=<checkpoint nuevo> python3 banco/probes/bench_voto.py --entrenamiento RUTA_ENTRENAMIENTO.jsonl

La línea `reentreno` del informe y la clave `reentreno` del artefacto llevan
el veredicto.
