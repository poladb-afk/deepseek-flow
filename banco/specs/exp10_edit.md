# Spec: edit_file con feedback rico (exp/10)

(Motivo medido: edit_file genera 27/43 errores — el 63% del total — casi
todos old_string que no matchea; el error actual manda "releé el archivo"
y el modelo relee a ciegas y reintenta. Con candidatos y diagnóstico de
whitespace el reintento debería ser uno y sin relectura completa.)

## Cambios en `modules/coding.py`

### 1. Dos funciones PURAS nuevas (junto a edit_file, importables)

```python
def _normalizar_ws(s):
    """Normaliza whitespace para el diagnóstico: tabs→4 espacios y sin
    espacios al final de línea. Sirve para DISTINGUIR la causa clásica
    del no-match (indentación/copiado a mano) sin perdonar el match."""
    return "\n".join(
        linea.expandtabs(4).rstrip() for linea in s.splitlines()
    ).strip("\n")


def candidatos_similares(texto, old_string, max_candidatos=3):
    """Top ventanas de líneas parecidas a old_string (difflib): para que
    el modelo corrija en UN intento sin releer el archivo entero. Cada
    candidato es (num_linea_inicio_base_1, excerpt). Ventanas del mismo
    alto que old_string; si old_string tiene 1 línea, ventanas de 1.
    Empates y orden por ratio descendente."""
```

Implementación: partir texto en líneas; alto = len(old_string.splitlines())
o 1 si vacío; para cada ventana i, ratio =
difflib.SequenceMatcher(None, ventana, old_string_a_lineas).ratio();
quedarse con las max_candidatos mejores (ratio > 0.5, si ninguna supera
0.5 devolver las 3 mejores igual pero está bien devolver []) — decidí:
umbral 0.5, si ninguna pasa devolver [].

### 2. Los DOS errores de edit_file, enriquecidos

- `n == 0`: mantener el mensaje actual y AGREGAR:
  - Si `_normalizar_ws(old_string) in _normalizar_ws(texto)` (comparación
    por líneas normalizadas — implementala como comparación de listas de
    líneas normalizadas): línea "NOTA: coincide salvo espacios/tabs —
    copiá la indentación EXACTA del archivo (tabs vs espacios)."
  - Si hay candidatos: "¿Quisiste decir (línea {n}):" + un excerpt por
    candidato (recortado a ~200 chars), formato:
    `  L{n}: {excerpt!r}`.
- `n > 1`: mantener el mensaje y AGREGAR las líneas donde ocurre:
  "Ocurrencias en líneas: 12, 45, 78 — agregá contexto para apuntar una."

### 3. Tests (`tests/test_smoke.py`, append)

Con un texto sintético de ~10 líneas con indentación mixta (tabs y
espacios) y una línea "similar":
- normalizada matchea: old_string igual pero con indentación de espacios
  cuando el archivo usa tabs → el diagnóstico dispara (probar la
  comparación normalizada directamente, función pura aparte o vía el
  comportamiento de _normalizar_ws).
- candidatos_similares: old_string de 2 líneas que casi está (una palabra
  distinta) → devuelve la ventana correcta con num de línea exacto; una
  cadena totalmente ajena → [] (umbral).
- n>1: dos ocurrencias → el error lista ambas líneas (test del cálculo
  de líneas de ocurrencias como función pura si hace falta extraerla).

## 4. Escenario de medición (crear, no correr)

`banco/escenarios/exp10-reintento.yaml`: scratch [prueba_edit], permitir
el dir del proyecto, dos turnos:
1. "Creá prueba_edit/datos.py con EXACTAMENTE este contenido de 6 líneas:
   def f():<newline>    x = 1  (4 espacios)<newline>    return x<newline>
   def g():<newline>\ty = 2  (UN TAB)<newline>    return y" (hitl s)
2. "Editá prueba_edit/datos.py reemplazando la línea que dice 'y = 2'
   (escribila con CUATRO ESPACIOS en el old_string, no con tab) por
   'y = 3'" (hitl s) — el old_string del modelo no va a matchear por
   indentación: el feedback debe decirle la causa y el modelo corregir
   en UN reintento.
3. salir.

## Fuera de alcance

No cambiar la semántica de edit_file (unicidad exacta, HITL, diff).
No tocar write_file.
