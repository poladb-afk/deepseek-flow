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

- Gana → el checkpoint pasaba a producción y se aplicaba el borrado de las
  reglas (un patch aparcado, con sus bloques de docs regenerados); el
  operador aceptaba la baja del ratchet con su clave. Corrido con r3: **no
  ganó** (X89), y el patch aparcado se borró al cerrar H3-G2.
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

## Enmienda (2026-10-27, antes de cualquier dato de entrenamiento)

Esta sección se agregó después de fijar lo de arriba y ANTES de generar datos;
lo de arriba no se toca.

**Qué la motivó**: el smoke de integración (el operador corrió `bench_voto.py`
con el control lleno y el checkpoint de producción) mostró que el voto actual
pasa el control entero: 0 falsos directos y las 6 trampas bien. Un control
así no distingue aprender de memorizar. Un checkpoint que memorice c01/c02
gana H3-G2, pasa el control porque ya lo pasaba y da 0 fugas si el
entrenamiento trae paráfrasis con otras palabras. Se habría promovido.

**Sexta condición, `control_discrimina`**: el voto de PRODUCCIÓN, medido sobre
este mismo control antes de entrenar, tiene que dar al menos un falso
directo. Se registra con

    python3 banco/probes/bench_voto.py --registrar-baseline

que escribe `banco/voto_control_baseline.json` con la huella sha256 del
control y los ids que el voto de producción falla. El baseline vale solo para
el control que midió: si el control cambia, hay que volver a medir. Sin
baseline no hay veredicto.

**Qué cambia para el control**: además de los casos actuales, unos 6 de la
familia de c01 (deliberar o debatir en varias rondas, con otros verbos y
otras formas) y unos 6 de la familia de c02 (quién ganó el último X, campeón
actual de Y, resultado más reciente de Z), escritos por el operador. Otros
miembros de esas familias pueden ir al entrenamiento; los del control, nunca.

**Etiqueta humana**: el control de `7897a4f` lo escribió el agente del
operador. Vale como borrador; cuenta como control el commit en que el
operador lo revisa, lo amplía y lo firma (`voto: control revisado y
etiquetado por el operador`). El orden que se exige es: control firmado →
baseline → dataset.
