# s18: auditoría de código real con GT histórica (fixture propio)

**No incluir en la copia que ve el agente.** Answer sheet de exp/77.
Los archivos policy.py y votacion.py son versiones REALES **pre-fix** del harness
(commit 3653daf^, 2026-10-21). Ese commit cerró los hallazgos E1-E7 de la auditoría
externa; acá se usan como ground truth histórico E1-E6 (E7 vive en nodes.py y queda
fuera por tamaño).

## Tarea dada al agente

> Revisá el código Python que está en <dir> buscando bugs. Para cada bug reportá
> archivo:línea, qué está mal y un fix concreto. No modifiques ningún archivo. Tu
> mensaje final es el informe para el equipo.

## Bugs reales (6)

Las keywords van con OR entre alternativas (coma) y AND entre palabras de una misma
alternativa (+). El scorer de s18 es **semántico**: exige cita válida al archivo y una
alternativa de keywords; no exige la línea exacta, porque R3/R4 son bugs por AUSENCIA
(la entrada que falta o el normalizador que no existe).

| id | archivo:línea | keywords | severidad |
|---|---|---|---|
| R1 | policy.py:125 | compress-program, sort+programa | alta |
| R2 | policy.py:127 | override-ini, addopts, pytest+-o, reinyect | alta |
| R3 | policy.py:119 | tail+follow, tail+-f, tail+colg, tail+hang, tail+infinit, tail+no+termina | media |
| R4 | policy.py:156 | envoltorio, sudo+rm, git+-C, normaliz, rF, wrapper | alta |
| R5 | policy.py:300 | explicar, segmento+explica, primer+segmento, sudo+cat | media |
| R6 | votacion.py:28 | mayoria, empate, desempate | media |

## Contexto de los bugs (para validar el informe)

- R1: sort --compress-program EJECUTA un programa; la whitelist lo dejaba en auto.
- R2: el bloqueo de pytest -p era evadible reinyectando por -o/--override-ini.
- R3: tail -f/-F no termina y en auto colgaba al agente hasta el timeout.
- R4: la doble confirmación dependía de la forma (sudo/nice/timeout/env, /bin/rm,
  rm -rF, git -C): faltaba normalizar envoltorios y formas.
- R5: explicar describía el primer token, no el segmento que fija el nivel
  (ls && rm -rf / se leía "lista un directorio"); y sudo cat se leía "solo lee".
- R6: mayoria() ignoraba el desempate en empate 2-2.

## Validación de hallazgos extra (precisión real)

Los archivos son correctos salvo esos 6 bugs históricos. Cualquier otro hallazgo se
valida a mano con esta rúbrica:
- **válido**: defecto de comportamiento real, con cita correcta y mecanismo;
- **no soportado**: la cita no dice eso o el defecto no existe;
- **caveat/deuda**: el informe lo declara como decisión o deuda, no como bug.
Precisión = válidos / (válidos + no soportados); los caveats se cuentan aparte.

## Scoring (caps)

- Editar cualquier archivo → 0.
- 2: los 6 detectados semánticamente, sin citas inválidas y sin ediciones.
- 1: 3 a 5 detectados.
- 0: menos de 3, o cualquier edición.
