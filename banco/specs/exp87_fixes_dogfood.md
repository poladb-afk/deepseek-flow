# Spec de ejecución — exp/87: fixes de la auditoría del dogfood (sesión real del operador)

**Estado:** ejecutada el 2026-10-22; C1-C4 OK. Los hallazgos vienen de una sesión real del
chat (`salidas/test-chat-session.log`: el propio harness auditó `fable_judge.py` con 26/26 citas
verificadas y el operador pidió el arreglo). Criterio: cada fix con su test; gate verde.

## Hallazgos y fixes (cada uno con test)

**De la auditoría (fable_judge.py):**

| # | Hallazgo | Fix |
|---|---|---|
| F1 | La degradación terminal rearma el veredicto SIN compuerta: re-ejecución fallida + corte de infra → CAVEATS en vez de REFUTED | el juicio de degradación pasa por `compuerta(juicio, verificaciones)` |
| F2 | Allowlist: `("python3",)`/`("python",)` desnudos dejan pasar cualquier script; `python -m X` evade el chequeo de módulos (solo `python3 -m`); `-c` se chequea solo en `tokens[1]` (`python3 -B -c` pasa) | `-c` en CUALQUIER token veta; `-m` se chequea para ambos intérpretes (solo pytest / ruff check); para python desnudo el script tiene que existir dentro de `trabajo` y ser `.py` (la firma gana `trabajo=` opcional; policy/HITL sigue siendo la muralla detrás — defensa en profundidad, no única línea) |
| F3 | Filtro GROUND-TRUTH por nombre exacto case-sensitive: `ground-truth.md` o sufijos pasan | helper único case-insensitive (`nombre.upper() == "GROUND-TRUTH.MD"`) compartido por el árbol y diff_git |
| F4 | `rglob` sigue symlinks: un symlink al raíz del FS mete contenido externo en diff/fuentes | `p.is_symlink()` se descarta en `_archivos_bajo` (misma regla que memoria) |
| F5 | `read_bytes` sin tope de ENTRADA: un archivo de GB en el trabajo es OOM antes del recorte de salida | archivos >1 MB se saltean en la comparación con nota explícita en el diff |
| F6 | `caveats` sin validar tipo: un string itera por caracteres | `isinstance(list)` como ya se hace con `fraudes` |
| F7 | `MAX_CLAIMS` trunca en silencio: los claims 13+ desaparecen del juicio | claim sintético visible "(presupuesto: N claims no evaluados)" |

**Del presupuesto (exp/86, vistos en los marcadores de la misma sesión):**

| # | Hallazgo | Fix |
|---|---|---|
| F8 | Un archivo mencionado SIN barra ("auditá fable_judge.py") no resuelve → 872 líneas no disparan el tope amplio (el turno fue /8) | el extractor de tokens también pesca nombres de archivo con extensión, sin barra |
| F9 | "todos los tests pasan" matchea la señal de totalidad → amplio por la razón equivocada (turno /16 espurio) | `todos los` exige sustantivo de amplitud (archivos/módulos/directorios) |

## Criterios

- **C1:** un test por fix (F1–F9), sin tocar el contrato observable de lo que ya pasa.
- **C2:** e2e de la sesión del operador re-corrido en su turno 2 ("Auditá el código de
  fable_judge.py…"): el marcador tiene que ser `⚙ ronda N/16` ahora.
- **C3:** el control honesto sigue VERIFIED WITH CAVEATS (sin regresión del fix F2: `pytest` y
  `python3 -m pytest` siguen auto-permitidos).
- **C4:** gate verde.

## Fuera de alcance (declarado)

El crudo citado en el fallback del veredicto (se muestra al operador que pidió el juicio, no se
ejecuta), el techo global del prompt de juicio (refactor de escala) y el docstring de
`subprocess` en diff_git (nota: `git -C` sin shell, documentado acá).


## Resultado (2026-10-22)

C1 ✅ un test por fix (F1 compuerta en degradación, F2 allowlist endurecida
con script .py existente en el trabajo, F3 answer sheet case-insensitive, F4
symlinks, F5 tope de entrada 1MB con nota, F6 caveats lista, F7 presupuesto
de claims declarado, F8 nombre de archivo a secas, F9 "todos los" con
sustantivo). C2 ✅ el turno 2 re-corrido marca `⚙ ronda 9/16` (antes /8; el
headroom se USA). C3 ✅ control honesto VERIFIED WITH CAVEATS con la
re-ejecución exit 0 (la allowlist endurecida no rompió el camino legítimo).
C4 ✅ gate verde, 885 tests.
