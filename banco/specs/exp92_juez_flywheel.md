# Spec de ejecución — exp/92: el juez re-ejecuta lo que importa — y arranca la flywheel

**Estado:** aprobada 2026-10-23 (operador: "acepto" — exp/92 como primera ventana
shadow). Las dos fricciones quedaron medidas en exp/91: el juicio 1 no
re-ejecutó NADA (el presupuesto de claims se llenó de descripciones antes de
llegar a las verificaciones) y el juicio 2 no pudo re-ejecutar `ruff check`
(la política no lo lista como solo-lectura y el HITL bloquea corridas sin
terminal).

## Pregunta

¿Pueden ambas fricciones arreglarse sin relajar nada más — y la propia sesión
de trabajo ser la primera ventana `LAYA_MODO=shadow` que arranca la flywheel
del router (≥250 pares / ≥14 días, hoy 0/250 y 0/14)?

## Diseño (pre-registrado)

**Fix 1 — prioridad de claims verificables** (lo implementa el CHAT del
harness en la sesión shadow, `PROMPT_FABLE=1`):

- En `fable_judge.validar_claims`: el corte de `MAX_CLAIMS=12` hoy se queda
  con los primeros 12 claims del orden en que los listó el LLM — si el reporte
  describe mucho y verifica al final (el formato outcome-first natural), las
  verificaciones quedan fuera y el juicio sale ciego.
- Nuevo comportamiento: se validan TODOS los claims (un claim inválido falla
  como hoy, sin zona muerta tras el corte); si hay más de `MAX_CLAIMS`, la
  selección prioriza los de `tipo: verificacion` (en su orden) y completa con
  el resto hasta el tope. El claim sintético de presupuesto (F7) se mantiene y
  su texto dice la verdad nueva: que se priorizaron los verificables.
- El prompt de claims NO cambia: los tipos ya salen bien (medido en exp/91,
  juicio 2); la prioridad es post-procesamiento determinista.

**Fix 2 — `ruff check` solo-lectura** (lo implementa el OPERADOR, no el chat:
separación de deberes — el agente no relaja su propia política de comandos;
cambio autorizado por el operador, precedente A45):

- `utils/policy.py`: `_LECTURA` suma los prefijos `("ruff", "check")` y
  `("python3", "-m", "ruff", "check")` con rótulo honesto ("lintea — parsea el
  código SIN ejecutarlo; escribe caché").
- `_FLAGS_PELIGROSOS["ruff"] = ("--fix", "--fix-only", "--watch")`: lo que
  ESCRIBE archivos o cuelga sigue preguntando. `ruff format`, `ruff` a secas y
  cualquier otra forma NO matchean el prefijo y siguen preguntando.
- La normalización de base para flags (hoy `python3 -m pytest` → `pytest`)
  se generaliza para que `python3 -m ruff check --fix` TAMBIÉN quede vetado
  (hoy la forma modular esquivaría el veto).
- Nada más cambia de nivel: es la admisión más conservadora posible —
  estrictamente más segura que `pytest`, que ya está admitido con riesgo
  aceptado y documentado (A45 ejecuta conftest/plugins; ruff solo parsea).

**La sesión shadow (la ventana):**

- La sesión del chat corre con `LAYA_MODO=shadow` (origen `terminal`, NO
  banco — el banco no cuenta por diseño), `PROMPT_FABLE=1`,
  `MAX_TOOL_ROUNDS=40`, `COMPACTION_CHARS=120000`.
- Orden: fix 2 ANTES de la sesión — así el chat puede verificarse con pytest
  Y `ruff check`, ambos auto, y la sesión ejercita la política nueva en vivo.
- Verificación de la sesión: SOLO `python3 -m pytest` y `ruff check` (auto);
  la sesión es dirigida por stdin sin humano para los s/n.

**RAM (declarado):** `LAYA_MODEL_VOTO=0` en la sesión — el voto local cae al
árbitro DeepSeek y ahorra ~2–3 GiB (precedente exp/3: router+voto en un
proceso dio OOM). Con el router solo (~2,9 GiB) queda margen. Monitoreo con
`free -h` durante la sesión; el gate completo corre el auditor DESPUÉS,
secuencial.

## Criterios

- **C1:** claims — con >12 claims y las verificaciones al final, las
  verificaciones sobreviven al corte y el claim de presupuesto declara la
  prioridad; ≤12 claims no cambia nada; verificaciones solas >12 se capean;
  un claim inválido en cualquier posición falla como hoy.
- **C2:** política — `ruff check .` y `python3 -m ruff check .` auto con
  rótulo honesto; `ruff check --fix`, `--fix-only`, `--watch`, `ruff format`
  y `python3 -m ruff check --fix` preguntan; NINGÚN otro comando cambia de
  nivel (la suite de policy existente sin tocar).
- **C3 (re-juicio recursivo):** el juez MEJORADO audita el trabajo de exp/92
  (fix 1 del chat + fix 2 del operador): las verificaciones del reporte
  entran al presupuesto, pytest Y `ruff check` se re-ejecutan.
- **C4:** gate verde completo (auditor, post-sesión).
- **C5 (flywheel):** la sesión shadow deja su par en `routing.jsonl` con
  origen `terminal`; `estado_flywheel.py` refleja progreso (el reloj de los
  14 días arranca).

## Fuera de alcance (declarado)

Cambiar el prompt de claims, el techo global del prompt de juicio (exp/87),
otras admisiones de política, el voto local en la sesión (RAM), correr
`etiquetar_ambiental` (pisa el artefacto de calibración hasta la revisión).

## Resultado (2026-10-23)

C1 ✅ (7 casos; enmienda declarada: en el borde de EXACTAMENTE 12 claims el
claim sintético de presupuesto YA NO se agrega — el código viejo lo agregaba
mintiendo ("el resto no fue juzgado" sin resto); la spec decía "≤12 no cambia
nada" y el juez lo marcó como spec_betrayal: la spec se enmienda, el código
queda). C2 ✅ con AMPLIACIÓN post-refutación: el re-juicio destapó que
`--add-noqa` (reescribe código, verificado en vivo) y `-o/--output-file`
(escribe a ruta arbitraria) quedaban en auto — vetados + tests, incluidas las
formas pegadas con `=` (el juez acusó un by-pass ahí: falso positivo,
verificado empíricamente — el matcher ya las vetaba; casos clavados). C3 ✅
ronda 1: los 3 claims verificables re-ejecutados exit 0, `ruff check` en auto
— los dos fixes probándose en vivo; el veredicto igual fue REFUTED por el
agujero de --add-noqa (con razón). Ronda 2: REFUTED con un falso positivo (el
`=`) y el hallazgo real del borde de 12. C4 ✅ gate verde (924 passed + 3
skips; test_fable_judge.py partió en `test_fable_judge_claims.py` por el
tope de 800 líneas: 688 + 167). C5 ✅ **pares 1/250, días 1/14** — la sesión
shadow (tmux, origen terminal, 4 aprobaciones supervisadas, costo ~$0,0071)
registró su par. RAM: mínimo ~4,3 Gi disponibles con LAYA_MODEL_VOTO=0
(desviación declarada).
