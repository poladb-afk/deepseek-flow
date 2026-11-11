# X197 — `research` con el template y la composición research + council (pre-registro)

**Estado: CERRADO (2026-11-11). Pre-registro escrito ANTES de tocar el
producto; los criterios 1–7 se midieron y el brazo quedó aceptado por el
operador con su clave (ver "Aceptación" al final). La composición cambia
conducta (es una capacidad nueva), así que sin este documento y las
decisiones D5–D8 del operador no se escribe el brazo.**

## El dato delante

- **X194**: el template (5 tipos, `Artefacto`, `Conector`, `componer()` en
  `utils/conector.py`).
- **X195/X196**: `fable` y `debate` declaran su `Conector` (producen
  `veredicto`); la foto de X196 fija los prompts de debate byte a byte y su
  arista es `consume=("pregunta",)`.
- **`research`** es el tercer pipeline sin arista: `modules/research.py` expone
  `deep_research` al chat y devuelve **la ruta** del informe; la pieza
  `research.py` (`investigar`) escribe el informe con fuentes web.
- La arquitectura pide: composición **declarada por el usuario** como dato,
  **validada al armar**, un adaptador entre tipos como módulo más, y **un solo
  saldo** por árbol (`docs/arquitectura.md`, "La composición").

## La forma de la composición

```
pregunta → [research] → borrador → [puente] → pregunta → [council] → veredicto
```

`componer(research, puente, debate)` arma; `componer(research, debate)` **no**
arma (`borrador` no encaja con `pregunta`). Por eso la arista de `debate` que
fijó X196 **no se mueve**: el puente es el adaptador que la arquitectura ya
prevee, no un ensanche del council.

## Decisiones (para el operador)

| # | Decisión | Opciones |
|---|---|---|
| **D5** | El artefacto de `research` | **A (recomendada) `borrador`**: el informe es un trabajo intermedio; sus fuentes son URLs y no verifican como cita `archivo:línea`. B `hallazgos`: el tipo exige citas `archivo:línea` verificables y research no las produce |
| **D6** | El contenido que viaja | **A (recomendada)**: el conector de research corre la pieza y devuelve el **informe**; el `IMPL` del chat sigue devolviendo la ruta (no se inunda el contexto del chat). B el puente lee la ruta que dejó el puntero (acopla al layout de `salidas/`). C cambiar el `IMPL` a contenido (rompe el contrato del chat) |
| **D7** | Quién declara la composición | **A (recomendada) CLI** `main.py composicion research_council "tema"`: la declara el operador y no suma tools al request. B una tool del chat (suma una tool justo antes del catálogo de X198) |
| **D8** | El puente `borrador → pregunta` | **A (recomendada) determinista**: arma la moción con el informe recortado, sin LLM (la decisión es de forma, no de contenido). B un LLM que formule la moción (+1 llamada, +costo, calidad sin medir). **C ensanchar `debate.consume` a `borrador`: rechazada, mueve la arista de X196** |

**Decidido por el operador (2026-11-11): D5 = A, D6 = A, D7 = A, D8 = A.**
El humo real (criterio 7) lo corre **Laboratorio**, no Código, con el tope de
**US$0,10** que autorizó el operador (el pre-registro había puesto 0,05: el
tope sube, se declara) y una corrida a la vez.

## El diseño con las A

- `modules/research.py`: `CONECTORES = (Conector(Tool("deep_research",
  TOOLS[0], correr_informe), "borrador", ("pregunta",)),)`; `correr_informe`
  llama a `investigar(tema)` y lee el informe (D6=A). El chat queda igual.
- `utils/composicion.py`: el puente, la tabla de composiciones
  (`COMPOSICIONES = {"research_council": (research, puente, debate)}`), el
  runner y `main(argv)`. `main.py` suma `"composicion": "utils.composicion"`
  en `SUBCOMANDOS` (import perezoso).
- El runner: `componer(...)` al armar (falla cerrada, sin gastar); un
  `kernel.Ledger(1)` para el árbol y cada tool por `correr_protegido` dentro
  de `tracing.cobrando(ledger, …)` (las llamadas de las dos piezas se cobran
  al mismo saldo; el puente no llama al modelo).
- La entrada es `Artefacto("pregunta", tema, "usuario")`; cada salida es
  `conector.producir(texto)`; el runner imprime el veredicto.

## Criterios

**Estructurales (sin LLM):**

1. `componer(research, puente, debate)` arma; `componer(research, debate)` y
   `componer(puente, research)` lanzan `ValueError` **antes** de gastar; la
   arista de `debate` no cambió (`consume=("pregunta",)`) y la foto de
   debate sigue **0 diferencias**.
2. El runner con LLM guionado: el puente arma la moción con el informe, el
   council produce el veredicto, y los prompts de research y debate son los
   de sus piezas (el council arranca con la moción del puente, no con el tema
   del usuario).
3. Un solo saldo: con el cliente real falso, las llamadas de la composición
   se cobran al `Ledger` del árbol (mismo patrón que los 3 tests de X202).
4. El contrato de X194 no se mueve: sus tests y `test_contratos.py` sin
   regenerar; `tests_definidos` no baja.
5. `lineas_del_producto` **≤ 7578 + 80** (estimado, no medido: research
   conector + `utils/composicion.py` + el CLI). Si sube dentro del techo, el
   operador lo acepta con su clave; si lo supera, **NO PASA** y se revierte.
6. Gates de siempre: suite verde, tipos 0, `./calidad.sh` 6/6.

**Humo real (gasto del operador):**

7. `main.py composicion research_council "<tema chico>"` con tope **US$0,10**
   (autorizado por el operador; se para y se reporta si lo pasa). Criterio: el veredicto sale, el ledger
   de la composición cuenta lo que las piezas hicieron (medido con la traza),
   y 0 acciones fuera de la política. **No hay A/B**: la composición es una
   capacidad nueva, no un reemplazo; comparar su calidad contra "research y
   después pedir el debate a mano" es otro pre-registro.

## Resultado estructural (2026-11-11)

| # | Criterio | Medido | |
|---|---|---|---|
| 1 | Validación al armar | `componer(research, puente, debate)` arma; `componer(research, debate)` y `componer(puente, research)` lanzan antes de gastar; la arista de `debate` no se movió (`consume=("pregunta",)`) y la foto de X196 sigue verde | ✅ |
| 2 | El runner corre con LLM guionado | el puente arma la moción con el informe; el council produce el veredicto | ✅ |
| 3 | Un solo saldo | 10 llamadas (5 de research + 5 del council) cobradas al `Ledger` de la composición | ✅ |
| 4 | Contrato de X194 quieto | tests de X194 y `test_contratos.py` sin regenerar; `tests_definidos` 1517 → 1523 | ✅ |
| 5 | Presupuesto | `lineas_del_producto` **7578 → 7650 (+72)**, dentro del techo 7658: **aceptado por el operador con su clave (2026-11-11)** | ✅ |
| 6 | Gates de siempre | suite **1519 passed**, `tests_definidos` 1523, cobertura **869 → 867**, tipos 0; gate **6/6** con la clave (`bypass del operador (clave verificada)`) | ✅ |
| 7 | Humo real | **PASA** (Laboratorio, 2026-11-11): "Ganador: proponente" con síntesis; **16 llamadas del árbol == 16 eventos `llm`** (research 11 + council 5); costo **US$0,0173** (techo 0,0179) ≤ 0,10; 0 `hitl`, 0 comandos, única escritura `salidas/research.md` | ✅ |

**Desvío declarado.** El primer corte dio **+85** (7663): 5 sobre el techo. Se
simplificó la misma pieza para entrar: fuera el guard de parámetro requerido
(el runner pasa el primer `required` del esquema, que las tres tools declaran),
fuera el `if __name__ == "__main__"` (el CLI entra por `main.py`) y la llamada
armada inline. Nada de eso cambia el diseño ni los tipos.

## Fuera de alcance

- El catálogo (X198) y el N simétrico (X199).
- La composición declarada por el modelo: acá la declara el operador.
- Recetas/cookbook y más de una composición.

## Decisión atada al resultado

- **PASA**: entra con sus docs en el mismo paso.
- **NO PASA** (criterio 5 o los estructurales): se revierte el brazo; quedan
  este spec y el instrumento. No vuelve como parche.

## Desvíos declarados

- **El humo se corrió con `ddgs` fuera del `.venv`**: la dependencia está en
  `requirements-opcionales.txt:5` y no estaba instalada; se instaló 9.16.1
  con `pip --target salidas/x197_humo/pylibs` y se usó por `PYTHONPATH`
  solo en ese proceso. El venv del gate no se tocó.
- **Costo medido de la traza**: el subcomando no pasa por `sesion()`, así
  que no imprime `[tokens] sesión`; se computó de los eventos `llm` de
  `.runs` con la tarifa de `utils/costos.py` (off-peak, `~`; el techo con
  todo el prompt como miss no subestima).

## Resultado del humo (criterio 7, 2026-11-11)

`main.py composicion research_council "¿Qué es PocketFlow y para qué sirve?"`
sobre la copia del árbol de trabajo (`f26e3c1` + el diff, 0 diferencias):
research (3 rondas, informe de 32 líneas) → puente → council (2 rondas +
juez), veredicto **"Ganador: proponente"**. Costo **US$0,0173** con split
de cache (US$0,0179 de techo) contra el tope de US$0,10; prompt 16.366,
completion 25.729, cache hit 3.968 en 16/16 llamadas. Sin acciones fuera de
la política. Informe: `docs/informes/x197_humo_2026-11-11.md`.

## Aceptación (2026-11-11)

**Aceptado por el operador con su clave (2026-11-11): baseline
`lineas_del_producto` 7650, `lineas_del_loop` 660, `tests_definidos` 1523;
gate 6/6.** El operador corrió `python3 ratchet.py --actualizar` y después
`./calidad.sh` con `HUMAN_RATCHET_BYPASS_KEY`: el ratchet imprimió
`bypass del operador (clave verificada)` y dejó IGUAL en 7650, 1523 y 660;
la etapa 5 dio cobertura **867** (`utils/composicion.py`: 0 líneas sin test)
y la 6, tipos **0**; la 4, **1519 passed, 27 deselected** (más 25 passed,
2 skipped de la pasada marcada). El criterio 7 queda ✅ con el humo real de
Laboratorio (**US$0,0173**, 16 llamadas del árbol == 16 eventos `llm`). El
commit del brazo lleva código, tests, docs y los dos baselines aceptados en
el mismo paso; `ratchets/cobertura.json` mejora (867), así que entra.
