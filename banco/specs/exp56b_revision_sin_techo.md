# Spec de ejecución — exp/56b: skill `revision` SIN techo (corrida diferida de exp/56)

**Estado:** ejecutada el 2026-10-22 (6 corridas); C0 ✅ hay margen, **C1 FALSA (sin excusa de techo)**, C4 ✅ — resultado en bitácora exp/56b.

## Contexto

exp/56 midió la skill `revision` con el techo puesto: el `[pre-fetch]` inyectaba el archivo y
el control ya detectaba 3/3 — la hipótesis de detección era inmedible (NO CUMPLE por techo, no
por señal). El siguiente paso quedó pre-registrado: **quitar el techo ANTES de medir** —
`PREFETCH=0` (el modelo tiene que leer por tools) + fixture con issues sutiles.

## Diseño

- **Fixture:** `s16-hard-bug-hunt` (exp/75): 8 bugs sutiles — semánticos, de estado y de
  concurrencia (race check-then-act, shallow copy, float en centavos, idempotencia, atributo
  de clase compartido, iterador exhausto, lock sin finally, utcnow naive) en 4 archivos.
- **Brazos:** A control (`SKILLS=0`) vs C skill `revision` (`SKILLS=1`); 3 seeds = 6 corridas.
- **Techo removido en ambos:** `PREFETCH=0` exportado en el entorno del bench (el banco
  hereda `os.environ`; el env del escenario no lo pisa).
- **Scoring:** determinista (`puntuar_s16`: recall /8 por keywords de la GT, citas validadas
  contra el disco con `utils/citas`, conteo de palabras del reporte).

## Criterio (congelado — el de exp/56, adaptado a /8)

- **C0 (precondición de poder):** el control A tiene que quedar bajo techo — recall medio
  A < 8/8. Si A sigue en 8/8, el bench sigue sin poder y se DECLARA (no se retoca nada).
- **C1 (hipótesis):** recall medio C ≥ A + 1,0.
- **C2:** citas válidas C ≥ A. **C3:** citas inválidas C = 0.
- **C4 (señal secundaria de exp/56):** palabras C ≤ 1,4 × A.
- **Predicción registrada:** con PREFETCH=0 el control baja (leer 4 archivos por tools en 8
  rondas cuesta; exp/21 midió p90 16 rondas para alcance amplio). La skill guía el FORMATO
  (ruta:línea — problema — fix) y el subset de tools, pero no las ubicaciones: espero lift
  chico o nulo en detección (C1 al límite) y el ruido otra vez a favor de C.

## Fuera de alcance

Cambiar la skill, PROMPT_FABLE (brazo B), F2, el checklist D.


## Resultado (2026-10-22)

| brazo | recall anclado /8 por seed | media | citas válidas | palabras |
|---|---|---|---|---|
| A control (PREFETCH=0) | 8 · 8 · 7 | **7,67** | 53/53 (100%) | 1.468 |
| C skill revision | 8* · 7 · 6 | **7,00** | 33/34 (97%) | **601** |

(*s1 ancló los 8 pero con 1 cita inválida → ca=1.)

- **C0 ✅**: sin pre-fetch el control YA NO está en techo perfecto (7,67/8;
  el modelo lee 4 archivos por tools en 2-4 rondas — la inyección del
  pre-fetch no era la fuente del techo en s16).
- **C1 ❌ FALSA**: C (7,00) no solo no supera A+1 (8,67): queda −0,67 POR
  DEBAJO del control, con más varianza (hasta 6/8; perdió H3 float-centavos
  y H7 lock-sin-finally). La skill no mejora la detección.
- **C2 ❌** por conteo (33 vs 53; por tasa 97% vs 100%). **C3 ❌**: 1 cita
  inválida en C s1.
- **C4 ✅ holgado**: 601 vs 1.468 palabras = **0,41× (−59%)** — replica y
  agranda la señal de ruido de exp/56 (−40%).
- Nota de instrumento: el resumen auto-generado aplica el template de
  exp/72 (brazo B ausente); la lectura oficial es este criterio congelado.

**Conclusión:** la conclusión de exp/56 queda sostenida SIN la limitación del
techo: la skill `revision` es un reductor de ruido (−59% palabras a
detección comparable), no un detector. SKILLS queda como está (opt-in).
