# Spec de ejecución — exp/96: dried — la convergencia medida del loop del supervisor

**Estado:** aprobada 2026-10-23 (operador: "sigamos recomendación" del research
de SOTA). Es el diseño mínimo destilado en
[sota_experimentos_2026-10-23.md](sota_experimentos_2026-10-23.md) §3: la
industria parchea los loops con topes de iteración; la convergencia textual no
tiene fuente primaria — el `dried` del prototipo del operador
(`fractal_agent__1_.py:186-189`) es diseño propio.

## Pregunta

El supervisor corre hasta que el modelo deja de pedir tools (ruta "sintetizar")
o hasta `MAX_PASOS=5`. Si el modelo sigue pidiendo tools cuando los `hechos` ya
no aportan material nuevo, paga rondas sin información. **¿Con qué frecuencia
las rondas son secas?** ¿Y un corte por dos rondas secas consecutivas ahorra
rondas sin perder calidad? Precedente bifurcante: exp/52-B midió redundancia
~0 en el loop del chat y su corte quedó apagado — acá puede pasar igual, y
también es resultado.

## Diseño (pre-registrado; lo implementa el chat en sesión shadow)

1. **`seco(a, b, umbral=0.95)` PURA** en `utils/convergencia.py` (nuevo,
   ~30 líneas): normaliza espacios; iguales → True; si no,
   `difflib.SequenceMatcher(None, a, b).ratio() >= umbral`. Cero dependencias
   (stdlib). Tests: iguales, casi-iguales sobre el umbral, distintos bajo él,
   umbral borde, strings vacíos.
2. **Instrumentación en el supervisor** (telemetría SIN corte): al cierre de
   cada ronda, comparar el texto de los hechos NUEVOS de esta ronda contra los
   de la anterior; registrar la sequedad por ronda (una línea en la salida +
   `shared["secadas"] = [bool, ...]` para tests y para que la sonda lea).
   NADA cambia de comportamiento en esta fase.
3. **Sonda**: correr los escenarios supervisor existentes del banco
   (`supervisor-v2-aplicar.yaml`, `supervisor-v2-tests.yaml`, 1 corrida c/u) y
   reportar la frecuencia de rondas secas y de ≥2 secas CONSECUTIVAS por
   corrida.
4. **Criterio bifurcante (pre-registrado):**
   - Si ALGUNA corrida muestra ≥2 secas consecutivas → el corte se activa
     (segunda fase, misma sesión si alcanza el presupuesto): dos secas
     consecutivas retiran las tools como al llegar a MAX_PASOS (aviso
     `[supervisor] ronda seca ×2 → cierre`, `shared["seco_en"]`), con setting
     `SUPERVISOR_CORTE_SECO` (default 2; 0 = off) y test del corte.
   - Si NINGUNA → `seco` queda como utilidad pura + la telemetría, el ítem se
     cierra con la medición (estilo exp/52-B) y se declara en el resultado.

## Criterios

- **C1:** `seco` pura con tests (los casos de arriba).
- **C2:** telemetría por ronda en el supervisor (visible y testeable sin LLM:
  dos rondas con hechos idénticos registran seca).
- **C3:** sonda sobre ≥2 corridas reales del banco con el REPORT de frecuencia
  en el resultado de la spec.
- **C4:** si bifurca a corte: test del corte (dos secas cortan, una no, 0=off)
  y sin regresión de los marcadores del banco; gate verde.
- **C5 (meta):** sesión shadow con origen terminal — par #10 de la flywheel.

## Fuera de alcance (declarado)

Cambiar MAX_PASOS, tocar el loop del chat (exp/52-B ya lo midió), paralelismo,
el `until_dry` del prototipo (otro loop), juez/debate.

## Resultado (2026-10-24)

C1 ✅ `seco` pura en `utils/convergencia.py` (37 líneas) con tests (iguales,
normalización, umbral con ratio exacto calculado, vacíos, paramétrico). C2 ✅
telemetría tanda-vs-tanda en `Ejecutar.post` (la primera versión comparaba el
ACUMULADO contra acumulado+nuevos — el prefijo idéntico inflaba el ratio y toda
ronda tardía salía seca; el supervisor RECHAZÓ el edit y la corrección llegó
por mensaje del auditor). C3 ✅ **sonda: 4 tareas reales + 1 corta = 10
comparaciones de ronda, CERO secas; ninguna corrida con ≥2 secas
consecutivas.** C4 bifurcó a **NO**: el corte no se activa; `seco` queda como
utilidad pura + telemetría de costo cero, y el ítem se cierra con medición
(precedente exp/52-B). Lectura estructural: el supervisor es un loop de
PLANIFICACIÓN (cada paso elige una tool distinta — material nuevo por
construcción), no de REFINAMIENTO; dried aplica a loops que mejoran el mismo
artefacto (el `until_dry` del prototipo envolvía un refiner). Si el debate
algún día se mide girando en redondo, la utilidad ya está. C5 ✅ pares #10 y
#11 (la sesión tuvo dos preguntas: la tarea y la corrección de la métrica).

**Incidente de auditoría (declarado):** el árbol terminó con cambios en
`supervisor.py` que NO estaban en los hunks visibles del panel al aprobar
(remoción de `catalogo()` — que `sonda_supervisor.py` importa — y refactor del
`system_prompt`): el panel TRUNCA diffs multi-hunk y el supervisor aprobó
vistas parciales. Resolución: `git checkout` + reaplicación textual de los 4
hunks aprobados (del log de sesión). Lección HITL: el diff de `edit_file`
debería mostrar el cambio completo o declarar cuántos hunks quedan fuera de
vista — queda como mejora del instrumento. Otros ajustes del auditor: split de
`test_flujos.py` (841 → 733 + `test_supervisor_convergencia.py` 113) por el
tope de 800, y el inventario NO se tocó (foto congelada del PR 4; convención
desde exp/89 — el intento de la sesión se rechazó).
