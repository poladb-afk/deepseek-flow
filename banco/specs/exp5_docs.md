# Spec exp/5 — docs

## 1. docs/design.md — después de la sección exp/3

(Insertar después del bloque que termina en "sin tocar el contrato." — textual):

```
### exp/5 — search_files con conteo exacto (2026-10-06)

Patología medida (test exhaustivo): el conteo de ".py" quedaba "50+" y
el modelo no sabía cuántos eran; su find para cerrar el número cayó en
preguntar (hasta exp/1). Ahora el conteo EXACTO se calcula antes de
truncar la muestra: "N archivos coinciden" con N real, y al cortar el
tope agrega "... y M más (mostrando 50 de TOT; para el listado completo:
run_command 'find ...' ya es solo-lectura auto)" — la sugerencia apunta
al camino que exp/1 volvió automático.
```

## 2. docs/roadmap.md — después de la entrada exp/3

(Append textual):

```
- **exp/5 ✅ mergeada** — search_files con conteo exacto: "N archivos"
  con N real calculado antes del tope + sugerencia de find (auto desde
  exp/1). Fin del "50+" del test exhaustivo.
```

## Reglas
Solo estas 2 operaciones textuales.
