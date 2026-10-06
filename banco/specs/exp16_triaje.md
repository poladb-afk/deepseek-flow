# Spec: triaje_trazas.py — qué trazas vale la pena auditar (exp/16)

(Motivo medido: la auditoría nocturna sobre TODAS las trazas cuesta N
llamadas LLM que crece sin techo (176 hoy). El triaje DETERMINISTA
(linter + outliers de duración) selecciona 37/176 (21%) — el ahorro del
79% no necesita modelo: tercera decisión por evidencia donde Laya no
corresponde.)

## Crear `triaje_trazas.py` (standalone en raíz, patrón minar_errores)

### Funciones puras (importables)

```python
def seleccionar(evaluaciones, umbral_seg=120.0):
    """({nombre: [(nodo, accion, seg), ...]}) → set de nombres a auditar:
    los flaggeados por el linter (linter_traza de evals) más los outliers
    de duración total (suma de seg > umbral_seg). Determinista."""
```

### main

- Recorre .runs/*.jsonl con `_leer_eventos` de evals (misma tolerancia a
  trazas corruptas), arma el dict de evaluaciones, llama seleccionar(),
  escribe `salidas/evals/triaje_trazas_<fecha>.md`:
  - resumen: total, vacías, seleccionadas, % (y la frase "ahorro de la
    auditoría nocturna: X%" destacada);
  - tabla de seleccionadas con MOTIVO (violaciones=n | duración=Ys | ambos)
    ordenada por severidad (ambos, violaciones, duración desc);
  - límite honesto en el docstring y el informe: el triaje ve lo
    ESTRUCTURAL (invariantes, duración); lo semántico (decisiones malas
    sin violación) requiere lectura LLM — la auditoría completa sigue
    disponible para cuando haga falta profundidad.
- argparse: --carpeta (.runs), --umbral (120.0), --salida (salidas/evals).

### Tests (append en tests/test_minar_errores.py o nuevo test_triaje.py)

- seleccionar() con sintéticos: traza limpia corta → fuera; traza con
  violación → dentro (motivo violaciones); traza larga limpia → dentro
  (motivo duración); traza con ambas → dentro (motivo ambos).
- La leyenda de motivo se ordena por severidad (probá con 3 trazas).

## Fuera de alcance

No tocar heartbeat.py ni su config jsonl (la integración como tarea
nocturna queda documentada, no cableada). No llamar a LLM.
