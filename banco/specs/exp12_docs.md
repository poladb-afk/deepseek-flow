# Spec exp/12 — docs

## 1. `docs/design.md` — después de la sección exp/10

(Insertar después del bloque que termina en "para vigilar la tasa a
futuro." — textual):

```
### exp/12 — el bypass DSML del presupuesto, cerrado (2026-10-06)

Hallazgo de exp/4: al retirarse las tools por el tope, el modelo emitía
la llamada como TEXTO DSML y la recuperación la ejecutaba igual — la ley
"todo bucle tiene presupuesto" no era tope duro por el canal de texto.

`dsml_con_presupuesto_agotado`: con tools ofrecidas, la recuperación de
siempre; con tools retiradas, el markup se corta (lo previo sobrevive) y
si no queda nada, el contenido pasa a ser el mensaje honesto "(sin
texto: emitiste tool-calls con el presupuesto agotado — decí 'seguí'
para reiniciarlo)". Terminal: "[DSML] tool calls como texto: IGNORADOS".

Re-medición del escenario que by-paseaba (exp4-protocolo, tope 2):
antes — el write_file corría tras el retiro (recuperacion×1); ahora —
dsml_ignorado×1, cero ejecución en el turno 1, y el turno de
continuación completa con su HITL. La ley vuelve a sostenerse.
```

## 2. `docs/roadmap.md` — después de la entrada exp/10

(Append textual):

```
- **exp/12 ✅ mergeada** — bypass DSML del presupuesto cerrado: la
  recuperación no re-arma tools retiradas por el tope (markup cortado +
  mensaje honesto + aviso en terminal). Re-medición del escenario que
  by-paseaba: cero ejecución tras el retiro, continuación limpia.
```

## Reglas

Solo estas 2 operaciones textuales.
