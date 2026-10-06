# Spec: presupuesto visible + protocolo de continuación (exp/4)

(Motivo medido: el modelo NO ve su propio presupuesto — el `⚙ ronda n/8`
va a la terminal, nunca a la conversación, y el tope lo corta en mudo.
Tres sesiones de aplicación murieron así. Medición además: 87% de las
rondas tiene 1-2 llamadas — el problema es rondas para la clase
editar→probar→editar, no llamadas por ronda.)

## 1. `nodes.py` — la nota de presupuesto, visible para el modelo

Función PURA a nivel de módulo:

```python
def nota_presupuesto(ronda, maximo):
    """La nota que ve el MODELO al entrar a la anteúltima ronda: su única
    vista del presupuesto (el ⚙ de la terminal no llega a la conversación).
    None en toda otra ronda — una nota por pregunta alcanza."""
    if ronda == maximo - 1:
        return (
            f"⚙ ronda {ronda}/{maximo} — la próxima respuesta es SIN tools: "
            "cerrá el estado de la tarea (qué falta, qué hiciste) o pedí "
            "continuación; un mensaje nuevo del usuario reinicia el presupuesto."
        )
    return None
```

En `ExecuteTools.post`, DESPUÉS de incrementar `shared["tool_rounds"]` y
ANTES de `shared["messages"].extend(exec_res)`: si la nota aplica,
appendearla al contenido del ÚLTIMO resultado del turno:

```python
        nota = nota_presupuesto(ronda, MAX_TOOL_ROUNDS)
        if nota and exec_res:
            exec_res[-1]["content"] = f"{exec_res[-1]['content']}\n{nota}"
```

(`ronda` ya existe en post — es la variable que usa progreso_ronda.)
Importar MAX_TOOL_ROUNDS ya está hecho en nodes.py (viene de fs_tools).

## 2. `banco/banco.py` — `env:` por escenario

El esquema acepta clave opcional `env:` (dict str→str) a nivel escenario:
`correr()` la mergea en el env_extra del Chat (las variables del
escenario PISAN las del entorno, no al revés). Actualizar el docstring
del banco (una línea: "env: variables por escenario — p. ej.
MAX_TOOL_ROUNDS=40 para sesiones de aplicación").

## 3. Tests

- `nota_presupuesto`: (ronda=max-1 → nota con ambos números y la palabra
  "SIN tools"; ronda < max-1 → None; ronda == max → None; maximo=1 →
  ronda 0... decidí: con maximo=1, ronda 0 == max-1 → nota — cubrilo).
- Esquema del banco: escenario con `env:` carga y `cargar_escenario` lo
  expone; sin `env:` sigue válido (compatibilidad).
- (En tests/test_smoke.py la nota; en tests/test_banco.py el env.)

## 4. Escenarios de medición (crearlos, no correrlos — los corre el conductor)

- `banco/escenarios/exp4-bajo.yaml`: `env: {MAX_TOOL_ROUNDS: "4"}`,
  scratch [prueba_rondas], un turno que pida: "Leé uno por uno estos
  SEIS archivos y después creá prueba_rondas/resumen.md con una línea de
  resumen por archivo: sonda_laya.py, minar_errores.py, banco/banco.py,
  nodes.py, modules/coding.py, utils/policy.py" (hitl s, timeout 420) +
  turno salir.
- `banco/escenarios/exp4-amplio.yaml`: IDÉNTICO pero
  `env: {MAX_TOOL_ROUNDS: "40"}`.

## Fuera de alcance

No cambiar el default 8 (la medición dice mediana 2 rondas/pregunta).
No tocar GetQuestion (el reset ya existe). No tocar la terminal.
