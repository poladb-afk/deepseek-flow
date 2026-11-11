# X204 — `run_supervisor` como copia del kernel, pagada con borrado (pre-registro)

**Estado: pre-registro sobre el árbol post-X194 (2026-11-11), con el
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
