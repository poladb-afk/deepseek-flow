# Spec verificada: robustez del banco (2026-10-07, segunda tanda)

Fuente: zoom de auditoría sobre los dos hallazgos de la tanda de deuda
(marcador `veto` roto en ambas direcciones; tope de 6 HITL que cuelga el
turno sin registrar la causa). Verificado en código y en los transcripts
de las corridas del día. Principio de la tanda: **nada de parches
hardcodeados** — cada fix se ancla a un contrato existente (la línea que
el código imprime, el YAML del escenario, la semántica del shell) y trae
su candado de test contra líneas REALES.

Reglas generales: comentarios en español, churn mínimo, estilo del
archivo. Verificación: `python3 -m pytest tests/ -q` EXACTO (auto, sin
pipes ni 2>&1 ni &&). ruff NO lo corras: la auditoría lo corre.

---

## Fix 10 — marcadores de veto anclados a las líneas impresas reales

**Problema** (`banco/banco.py`, dict `MARCADORES`): `"veto": r"PROHIBID|[Vv]etad"`
es una palabra suelta sin anclar. Medido hoy (transcripts en
salidas/banco/): 6 falsos positivos en 3 turnos — `PROHIBIDOS` (la
constante de modules/db.py) dentro de diffs preview de edit_file, "vetado"
en prosa ecoada de instrucciones. Y el falso negativo: el veto de SEGURIDAD
(`ERROR: comando prohibido por la denylist de seguridad`, modules/coding.py,
lowercase) nunca matchea `PROHIBID` (case-sensitive) — además ese texto
viaja solo al modelo como resultado de tool, NO se imprime en terminal,
así que ningún anclaje a él podría contarlo: hay que imprimirlo primero.
El único veto que hoy matchea es el del supervisor.

**Fix (dos partes, mismo contrato):**

(a) `modules/coding.py`, `_vetar_comando_prohibido`: ANTES de devolver el
veto, imprimir el aviso en terminal — paridad de observabilidad con el
hook de sintaxis (`_hook_py_compile` imprime `[hook] ⚠ SINTAXIS…`, exp/3:
"ninguna acción del hook es invisible"). Estilo del archivo:

```python
from utils.terminal import colorear  # (sumar al import existente de highlight_diff)
...
print(colorear("  [denylist] comando vetado (daño irreversible): "
               "no se ejecutó ni se pidió aprobación", "error"), flush=True)
```

(b) `banco/banco.py`, `MARCADORES`: reemplazar la clave `"veto"` por DOS
claves ancladas a prefijos de línea, como ya lo están `[laya]`, `[voto]`,
`[DSML]`:

```python
"veto_l8": r"\[laya\] \S+ está vetada|\[L8\] \S+ vetada",
"veto_denylist": r"\[denylist\]",
```

(el `\[denylist\]` es el prefijo del print nuevo; el ancla es el formato
impreso, no una palabra del vocabulario).

**Candado** (`tests/test_banco.py`, sección de marcadores):
1. Fixtures POSITIVOS = líneas textuales reales: `"  [laya] search_files está vetada (dos fallos) → elige DeepSeek"` (supervisor.py), `"  [L8] db_schema vetada y elegida igual → finish"` (supervisor.py) y el print nuevo de coding.py, verbatim.
2. Fixture NEGATIVO nuevo (la convención "Fixtures REALES" que la sección
   de scope ya declara): las DOS líneas contaminantes medidas hoy —
   `"+        if PROHIBIDOS.search(limpia):"` (diff preview) y
   `"vetado por la denylist del driver; lo documenta la auditoría)"` (eco
   de instrucción) — NO matchean ningún marcador (`contar_marcadores`
   sobre cada una da {} o sin las claves de veto).
3. El fixture viejo `"comando PROHIBIDO por la denylist dura"` (mayúsculas
   que no existen en producción) se ELIMINA.

**Test del print** (`tests/test_smoke.py`): el test existente de la
denylist de run_command se extiende (o se agrega uno al lado) para
capturar stdout (capsys) y afirmar que el veto imprime la línea
`[denylist]`.

---

## Fix 11 — tope HITL: agotamiento elegante + knob por escenario

**Problema** (`banco/banco.py`, `MAX_HITL_POR_TURNO = 6` y el while del
turno): al agotar el presupuesto el driver ENMUDECE — el prompt (s/n)
queda colgado, el turno gira hasta su timeout (hasta 20 min de espera
muerta), `estado="timeout"` corta el escenario ENTERO (break) y no existe
ningún evento que registre que la causa fue el tope. Medido: dos turnos
colgados hoy (el 7º prompt era siempre la verificación pytest), y CINCO
turnos "aplicar" históricos (exp3/5/7×2) terminando exactamente en 6/6 —
al borde del ruptor.

**Fix (dos piezas):**

(a) **Knob declarativo por turno**: `max_hitl: N` en el YAML del turno;
default = MAX_HITL_POR_TURNO (6), compatibilidad total. Validación en
`cargar_escenario`: si `max_hitl` está presente debe ser int >= 1
(ValueError con el path, como el chequeo de ids duplicados).

(b) **Agotamiento elegante** en el while de `correr`: cuando hay prompt
HITL pendiente y `hitl_dados >= tope`, en vez de enmudecer:
```python
# presupuesto agotado: rechazar y registrar, no colgar (default seguro —
# el rechazo es feedback para el modelo, que cierra el turno en prosa)
time.sleep(0.5)
chat.enviar("n")
evento("hitl-tope", {"n": <n_turno>, "id": <tid>, "prompt": <última línea, recortada a ~120 chars>})
ventana += chat.nuevo; chat.nuevo = ""
continue
```
El evento `hitl-tope` es la medición que hoy no existe (causa registrada,
no timeout mudo). "n" y no "s": rubber-stamping más allá del tope anularía
el rail de seguridad. Contar también cuántos `hitl-tope` hubo en el turno
y sumarlos al detalle del `turno-fin` (p. ej. `"hitl_tope": k` junto a
`"hitl"`).

**Candado** (`tests/test_banco.py`):
1. `cargar_escenario` valida `max_hitl`: entero válido pasa (y llega en el
   dict), `"0"`/`"x"`/`-1` → ValueError.
2. (El comportamiento E2E del agotamiento lo verifica la auditoría con el
   escenario `tope-hitl-smoke.yaml`, LLM real — la pieza impura no se
   simula.)

---

## Fix 12 — policy: `2>&1` es lectura, no redirección que escribe

**Problema** (`utils/policy.py`, `_PELIGRO_SHELL = r">|<|\$\(|`|\bxargs\b"`):
el regex caza el `>` de `2>&1`, que NO escribe nada (duplica stderr al
stdout ya capturado). Consecuencia medida: `python3 -m pytest … 2>&1 | tail -20`
— la forma natural de verificar — degrada a `preguntar` aunque ambos
segmentos sean solo-lectura whitelisted; quema presupuesto HITL del banco
y fricción de más en el chat interactivo.

**Fix (regla semántica, no excepción puntual)**: en `_segmento_es_auto`,
quitar las ocurrencias del token `2>&1` ANTES del escaneo de
`_PELIGRO_SHELL`. La justificación (va en el comentario): `2>&1` es una
duplicación de descriptor de LECTURA — quitarlo no puede ocultar ninguna
escritura, porque toda redirección REAL conserva su carácter cazable:
`> f` queda, `2> f` queda, `2>&1 > f` queda como `> f`, `> f 2>&1` queda
como `> f`. La whitelist de prefijos NO se toca: sigue mandando qué
comandos son auto; esto solo corrige un falso "escritor" en el escaneo.

**Candado** (`tests/test_smoke.py`, junto a los tests de policy
existentes) — la matriz que demuestra que ninguna escritura se escapa:
1. `python3 -m pytest tests/ -q 2>&1` → auto
2. `python3 -m pytest tests/ -q 2>&1 | tail -20` → auto
3. `grep algo archivo 2>&1` → auto
4. `echo hola > f` → preguntar (redirección real)
5. `echo hola > f 2>&1` → preguntar (el `> f` sobrevive al strip)
6. `comando 2> err.txt` → preguntar (fd a archivo: no es `2>&1`)
7. `comando 2>&1 > f` → preguntar (orden importa: queda `> f`)
8. `cat x | head -3 2>&1` → auto
El docstring de policy.py se actualiza con la regla (misma sección que
explica redirección/sustitución).
