# exp/110 — la asimetría medida: hijos especializados (2026-11-04)

**Estado: corrido y dictaminado por el criterio pre-registrado — NO PASA.**
Hito X150. El pre-registro aprobado es `banco/specs/exp110_asimetria.md` (X148);
el instrumento, `banco/probes/exp110.py` y el montaje
`banco/probes/exp110_brazo_f/` (commit `f20c0e4`). Filas crudas:
`salidas/exp110/{A,F}.jsonl` (ignoradas por git); el veredicto automático, en
`salidas/exp110/veredicto.md`.

## Qué se midió

La replicación **simétrica** ya había dado 0 de 144 llamadas (exp/103 y
exp/105). Lo que nunca se midió es la **asimétrica**: el mismo loop con tres
hijos **especializados** de lectura —`barrido` (índice de archivos), `lectura`
(hechos con citas) y `sintesis` (borrador con citas)—, cada uno con su prompt y
su subconjunto de las tools del padre (P2c, X147), sin recursivo y a
profundidad 1.

- **Brazo A**: el chat de hoy sobre `kernel.loop` (X126), `SKILLS=0`, techo
  único 16, `deepseek-flash` pineado.
- **Brazo F**: A más los tres especialistas montados como tools del kernel
  (instrumento `exp110_brazo_f`, solo en F).
- **48 corridas**: 5 escenarios anchos (`s13`, `s17`, `s18`, `s19`, `s20`) +
  control `s2`, seeds 1–4, 24 por brazo, **0 errores** y todas con su línea
  `[tokens]`.

La Ley 1 se aplicó con el cobro del gasto de hijos a `turno` en
`ActuarChat.post` (desviación de instrumento declarada en el pre-registro): se
verificó en todas las corridas de F (**máximo 17 llamadas del árbol**, medio
10; el techo es 2R+1 = 33).

## Resultados

### Los cuatro criterios (pre-registrados, todos juntos)

| # | criterio | resultado | números |
|---|---|---|---|
| 1 | adopción: ≥ 2 de 4 seeds en ≥ 3 de los 5 anchos | ❌ | seeds con delegación: `s13` 1 · `s17` 2 · `s18` 0 · `s19` 0 · `s20` 2 → **2 de 5**; **6 delegaciones en 24 corridas** (`barrido` 5 · `lectura` 1 · `sintesis` 0) |
| 2 | calidad no inferior (margen −0,5) | ❌ | ancha **A 1,50 · F 0,95** (caída 0,55) · control `s2` A 1,00 · F 1,25 |
| 3 | costo ≤ 1,25× | ✅ | tokens medios ancha **A 115.471 · F 116.998 = 1,013×** |
| 4 | Ley 1: llamadas del árbol ≤ 33 | ✅ | peor corrida F **17**; sin montaje 0; sin línea de tokens 0 |

### Calidad por escenario (media de 4 seeds) y delegaciones

| escenario | A | F | delegaciones F (por seed s1–s4) |
|---|---|---|---|
| `s13-twin-fleet` | 1,50 | 1,50 | 0 · 1 · 0 · 0 |
| `s17-scale-audit` | 1,00 | 1,00 | 2 · 0 · 1 · 0 |
| `s18-real-audit` | 1,00 | 0,75 | 0 · 0 · 0 · 0 |
| `s19-real-audit-2` | 2,00 | 1,00 | 0 · 0 · 0 · 0 |
| `s20-real-audit-3` | 2,00 | 0,50 | 0 · 1 · 1 · 0 |
| `s2-surprise-trap` (control) | 1,00 | 1,25 | 0 · 0 · 0 · 0 |

La caída de la media ancha **no es toda del mecanismo**: `s19` y `s18` bajaron
**sin ninguna delegación** (son corridas del mismo mecanismo que A, o sea
varianza de 4 seeds), y el único escenario donde la caída coincide con
delegaciones es `s20` (2,00 → 0,50 con 2 corridas que delegaron). El criterio
escalar pre-registrado falló igual (0,55 > margen 0,50) y así se informa; lo
que la descomposición agrega es que el daño atribuible a la forma asimétrica es
más chico que el número escalar y que este A/B no alcanza para separarlo del
ruido.

### Forma del árbol (solo F)

- Delegaciones: **6 en 24 corridas**; por tool: `barrido` 5, `lectura` 1,
  `sintesis` 0. El modelo eligió el especialista de barrido y casi nunca los
  otros dos.
- D (Ley 2): `s17` 0,20; `s13` y `s20` 0,0 (divisiones con ramas de alcance
  mínimo); sin divisiones en `s18`/`s19`. **Fallas: 0**.
- Rondas medias: A 7,38 · F 7,08; llamadas al modelo: A 203 · F 245.

### Costo y duración

- Humo (4 corridas): **US$0,0104** (techo US$0,15); montaje ok, Ley 1 ok.
- Tanda (48 corridas): **A US$0,1388 · F US$0,1532 = US$0,2920**; total con
  humo **US$0,3024** de los **US$1,00** autorizados.
- 2.440.516 tokens (A) + 2.505.758 (F) = **4.946.274 tokens**; 937 s + 1.011 s
  sumados por corrida (≈33 min de chat); **~35–40 min de reloj** en secuencia.

## Veredicto y consecuencia pre-registrada

**NO PASA** por **adopción** (clara: 6 delegaciones en 24 corridas y el umbral
pedía ≥2 seeds en 3 de los 5 anchos) y por **calidad** (escalar 0,55 contra un
margen de 0,50), con costo y Ley 1 ✅. Como ata el pre-registro: la forma
asimétrica queda **medida y no adoptada**, con su número escrito, y P2 se
re-expresa con el dato, sin parche y sin forzar el criterio (N1). El montaje y
el runner **se conservan como evidencia** (desvío post-dato del operador,
declarado abajo), como los brazos de exp/103/104/105/107. El dato
nuevo y honesto: **la asimetría se elige más que la simétrica** (0 de 144
llamadas) **pero lejos del umbral pre-registrado** (6 de 24 corridas), y cuando
se elige, el especialista de barrido se lleva casi todo.

## Lo que este A/B no prueba (límites)

- Potencia y ruido: 4 seeds por escenario; la caída de calidad de `s19`/`s18`
  sin delegación muestra el tamaño del ruido, y el margen de 0,5 tenía ~1,8 %
  de rechazo por azar bajo la nula (calibrado antes de correr con el exp/105).
  El resultado escalar es el pre-registrado; la atribución fina no está
  identificada.
- El menú de F tiene **3 tools más** que A: aunque no delegue, el contexto
  cambia (exp/104 midió que una tool inerte no cambia la calidad; tres no se
  midieron). Es un confundido declarado del brazo.
- Hijos **solo de lectura**: no mide hijos con escritura, coordinación entre
  hijos ni reutilización de contexto.
- El montaje es **instrumento**: el experimento prueba la forma con los parches
  del montaje (menú, cobro de la Ley 1, inventario del juez), no que el
  producto cumpla la Ley 1 sin ellos (deuda abierta en el roadmap).
- Un modelo (`deepseek-flash`), un bench (`fable`, scoring por keywords y
  citas) y `s18` sin varianza histórica para calibrar.

## Desvíos declarados

1. **El humo y la tanda corrieron sobre `f20c0e4`** (el commit del montaje)
   cuando todavía no estaba pusheado; las filas llevan ese sha en `arbol`.
   Correr el humo antes del push fue una decisión de tiempo: si el commit
   cambiaba, el humo se repetía (cuesta ~US$0,01).
2. **Raíz de la tanda**: el runner fija `PYTHONPATH=""` en el brazo A (desvío
   de Código) para que A no herede un montaje del shell.
3. La columna "tools" del JSON del montaje lista los **tres especialistas**
   (contrato), no el menú completo de 34; el runner lo verifica como
   `montado: true` + `tools` con los tres.
4. **Post-dato (operador)**: el pre-registro ataba el retiro del montaje y del
   runner si NO PASA; el operador decidió conservarlos como evidencia
   (`f20c0e4` pusheado), igual que los brazos de exp/103/104/105/107 que siguen
   en el repo. Se decide después de ver el veredicto y por eso queda escrito
   acá; no cambia el resultado.

## Cómo se reproduce

```bash
python3 banco/probes/exp110.py --humo      # 4 corridas, techo US$0,15
python3 banco/probes/exp110.py --tanda     # 48 corridas (A y F)
python3 banco/probes/exp110.py --comparar salidas/exp110/A.jsonl salidas/exp110/F.jsonl
```

El runner no arranca `--humo/--tanda` sin X147 y el montaje, y la tanda exige
un humo válido del mismo HEAD.

## Las 48 filas

| brazo | seed | escenario | ca | tokens | deleg | arbol |
|---|---|---|---|---|---|---|
| A | 1 | `s13-twin-fleet` | 2 | 92314 | 0 | - |
| A | 2 | `s13-twin-fleet` | 2 | 82171 | 0 | - |
| A | 3 | `s13-twin-fleet` | 2 | 82915 | 0 | - |
| A | 4 | `s13-twin-fleet` | 0 | 103375 | 0 | - |
| A | 1 | `s17-scale-audit` | 1 | 93977 | 0 | - |
| A | 2 | `s17-scale-audit` | 1 | 82894 | 0 | - |
| A | 3 | `s17-scale-audit` | 1 | 56124 | 0 | - |
| A | 4 | `s17-scale-audit` | 1 | 71374 | 0 | - |
| A | 1 | `s18-real-audit` | 1 | 93813 | 0 | - |
| A | 2 | `s18-real-audit` | 1 | 31088 | 0 | - |
| A | 3 | `s18-real-audit` | 1 | 134122 | 0 | - |
| A | 4 | `s18-real-audit` | 1 | 99802 | 0 | - |
| A | 1 | `s19-real-audit-2` | 2 | 233458 | 0 | - |
| A | 2 | `s19-real-audit-2` | 2 | 74439 | 0 | - |
| A | 3 | `s19-real-audit-2` | 2 | 160057 | 0 | - |
| A | 4 | `s19-real-audit-2` | 2 | 116790 | 0 | - |
| A | 1 | `s2-surprise-trap` | 1 | 39030 | 0 | - |
| A | 2 | `s2-surprise-trap` | 1 | 26042 | 0 | - |
| A | 3 | `s2-surprise-trap` | 1 | 40108 | 0 | - |
| A | 4 | `s2-surprise-trap` | 1 | 25921 | 0 | - |
| A | 1 | `s20-real-audit-3` | 2 | 120396 | 0 | - |
| A | 2 | `s20-real-audit-3` | 2 | 247596 | 0 | - |
| A | 3 | `s20-real-audit-3` | 2 | 248481 | 0 | - |
| A | 4 | `s20-real-audit-3` | 2 | 84229 | 0 | - |
| F | 1 | `s13-twin-fleet` | 2 | 69896 | 0 | 8 |
| F | 2 | `s13-twin-fleet` | 2 | 99946 | 1 | 13 |
| F | 3 | `s13-twin-fleet` | 0 | 56336 | 0 | 7 |
| F | 4 | `s13-twin-fleet` | 2 | 95026 | 0 | 10 |
| F | 1 | `s17-scale-audit` | 1 | 124770 | 2 | 17 |
| F | 2 | `s17-scale-audit` | 2 | 67389 | 0 | 7 |
| F | 3 | `s17-scale-audit` | 0 | 149085 | 1 | 15 |
| F | 4 | `s17-scale-audit` | 1 | 62841 | 0 | 6 |
| F | 1 | `s18-real-audit` | 0 | 216265 | 0 | 16 |
| F | 2 | `s18-real-audit` | 1 | 130968 | 0 | 9 |
| F | 3 | `s18-real-audit` | 1 | 182359 | 0 | 15 |
| F | 4 | `s18-real-audit` | 1 | 166499 | 0 | 12 |
| F | 1 | `s19-real-audit-2` | 2 | 141815 | 0 | 9 |
| F | 2 | `s19-real-audit-2` | 0 | 143005 | 0 | 11 |
| F | 3 | `s19-real-audit-2` | 0 | 148583 | 0 | 8 |
| F | 4 | `s19-real-audit-2` | 2 | 45432 | 0 | 4 |
| F | 1 | `s2-surprise-trap` | 2 | 68934 | 0 | 9 |
| F | 2 | `s2-surprise-trap` | 1 | 33731 | 0 | 5 |
| F | 3 | `s2-surprise-trap` | 1 | 33108 | 0 | 5 |
| F | 4 | `s2-surprise-trap` | 1 | 30034 | 0 | 4 |
| F | 1 | `s20-real-audit-3` | 0 | 141221 | 0 | 9 |
| F | 2 | `s20-real-audit-3` | 0 | 140990 | 1 | 17 |
| F | 3 | `s20-real-audit-3` | 0 | 70947 | 1 | 17 |
| F | 4 | `s20-real-audit-3` | 2 | 86578 | 0 | 6 |
