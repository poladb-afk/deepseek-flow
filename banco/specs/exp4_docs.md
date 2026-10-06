# Spec exp/4 — docs con el hallazgo del bypass DSML

## 1. `docs/design.md` — después de la sección exp/11

(Insertar después del bloque que termina con "quedó intacto. 3/3 turnos OK."
— texto textual):

```
### exp/4 — presupuesto visible + protocolo de continuación (2026-10-06)

Medición que cambió el diagnóstico: el problema nunca fue "llamadas por
ronda" (87% de las rondas tiene 1-2; el outlier de 17 read_file fue UNA
ronda) sino RONDAS para la clase editar→probar→editar — 42 preguntas
históricas sobre 8 (máx. 242) y tres sesiones de aplicación muertas por
el corte. Y el hallazgo de diseño: el modelo NO veía su presupuesto (el
⚙ iba a la terminal, nunca a la conversación).

- `nota_presupuesto`: en la anteúltima ronda, la nota viaja en el
  resultado de la última tool ("la próxima es tu ÚLTIMA con tools...
  cerrá el estado y pedí continuación — un mensaje nuevo reinicia el
  presupuesto"). El reset ya existía (cada mensaje nuevo pone
  tool_rounds en 0): lo que faltaba era el aviso.
- El default 8 queda: mediana 2 rondas/pregunta; 19 min colgados en una
  pregunta es mala UX de chat — la solución es el aviso + la mano amiga,
  no un tope enorme.
- `env:` por escenario en el banco: las sesiones de aplicación pesadas
  corren con MAX_TOOL_ROUNDS=40 (así se aplicó exp/11).

Demostración (exp4-protocolo, tope 2, tarea de 3 rondas dependientes):
protocolo verificado — el presupuesto se reinicia con el mensaje nuevo.
Y UN HALLAZGO: al retirarse las tools, el modelo emitió el write_file
como TEXTO DSML y la recuperación lo ejecutó igual (recuperacion×1) —
la recuperación DSMA by-pasea el presupuesto de tools: la ley L8 no es
tope duro por ese camino. Benigno acá (la tarea se completó), pero es
una interacción conocida: candidato a fix — que la recuperación
respete el retiro de tools o consuma ronda.

Las corridas de control (exp4-bajo/amplio, presupuesto 4 vs 40 con la
misma tarea) no muestran daño en defaults: 2 rondas, sin nota, sin
diferencia.
```

OJO: escribí "DSMA" arriba por typo — corregilo a "DSML" al aplicar.

## 2. `docs/roadmap.md` — después de la entrada exp/11

(Append textual):

```
- **exp/4 ✅ mergeada** — presupuesto visible: la nota de la anteúltima
  ronda viaja en el resultado de la tool (el modelo ya ve su tope),
  protocolo de continuación documentado ("seguí" reinicia) y env por
  escenario en el banco (MAX_TOOL_ROUNDS=40 para aplicar). HALLAZGO:
  la recuperación DSML by-pasea el retiro de tools — candidato a fix.
```

## Reglas

Solo estas 2 operaciones (con la corrección del typo indicada).
