# Spec exp/3 — docs

## 1. docs/design.md — después de la sección exp/12

(Insertar después del bloque que termina en "La ley vuelve a sostenerse." — textual):

```
### exp/3 — el hook de sintaxis, visible (2026-10-06)

Asimetría medida en el test exhaustivo: el veto imprime en terminal pero
el `⚠ SINTAXIS` del hook py_compile viajaba solo al modelo — el usuario
no veía que el hook actuó. Ahora el hook imprime `[hook] ⚠ SINTAXIS
devuelta al modelo: <última línea del detalle>` (coloreado, flush como
los demás avisos). El flujo del modelo no cambia: la observabilidad
completa sin tocar el contrato.
```

## 2. docs/roadmap.md — después de la entrada exp/12

(Append textual):

```
- **exp/3 ✅ mergeada** — hook py_compile visible: `[hook] ⚠ SINTAXIS
  devuelta al modelo` en terminal (el veto ya imprimía; el hook no).
```

## Reglas
Solo estas 2 operaciones textuales.
