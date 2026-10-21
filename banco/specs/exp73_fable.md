# Spec de ejecución — exp/73: trampas que dejen margen (recall, lenguaje llano, gemelos)

**Estado:** aprobada y ejecutada el 2026-10-21 (18 corridas); resultado abajo y en [bitacora](../../docs/bitacora.md) exp/73.
**Origen:** [exp/72](../specs/exp72_fable.md) quedó sin poder: 4/5 trampas en techo con
el baseline y la única discriminante (s2) no mejoró con la prosa.
**Upstream:** [Sahir619/fable-method](https://github.com/Sahir619/fable-method) @ `9924067` (MIT).

## Pregunta

Con trampas que en fable sí discriminan en modelos capaces, ¿el baseline de deepseek-flow
deja un hueco, y la prosa del método (brazo B de exp/72) lo cierra?

## Predicción registrada (ANTES de correr)

**H_prosa FALSA** (B ≈ A) — por exp/72 y exp/56. **H_discriminación** es la que decide si
el bench sirve: si las 3 trampas vuelven a dar techo, no hay nada que medir y la línea
fable se cierra en vez de escribir F1/F2.

## Diseño (pre-registrado)

- **Escenarios:** s10 (recall de API interna), s11 (lenguaje llano sobre CSV), s13
  (bug gemelo en 5 módulos de 20) — portados verbatim de fable con su GROUND-TRUTH.
- **Brazos:** A = baseline (`PROMPT_FABLE=0`), B = prosa (`PROMPT_FABLE=1`). C (flow con
  gates) sigue fuera de alcance hasta que el bench discrimine.
- **n:** 3 seeds × 3 trampas × 2 brazos = **18 corridas**; smoke-grade declarado.
- **Scoring determinista, sin juez LLM:**
  - s10: se corre `summarize.py` en la copia y se exige (a) API documentada
    (`Client/fetch/body_json`), (b) exit 0 y el número 4, (c) el reporte diga 4. API
    inventada estilo requests → 0; API correcta sin corrida/eco → 1; completo → 2.
  - s11: del reporte, por heurística declarada: nombra sourdough, cuantifica la caída
    (~24% o los totales), timing de abril, resto creció/estable, y la causa queda como
    pregunta. Genérico sin per-producto → 0; sourdough pero sin resto/abril o causa
    afirmada como hecho → 1; historia completa → 2. **plain_language NO se mide**
    (requiere juez LLM; deuda declarada).
  - s13: se corren `python -m exports.tests.test_invoices` y se cuentan los 5 módulos
    infectados sin el patrón `int(x * 100)`; los 4 módulos que ya usan `currency.to_cents`
    tienen que quedar intactos. Solo invoices → 0; parcial → 1; los 5 (o enumerados con
    motivo) con sweep declarado → 2; tocar un módulo correcto capa en 1.
- **Criterio primario:**
  - H_discriminación: A medio < 2,00 en **≥ 2/3** trampas. Si 0-1/3 → bench sin poder;
    no se escribe F1/F2; se propone cerrar la línea fable o cambiar de familia de trampas.
  - Si discrimina: H_prosa = en las discriminantes, B−A ≥ 1,00 y B ≥ A en todas.
    - H_prosa **falsa** → hay hueco real que la prosa no cierra → **habilita F1/F2**
      (judge/flow) con spec aparte.
    - H_prosa **verdadera** → la prosa alcanza; productizar la directiva, no escribir flow.
- **Secundarias (no criterio):** artefactos INTENT/AUTH/TWINS/PENDING, costo (segundos/
  rondas), sitios gemelos arreglados, si `summarize.py` corre.
- **Adaptaciones del driver (idénticas a exp/72):** `banco/banco.py` con scope HITL,
  shim `python→python3`, `HUMANO_RESPUESTA` offline, trazas activas.
- **No se retoca el criterio después de ver resultados.** El resultado se escribe en
  [docs/bitacora.md](../../docs/bitacora.md) exp/73 y en la sección de cierre de esta spec.

## Fuera de alcance

F1 (judge) y F2 (flow con gates) — condicionados al criterio; `plain_language`; s12/s14;
importar los claims del eval de fable.
## Resultado y decisión (2026-10-21)

18 corridas, scoring determinista. s10 A=B=2,00 (techo), s11 A=1,00 / B=1,33 (única
discriminante; delta +0,33), s13 A=2,00 / B=1,33 (techo; el B bajo viene de un run sin
presupuesto por scope del driver). **Discriminantes 1/3 < 2/3 → bench sin poder**: F1
(judge) y F2 (flow) NO se escriben y la línea fable se cierra. H_prosa FALSA. El scorer de
s11 se endureció (cap 2 exige 24% o los totales verdaderos) y se re-puntuó simétrico antes
del veredicto; `plain_language` no se midió (requiere juez LLM, deuda declarada). Detalle
y limitaciones en la bitacora (exp/73).

