# deepseek-flow — código mal vs. código bien

Revisión del 2026-10-15. Cada bloque muestra **el código actual a la izquierda** y **la corrección a la derecha**, con la evidencia medida.
Las correcciones están aplicadas y verificadas sobre una copia del repo; el diff completo está en `deepseek-flow-fixes.patch`.

## Resultado global

| Gate | Antes | Después |
|---|---|---|
| `ruff check .` | ✅ verde | ✅ verde |
| `pytest tests/` | ❌ **9 failed**, 282 passed, 5 skipped | ✅ **326 passed**, 0 failed, 9 skipped |
| Tests nuevos de seguridad | — | `tests/test_policy_bypass.py` (39 casos) |

Los 9 skips son legítimos: dependen de `ddgs`, del checkpoint de Laya o del `router_flow_test.jsonl` de bmo. En tu máquina, con todo eso presente, corren.

## Índice

1. 🔴 Bypass del HITL graduado — `utils/policy.py`
2. 🔴 Denylist dura demasiado estrecha — `modules/coding.py`
3. 🟠 `run_command` auto ignora las raíces permitidas — `modules/coding.py`
4. 🟡 Ruta fija en `evals.py`
5. 🟡 Memoria anclada al CWD — `modules/memoria.py`
6. 🟡 Tests no herméticos — `tests/test_smoke.py`
7. ➕ Tests nuevos

---

## 1. 🔴 Bypass del HITL graduado

### `clasificar()` no parte por todos los separadores ni mira flags

**Archivo:** `utils/policy.py`

El shell ejecuta `\n` y `&` como separadores de comandos, pero `clasificar()` solo partía por `&&`, `|` y `;`. Resultado: se colaba un `rm -rf` en un segmento invisible y todo salía **auto**, es decir sin `s/n`. Además, varios comandos de la whitelist escriben o ejecutan según sus flags.

<table>
<tr><th width="50%">❌ Código actual (mal)</th><th width="50%">✅ Código corregido (bien)</th></tr>
<tr>
<td valign="top">

```python
_PELIGRO_SHELL = re.compile(r">|<|\$\(|`|\bxargs\b")


def _segmento_es_auto(segmento):
    ...
    segmento = segmento.replace("2>&1", "")
    if _PELIGRO_SHELL.search(segmento):
        return False
    return any(_empieza_con(tokens, prefijo)
               for prefijo in _WHITELIST_PREFIJOS)


def clasificar(comando):
    ...
    # Partimos por &&, | y ;
    segmentos = re.split(r"&&|\||;", comando)
    # ⚠ falta: "\n" y "&" simple — el shell los
    #   ejecuta como separadores y acá no se parten
    # ⚠ falta: flags que vuelven escritor a un
    #   comando "de lectura" (find -delete, sort -o…)
```

</td>
<td valign="top">

```python
_PELIGRO_SHELL = re.compile(r">|<|\$\(|`|\bxargs\b")

# TODOS los separadores que el shell ejecuta
_SEPARADORES = re.compile(r"&&|\|\||\||&|;|\n|\r")

# Flags que vuelven escritor/ejecutor a un
# comando de la whitelist
_FLAGS_PELIGROSOS = {
    "find": ("-delete", "-exec", "-execdir", "-ok",
             "-okdir", "-fprint", "-fprint0",
             "-fprintf", "-fls"),
    "sort": ("-o", "--output"),
    "git": ("--output", "--ext-diff", "--textconv"),
    "pytest": ("-p", "--basetemp", "--rootdir",
               "-c", "--confcutdir"),
}


def _segmento_es_auto(segmento):
    ...
    segmento = segmento.replace("2>&1", "")
    if _PELIGRO_SHELL.search(segmento):
        return False
    if _tiene_flag_peligroso(tokens):
        return False
    return any(_empieza_con(tokens, prefijo)
               for prefijo in _WHITELIST_PREFIJOS)


def _tiene_flag_peligroso(tokens):
    if not tokens:
        return False
    base = ("pytest"
            if tokens[:3] == ["python3", "-m", "pytest"]
            else tokens[0])
    flags = _FLAGS_PELIGROSOS.get(base, ())
    for tok in tokens[1:]:
        for flag in flags:
            if tok == flag or tok.startswith(flag + "="):
                return True
            # forma corta pegada: -osalida.txt
            if (len(flag) == 2 and tok.startswith(flag)
                    and not tok.startswith("--")):
                return True
    return False


def clasificar(comando):
    ...
    # 2>&1 primero: su "&" NO es separador
    segmentos = _SEPARADORES.split(
        comando.replace("2>&1", ""))
```

</td>
</tr>
</table>

**Evidencia (salida real de `clasificar()` antes y después):**

| Comando | Antes | Después |
|---|---|---|
| `ls\nrm -rf ~` | 🟢 auto | 🔴 confirmar_doble |
| `cat a & rm -rf b` | 🟢 auto | 🔴 confirmar_doble |
| `find . -delete` | 🟢 auto | 🟡 preguntar |
| `find . -exec rm {} \;` | 🟢 auto | 🟡 preguntar |
| `find / -fprint /tmp/x` | 🟢 auto | 🟡 preguntar |
| `git diff --output=/tmp/x` | 🟢 auto | 🟡 preguntar |
| `sort -o salida.txt a` | 🟢 auto | 🟡 preguntar |
| `python3 -m pytest -p evil` | 🟢 auto | 🟡 preguntar |
| `pytest --basetemp=/` | 🟢 auto | 🟡 preguntar |

**Sin regresiones**: lo que es lectura de verdad sigue en auto.

| Comando | Antes | Después |
|---|---|---|
| `ls` | 🟢 auto | 🟢 auto |
| `pytest -q` | 🟢 auto | 🟢 auto |
| `cd /x && python3 -m pytest tests/ -q` | 🟢 auto | 🟢 auto |
| `grep -r x . 2>&1` | 🟢 auto | 🟢 auto |
| `pytest 2>&1 \| tail -5` | 🟢 auto | 🟢 auto |
| `find . -name '*.py' \| sort -rn \| head -5` | 🟢 auto | 🟢 auto |
| `git log --oneline` | 🟢 auto | 🟢 auto |


---

## 2. 🔴 Denylist dura demasiado estrecha

### `_PROHIBIDOS` solo reconoce `rm -XX /` literal

**Archivo:** `modules/coding.py`

Variantes triviales del borrado de la raíz o del home no se vetaban. Caían a la política, que pide `s/n`, pero la denylist promete «no hay s/n que los apruebe».

<table>
<tr><th width="50%">❌ Código actual (mal)</th><th width="50%">✅ Código corregido (bien)</th></tr>
<tr>
<td valign="top">

```python
_PROHIBIDOS = _re.compile(
    r"(?:^|[;&|`(]|\s)\s*"
    r"(?:rm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+/\s*(?:$|[;&|])"
    r"|:\s*\(\s*\)\s*\{)"
)
# ⚠ solo "rm -XX /" literal:
#   no cubre /*, ~, $HOME, -r -f separados,
#   /bin/rm, --no-preserve-root
# ⚠ [rf] acepta "rm -f /" (sin recursivo)
```

</td>
<td valign="top">

```python
_PROHIBIDOS = _re.compile(
    r"(?:^|[;&|`(\n]|\s)\s*(?:sudo\s+)?"
    r"(?:(?:/usr)?/bin/)?rm\s+"
    # exige un flag RECURSIVO en cualquier posición
    r"(?=(?:\S*\s+)*?-(?:[a-zA-Z]*[rR][a-zA-Z]*"
    r"|-recursive)\b)"
    r"(?:\S+\s+)*?"                 # -r -f separados
    r"(?:--no-preserve-root\s+)?"
    r"(?:/\*?|~/?\*?|\$HOME/?\*?|/\.\*?)"
    r"\s*(?:$|[;&|\n])"
    r"|:\s*\(\s*\)\s*\{"            # fork bomb
)
```

</td>
</tr>
</table>

**Evidencia (`_PROHIBIDOS.search()` real):**

| Comando | Antes | Después |
|---|---|---|
| `rm -rf /*` | — pasa a la política | ⛔ vetado |
| `rm -r -f /` | — pasa a la política | ⛔ vetado |
| `rm -rf ~` | — pasa a la política | ⛔ vetado |
| `rm -rf ~/` | — pasa a la política | ⛔ vetado |
| `/bin/rm -rf /` | — pasa a la política | ⛔ vetado |
| `rm -rf --no-preserve-root /` | — pasa a la política | ⛔ vetado |
| `rm -fr $HOME` | — pasa a la política | ⛔ vetado |
| `rm -rf /` | ⛔ vetado | ⛔ vetado |
| `sudo rm -rf /` | ⛔ vetado | ⛔ vetado |
| `:(){ :\|:& };:` | ⛔ vetado | ⛔ vetado |

**Sin falsos positivos**: los borrados acotados no se vetan (siguen en `confirmar_doble`, con doble `s/n`).

| Comando | Antes | Después |
|---|---|---|
| `rm -rf /tmp/x` | — pasa a la política | — pasa a la política |
| `rm -rf ./build` | — pasa a la política | — pasa a la política |
| `rm -rf ~/proyecto/build` | — pasa a la política | — pasa a la política |
| `rm -rf build/ && ls` | — pasa a la política | — pasa a la política |

> Nota: `rm -f /` sin `-r` antes se vetaba y ahora no. Es correcto: `rm` sin `-r` no puede borrar un directorio, y igual cae en `preguntar`.


---

## 3. 🟠 `run_command` en modo auto ignora `AGENT_ALLOWED_DIRS`

### La aprobación era la única contención y el modo auto la quitó

**Archivo:** `modules/coding.py`

El propio docstring dice que la aprobación *es* la contención del shell. Con HITL graduado, un `cat` o `grep` a cualquier ruta del disco corría sin preguntar.

<table>
<tr><th width="50%">❌ Código actual (mal)</th><th width="50%">✅ Código corregido (bien)</th></tr>
<tr>
<td valign="top">

```python
def run_command(command):
    ...
    nivel = clasificar(command)
    if _setting("HITL_AUTO", "1") != "1":
        nivel = "preguntar"

    if nivel == "auto":
        # ⚠ "cat /cualquier/ruta" corre sin s/n:
        #   las raíces de AGENT_ALLOWED_DIRS
        #   no se miran nunca
        print(f"── run_command [auto] ──\n{command}")
```

</td>
<td valign="top">

```python
def _sale_de_raices(command):
    """True si algún token-ruta resuelve fuera de
    las raíces permitidas. Ante la duda, True."""
    import shlex
    from utils.fs_tools import allowed_roots

    try:
        tokens = shlex.split(command)
    except ValueError:
        return True  # comillas rotas: no verificable
    roots = allowed_roots()
    for tok in tokens:
        if "=" in tok and tok.startswith("-"):
            tok = tok.split("=", 1)[1]   # --flag=/ruta
        if not (tok.startswith(("/", "~", "$"))
                or ".." in tok):
            continue
        if tok.startswith("$"):
            return True   # $HOME, $VAR: invisible
        destino = (Path.cwd() / Path(tok).expanduser()).resolve()
        if not any(destino == r or r in destino.parents
                   for r in roots):
            return True
    return False


def run_command(command):
    ...
    nivel = clasificar(command)
    if nivel == "auto" and _sale_de_raices(command):
        nivel = "preguntar"   # lee FUERA del proyecto
    if _setting("HITL_AUTO", "1") != "1":
        nivel = "preguntar"
```

</td>
</tr>
</table>

**Evidencia:** con `AGENT_ALLOWED_DIRS=/tmp/.../in`:

| Llamada | Antes | Después |
|---|---|---|
| `read_file("/tmp/.../secreto.txt")` | ⛔ `ERROR: ruta fuera de los directorios permitidos` | igual |
| `run_command("cat /tmp/.../secreto.txt")` | 🟢 **auto → `exit 0  SECRETO`** (sin `s/n`) | 🟡 pide aprobación → `RECHAZADO` |

Antes, la misma lectura que `read_file` bloqueaba pasaba por `run_command` sin preguntar. Lo cubre `test_auto_fuera_de_raices_pregunta`.


---

## 4. 🟡 Ruta fija en `evals.py`

### `TEST_ROUTER` apunta a `/home/roquedb/...`

**Archivo:** `evals.py`

Las sondas ya centralizaron el default en `utils/rutas.tasks_dir()` (con `BMO_TASKS_DIR`). `evals.py` quedó como cuarta copia de ese mismo default.

<table>
<tr><th width="50%">❌ Código actual (mal)</th><th width="50%">✅ Código corregido (bien)</th></tr>
<tr>
<td valign="top">

```python
# evals.py
TEST_ROUTER = Path(
  "/home/roquedb/Documentos/00_IA/bmo/train/tasks/router_flow_test.jsonl"
)
# ⚠ ruta de UNA máquina; el resto del repo ya
#   usa BMO_TASKS_DIR (utils/rutas.py)
```

</td>
<td valign="top">

```python
# evals.py
from utils.rutas import tasks_dir

TEST_ROUTER = tasks_dir() / "router_flow_test.jsonl"
# BMO_TASKS_DIR lo mueve; mismo default histórico
```

</td>
</tr>
</table>

**Evidencia:** `FileNotFoundError: '/home/roquedb/Documentos/00_IA/bmo/train/tasks/router_flow_test.jsonl'` en 3 tests. Con el fix, `BMO_TASKS_DIR` mueve el bench y los tests se saltean con motivo cuando el archivo no está.

---

## 5. 🟡 Memoria anclada al CWD

### `MEMORIA_DIR` relativo depende de desde dónde arranques

**Archivo:** `modules/memoria.py`

`.runs/` ya se ancla al proyecto (`utils/tracing.py` usa `Path(__file__)...parent.parent`), pero la memoria no. Si corrés `python3 ~/…/main.py` desde otra carpeta, el catálogo sale vacío y el resumen de sesión se guarda en otro lado.

<table>
<tr><th width="50%">❌ Código actual (mal)</th><th width="50%">✅ Código corregido (bien)</th></tr>
<tr>
<td valign="top">

```python
def _raiz():
    raw = _setting("MEMORIA_DIR", MEMORIA_DIR_DEFAULT)
    return (Path(raw).expanduser().resolve()
            if not Path(raw).is_absolute() else Path(raw))
# ⚠ "memoria" relativo se resuelve contra el CWD:
#   arrancar desde otra carpeta = biblioteca vacía
#   nueva en otro lado
```

</td>
<td valign="top">

```python
def _raiz():
    raw = Path(_setting("MEMORIA_DIR",
                        MEMORIA_DIR_DEFAULT)).expanduser()
    if not raw.is_absolute():
        # anclada al PROYECTO, no al CWD
        raw = Path(__file__).resolve().parent.parent / raw
    return raw.resolve()
```

</td>
</tr>
</table>

**Evidencia:** los tests de memoria usan `MEMORIA_DIR` absoluto (`tmp_path`), así que el comportamiento con path absoluto no cambia. Siguen verdes.

---

## 6. 🟡 Tests no herméticos (`calidad.sh` rojo fuera de tu máquina)

### Rutas fijas a tu carpeta

**Archivo:** `tests/test_smoke.py::test_contencion_de_rutas`



<table>
<tr><th width="50%">❌ Código actual (mal)</th><th width="50%">✅ Código corregido (bien)</th></tr>
<tr>
<td valign="top">

```python
resolved, err = _resolve(
    "Pocketflow/deepseek-flow/docs/design.md")
assert err is None and resolved.is_file()
```

</td>
<td valign="top">

```python
raiz = Path(__file__).resolve().parent.parent
resolved, err = _resolve(str(raiz / "docs" / "design.md"))
assert err is None and resolved.is_file()
```

</td>
</tr>
</table>



### Rutas fijas a tu carpeta

**Archivo:** `tests/test_smoke.py::test_search_files_por_nombre`



<table>
<tr><th width="50%">❌ Código actual (mal)</th><th width="50%">✅ Código corregido (bien)</th></tr>
<tr>
<td valign="top">

```python
r = search_files(glob="requirements.txt",
                 path="Pocketflow/deepseek-flow")
```

</td>
<td valign="top">

```python
raiz = Path(__file__).resolve().parent.parent
r = search_files(glob="requirements.txt", path=str(raiz))
```

</td>
</tr>
</table>



### La síntesis llama a la API real

**Archivo:** `tests/test_smoke.py::test_votacion_laya_segura_no_gasta`



<table>
<tr><th width="50%">❌ Código actual (mal)</th><th width="50%">✅ Código corregido (bien)</th></tr>
<tr>
<td valign="top">

```python
monkeypatch.setattr(sup, "elegir_con_deepseek", nunca)
monkeypatch.setattr("utils.laya.disponible", ...)
# ⚠ Sintetizar llama call_llm → exige API key
```

</td>
<td valign="top">

```python
monkeypatch.setattr(sup, "elegir_con_deepseek", nunca)
monkeypatch.setattr(sup, "call_llm",
                    lambda *a, **k: "síntesis falsa")
monkeypatch.setattr("utils.laya.disponible", ...)
```

</td>
</tr>
</table>



### La síntesis llama a la API real

**Archivo:** `tests/test_smoke.py::test_informe_dos_corridas_en_el_mismo_proceso`



<table>
<tr><th width="50%">❌ Código actual (mal)</th><th width="50%">✅ Código corregido (bien)</th></tr>
<tr>
<td valign="top">

```python
monkeypatch.setattr(informe, "interpretar", resumen_falso)
# ⚠ el reduce (call_llm sync) no está mockeado
```

</td>
<td valign="top">

```python
monkeypatch.setattr(informe, "interpretar", resumen_falso)
monkeypatch.setattr(informe, "call_llm",
                    lambda *a, **k: "síntesis falsa")
```

</td>
</tr>
</table>



### Dependencia opcional sin skip

**Archivo:** `tests/test_smoke.py::test_search_web_degrada_a_error_sin_red`



<table>
<tr><th width="50%">❌ Código actual (mal)</th><th width="50%">✅ Código corregido (bien)</th></tr>
<tr>
<td valign="top">

```python
import ddgs   # ⚠ ModuleNotFoundError si no está
```

</td>
<td valign="top">

```python
ddgs = pytest.importorskip("ddgs")
```

</td>
</tr>
</table>



### Asume que `.runs/` existe

**Archivo:** `tests/test_smoke.py::test_tool_evals_no_pisa_el_baseline`



<table>
<tr><th width="50%">❌ Código actual (mal)</th><th width="50%">✅ Código corregido (bien)</th></tr>
<tr>
<td valign="top">

```python
r = mod.evals(dir_runs=None, salida="salidas/banco")
# ⚠ en una PC nueva: "ERROR: no es una carpeta de trazas: .runs"
```

</td>
<td valign="top">

```python
vacio = Path("salidas/banco/runs_vacio")
vacio.mkdir(parents=True, exist_ok=True)
monkeypatch.setattr(mod, "DIR_RUNS", vacio)
r = mod.evals(dir_runs=None, salida="salidas/banco")
```

</td>
</tr>
</table>



### Evidencia externa al repo sin skip

**Archivo:** `tests/test_smoke.py::_bench_con (+ 2 tests de bench)`



<table>
<tr><th width="50%">❌ Código actual (mal)</th><th width="50%">✅ Código corregido (bien)</th></tr>
<tr>
<td valign="top">

```python
def _bench_con(fake_agente):
    from evals import correr_bench
    return correr_bench(agente=fake_agente)
# ⚠ FileNotFoundError si falta router_flow_test.jsonl
```

</td>
<td valign="top">

```python
def _bench_con(fake_agente):
    from evals import TEST_ROUTER, correr_bench
    if not TEST_ROUTER.is_file():
        pytest.skip(f"falta el test del router: {TEST_ROUTER}")
    return correr_bench(agente=fake_agente)
```

</td>
</tr>
</table>



**Evidencia (errores reales antes del fix):**

```
E  AssertionError: ... PosixPath('.../Pocketflow/deepseek-flow/docs/design.md').is_file
E  AssertionError: 'requirements.txt' in 'ERROR: no existe: .../Pocketflow/deepseek-flow'
E  RuntimeError: API key de DeepSeek no encontrada.          (x2)
E  FileNotFoundError: '/home/roquedb/.../router_flow_test.jsonl'  (x3)
E  AssertionError: 'Informe de evals generado' in 'ERROR: no es una carpeta de trazas: .runs'
E  ModuleNotFoundError: No module named 'ddgs'
```

---

## 7. ➕ Tests nuevos — `tests/test_policy_bypass.py`

Fijan los bypass para que no vuelvan:

```python
@pytest.mark.parametrize("comando, esperado", [
    ("ls\nrm -rf ~", "confirmar_doble"),
    ("cat a & rm -rf b", "confirmar_doble"),
    ("find . -delete", "preguntar"),
    ("find . -exec rm {} \\;", "preguntar"),
    ("git diff --output=/tmp/x", "preguntar"),
    ("sort -o salida.txt a", "preguntar"),
    ("python3 -m pytest -p plugin_malo", "preguntar"),
    ("pytest --basetemp=/", "preguntar"),
    ...
])
def test_policy_bypass_cerrados(comando, esperado): ...

def test_policy_lectura_legitima_sigue_auto(comando): ...   # sin regresiones
def test_denylist_veta(comando): ...                        # /*, ~, -r -f, /bin/rm...
def test_denylist_no_veta_borrados_acotados(comando): ...   # rm -rf ./build pasa
def test_auto_fuera_de_raices_pregunta(tmp_path, ...): ...  # cat fuera ⇒ s/n
```

---

## Pendiente (no tocado a propósito)

- **README**: dice «Capacidades (24)» y al cargar `nodes.TOOLS` hay **28**.
- **Streaming + `max_retries=3`**: si `exec` lanza después de imprimir deltas, el retry puede reimprimir texto parcial. Conviene que el reintento del stream imprima una marca `[reintento]`.
- **`heartbeat.jsonl`** versionado con rutas `~/Documentos/00_IA/bmo/data`.
- **Límite de diseño:** `clasificar()` sigue siendo un clasificador por superficie. No interpreta comillas, así que `echo "a; b"` se parte de más, aunque siempre hacia el lado seguro. Para una contención fuerte de verdad, el próximo paso sería ejecutar en sandbox (bubblewrap/firejail o un contenedor) en vez de seguir agrandando la lista negra.
