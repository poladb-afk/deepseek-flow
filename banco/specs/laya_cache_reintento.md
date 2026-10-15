# Fix: el caché de errores de Laya envenena la sesión entera

Medido (revisión del harness, 2026-10-13): 31/37 decisiones del router en
producción salieron "respuesta inválida: sin detalle de Laya" — el checkpoint
no cargó (presión de RAM en procesos frescos del banco) Y el fallo quedó
cacheado PARA SIEMPRE dentro del proceso: un OOM transitorio degrada el resto
de la sesión sin un solo reintento. La flywheel de exp/43 solo recolecta
cuando el checkpoint carga — este fix multiplica el valor de todo lo demás.

## El problema exacto (`utils/laya.py`, `agente()`)

```python
_errores = {}  # setting → error
...
                except Exception as e:  # sin modelo local: degradar, no romper
                    _errores[clave] = f"{type(e).__name__}: {e}"
    if clave in _errores and clave not in _agentes:
        raise RuntimeError(f"laya no disponible: {_errores[clave]}")
```

Un solo fallo de `laya.load` (transitorio o no) entra a `_errores` y NUNCA
se reintenta en el proceso.

## Fix EXACTO — el error VENCE

1. `_errores` guarda `(ts, msg)` con `time.monotonic()` al fallar.
2. En `agente()`, antes del raise: si el error tiene menos de
   `LAYA_ERROR_COOLDOWN` segundos (setting, default 60, entero a prueba de
   typos con `_entero`), se lanza el RuntimeError cacheado (rápido, como
   hoy); si VENCIÓ, se borra del caché y se reintenta la carga en esa misma
   llamada (la estructura de doble-chequeo con `_lock` se mantiene: el
   borrado del error vencido va DENTRO del lock, antes del try).
3. El raise conserva el mensaje (que incluya la edad del error ayuda a
   debuggear: p. ej. `laya no disponible (hace 34s): OOM ...`).
4. Los aciertos limpian cualquier error residual de esa clave (si la carga
   entra a `_agentes`, sacar la clave de `_errores`).

Un checkpoint roto permanente pasa a reintentarse una vez por cooldown —
costo aceptable (`Path.exists` + fallo rápido de `laya.load`); un OOM
transitorio se recupera al minuto. La ley de degradación no cambia: quien
llama sigue tratando el RuntimeError como "sin Laya".

## Tests (nuevos, sin modelo real)

Estilo: inyectar un módulo `lay` falso en `sys.modules`
(`monkeypatch.setitem(sys.modules, "laya", SimpleNamespace(load=...))`) y
manipular el reloj — para eso el ts es `time.monotonic()`, que también se
puede monkeypatchear, o se puede vencer el error escribiendo un ts viejo
directo en `utils.laya._errores` (más simple y honesto: el test siembra el
estado). Limpiar `_agentes`/`_errores`/`_uso` entre tests (fixture).

1. **Fallo transitorio se recupera**: load falla 1ª vez → RuntimeError; el
   test siembra el ts vencido (o cooldown=0 por setting); 2ª llamada con
   load que ahora sí → devuelve el agente y `_errores` queda limpio.
2. **Dentro del cooldown NO reintenta**: load falla; 2ª llamada inmediata →
   RuntimeError SIN volver a llamar load (un contador en el fake lo clava).
3. **El éxito limpia el error residual**: clave con error vencido + agente
   cargado → sin RuntimeError.
4. `LAYA_ERROR_COOLDOWN` con basura ("sesenta") → avisa y usa 60 (patrón
   `_entero`).

## Candado final

`python3 -m pytest tests/ -q` verde (hoy 334) y ruff limpio. No tocar
`preguntar`/`preguntar_detalle`/`disponible` ni la ley de eviction
(`MAX_EN_PROCESO` sigue como está).
