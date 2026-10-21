# Sugerencias de arreglo: absurdos funcionales en deepseek-flow

**Estado (2026-10-21):** aplicado en exp/68 con estas correcciones sobre la
propuesta: (1) `_normalizar` cubre `rm -rF/-FR` (mayúsculas) y las opciones de
los envoltorios (`sudo -u root`, `nice -n 10`, `timeout 5`, `env -i`);
(2) `explicar` NO normaliza el texto de solo-lectura (un `sudo cat` no debe
leerse "solo lee"); (3) se agregaron tests e2e por el flujo (`_nivel` y
`run_command`). El `.patch` que acompaña este informe es la **propuesta
original**, no el diff aplicado. **E8 también se aplicó** (exp/69): la suite ya
no depende de git ni de la profundidad del checkout (ver abajo, punto 6).

Acompaña a `evidencia_absurdos_funcionales.md`. Los arreglos 1 a 4 vienen en **`arreglos_absurdos_funcionales.patch`** (198 líneas) y están verificados:

```text
patch -p1 < arreglos_absurdos_funcionales.patch
ruff check .                                   → All checks passed!
ruff C901 ≤ 12 (coding, fs_tools, policy)      → All checks passed!
python3 ratchet.py                             → VERDE (tests_definidos 690 → 718)
pytest tests/                                  → 721 passed, 9 skipped, 4 failed
                                                 (los 4 rojos son los de git del punto 6: ya fallaban antes del patch)
pytest tests/test_absurdos_funcionales.py      → 28 passed
```

> El baseline del ratchet **no** va en el patch. `calidad.sh` lo reescribe solo cuando la métrica mejora, como pide R6 de tu `AGENTS.md`.

---

## 1. Cerrar los flags que ejecutan o cuelgan (E1, E2, E3)

**Principio:** un comando entra en la lista blanca por lo que **hace**, no por su nombre. Además de "¿escribe?", hay que preguntarse "¿ejecuta algo?" y "¿termina?".

```python
# utils/policy.py — _FLAGS_PELIGROSOS
    # --compress-program EJECUTA el programa que se le pasa (GNU sort)
    "sort": ("-o", "--output", "--compress-program"),
    # tail -f/-F no termina: en auto el agente queda colgado hasta TIMEOUT_S
    "tail": ("-f", "-F", "--follow", "--retry"),
    # -o/--override-ini reinyecta cualquier flag (addopts=-p plugin) y saltea la lista
    "pytest": ("-p", "--basetemp", "--rootdir", "-c", "--confcutdir", "-o", "--override-ini"),
```

También se ajusta `tests/test_policy.py:39`: `"tail -f x"` pasa a `"tail -n 5 x"`. El test exigía el comportamiento roto.

**A mediano plazo (no está en el patch):** pasar de "lista blanca de comandos + lista negra de flags" a **lista blanca de flags** por comando. Cualquier flag desconocido pasaría a `preguntar`:

```python
_FLAGS_SEGUROS = {
    "sort": {"-n", "-r", "-u", "-k", "-t", "-h", "-V", "-f"},
    "tail": {"-n", "-c", "-q"},
    "grep": {"-r", "-n", "-i", "-l", "-c", "-E", "-F", "-w", "-v", "--include", "--exclude"},
}
```

Es más conservador y no depende de conocer cada flag peligroso. Tiene un costo: va a pedir aprobación más seguido hasta que la lista se complete. Medilo con el banco antes de adoptarlo.

## 2. Normalizar antes de buscar en la lista negra (E4)

**Principio:** comparar contra el **significado** del comando, no contra su forma. La normalización se aplica **solo a la lista negra**, así que nunca baja la fricción.

```python
_ENVOLTORIOS = {"sudo", "env", "command", "exec", "nice", "nohup", "time"}
_GIT_GLOBAL_CON_VALOR = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}

def _normalizar(tokens):
    """Tokens con el riesgo a la vista: sin envoltorios, `/bin/rm` → `rm`,
    flags de rm recursivo+forzado como `-rf`, y git sin opciones globales.
    Solo SUBE fricción: se usa para la lista negra, nunca para la whitelist."""
    ...
```

Resultados verificados:

| Comando | Antes | Después |
|---|---|---|
| `rm -r -f x`, `rm -Rf x`, `rm -fR x`, `rm --recursive --force x` | preguntar | **confirmar_doble** |
| `sudo rm -rf x`, `/bin/rm -rf x`, `env rm -rf x`, `command rm -rf x` | preguntar | **confirmar_doble** |
| `git -C . push`, `git -c user.name=x push origin main`, `sudo git push` | preguntar | **confirmar_doble** |
| `rm -r x`, `rm -f x` | preguntar | preguntar (sin cambio) |
| `git log --grep push` | auto | auto (`push` como argumento no cuenta) |

## 3. Explicar el segmento que fija el nivel (E5)

```python
# utils/policy.py — explicar()
segmentos = [x for x in _SEPARADORES.split(_sin_dup_stderr(comando)) if x.strip()]
peor = next((x for x in segmentos if clasificar(x) == nivel), comando)
tokens = _normalizar(peor.split())
```

| Comando | Antes | Después |
|---|---|---|
| `ls && rm -rf /` | lista un directorio (solo lee) | **borrado recursivo forzado (destructivo)** |
| `cd /tmp && rm -rf x` | cambia de directorio (...) | **borrado recursivo forzado (destructivo)** |
| `cat a && git -C . push` | muestra un archivo (solo lee) | **publica commits al remoto (...)** |

También se borra del docstring la frase que describía el bug como "límite conocido".

## 4. `mayoria()`: un empate usa el desempate (E6)

```python
(opcion, n), *resto = conteo.most_common()
empate = bool(resto) and resto[0][1] == n
if n >= minimo and not empate:
    return opcion
return desempate if desempate is not None else opcion
```

Es compatible con los tests existentes (`test_router.py::test_mayoria`, `test_flujos.py::test_votacion_mayoria_piso_absoluto`) y no cambia nada en producción con 3 votos. Si querés que "mayoría" signifique *más de la mitad*, cambiá el piso a `n > len(votos) // 2`. Eso **sí** rompe `test_votacion_mayoria_piso_absoluto`, porque hoy el diseño fija 2 de 5 a propósito, así que es una decisión tuya, no un bug.

## 5. Quitar la indirección inútil (E7)

```diff
-    return globals().get("MAX_TOOL_ROUNDS", MAX_TOOL_ROUNDS)
+    return MAX_TOOL_ROUNDS
```

Habría que acortar también el docstring de `presupuesto`, porque gran parte explica la indirección. No lo toqué para respetar la regla de tu `AGENTS.md` sobre comentarios.

## 6. Tests que dependen del entorno (E8): NO incluido en el patch

```python
# tests/conftest.py
import shutil
requiere_git = pytest.mark.skipif(shutil.which("git") is None, reason="requiere git")
```

```toml
# pyproject.toml → markers
"git: requiere git y el repo inicializado",
```

Aplicalo a los 4 tests de E8. Para `test_contencion_de_rutas`, la raíz permitida de `conftest.py` no debería depender de `RAIZ.parent.parent`. Mejor que el test fije su propia raíz con `tmp_path`, como ya hacen los de `test_policy_bypass.py`.

## 7. El test nuevo: `tests/test_absurdos_funcionales.py` (28 casos)

| Test | Qué fija |
|---|---|
| `test_whitelist_no_deja_ejecutar_ni_colgar` | E1, E2, E3: `sort --compress-program`, `pytest -o`, `tail -f/-F` → preguntar |
| `test_destructivo_pide_doble_aunque_cambie_la_forma` | E4: 12 variantes de rm y git push → confirmar_doble |
| `test_normalizar_no_sube_friccion_de_mas` | Sin regresiones: `rm -r`, `git log --grep push`, `tail -n`, `sort`, `pytest -q` |
| `test_explicar_nombra_el_segmento_que_fija_el_nivel` | E5 |
| `test_auto_fuera_de_raices_sigue_preguntando` | **Contrato de la segunda capa** (`_sale_de_raices`), para que nadie la quite creyendo que sobra |
| `test_mayoria_empate_usa_el_desempate` | E6 |

Después de agregarlo, el inventario sigue verde (solo controla que no **falten** tests) y el ratchet sube `tests_definidos` a 718.

## 8. Cambios de proceso (sin código)

1. **Seguir el flujo hasta donde se ejecuta antes de declarar un bypass.** Me pasó a mí en la revisión anterior. Para tu agente, sumá esta regla blanda en `AGENTS.md`: *"un hallazgo de seguridad se confirma ejecutando la tool completa (`run_command`, `read_file`), no la función aislada"*.
2. **Un bug conocido no se documenta: se arregla o se prueba.** Si queda como límite aceptado, que tenga un test que lo fije, como ya hiciste con A45 para pytest y conftest.
3. **Revisar los tests que fijan el comportamiento roto.** `test_policy.py:39` exigía `tail -f` en auto. Al pedirle a un agente "que los tests pasen", va a defender ese tipo de casos.
4. **Para la política de comandos, preguntar "¿ejecuta algo?" y "¿termina?"**, además de "¿escribe?". Las tres preguntas cubren E1, E2 y E3.
