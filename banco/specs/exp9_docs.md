# Spec exp/9 — docs: sección design.md + veredicto en roadmap

## 1. `docs/design.md` — sección después de la de exp/8

(Insertar después del bloque exp/8 que termina con "...documentado en
.env.example)." — texto textual):

```
### exp/9 — minería de errores: el triaje con Laya, descartado con el número a la vista (2026-10-06)

`minar_errores.py` minó las 108 trazas de `.runs/` (SIN torch, JSON puro;
reusa el parseo de evals). Límite honesto: la traza no guarda el texto del
error (solo tool + ok/error + segundos) — la causa es imposibilidad, no
omisión; lo medible es frecuencia, firma de duración y destino del
reintento.

- 43 errores de tools en 108 sesiones (18 sesiones con errores): frecuencia
  baja, ~0,4 por sesión.
- **Tasa de autocorrección 67,4%** (29/43): de los errores que la misma
  sesión reintentó (35), **33 terminaron bien (94%)** — el lazo
  error-como-feedback ES el triaje, y es gratis.
- edit_file concentra 27/43 (old_string que no matchea → el modelo corrige
  y reintenta, delta mediano 4 s); run_command 4/4 recuperados.
- Los 8 abandonos son mayormente timeouts de flujos largos (juez_lote,
  deep_research) donde el reintento no es decisión del modelo de todos modos.
- 4 timeouts con firma de duración ~100 s: si algo se automatiza, es un
  REINTENTO DETERMINISTA por firma (regla de código, no un modelo).

**Veredicto: el triaje con noul de Laya queda DESCARTADO por evidencia** —
a esta frecuencia y con esta autocorrección, una capa de decisión no agrega
valor; su costo (checkpoint, umbral, fallback) no se paga. Revisar si la
frecuencia de errores crece o si aparecen errores caros que el modelo no
puede autodiagnosticar.
```

## 2. `docs/roadmap.md` — actualizar la entrada de exp/9

Reemplazar la línea `- **exp/9 (pendiente)** — minar los 114 .runs: taxonomía de errores de
  tools y qué pasó después de cada uno; decide si el triaje con noul de
  Laya se justifica (evidencia antes que integración).`
por:
```
- **exp/9 ✅ mergeada** — minar_errores.py: 43 errores en 108 sesiones,
  tasa de autocorrección 67% (94% entre los reintentados) — el lazo
  error-como-feedback ya ES el triaje. **Triaje con Laya descartado por
  evidencia**; único candidato residual: reintento determinista para los
  4 timeouts por firma de duración. Sección en design.md.
```

## Reglas

Solo estas 2 operaciones textuales. Nada más.
