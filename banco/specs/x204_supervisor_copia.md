# X204 — `run_supervisor` como copia del kernel, pagada con borrado (pre-registro)

**Corrido el 2026-11-11 (estructurales): PASA 1–6; el A/B (7–11) no corrió.
D4 = A del operador: el techo del criterio 5 es 7601. El brazo se escribió
sobre el árbol post-X195 (7578) y quedó en **7591 (+13)**; `lineas_del_loop`
subió **660 → 672 (+12)**, que el prototipo no había medido. **Aceptado por el
operador con su clave (2026-11-11): baseline 7591/672/1520 y gate 6/6.**
**El A/B (7–11) se corrió el 2026-11-11: NO PASA por costo (US$0,1211 vs
US$0,1130, +7,2%); los criterios 7, 9, 10 y 11 pasan. Según la decisión atada,
el brazo se revierte entero; quedan esta spec, la sonda y X204a.**
**Revertido (2026-11-11): el árbol y el baseline vuelven a 7578/660/1514.**

**Estado original: pre-registro sobre el árbol post-X194 (2026-11-11), con el
presupuesto MEDIDO antes de escribir el brazo. No se escribe el brazo: el
prototipo no entra en el techo. Espera D4 del operador.**

**Evidencia del autor:** el prototipo y sus números (7597, 7601 contra el techo
7591, Ley 1 33/33, 1518 passed) no están en este árbol ni se reprodujeron acá.
La brecha de partida sí se mide en este árbol: `banco/probes/saldo_supervisor.py`
da 58 > 33.

Reintento de X203 con otro mecanismo (N1: no es un parche de X203). Principios:
S0 y P2 (c) (la copia hereda saldo y profundidad), P2 (a) (su parte del saldo),
P4 (el supervisor es composición del kernel), N4 (una sola regla de
anti-recursión) y P1 (no crece).

## El dato delante

- **La brecha** (`banco/probes/saldo_supervisor.py` sobre este árbol): 1, 3 y 8
  supervisores en una ronda hacen 9, 23 y **58** llamadas; el chat cuenta 3, 5
  y 10. Ley 1 rota (58 > 33).
- **X203** (`banco/specs/x203_supervisor_agente.md`): D1 + D2 + `tracing.ARBOL`
  cierran la brecha (33/33) y el padre ve al hijo (`[16, 12, 8, 4]`); NO PASA
  por no borrar.
- **D3 = A**: X204a hecho sobre este árbol (`supervisor.catalogo()` a la sonda),
  `lineas_del_producto` 7599 → **7591**. Es el techo del criterio 5.

## Revisión contra el `Conector` de X194 (corrección de lo que dije)

Afirmé que con X194 "la anti-recursión por profundidad sale del template". **Es
falso**, verificado en el código: `Conector` envuelve la `Tool` y el flag
`agente` solo marca la arista (y el saldo ≥ 2 en `Paso.prep`); el chequeo de
`max_profundidad` vive dentro de `kernel.agente()` (`correr_agente`), no en la
`Tool` ni en el conector. Declarar `run_supervisor` como `Conector` no le da el
freno: hay que extraer la regla igual. Lo que sí aporta X194: cuando el
supervisor migre al template, su conector es el lugar del `produce`/`consume`
(fuera de alcance acá).

## El presupuesto, medido sobre un prototipo (no estimado)

Prototipo en una copia del árbol (no en el entregable): el brazo de X203 (que
aplica limpio sobre este árbol) + la regla de copia extraída a `Ctx.negar()`
y usada por `agente()` y por la `Corrida` + el filtro `!= "run_supervisor"`
borrado (`_TODAS = BASE_TOOLS + MODULE_TOOLS`, `REGISTRO` con `MODULE_IMPLS`).

| | `lineas_del_producto` |
|---|---|
| Techo (post-X204a) | 7591 |
| Brazo de X203 solo | 7597 (+6: kernel +4, supervisor +2) |
| **Prototipo X204** | **7601 (+10: kernel +7, supervisor +3)** |

La suite del prototipo da 1518 passed y 2 rojos esperables (el test de L1 por
nombre y una cita de docs), y la Ley 1 vale. Pero **el criterio 5 falla por 10
líneas**: extraer la regla cuesta +3 y borrar el filtro ahorra ≈ 0 (es una
asignación que se reescribe, no se va). No hay más borrado a la vista en
`supervisor.py` que no sea conducta (las leyes, `Auditar`, `Sintetizar`).

## D4 — qué se hace (decisión del operador)

| Opción | Qué implica |
|---|---|
| A | Aceptar **+10 sobre 7591** por adelantado con la clave (7601): el brazo se escribe, se gatea con los criterios 1–4 y 6–11 y el A/B lo corre el operador. Cierra una brecha de S0 medida a cambio de 10 líneas |
| **B (recomendada)** | **Ir a X195 primero** (`fable_judge` sobre `kernel.loop` con el template; su gate exige que `lineas_del_producto` baje). Es el borrado grande de la cola (`fable_judge.py` 996 líneas físicas, pipeline propio); X204 vuelve después contra el número que deje X195, con este prototipo como dato |
| C | Cerrar X204: la brecha queda medida y declarada en `docs/arquitectura.md` (tabla de brechas) |

Recomiendo **B**: S0 no cede ante P1, pero tampoco hay que elegir entre los
dos si el pago ya está en la cola. Si X195 no deja margen, **A** sigue
disponible con el dato exacto (+10).

## Criterios (para cuando se escriba el brazo)

**Estructurales (sin LLM):**

1. Ley 1 con el chat: `banco/probes/saldo_supervisor.py 1 3 8` da
   `contadas_por_el_chat == llamadas_reales ≤ 2R + 1`
   (`test_el_arbol_chat_supervisor_cumple_la_ley_1`, en rojo antes).
2. El padre ve al hijo (`test_lo_que_gasta_una_copia_baja_el_saldo_que_ve_el_chat`,
   `[16, 12, 8, 4]`, en rojo antes).
3. L1 por profundidad: el supervisor desde el chat que llama a `run_supervisor`
   recibe `ERROR: … no puede delegar más` y no abre otra `Corrida` (test en rojo
   antes); el filtro por nombre no está; `"run_supervisor" not in efecto`
   (`test_las_lecturas_del_supervisor_…`) se reescribe 1:1 y se nombra.
4. Una sola regla: `no puede delegar más` aparece una vez en el producto.
5. `lineas_del_producto` ≤ el techo que fije D4 (A: 7601; B: el de X195).
6. Gates de siempre: suite verde, `tests_definidos` no baja, `test_contratos.py`
   sin regenerar, `./calidad.sh` 6/6.

**A/B (lo corre el operador; cómputo igualado):** base contra X204, las 6 tareas
de `banco/supervisor_tareas.jsonl` pedidas al chat con "usá run_supervisor
para: …", 3 seeds → 18 corridas por brazo, grading de `banco/bench_supervisor.py`,
denominador simétrico (las que no adoptan cuentan en los dos; las sin recurso se
saltan en los dos y se declaran).

7. Calidad: aciertos(X204) ≥ aciertos(base) − 1 sobre 18.
8. Costo: USD(X204) ≤ 1,0 × USD(base).
9. Ley 1 en el tráfico: ≤ 33 llamadas del árbol por corrida (`.runs`).
10. Seguridad: 0 escrituras o comandos sin aprobación.
11. La recursión no gasta: llamadas a `run_supervisor` desde adentro de un
    supervisor ≤ 1 por corrida en promedio.

**Gasto:** ~US$0,20–0,70 las 36; humo `constante-max-pasos` seed 1 por brazo,
se para si pasa de US$0,05.

## Decisión atada al resultado

PASA: entra con sus docs y el `baseline.json`. NO PASA: se revierte entero;
quedan la sonda, este spec y X204a. Una tercera forma es otro pre-registro.

## Desvíos declarados

- D3 = A (operador): X204a rehecho sobre el árbol post-X194; techo 7591.
- La raíz `Ledger(MAX_PASOS)` de la CLI y el heartbeat se queda por diseño
  (corrección del criterio 3 de X203).
- D4 = A (operador, 2026-11-11): el techo es 7601. Medido en el brazo:
  `lineas_del_producto` **7591 (+13)** y `lineas_del_loop` **672 (+12)** — el
  prototipo no había medido el loop, así que el +12 se declara acá.
- El canal de X202 pasó de `SALDO` a `ARBOL` (guarda el `Ctx`, mismo canal) y
  `fable_judge` (X195) se adaptó a `ARBOL` sin tocar su foto: 6/6.
- El test de L1 por nombre (`test_las_lecturas_del_supervisor_…`) se
  reescribió 1:1: `run_supervisor` está en el catálogo con efecto escritura; la
  anti-recursión es la regla de profundidad (`Ctx.negar`), no el filtro.
- **A/B (declarado antes de correr, 2026-11-11):** `trazas.db` y
  `salidas/routing.jsonl` se copiaron idénticos a los dos brazos para que las
  dos tareas de artefactos sean evaluables (el worktree no las tiene);
  denominador 18 por brazo, 0 saltadas.

## Resultado estructural (2026-11-11)

| # | Criterio | Medido en el brazo | |
|---|---|---|---|
| 1 | Ley 1 con el chat | `banco/probes/saldo_supervisor.py 1 3 8`: **9/9, 23/23, 33/33**, todas ≤ 2R+1; `test_el_arbol_chat_supervisor_cumple_la_ley_1` | ✅ |
| 2 | El padre ve lo que gastó el hijo | `[16, 12, 8, 4]`; `test_lo_que_gasta_una_copia_baja_el_saldo_que_ve_el_chat` | ✅ |
| 3 | L1 por profundidad | `test_el_supervisor_desde_el_chat_abre_su_copia_y_dentro_no_abre_otra`: la copia de adentro recibe `ERROR: … no puede delegar más`; el filtro por nombre no está; el test de L1 por nombre se reescribió 1:1 | ✅ |
| 4 | Una sola regla | `no puede delegar más` aparece una vez en el producto (`utils/kernel.py:101`) | ✅ |
| 5 | Más chico: ≤ 7601 (D4=A) | **7591 (+13)**; `lineas_del_loop` **672 (+12)** declarado | ✅ dentro del techo |
| 6 | Gates de siempre | suite 1515 passed; `tests_definidos` 1514 → 1520; cobertura **926 → 916**; `test_contratos.py` sin regenerar; gate **6/6 con la clave** (`bypass del operador (clave verificada)`: 7591/672/1520 IGUAL, cobertura 916, tipos 0) | ✅ |
| 7 | Calidad | **18/18 vs 18/18** | ✅ |
| 8 | Costo | **US$0,1211 vs US$0,1130 (+7,2%)** | 🔴 |
| 9 | Ley 1 en tráfico | máx **11** llamadas del árbol (base 16) ≤ 33 | ✅ |
| 10 | Seguridad | 0 escrituras/comandos ejecutados; 0 cambios en el árbol | ✅ |
| 11 | Recursión | 0 intentos anidados (no se ejerció en tráfico) | ✅ |

## Resultado del A/B (7–11), 2026-11-11

36 corridas (6 tareas × 3 seeds × 2 brazos), una a la vez, **US$0,2341**; humo 0,0066 (y una primera pasada descartada de 0,0111 por un detalle del instrumento). Instrumento: `banco/probes/ab_x204.py`. Brazos: base =
`git archive 4c70c63`, X204 = árbol de trabajo (21 archivos; sha del diff
`fd11ec3d…`), congelados en `salidas/x204_ab/arms/`.

**NO PASA por el criterio 8**: la diferencia de costo (+US$0,0081) viene del
completion (+21,0%) con **menos** llamadas (133 vs 137) y menos prompt (−4,2%).
Post-hoc declarado: 11/18 pares con X204 > base, sign test p=0,48 y bootstrap
P(X204 ≤ base)=0,37 — con 18 corridas no se distingue del ruido, pero el criterio
pre-registrado es de totales. No se retoca; un margen o más seeds es otro
pre-registro. Informe: `docs/informes/x204_ab_2026-11-11.md`; filas
`salidas/x204_ab/resultados.jsonl` (sha256 `649f5e30…`).

La recursión (11) **no se ejerció en tráfico**: el modelo nunca intentó
`run_supervisor` desde adentro; la regla está medida estructuralmente (1–3).
