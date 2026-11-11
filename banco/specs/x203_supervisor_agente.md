# X203 — el supervisor como copia del chat (pre-registro)

**Corrido el 2026-11-11 (estructurales): NO PASA por los criterios 3 y 5.**
Los criterios 1 y 2 pasan (la Ley 1 vale con el chat y el padre ve lo que
gasta el hijo), pero lo que el spec prometía borrar no se borró y el producto
creció (7547 contra el techo de 7541). Consecuencia pre-registrada ejecutada:
el brazo se revierte entero, no se corre el A/B; quedan la sonda y este spec.
El brazo queda como evidencia fuera del árbol (`x203_brazo_no_pasa.patch`).

---

**Estado original: pre-registro, escrito ANTES de tocar el producto (2026-11-11).**
Cambia conducta (el supervisor deja de tener saldo propio), así que sin este
documento no se toca el código. Si algo cambia al correrlo, va como desvío
declarado al final; los criterios no se retocan después de ver los datos.
**Decisiones del operador (2026-11-11): D1 = A y D2 = A** (sección "Decisiones previas").

Paso siguiente de X202 (`docs/roadmap.md`). Principios que avanza: S0 (la copia
hereda el saldo), P2 (c) (jerarquía) y P2 (a) (cada instancia con su parte del
saldo), P4 (el supervisor es una composición, no un subsistema), N4 (un saldo,
no dos).

## La medición de partida (antes del código)

`banco/probes/saldo_supervisor.py` (sin LLM, sin red) corre el chat REAL con un
cliente falso: el chat pide `n` supervisores en una ronda y cada supervisor
pide leer hasta agotar su saldo. Medido sobre el árbol X202:

| supervisores en una ronda | llamadas reales | contadas por el saldo del chat | rondas descontadas al chat | cota 2R + 1 (R = 16) |
|---|---|---|---|---|
| 1 | 9 | 3 | 1 | 33 |
| 3 | 23 | 5 | 1 | 33 |
| 8 | **58** | 10 | 1 | 33 |

Con 8 supervisores el árbol hace 58 llamadas: **la Ley 1 se rompe** (58 > 33).
X202 hizo que el saldo cobrara lo que piden las tools, pero cada supervisor
arma su `Ledger(MAX_PASOS)` (`supervisor.py:223`) y le cobra a ese.

**Segundo hallazgo, que bloquea el diseño obvio.** Aunque el supervisor gastara
del `Ledger` del chat, el chat lo pisaría: `PasoChat.prep` re-deriva
`ledger.rondas = presupuesto − turno["rondas"]` antes de cada llamada
(`nodes.py:428`, decisión X140). Medido: una tool que toma 10 rondas del saldo
del árbol en cada ronda deja ver al chat `[16, 15, 14, 13]` — lo que gastó el
hijo no existe para el padre. Con el chat, "un saldo por árbol" hoy no se puede
cumplir sin tocar X140.

## Decisiones previas (del operador, antes del código)

**Decisión del operador (2026-11-11): D1 = A y D2 = A.** Las tablas de abajo
quedan como el registro de las opciones; el código y el A/B implementan A: el
`Ledger` manda y `turno` es su proyección, y `Ctx.hijo(tope=n)` arma el tope
propio con `MAX_PASOS = 5` para el supervisor.

**D1 — la fuente del saldo del chat** (choca con X140).

| Opción | Qué cambia | Costo |
|---|---|---|
| **A (recomendada)** | Dentro de una pregunta la fuente es el `Ledger`; `Observar` escribe `turno["rondas"] = presupuesto − ledger.rondas` (la proyección se invierte) y `PasoChat.prep` solo arma el `Ledger` al abrir la pregunta o al rehidratar un thread (`turno` es lo que viaja en el checkpoint) | revierte la dirección de X140; el gate fractal de X140 (8 mutantes) se re-escribe con la dirección nueva, 1:1 |
| B | `turno` sigue siendo la fuente y el hijo le suma sus rondas | el hijo no ve `shared` (P3, EL3): haría falta otro canal — es un segundo saldo con otro nombre (N4) |

**D2 — "su parte del saldo"** (P2 a). Hoy `Ledger` es uno y compartido: un
hijo puede gastarse todo lo del padre. El supervisor tenía 5.

| Opción | Qué cambia |
|---|---|
| **A (recomendada)** | `Ctx.hijo(tope=n)` arma un `Ledger` hijo con `min(n, padre.rondas)` cuyo `tomar()` descuenta de los dos (y `contar_llamada`, de los dos): primitiva del kernel, +≈8 líneas; `MAX_PASOS = 5` queda como el tope del supervisor |
| B | sin tope propio: el supervisor gasta lo que le quede al chat | 0 líneas; un supervisor puede dejar al chat sin saldo para responder (el cierre sin tools igual responde) |

## El brazo X203 (qué se borra y qué queda)

- `run_supervisor` pasa a ser la `Tool` de un agente del kernel: corre
  `supervisor.create_supervisor_flow` sobre `ctx.hijo(...)` (el mismo `llm`,
  el mismo saldo, profundidad + 1, la misma traza). El `Ctx` llega al módulo por
  el mismo canal que X202: el contextvar de `utils/tracing.py` deja de guardar
  solo el `Ledger` y guarda el `Ctx` (se reemplaza, no se suma un canal).
- **Se borra**: `Ledger(MAX_PASOS)` y el `ctx` propio de `Corrida`
  (`supervisor.py:223`); el filtro por nombre `!= "run_supervisor"`
  (`supervisor.py:49-50`), que pasa a ser la semántica de `agente()` —una
  copia no se tiene entre sus tools salvo `recursivo=True`— más la
  profundidad (`max_profundidad = 1`: el supervisor no puede delegar);
  `MAX_PASOS - ctx.ledger.rondas` como cuenta de rondas (el registro de la ley
  ya sabe en qué ronda corrió cada llamada).
- **Queda**: las leyes (`con_leyes`, `guarda_vetada`, `guarda_repetida`),
  `Auditar`, `Sintetizar`, la CLI `main.py supervisor` (sin padre: arma un `Ctx`
  raíz con `MAX_PASOS` como saldo, como hoy) y el contrato congelado de la
  sonda (`banco/probes/sonda_supervisor.py`, sin `run_supervisor`).
- **Declarado, no escondido**: el filtro por nombre no desaparece del todo,
  pasa al kernel como "una copia no-recursiva no se ofrece a sí misma"
  (`t is not propio`), que es la regla general y no un `if` sobre un nombre.

## Criterios (todos, o no pasa)

**Estructurales (sin LLM; los corre `./calidad.sh`):**

1. **La Ley 1 vale con el chat**: `banco/probes/saldo_supervisor.py 1 3 8` da
   `contadas_por_el_chat == llamadas_reales` y `llamadas_reales ≤ 2R + 1` en las
   tres filas. Se fija como test (`test_el_arbol_chat_supervisor_cumple_la_ley_1`,
   parametrizado en 1, 3 y 8), visto en rojo contra el árbol X202 antes del fix.
2. **El padre ve lo que gastó el hijo**: el caso de D1 (una tool que toma
   rondas del árbol) baja el saldo que ve el chat en la ronda siguiente. Test
   visto en rojo antes.
3. **Lo borrado se fue**: `grep -n 'Ledger(MAX_PASOS)' supervisor.py` y
   `grep -n '!= "run_supervisor"' supervisor.py` dan 0; `Corrida` no tiene `ctx`.
4. **Los gates de siempre**: `tests/test_gate_fractal.py` (los tres niveles,
   reescritos 1:1 si D1 = A, con la lista de los tocados en el reporte),
   `tests/test_contratos.py` sin regenerar sha1, `tests_definidos` no baja,
   `./calidad.sh` verde.
5. **Más chico**: `lineas_del_producto` ≤ 7541 (el número de X202). Si D2 = A
   suma más de lo que se borra, **no pasa**: el tope propio se vuelve otro
   pre-registro.

**De conducta (A/B, el cómputo igualado):** el supervisor desde el chat ahora
compite por el mismo techo de 16, así que puede cortar antes.

- **Brazos**: base (árbol X202) y X203, cada uno en su worktree.
- **Tareas**: las 6 de `banco/supervisor_tareas.jsonl`, pedidas AL CHAT con
  "usá run_supervisor para: …", 3 seeds → 18 corridas por brazo. Grading: las
  verificaciones deterministas de `banco/bench_supervisor.py`.
- **Denominador** (declarado y simétrico): las 18 corridas por brazo. Una
  corrida donde el chat no llamó a `run_supervisor` cuenta con su nota (0 o 1)
  en los dos brazos, y la adopción se informa aparte. Una tarea que se salta
  por falta de recurso (`tablas-trazas` sin `trazas.db`, `conteo-routing` sin
  `salidas/routing.jsonl`) se salta en los dos brazos y se declara.

6. **Calidad no inferior**: aciertos(X203) ≥ aciertos(base) − 1 sobre 18.
7. **Costo no mayor**: USD(X203) ≤ 1,0 × USD(base), misma tarifa.
8. **Ley 1 en el tráfico real**: en todas las corridas X203, las llamadas del
   árbol (traza `.runs`, eventos `llm`) ≤ 2 × 16 + 1.
9. **Seguridad**: 0 escrituras o comandos sin aprobación en los dos brazos.

## Decisión atada al resultado

- **PASA**: entra a `main` con sus docs en el mismo commit (`docs/design.md`,
  `docs/estado.md`, `docs/bitacora.md`, la fila de brechas de
  `docs/arquitectura.md`) y el `baseline.json` que el ratchet reescriba solo.
- **NO PASA**: se revierte entero; quedan la sonda y este spec. No vuelve como
  parche (N1) ni con otro tope dentro de este spec.

## Regla de gasto

Proyección (estimada, no medida): una corrida ≈ 3 llamadas del chat + ≈ 7 del
supervisor, prompts cortos → ~US$0,005–0,02; 36 corridas **US$0,20–0,70**.
Humo primero: `constante-max-pasos` seed 1 en los dos brazos; si cuesta más de
**US$0,05** se para y se reporta. Una corrida de banco a la vez.

## Fuera de alcance

- Que la tool **frene** (no solo cuente) a las demás capacidades (`research`,
  `juez`, ...): otro paso, con su pre-registro.
- Migrar otras capacidades a `kernel.loop` (X195 en adelante).

## Desvíos declarados

- D1 y D2 decididos por el operador el 2026-11-11: **A y A**, sin cambios de
  criterio.
- El canal de X202 se reemplazó como decía el spec (`tracing.SALDO` → `ARBOL`,
  que guarda el `Ctx`): sin canal nuevo.

## Resultado (2026-11-11, solo estructurales; el A/B no se corrió)

| # | Criterio | Medido en el brazo | |
|---|---|---|---|
| 1 | Ley 1 con el chat (1, 3, 8 supervisores) | `contadas == reales`: 9/9, 23/23, 33/33; todas ≤ 33. Los tres casos de `test_el_arbol_chat_supervisor_cumple_la_ley_1` vistos en rojo antes (3≠9, 5≠23, 10≠58) | ✅ |
| 2 | El padre ve lo que gastó el hijo | `[16, 12, 8, 4]` (antes `[16, 15, 14, 13]`); test visto en rojo antes | ✅ |
| 3 | Lo borrado se fue | `Ledger(MAX_PASOS)` sigue (la raíz de la CLI, más la mención del docstring) y el filtro `!= "run_supervisor"` **no se tocó**: sin él, el supervisor se ofrece a sí mismo y `run_supervisor` no es una `kernel.agente()` con chequeo de profundidad. `Corrida` conserva `ctx` (ahora una copia) | ❌ |
| 4 | Gates de siempre | suite 1486 passed, 20 skipped; ruff verde; `test_contratos.py` sin regenerar; un test de X140 reescrito 1:1 (`..._se_deriva_de_turno_...` → `test_el_saldo_del_chat_se_arma_al_abrir_la_pregunta_y_turno_lo_proyecta`) y 5 llamadas a `Observar()` adaptadas a `Observar(ctx, [])` | ✅ |
| 5 | Más chico: `lineas_del_producto` ≤ 7541 | **7547** (+6: `utils/kernel.py` +4 por el `Ledger` con padre y `hijo(tope)`, `supervisor.py` +2); `lineas_del_loop` 660 → 665 | ❌ |

**Lectura.** El mecanismo funciona: con D1 y D2 la Ley 1 vale de punta a punta
y, con 8 supervisores, el árbol se frena justo en la cota (33). Pero el spec
prometía que el cambio se pagaba borrando, y no se pagó: el supervisor no se
volvió una `kernel.agente()`, siguió siendo una tool de módulo que cuelga del
árbol por el contextvar, así que el filtro por nombre y la raíz de la CLI se
quedaron. **Dato de conducta nuevo, visto al medir**: con D1 un supervisor
desde el chat gasta del techo de 16 (3 supervisores lo agotan), así que el chat
puede cerrar antes; es lo que el A/B iba a medir.

**Lo que no vuelve como parche (N1).** Otra forma de pagar las 6 líneas
(borrar el filtro con un chequeo de profundidad en el despacho, hacer de
`run_supervisor` una `kernel.agente()` real) es otro pre-registro, con este
dato delante.
