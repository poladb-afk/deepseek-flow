# Spec: hook de sintaxis visible + search_files con conteo exacto (exp/3 + exp/5)

(Dos quick wins en una branch cada uno NO: esta spec cubre SOLO exp/3 —
el conductor aplica exp/5 aparte.)

## exp/3 — el hook py_compile, visible en terminal

Asimetría medida (test exhaustivo): el veto imprime, el `⚠ SINTAXIS` viaja
solo al modelo — el usuario no ve que el hook actuó.

En `utils/fs_tools.py`, `_hook_py_compile`, donde hoy solo hace
`return resultado + f"\n⚠ SINTAXIS: {detalle}"`: AGREGAR antes del return
un print en terminal (importá `colorear` de `utils.terminal` — verificá
que no haya import circular: terminal no importa fs_tools):

```python
            print(colorear(f"  [hook] ⚠ SINTAXIS devuelta al modelo: "
                           f"{detalle.splitlines()[-1] if detalle else path}", "aviso"), flush=True)
```

(la ÚLTIMA línea del detalle es la que dice línea/archivo; flush como los
otros avisos del chat.)

Test: en tests/test_smoke.py, el/los tests existentes del hook py_compile
(buscalos por "py_compile" o "SINTAXIS") — agregarles assert del print
con capsys: la línea "[hook] ⚠ SINTAXIS" aparece en stdout cuando el hook
dispara, y NO aparece cuando compila bien.

## exp/5 — search_files con conteo exacto

`SEARCH_MAX_FILES = 50` (fs_tools.py:22). La función search_files hoy
trunca la lista a 50 y el modelo ve "50+" sin saber cuántos son.

Buscar la función `search_files` y donde aplica el tope: cuando hay MÁS
resultados que el tope, el string de resultado debe decir el CONTEO
EXACTO y la sugerencia, p. ej.:

`... y N archivos más (mostrando 50 de TOTales; para el listado completo: run_command 'find <path> <glob>' ya es solo-lectura auto)`

— AJUSTÁ el texto al formato real de salida de la función (mirá cómo
arma el string hoy y respétalo; lo importante: número exacto + que el
tope es de MUESTRA, no del conteo). El conteo total se calcula ANTES de
truncar (la búsqueda ya lo sabe o puede contar la lista completa).

Test: search_files (o la función pura que arma el string, si conviene
extraerla) con un directorio fake de >50 archivos (tmp_path con 55
archivos vacíos) → el resultado contiene "55" y "50". Con <50 → sin el
aviso de truncado.
