# Spec exp/10 — docs finales

## 1. `docs/design.md` — después de la sección exp/4

(Insertar después del bloque que termina con "sin diferencia." — textual):

```
### exp/10 — edit_file con feedback rico (2026-10-06)

edit_file generaba el 63% de los errores del harness (27/43, minería
exp/9) con un feedback ciego: "old_string no aparece... releé el
archivo" — el modelo relee entero y reintenta a ciegas.

El error ahora diagnostica: (a) si el texto matchea normalizado
whitespace (tabs→4, sin trailing), NOTA explícita de indentación — la
causa clásica, incluso para old_strings de una línea; (b) top-3 de
candidatos con número de línea (difflib sobre el texto unido — sobre
listas de líneas compararía líneas enteras y toda casi-igual daría
ratio 0); (c) en ocurrencias múltiples, las líneas exactas para apuntar
con contexto.

Medición (exp10-reintento, indentación tab-vs-espacios): 2 intentos de
edit, CERO relecturas del archivo, diff correcto aprobado y verificado
— el reintento único hipotetizado. minar_errores queda como línea de
base (27 errores) para vigilar la tasa a futuro.
```

## 2. `docs/roadmap.md` — después de la entrada exp/4

(Append textual):

```
- **exp/10 ✅ mergeada** — edit_file con feedback rico: diagnóstico de
  indentación (incluye old_strings de 1 línea), candidatos con línea y
  ocurrencias listadas. Medido: reintento único y cero relecturas en el
  caso tab-vs-espacios. Línea de base: 27 errores históricos.
```

## Reglas

Solo estas 2 operaciones textuales.
