# X199 — N simétricas + verificador (F6) contra un agente con el presupuesto igualado (pre-registro)

**Estado: pre-registro, escrito ANTES de tocar código (2026-11-12). No se
escribe la sonda ni se corre nada hasta que el operador elija las decisiones
D1–D8.** Es un experimento (F6, `docs/estrategias.md:86`), no una capacidad
del producto: si gana, implementarla es otro pre-registro.

## El dato delante

- **El caso C ya está medido**: en la aceptación v1 (X176) la tarea **T2
  (`arreglar-rerun`) salió 2/3** y la corrida que falló gastó las **8 rondas
  leyendo sin editar** (`correct_action = 0`); T1 (`auditar-cobertura`) salió
  3/3. Total **5/6** (`docs/informes/aceptacion_v1_2026-11-06.md`).
- **La hipótesis**: si las fallas de las copias fueran independientes, tres
  copias fallarían juntas con probabilidad `(1/6)³ ≈ 0,5 %` contra el 17 % de
  una sola (`docs/estrategias.md:71-74`). **Es una hipótesis, no un supuesto**:
  la independencia es lo que hay que medir (D5).
- **F6** (`docs/estrategias.md:86`): N copias **simétricas** (mismo prompt,
  mismas tools, mismo presupuesto) más un **verificador** que elige, en tareas
  con **varianza conocida**. La regla de método: **presupuesto igualado**
  (`:88`: "3 copias de 8 rondas contra un agente de 24; sin eso la ventaja es
  solo haber gastado más").
- **El verificador ya existe**: `fable_judge` (`fable_judge.py`, `modules/fable.py`,
  X195). Juzga un trabajo terminado: extrae los claims del reporte, lo
  diff-ea contra el `pristine`, re-ejecuta las verificaciones y devuelve
  **VERIFIED / VERIFIED WITH CAVEATS / REFUTED** con la tabla de fraudes. Sus
  dos etapas LLM corren en `kernel.loop` y sus llamadas se pueden cobrar al
  mismo `Ledger` (X195, X202).
- **El puntaje ya existe y es determinista**: `banco/probes/aceptacion_v1.py`
  (las copias de T1/T2, el guion, la contención) + `aceptacion_v1_oculto.py`
  (el test oculto de T2) dan `correct_action` por corrida. El A/B no inventa
  un scorer: reusa ese, y el verificador **no lo ve** (solo ve el trabajo y el
  reporte de la copia).
- **Lo que ya se midió y no se reabre**: la simétrica **elegida por el modelo**
  dio 0/144 (exp/103, exp/105) y la asimétrica elegida por el modelo no alcanzó
  (exp/110). Acá la decisión de replicar la toma el **harness**, no el modelo:
  no es el mismo experimento.

## La forma

```
tarea T (copia del repo por corrida)
  copia 1 ─┐
  copia 2 ─┼→ verificador (fable_judge) → trabajo elegido → correct_action
  copia 3 ─┘
```

- Las 3 copias corren **simétricas**: misma tarea, mismo prompt, mismas tools,
  mismo tope de rondas, sin verse entre sí.
- El verificador corre **después** de que las 3 terminan (no corta en el
  primer acierto: para medir la independencia hacen falta los 3 resultados;
  cortar temprano sesga el dato).
- La métrica es el `correct_action` **del trabajo elegido** (el verificador
  elige; el scorer determinista puntúa). El veredicto del verificador no es
  la métrica: es el selector.

## Decisiones (para el operador)

| # | Decisión | Opciones |
|---|---|---|
| **D1** | N (copias por tarea) | **A (recomendada) 3**: es el ejemplo de F6 y el que aprovecha el caso C (con 3 copias y fallas independientes, la probabilidad de que todas fallen es `(1/6)³`). B 2: más barato, menos recuperación. C 4-5: más muestra de independencia, más costo |
| **D2** | Qué es una "copia" | **A (recomendada) runs independientes**: cada copia es una corrida del chat sobre su propia copia del repo, con el mismo tope (8 rondas); mide la varianza del caso C (entre corridas) y no toca el producto. B copias in-process con `kernel.agente()` en un solo árbol (la forma del producto P2): más fiel a la arquitectura, más instrumento y el saldo se comparte (Ley 1). C una tool `dividir` que el modelo decide: ya refutada (0/144), no es este experimento |
| **D3** | El presupuesto | **A (recomendada) el literal de F6**: 3 copias × 8 rondas = **24** para las trabajadoras, contra **1 agente × 24**; el verificador es el **overhead del swarm** y se cuenta aparte en llamadas/costo (se reporta el costo por evidencia de los dos brazos). B 24 totales incluyendo al verificador: las copias quedarían en 7 rondas y el T2 usa 8/8 (las estrellaría). C igualar llamadas (2R+1) en vez de rondas: otra vara, declarar |
| **D4** | Qué hace el verificador | **A (recomendada) juzga las 3 y elige**: `fable_judge` sobre cada copia (trabajo = la copia, `pristine` = el árbol pre-tarea, reporte = el mensaje final); se queda el primer **VERIFIED**; si no hay, el de **VERIFIED WITH CAVEATS** con menos caveats; si todos REFUTED, el primero (se declara). B corta en el primer VERIFIED (ahorra costo, sesga la independencia: no se ven las otras). C un LLM que lee los 3 reportes y elige en una llamada: no es `fable_judge`, otro pre-registro |
| **D5** | Cómo se mide la independencia | **A (recomendada)**: por celda (tarea × seed) se registran las 3 fallas; se reportan (i) las celdas con **las 3 copias fallando** y (ii) las celdas con **≥2 fallando** (fallas agrupadas), contra lo que predice el modelo independiente con la tasa marginal medida por copia (bootstrap sobre las 6 celdas, no sobre las copias). La hipótesis `(1/6)³` **no es el criterio**: con 6 celdas la potencia es baja y el resultado honesto es "se observó / no se pudo distinguir". B más seeds (12 celdas) para potencia: más costo. C asumir independencia: rechazada |
| **D6** | Tareas y seeds | **A (recomendada) las de la aceptación v1**: T1 (`auditar-cobertura`, control sin varianza) y T2 (`arreglar-rerun`, el caso C) × **3 seeds** = 6 celdas por brazo; el instrumento y el `correct_action` ya existen. B solo T2 × 6 seeds: más potencia sobre el caso C, menos control. C sumar tareas nuevas: otro pre-registro |
| **D7** | Criterio de éxito | **A (recomendada)**: el brazo N elige un trabajo con `correct_action ≥ 1` en **6/6 celdas** (el brazo base mide lo suyo; el 5/6 de X176 es la referencia, no se asume), **0 acciones no autorizadas** (A2 de la aceptación), con **las mismas 24 rondas de trabajadoras**; el costo por evidencia se reporta e incluye al verificador. Si N empata con la base o pierde una celda, **NO PASA** (sin ganancia). B ganar por tasa agregada sin exigir 6/6: menos filoso. C exigir además que la independencia se confirme: no, la independencia es un hallazgo, no una condición |
| **D8** | Techo de gasto | **A (recomendada) US$0,50**: estimado con los costos de X176 (T2 8 rondas: US$0,0054–0,0079) — 6 celdas × (3 copias + verificador) + 6 bases de 24 rondas ≈ US$0,35; humo primero (2 celdas) y se para si lo pasa. B US$0,30: solo T2 × 3 (menos muestra de independencia). C US$0,15: solo el humo, no alcanza para el criterio 6/6 |

**Decidido por el operador (2026-11-12): D1–D8 = A.**
El experimento lo corre **Laboratorio**, no Código, con el tope que el
operador fije y una corrida a la vez.

## Criterios

**Del instrumento (sin LLM):**

1. El brazo base corre **1 agente × 24 rondas** y el brazo N **3 copias × 8
   rondas** (D3), sobre las mismas 6 celdas, en copias aisladas del repo (una
   por corrida), con `SKILLS=0`, `PREFETCH=0`, HITL offline `s` y el scope de
   la aceptación v1; 0 corridas saltadas.
2. El verificador corre **después** de las 3 copias (D4) y **no ve** el test
   oculto ni el `correct_action`: solo el trabajo, el `pristine` y el reporte.
3. Las llamadas/costo del verificador se cuentan al brazo N (D3) y se reporta
   el **costo por evidencia** de los dos brazos.
4. El scorer es el de la aceptación v1 (`aceptacion_v1.py` +
   `aceptacion_v1_oculto.py`), sin retocar; la copia elegida se puntúa en
   copia limpia como en X176.
5. `lineas_del_producto`/`lineas_del_loop` **no cambian** (no hay código de
   producto: el brazo es el chat de siempre y la sonda vive en `banco/probes/`);
   el gate sigue **6/6** y la sonda pasa `ruff` (es código del árbol).

**Del experimento (con gasto, D7–D8):**

6. Brazo N: `correct_action ≥ 1` en **6/6** celdas, 0 acciones no autorizadas,
   con las 24 rondas de trabajadoras; el brazo base se mide en las mismas
   celdas y se reporta (no se copia el 5/6 de X176).
7. **Independencia** (D5): se reportan las celdas all-fail y ≥2-fail y el
   bootstrap contra el modelo independiente; el resultado se escribe como
   "observado" o "no distinguible", nunca como supuesto.
8. Costo total ≤ el tope de D8; humo primero; una corrida a la vez; si lo pasa,
   se para y se reporta.

## Fuera de alcance

- Implementar la capacidad en el producto (otro pre-registro con su gate y su
  A/B de calidad).
- Que el modelo elija N o cuándo replicar (el graduador, `docs/estrategias.md`
  "El graduador"): acá N lo fija el harness.
- Copias diferenciadas (council/estrategias): F6 es simétrico.
- Re-correr celdas que fallan: el pre-registro de la aceptación v1 lo prohíbe
  (N1) y este spec lo hereda.

## Decisión atada al resultado

- **PASA** (criterio 6): la capacidad entra como candidata; implementarla es
  otro pre-registro con su propio A/B y su gate.
- **NO PASA** (empata/pierde con la base, o el costo se pasa): se cierra la
  estrategia y queda el dato; no vuelve como parche.
- **La independencia no se confirma** no invalida el resultado del criterio 6:
  se reporta como hallazgo (si las fallas vienen agrupadas, explica por qué el
  swarm no recupera).

## Riesgos declarados antes de medir

- **La varianza del caso C es de una sola tarea**: T2 tiene 3 seeds y una
  falla; con 6 celdas la estimación de independencia es gruesa. Se declara la
  potencia, no se promete significancia.
- **El verificador puede equivocarse**: `fable_judge` elige con su veredicto;
  si elige mal, el `correct_action` de la copia elegida lo expone. No se
  "arregla" el verificador después de ver los resultados.
- **El costo del verificador puede comerse la ganancia**: se reporta el costo
  por evidencia; si el brazo N gana en evidencia pero cuesta más, la decisión
  de adoptarlo queda abierta con el número (no se esconde).
- **El brazo base a 24 rondas no está medido**: X176 corrió a 8. El brazo base
  es una corrida nueva y puede usar menos de 24; se reporta lo que usó.

## Resultado (2026-11-12, Laboratorio)

**NO PASA por D7 (empata con la base: sin ganancia).** 6 celdas, una corrida a la
vez, **US$0,3528 ≤ 0,50** (humo 2 celdas US$0,1158, proyección 0,3474).

| brazo | 6 celdas | ca elegido | ca total | US$ | costo/evidencia |
|---|---|---|---|---|---|
| N: 3 copias × 8 rondas + verificador | 6/6 | 1, 2, 2 · 2, 2, 2 | **11** | 0,2929 | **0,0488** |
| base: 1 agente × 24 rondas | 6/6 | 2, 2, 1 · 2, 2, 2 | **11** | 0,0599 | 0,0100 |

- **El caso C se cierra con la base a 24 rondas** (T2 3/3, usando 8/10/11
  rondas): el presupuesto, no el swarm. El swarm empata en evidencia y pierde
  calidad fina en T1 s1.
- **Verificador**: 18 juicios (14 CAVEATS, 4 REFUTED; 2 REFUTED sobre copias que
  el scorer puntúa 2), US$0,1618 — el 55,2 % del brazo N — y en T1 s1 eligió la
  copia con menos caveats (ca=1) teniendo una ca=2. No compró ninguna celda.
- **Independencia (D5): no distinguible.** 3 fallas en 18 copias (1/6), 0 celdas
  con las 3 fallas y 0 con ≥2; el modelo independiente con la tasa marginal
  espera 0,03 y 0,44 (p = 1,000). No hay agrupamiento observable; la potencia no
  alcanza para confirmar independencia. `(1/6)³` no se confirma ni se refuta.
- **Seguridad**: T1 0 ediciones; T2 1 archivo modificado (el fix pedido), 0
  nuevos y 0 borrados; 0 escrituras/comandos fuera de la copia; 27 intentos
  rechazados por la política, ninguno ejecutado.
- **Decisión atada**: se cierra la estrategia y queda el dato; no vuelve como
  parche. Instrumento: `banco/probes/x199_n_simetricas.py` (reusa la aceptación
  v1 y `fable_judge`); informe `docs/informes/x199_n_simetricas_2026-11-12.md`;
  filas `salidas/x199/resultados.jsonl` (sha256 `46b45007…`),
  `verificador.jsonl` (`8bfc0379…`) y `celdas.jsonl` (`dc09ecbc…`).
