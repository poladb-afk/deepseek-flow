# Evidencia: absurdos funcionales en deepseek-flow

**Estado (2026-10-21):** E1–E7 verificados de forma independiente y **aplicados**
en exp/68 (ver [bitácora](../bitacora.md)); E8 queda como pendiente opcional. Las
tablas de abajo son la evidencia original, reproducida contra el código previo
al arreglo.

Revisión del 2026-10-21 sobre `deepseek-flow-main.zip`. Cada fila salió de **ejecutar** el código del repo, no de leerlo. Entorno: Python 3.12, GNU coreutils 9.4, ruff 0.17.1, sin `git` instalado.

## 0. Corrección de la revisión anterior (leer primero)

En el chat dije que `cat ~/.ssh/id_rsa`, `grep -r secreto ~` y otros comandos parecidos **se ejecutaban sin aprobación**. **Me equivoqué.** `clasificar()` sí los marca `auto`, pero `run_command` pasa por `modules/coding.py:_nivel`, que los sube a `preguntar` con `_sale_de_raices`:

```python
# modules/coding.py:249-251
nivel = clasificar(command)
if nivel == "auto" and _sale_de_raices(command):
    nivel = "preguntar"
```

| Comando | `clasificar()` | `_nivel()` real |
|---|---|---|
| `cat ~/.ssh/id_rsa` | auto | **preguntar** ✅ |
| `grep -r secreto ~` | auto | **preguntar** ✅ |
| `find / -name '*.pem'` | auto | **preguntar** ✅ |
| `git diff --no-index /etc/passwd a` | auto | **preguntar** ✅ |
| `cat $HOME/.ssh/id_rsa`, `cat /e*/passwd`, `cat ../../etc/passwd` | auto | **preguntar** ✅ |

**Lección:** cometí el mismo error que le marco a la IA. Juzgué una pieza aislada (`policy.py`) sin seguir el flujo completo hasta donde se ejecuta. La contención existe. Lo que sí es cierto es que el docstring de `policy.py` presenta a `auto` como "solo lectura" y la seguridad depende de una segunda capa que vive en otro archivo. El test `test_auto_fuera_de_raices_sigue_preguntando` (ver sugerencias) deja fijada esa dependencia.

---

## 1. 🔴 E1: `sort --compress-program` ejecuta un programa sin aprobación (CONFIRMADO)

`sort` está en la lista blanca como "ordena líneas (solo lee)". En GNU sort, `--compress-program=PROG` **ejecuta PROG** para comprimir los archivos temporales.

```text
payload.sh:  #!/bin/sh
             touch PWNED_SORT
             exec gzip "$@"

comando:     sort -S 100K --compress-program=./payload.sh big.txt
_nivel():    auto                       ← no se pidió aprobación
resultado:   PWNED_SORT existe: True     ← el script corrió
salida:      exit 0 ...                  ← el sort además "funcionó", nada lo delata
```

`_FLAGS_PELIGROSOS["sort"]` solo cubre `-o` y `--output`, o sea, pensó en *qué escribe* y no en *qué ejecuta*.

## 2. 🔴 E2: `pytest -o addopts=-p…` carga un plugin aunque `-p` está prohibido (CONFIRMADO)

`-p` está en `_FLAGS_PELIGROSOS["pytest"]` porque carga plugins arbitrarios. Pero `-o` / `--override-ini` permite reinyectar ese mismo flag:

| Comando | `_nivel()` | ¿Corrió `plugmalo.py`? |
|---|---|---|
| `pytest -p plugmalo -q` | preguntar | no (bloqueado ✅) |
| `pytest -q -o addopts=-pplugmalo` | **auto** | **sí** |
| `pytest -q --override-ini=addopts=-pplugmalo` | **auto** | **sí** |

Es el patrón típico de una **lista negra textual**: bloquea la forma del flag, no su efecto.

> El docstring de `policy.py` ya acepta (A45) que `pytest` ejecuta `conftest.py`, así que correr código del repo en `auto` es una decisión tomada a propósito. Lo de acá es otra cosa: el bloqueo que **sí** se decidió (`-p`) se puede esquivar.

## 3. 🟠 E3: `tail -f` en `auto` cuelga al agente hasta el timeout (CONFIRMADO)

```text
run_command("tail -f log.txt")   con TIMEOUT_S=3
nivel=auto · tardó 3.0s · 'ERROR: timeout de 3s — el comando no terminó (¿loop infinito o esperaba algo?)'
```

Con el valor real de `TIMEOUT_S = 120`, son **2 minutos perdidos** en un comando que el sistema presenta como lectura inofensiva. `tests/test_policy.py:39` incluso **exige** que `tail -f x` sea `auto`: el test fija el absurdo como contrato.

## 4. 🟠 E4: la doble confirmación depende de cómo se escriba el comando (CONFIRMADO)

`_NEGRA_DOBLE = (("git","push"), ("rm","-rf"), ("rm","-fr"))` compara tokens literales:

| Comando | Nivel | Esperado según `policy.py` ("lo destructivo paga doble") |
|---|---|---|
| `rm -rf x` | confirmar_doble | ✅ |
| `rm -r -f x` | preguntar | confirmar_doble |
| `rm -Rf x` | preguntar | confirmar_doble |
| `rm --recursive --force x` | preguntar | confirmar_doble |
| `sudo rm -rf x` | preguntar | confirmar_doble |
| `/bin/rm -rf x` | preguntar | confirmar_doble |
| `env rm -rf x` | preguntar | confirmar_doble |
| `git -C . push` | preguntar | confirmar_doble |
| `cat a && git -C . push origin main` | preguntar | confirmar_doble |

No es un bypass total, porque igual se pide **una** aprobación. La denylist dura (`_vetar_comando_prohibido`) sí cubre `rm -r -f /` y `sudo rm -rf /` cuando el destino es la raíz. El problema es la fricción intermedia, que se activa por la forma y no por el riesgo.

## 5. 🟠 E5: la explicación que lee el humano al aprobar nombra el segmento equivocado (CONFIRMADO)

```text
explicar("ls && rm -rf /")              → 'lista un directorio (solo lee)'     nivel: confirmar_doble
explicar("cd /tmp && rm -rf x")         → 'cambia de directorio (...)'         nivel: confirmar_doble
explicar("cat a && git -C . push ...")  → 'muestra un archivo (solo lee)'      nivel: preguntar
```

Se imprime en `modules/coding.py:295` (`print(f"   ↳ {explicar(command)}")`), justo antes del `s/n`. El docstring de `explicar` **documenta** este comportamiento en vez de corregirlo.

## 6. 🟡 E6: `mayoria()` ignora el desempate cuando hay empate (CONFIRMADO)

```python
>>> mayoria(["a", "a", "b", "b"], desempate="b")
'a'     # empate 2-2: ganó el primero en aparecer, el desempate no se usó
>>> mayoria(["a", "a", "b", "c", "d"])
'a'     # 2 de 5 cuenta como "mayoría" (documentado como piso absoluto)
```

En producción solo se llama con 3 votos (`sonda_supervisor.py:129`), y con 3 votos no puede haber empate de 2. **Hoy no tiene impacto**, pero la función se presenta como "N-de-M" genérica.

## 7. 🟡 E7: una indirección que no hace nada

```python
# nodes.py:122
return globals().get("MAX_TOOL_ROUNDS", MAX_TOOL_ROUNDS)
```

Leer un nombre global dentro de una función **ya** se resuelve cuando se ejecuta. `return MAX_TOOL_ROUNDS` respeta igual `monkeypatch.setattr(nodes, "MAX_TOOL_ROUNDS", 42)`. Verificado: `tests/test_chat_flujo.py` sigue verde con la versión simple.

## 8. 🟡 E8: tests que dependen del entorno sin marker

| Test | Depende de | Síntoma |
|---|---|---|
| `test_utils_compartidos.py::test_sha_corto_y_largo_son_hex_del_repo` | `git` + repo inicializado | rojo sin git |
| `test_ratchet.py::test_guardia_bypass_*` (2) | `git` | `FileNotFoundError: 'git'` |
| `test_pendientes.py::test_ningun_archivo_versionado_tiene_rutas_absolutas_del_autor` | `git` | rojo sin git |
| `test_fs_tools.py::test_contencion_de_rutas` | **profundidad del checkout**: `conftest.py` usa `RAIZ.parent.parent` como raíz permitida | verde en `/tmp/proj/<repo>`, **rojo** en `/tmp/<repo>` |

El último es un absurdo sutil: el resultado del test depende de **en qué carpeta clonaste el repo**.

---

## Cómo reproducirlo

```bash
# desde la raíz del repo, sin git ni red
PREGUNTAS_LOG=0 python3 - <<'EOF'
import os, sys, tempfile
from pathlib import Path
raiz = Path(tempfile.mkdtemp()); os.chdir(raiz)
os.environ.update(AGENT_ALLOWED_DIRS=str(raiz), HITL_AUTO="1")
sys.path.insert(0, os.environ.get("REPO", "."))
from modules import coding
from utils.policy import explicar
from utils.votacion import mayoria
for c in ["sort --compress-program=./p.sh a", "pytest -q -o addopts=-pplugmalo",
          "tail -f a", "rm -r -f x", "git -C . push", "cat ~/.ssh/id_rsa"]:
    print(f"{coding._nivel(c):16} {c}")
print(explicar("ls && rm -rf /"))
print(mayoria(["a", "a", "b", "b"], desempate="b"))
EOF
```

(Usá `REPO=/ruta/al/repo` si lo corrés desde otra carpeta).
