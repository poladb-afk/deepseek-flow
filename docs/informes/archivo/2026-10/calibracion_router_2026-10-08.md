# Calibración conformal del router — primera tanda (exp/33)

**Qué se hizo.** `banco/probes/etiquetar_router.py` etiquetó **85 turnos reales**
(los `linea:` de los 62 escenarios del banco: son entradas que el driver tipea
al chat) con dos juicios por caso: el del **router local** (Laya, contrato
`PREGUNTA_ROUTER` congelado) y el del **árbitro** (DeepSeek, el mismo prompt del
voto de confirmación). El artefacto queda en
`banco/calibracion_router_2026-10-08.jsonl` y es lo que consume
`LAYA_CALIBRACION_ROUTER` (exp/31).

**Costo real:** 85 llamadas a DeepSeek (~3 min de reloj con el p50 medido de
2,1 s), 85 inferencias locales (~0,2 s cada una) y una carga de checkpoint
(2,86 GiB, una sola vez). Cero re-entrenamiento.

## Resultado del etiquetado

| Métrica | Valor |
|---|---|
| Casos | 85 |
| Acuerdo router ↔ árbitro | **77/85 = 0,906** |
| Etiquetas del árbitro | 84 `herramientas` · **1 `directo`** |

**El sesgo es el hallazgo**: la fuente disponible (escenarios del banco) es
casi toda tarea dirigida. Un set así **no puede calibrar el lado `directo`** —
la mitad conversacional del tráfico, que es justo donde el router ahorra la
llamada. Los `.log` del banco no sirven como fuente: el PTY corre con echo off,
así que `Tú:` queda pegado a la salida del chat y la pregunta tipeada no está
en el archivo (verificado).

## Evaluación honesta: calibrar acá, medir en el test de 30 (held out)

| alpha | q | umbral 1−q | cobertura en el test | decide local | precisión local |
|---|---|---|---|---|---|
| 0,05 | 0,678 | 0,322 | **0,967** | **0,900** | **0,963** |
| 0,10 | 0,577 | 0,423 | 0,933 | 0,967 | 0,931 |
| 0,20 | 0,319 | 0,681 | 0,867 | 0,900 | 0,963 |
| **hoy (fijo 0,85)** | — | 0,850 | — | 0,833 | **1,000** |

Las tres filas **respetan la cota** (cobertura ≥ 1−α) pese a que la calibración
vino de otra distribución: la confianza de Laya, no la mezcla de etiquetas, es
lo que domina el puntaje conformal.

## Lectura y decisión

- **α = 0,05 es el punto dulce medido**: 90% de decisiones locales (vs 83,3% de
  la compuerta fija) con cobertura 96,7% y precisión 96,3%. Se ganan ~2
  decisiones locales cada 30 turnos y se paga **1 error** (el "mundial" de
  0,831, que la compuerta fija bloquea).
- α = 0,10 sube a 96,7% local pero la precisión cae a 0,931: dos errores.
- La compuerta fija 0,85 sigue siendo la más precisa (1,000) y la menos
  eficiente (83,3%): es un presupuesto de riesgo ~del 5% aplicado a ciegas.

**Recomendación:** dejar la compuerta **opt-in** (como está) y, si se activa,
usar `LAYA_ALPHA=0.05`. Para calibrar el lado `directo` hace falta la pieza que
falta: **el chat no guarda las preguntas** (el trace solo tiene nodo/acción).
Una línea en `GetQuestion.post` que appendeé la pregunta a
`salidas/preguntas.jsonl` da, en una semana de uso, la muestra natural para
recalibrar — y ahí el α sí se puede apretar con datos propios.

## Reproducir

```bash
python3 banco/probes/etiquetar_router.py 87      # ~3 min de API, reanudable
python3 -c "..."                                 # evaluar (ver el commit)
```
