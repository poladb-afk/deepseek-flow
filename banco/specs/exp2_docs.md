# Spec exp/2 — docs

## 1. docs/design.md — después de la sección exp/5

(Insertar después del bloque que termina en "al camino que exp/1 volvió automática." — textual):

```
### exp/2 — evals como tool del chat (2026-10-06)

Medido en el test exhaustivo: el modelo QUISO correr evals en vivo, no
existía la tool, su run_command fue rechazado y degradó a leer la
corrida del día anterior del disco. La spec pedía dos tools (rápida +
pesada); el harness prefirió UNA `evals` estilo run_informe (informe a
disco + ruta) — consistente con el patrón del código, y la revisión del
conductor aceptó el diseño con UNA corrección de fondo: `generar` ganó
`actualizar_baseline` (default True = CLI intacto) y la tool pasa False
— el ancla de medición no se pisa desde una conversación.

Medición (exp2-medicion): tool nativa usada (cero run_command), informe
leído y resumido en 25 s, y el baseline verificado INTACTO tras la
corrida (filecmp).
```

## 2. docs/roadmap.md — después de la entrada exp/5

(Append textual):

```
- **exp/2 ✅ mergeada** — evals como tool del chat (estilo run_informe:
  informe a disco + ruta). Corrección de fondo del conductor: la tool
  compara pero NO guarda el baseline (`actualizar_baseline=False`).
  Medido: tool nativa, 25 s, baseline intacto.
```

## Reglas
Solo estas 2 operaciones textuales.
