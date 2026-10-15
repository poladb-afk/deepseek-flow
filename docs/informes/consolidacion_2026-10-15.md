# Consolidación deepseek-flow — 2026-10-15

Código **antes / después** de cada defecto que estaba abierto, con la evidencia medida en el zip actual.
Los cambios están en `consolidacion_2026-10-15.patch` (20 archivos). Se aplica limpio con `patch -p1` sobre el zip.

## Gate

| | Antes | Después |
|---|---|---|
| `ruff check .` | ✅ | ✅ All checks passed |
| `pytest tests/` | 427 passed | **471 passed**, 0 failed, 8 skipped |
| `tests/test_consolidacion.py` (44 casos nuevos) contra el árbol **viejo** | — | **35 fallan** (cada test detecta su defecto) |
| `tests/test_consolidacion.py` contra el árbol **nuevo** | — | **44/44 pasan** |
| Settings usados y no documentados | 18 | **0** |
| Settings documentados dos veces | 1 (`LAYA_UNSURE_HIGH`) | **0** |

## Evidencia: la misma sonda, antes y después

| Defecto | Antes | Después |
|---|---|---|
| 1 prefiltro sin Laya | 8 líneas · aviso Laya=True | 12 líneas · aviso Laya=False |
| 10 umbral NaN | ('directo', 'p(directo)=0.510 >= umbral nan') | ('herramientas', 'p(directo)=0.510 < umbral 0.85') |
| 11 mcp-server | crudo | por run_tool_call |
| 2 evals salida fuera | ESCRIBIÓ FUERA \| Informe de evals generado: /tmp/tmp4z74p7tv/fuera/evals_2026 | bloqueado \| ERROR: ruta fuera de los directorios permitidos: /mnt/data/c |
| 3 resumen sigue symlink | ESCRIBIÓ FUERA | bloqueado |
| 4 memory_search sigue symlink | FILTRA | bloqueado |
| 5 hook PRE que lanza | ABIERTO | CERRADO (no corrió) |
| 6 presupuesto agotado + tool nativa | acción=tool ejecutó=False | acción=answer ejecutó=False |
| 7 sql | default=50 filas \| LIMIT -1 → 200 filas \| -- limit → 200 filas | default=50 filas \| LIMIT -1 → ERROR: LIMIT debe ser un entero positivo \| -- limit → ERROR: sin comentarios S |
| 8 baseline con bench degradado | EXC TypeError | SIN BENCH |
| 9 memory_search {} | ERROR: TypeError: memory_search() missin | Biblioteca de memoria: - n00.md - n01.md |
| est. rm -rf / --no-preserve-root | no | vetado |
| est. tool huérfano | aceptado | detectado |
| est. traza exit 1 / RECHAZADO | ok=True / ok=True | ok=False / ok=False |

> En la fila 6, el «ejecutó=False» del árbol viejo es porque la sonda corre solo `AgentStep`; lo que delata el defecto es `acción=tool`, que en el chat lleva a `ExecuteTools`.

---

## Parte 1 — Defectos

### 1. 🔴 Prefiltro sin Laya recortaba y decía «Laya»

**Archivo:** `utils/contexto.py` — Sin juicio del modelo devolvía los primeros N y `memory_search`/`rag_search` lo anunciaban como prefiltro. Viola la regla de hierro «no perder recall».

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
con una sola unidad, o sin Laya disponible, devuelve `unidades` intactas:
    el default seguro es no perder recall."""
        return unidades[:max_unidades]  # sin juicio: no se pierde nada de más
```

</td><td valign="top">

```python
con una sola unidad, o sin juicio de Laya (no disponible o falla),
    devuelve `unidades` intactas — TODAS, no las primeras N: el default
    seguro es no perder recall."""
        # sin juicio NO se recorta: devolver los primeros N perdía recall en
        # silencio y el llamador lo anunciaba como "prefiltro Laya" (medido:
        # 12 notas → 8 sin Laya cargada). La regla de hierro es no-op.
        return unidades
```

</td></tr></table>

### 2. 🔴 `evals(salida=…)` escribía fuera de las raíces

**Archivo:** `modules/evals.py` — `dir_runs` pasaba por `_resolve`; `salida` (elegida por el modelo) no.

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
destino_dir = salida or DIR_SALIDA
```

</td><td valign="top">

```python
# la carpeta de salida la elige el MODELO: pasa por la misma contención
    # que dir_runs (medido: salida=/tmp/... escribía fuera de las raíces)
    destino_dir, err = _arg(salida, DIR_SALIDA)
    if err:
        return f"ERROR: {err}"
```

</td></tr></table>

### 3/4. 🟠 Memoria seguía symlinks (lectura y escritura)

**Archivo:** `modules/memoria.py` — `_archivos_md` no aplicaba `sin_enlaces`; `guardar_resumen_sesion` usaba `exists()` (False para symlink colgante) y no tenía la guarda de `memory_save`. Además `query` pasa a ser opcional como dice el schema.

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
(sin líneas: solo se agregó código)
```

</td><td valign="top">

```python
import os
```

</td></tr></table>
<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
return sorted(p for p in raiz.glob("*.md") if p.is_file())
def memory_search(query):
```

</td><td valign="top">

```python
# misma política que fs_tools.sin_enlaces: la biblioteca no sigue enlaces
    # (medido: un memoria/enlace.md -> /otro/lado devolvía contenido externo)
    return sorted(p for p in raiz.glob("*.md") if p.is_file() and not p.is_symlink())
def memory_search(query=None):
```

</td></tr></table>
<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
MEMORIA_PREFILTRO=0 o sin Laya, devuelve todos: la memoria completa,
    como siempre."""
```

</td><td valign="top">

```python
MEMORIA_PREFILTRO=0 o sin juicio de Laya, devuelve todos y False: el
    aviso "[prefiltro Laya: …]" aparece SOLO si Laya realmente puntuó."""
```

</td></tr></table>
<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
if raiz not in destino.resolve().parents:
```

</td><td valign="top">

```python
if destino.is_symlink() or raiz not in destino.resolve().parents:
```

</td></tr></table>
<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
if destino.exists():
        while destino.exists():
```

</td><td valign="top">

```python
# lexists, no exists: un symlink COLGANTE da exists()=False y write_text
    # lo seguía, creando el archivo fuera de memoria/ (medido)
    if os.path.lexists(destino):
        while os.path.lexists(destino):
    # misma guarda que memory_save: el destino resuelto queda DENTRO de memoria/
    if raiz not in destino.resolve().parents:
        return None
```

</td></tr></table>

### 5. 🟠 Hook PRE que lanza dejaba pasar la tool

**Archivo:** `utils/fs_tools.py` — Una guarda de seguridad que falla ahora veta (fail-closed). Los POST siguen fail-open.

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
# post: un hook NUNCA rompe la ejecución — si lanza, se ignora.
```

</td><td valign="top">

```python
# post, salvo que un PRE que lanza VETA (fail-closed): es una guarda.
```

</td></tr></table>
<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
# devuelve None, no opina. Un hook que lanza no rompe nada: se ignora.
        except Exception:  # noqa: BLE001
            veto = None
```

</td><td valign="top">

```python
# devuelve None, no opina. Un hook PRE que LANZA falla CERRADO: es una
    # guarda de seguridad y "no pude decidir" no puede significar "adelante"
    # (antes se ignoraba y la implementación corría igual). Los POST siguen
    # siendo fail-open: enriquecen, no autorizan.
        except Exception as e:  # noqa: BLE001
            veto = (f"ERROR: la guarda previa de {fn['name']} falló "
                    f"({type(e).__name__}); la herramienta no se ejecutó.")
```

</td></tr></table>

### 6. 🟡 Presupuesto agotado + tool call nativa / stream cortado

**Archivo:** `nodes.py` — Con las tools retiradas, una tool call nativa se descarta (la mitad DSML ya estaba cerrada).

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
(sin líneas: solo se agregó código)
```

</td><td valign="top">

```python
if tools is None and getattr(exec_res, "tool_calls", None):
            # ley L8 por el canal NATIVO (la mitad DSML ya estaba cerrada en
            # exp/12): retiradas las tools, una tool call que el modelo emita
            # igual NO se ejecuta (medido: tool_rounds=99 → acción "tool" y la
            # implementación corría). Mismo mensaje honesto que el DSML.
            print(colorear("  [L8] tool calls con las tools retiradas: IGNORADAS", "aviso"))
            exec_res.tool_calls = None
            if not (exec_res.content or "").strip():
                exec_res.content = (MENSAJE_DSML_AGOTADO if getattr(self, "ofrece_tools", True)
                                    else MENSAJE_DSML_SIN_TOOLS)
```

</td></tr></table>

### 6b. 🟡 Stream cortado despachaba tool calls truncadas

**Archivo:** `utils/call_llm.py` — Tras Ctrl+C o corte de red no viaja ninguna tool call; nunca viaja un fragmento sin `name`/`id`.

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
tool_calls = [
```

</td><td valign="top">

```python
# Un stream CORTADO (Ctrl+C o red) no despacha tool calls: sus argumentos
    # pueden estar truncados y el usuario pidió parar (medido: tras Ctrl+C la
    # llamada se conservaba y se ejecutaba). Tampoco viaja un fragmento sin
    # nombre o sin id ("herramienta desconocida: None").
    tool_calls = [] if cortado else [
        if acum["name"] and acum["id"]
```

</td></tr></table>

### 7. 🟡 `sql` sin tope efectivo

**Archivo:** `modules/db.py` — `LIMIT -1`, `LIMIT 0-1` y comentarios evadían el tope. Ahora: conexión `mode=ro`, sin comentarios, LIMIT entero positivo literal y techo duro de 1000 filas.

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
con = sqlite3.connect(ruta, timeout=5)
```

</td><td valign="top">

```python
# solo lectura TAMBIÉN en la conexión (mode=ro): el filtro de palabras es
    # la primera capa, no la única
    con = sqlite3.connect(f"{Path(ruta).resolve().as_uri()}?mode=ro", uri=True, timeout=5)
```

</td></tr></table>
<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
(sin líneas: solo se agregó código)
```

</td><td valign="top">

```python
# CADA cláusula LIMIT debe ser un entero positivo literal, sin aritmética
# (SQLite acepta expresiones: LIMIT -1 o LIMIT 0-1 = sin límite)
_RE_LIMIT_NO_POSITIVO = re.compile(r"\blimit\b(?!\s+[1-9]\d*\b(?!\s*[-+*/(]))", re.IGNORECASE)
_RE_COMENTARIO = re.compile(r"--|/\*")
MAX_FILAS_DURO = 1000  # techo absoluto aunque la consulta traiga su LIMIT
```

</td></tr></table>
<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
filas = con.execute(consulta).fetchall()
```

</td><td valign="top">

```python
# un comentario puede esconder la cláusula que se escanea
        # (medido: "select * from t -- limit" devolvía 200 filas sin tope)
        if _RE_COMENTARIO.search(limpia):
            return "ERROR: sin comentarios SQL (-- o /* */)"
        # LIMIT presente pero no positivo (LIMIT -1 = sin límite en SQLite)
        if _RE_LIMIT_NO_POSITIVO.search(limpia):
            return "ERROR: LIMIT debe ser un entero positivo"
            filas = con.execute(consulta).fetchmany(MAX_FILAS_DURO)
```

</td></tr></table>

### 8. 🟡 `comparar_baseline` reventaba con bench degradado

**Archivo:** `evals.py` — `None - float` → `TypeError`. Ahora veredicto `SIN BENCH`.

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
(sin líneas: solo se agregó código)
```

</td><td valign="top">

```python
if nuevo.get("score") is None:
        # bench degradado (sin Laya o sin test): nada que comparar — antes
        # reventaba con TypeError None - float si había baseline numérico
        comparacion["veredicto"] = "SIN BENCH"
        return comparacion
```

</td></tr></table>

### 10. 🟡 Umbral `NaN` aprobaba «directo»

**Archivo:** `utils/laya_routing.py` — `p < nan` es False. Ahora todo umbral fuera de [0,1] o no finito usa el default con aviso.

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
(sin líneas: solo se agregó código)
```

</td><td valign="top">

```python
def _umbral(nombre, default):
    """Un umbral de probabilidad VÁLIDO: finito y en [0, 1]. Cualquier otra
    cosa (typo, NaN, 1.5) usa el default — medido: LAYA_UNSURE_HIGH=nan hacía
    que `p < nan` diera False y el router eligiera directo."""
    from utils.call_llm import _setting

    try:
        valor = float(_setting(nombre, str(default)))
    except (TypeError, ValueError):
        return default
    if valor != valor or not 0.0 <= valor <= 1.0:
        print(f"  [laya] {nombre}={valor!r} fuera de [0, 1] -> {default}")
        return default
    return valor
```

</td></tr></table>
<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
try:
        umbral = float(_setting("LAYA_UNSURE_HIGH", "0.85"))
    except (TypeError, ValueError):
        umbral = 0.85
```

</td><td valign="top">

```python
umbral = _umbral("LAYA_UNSURE_HIGH", 0.85)
```

</td></tr></table>
<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
try:
        umbral = float(_setting("LAYA_UNSURE_HIGH_VOTO", "0.7"))
    except (TypeError, ValueError):
        umbral = 0.7
```

</td><td valign="top">

```python
umbral = _umbral("LAYA_UNSURE_HIGH_VOTO", 0.7)
```

</td></tr></table>

### 11. 🟡 `mcp-server` salteaba los hooks

**Archivo:** `mcp_server.py` — Se registraba la implementación cruda. Ahora se envuelve por `run_tool_call`, conservando la firma (FastMCP arma el schema de ahí).

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
(sin líneas: solo se agregó código)
```

</td><td valign="top">

```python
def envolver(nombre, fn, impls):
    """La función que se registra en FastMCP: misma firma que la implementación
    (FastMCP arma el schema desde ahí) pero el cuerpo despacha por
    run_tool_call — el ÚNICO camino con HOOKS_PRE (denylist) y HOOKS_POST.
    Antes se registraba la implementación cruda y un run_command expuesto
    salteaba la denylist."""
    import functools
    import inspect
    import json

    @functools.wraps(fn)
    def envuelta(**kwargs):
        tc = {"id": f"mcp-{nombre}", "type": "function",
              "function": {"name": nombre, "arguments": json.dumps(kwargs, ensure_ascii=False)}}
        return fs_tools.run_tool_call(tc, impls)["content"]

    envuelta.__signature__ = inspect.signature(fn)
    return envuelta
```

</td></tr></table>
<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
server.tool(impls[nombre], name=nombre, description=descripciones.get(nombre, ""))
```

</td><td valign="top">

```python
server.tool(envolver(nombre, impls[nombre], impls), name=nombre,
                    description=descripciones.get(nombre, ""))
```

</td></tr></table>

### E1. 🟡 Un módulo roto tiraba el chat entero

**Archivo:** `modules/__init__.py` — `discover()` saltea con aviso el módulo que no importa y avisa colisiones de nombres.

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
module = importlib.import_module(f"{__name__}.{info.name}")
        impls.update(getattr(module, "IMPL", {}))
```

</td><td valign="top">

```python
"""Un módulo que falla al importar se SALTEA con aviso (antes tiraba el
    chat entero: "quitar = borrar el archivo" también debe valer para un
    archivo roto). Un nombre de tool repetido entre módulos también avisa:
    el segundo pisaba al primero en silencio."""
    import sys

        try:
            module = importlib.import_module(f"{__name__}.{info.name}")
        except Exception as e:  # noqa: BLE001 (un módulo roto no tumba el chat)
            print(f"[módulos] {info.name} no cargó ({type(e).__name__}: {e}) → se saltea",
                  file=sys.stderr)
            continue
        nuevos = getattr(module, "IMPL", {})
        for nombre in set(nuevos) & set(impls):
            print(f"[módulos] {info.name} redefine la tool '{nombre}'", file=sys.stderr)
        impls.update(nuevos)
```

</td></tr></table>

### E2. 🟡 `validar_historial` aceptaba `tool` huérfano

**Archivo:** `utils/compaccion.py` — 5º invariante: todo `tool` responde a un tool_call del assistant previo.

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
`validar_historial` verifica los cuatro. Se corre en los tests ANTES y
```

</td><td valign="top">

```python
5. Ningún `tool` huérfano: responde a un tool_call del assistant previo.
`validar_historial` verifica los cinco. Se corre en los tests ANTES y
```

</td></tr></table>
<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
(sin líneas: solo se agregó código)
```

</td><td valign="top">

```python
abiertos = set()  # ids del último assistant con tool_calls aún sin respuesta
        if rol == "tool":
            # 5º invariante (contrato de la API): todo tool responde a un
            # tool_call del assistant inmediatamente anterior
            if m.get("tool_call_id") not in abiertos:
                fallas.append(f"[{i}] tool huérfano: {m.get('tool_call_id')!r} sin assistant que lo pida")
            abiertos.discard(m.get("tool_call_id"))
        elif rol == "assistant" and m.get("tool_calls"):
            abiertos = {tc.get("id") for tc in m["tool_calls"] if isinstance(tc, dict)}
        else:
            abiertos = set()
```

</td></tr></table>

### E3. 🟡 La traza marcaba `exit 1` y `RECHAZADO` como ok

**Archivo:** `nodes.py` — Nueva `resultado_ok()`.

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
(sin líneas: solo se agregó código)
```

</td><td valign="top">

```python
_EXIT_NO_CERO = re.compile(r"^exit (?!0\b)-?\d+")


def resultado_ok(contenido):
    """Lo que la traza registra como ok/error de una tool. Un RECHAZADO del
    humano o un comando con exit != 0 NO son éxitos (medido: los dos quedaban
    'ok' en .runs y el linter/costos los contaban como sanos)."""
    contenido = contenido or ""
    return not (contenido.startswith(("ERROR", "RECHAZADO")) or _EXIT_NO_CERO.match(contenido))
```

</td></tr></table>
<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
ok = not r["content"].startswith("ERROR")
```

</td><td valign="top">

```python
ok = resultado_ok(r["content"])
```

</td></tr></table>

### E4. 🟡 `rm -rf / --no-preserve-root` no se vetaba

**Archivo:** `modules/coding.py` — El flag después de la ruta ahora también se reconoce.

<table>
<tr><th width="50%">❌ Antes</th><th width="50%">✅ Después</th></tr>
<tr><td valign="top">

```python
r"(?:/\*?|~/?\*?|\$HOME/?\*?|/\.\*?)\s*(?:$|[;&|\n])"  # /, /*, ~, $HOME
```

</td><td valign="top">

```python
r"(?:/\*?|~/?\*?|\$HOME/?\*?|/\.\*?)(?:\s+--no-preserve-root)?\s*(?:$|[;&|\n])"  # /, /*, ~, $HOME
```

</td></tr></table>

---

## Parte 2 — Documentación alineada al código

| Archivo | Cambio |
|---|---|
| `README.md` | «Capacidades (24)» → **29 tools**; fila `request_human_input`; supervisor v2 descrito como es (tool-calling nativo, no Laya); `ver_pdf` usa `pdftoppm`, no Files API; `memory_search` con `query` opcional y sin symlinks; subcomandos `bench_juez`, `replay`, `resume`; árbol de `utils/` al día |
| `.env.example` | quitado el `LAYA_UNSURE_HIGH=0.7` duplicado y contradictorio; **18 settings documentados** (`PREFETCH*`, `THREAD_PERSIST`, `THREADS_DIR`, `LAYA_MODEL_RIESGO`, `RIESGO_*`, `LAYA_CALIBRACION_VOTO`, `LAYA_ALPHA_VOTO`, `LAYA_ERROR_COOLDOWN`, `JUEZ_LOTE_CONCURRENCIA`, `DB_PATH`, `SEARCH_PROVIDER`, `TRACE`, `NO_COLOR`, `COLOR`, `SONDA_LAYA_CKPT`); nota de rango válido de umbrales |
| `requirements.txt` | `requests>=2.31` y `ruff==0.17.1` (versión fijada del gate) |
| `docs/roadmap.md` | ítem «3. exp/50» duplicado → uno; nota de que el no-op del prefiltro recién se cumple desde hoy |
| `docs/design.md` | hooks PRE documentados como fail-closed; la segunda sección «Sanitizado…» pasa a subsección del episodio (ya no hay dos títulos iguales) |
| Docstrings | `utils/compaccion.py` (5 invariantes), `utils/contexto.py` y `modules/memoria.py` (el no-op real) |

## Tests modificados (2) — el contrato cambió a propósito

| Test | Antes afirmaba | Ahora afirma |
|---|---|---|
| `test_elegir_por_laya_sin_modelo_es_noop` | sin Laya → `["a","b"]` (los primeros N: el defecto, cercado como si fuera correcto) | sin Laya → **todas** |
| `test_hook_pre_que_lanza_no_rompe` → `test_hook_pre_que_lanza_falla_cerrado` | la implementación corre igual | **no corre**; vuelve `ERROR: la guarda previa … falló` |

## Fuera de alcance (sigue pendiente)

- Deduplicar `_approve`/`YES`/`PREVIEW_LINES` (coding/escritura) y las constantes `DIR_RUNS`/`DIR_SALIDA`.
- Juntar los 17 archivos de `docs/informes/` en un estado vivo + `archivo/`.
- CI que corra `calidad.sh`.
- `escribir_salida` pisa archivos dentro de las raíces sin HITL (es diseño declarado; decisión tuya).
- Cobertura baja de `resume.py`, `mcp_client`, `rag`, `banco/banco.py`.
