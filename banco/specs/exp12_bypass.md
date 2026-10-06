# Spec: cerrar el bypass DSML del presupuesto de tools (exp/12)

(Hallazgo medido en exp/4: al retirarse las tools por el tope L8, el modelo
emitió el write_file como TEXTO DSML y la recuperación lo ejecutó igual —
la ley "todo bucle tiene presupuesto" no es tope duro por ese camino.)

## Cambio en `nodes.py` — `AgentStep.exec`

El bloque de recuperación DSML actual dice (aproximadamente):

```python
        if not getattr(exec_res, "tool_calls", None) y RE_DSML.search(exec_res.content or ""):
            parseados = dsml_a_tool_calls(exec_res.content)
            if parseados:
                ...
```

Reemplazar la lógica por esta (respetando el código real que encuentres):

1. Si `parseados` y `tools is None` (las tools fueron RETIRADAS por el
   tope): la recuperación NO corre — la ley manda. En su lugar:
   - cortar el contenido en el inicio del markup DSML: lo que hay antes
     se conserva (rstrip);
   - si no queda nada utilizable, el contenido pasa a ser EXACTAMENTE:
     `"(sin texto: emitiste tool-calls con el presupuesto agotado — decí
     'seguí' para reiniciarlo)"` — mensaje honesto y accionable;
   - imprimir en terminal (colorear, nivel "aviso"):
     `  [DSML] tool calls como texto: IGNORADOS (presupuesto agotado; 'seguí' lo reinicia)`
2. Si `parseados` y `tools` no es None: la recuperación de siempre,
   intacta.

Extraer la decisión como función PURA para testearla sin LLM:

```python
def dsml_con_presupuesto_agotado(content, parseados, tools):
    """(nuevo_content, avisar): la recuperación DSML no re-armó tools que
    el tope retiró (ley L8 — medido en exp/4 que sí las ejecutaba)."""
```

Devuelve el contenido (cortado o el mensaje honesto) y True/False según
corresponda avisar en terminal. `exec` la usa para no duplicar lógica.

## Cambio en `banco/banco.py`

Agregar al diccionario MARCADADORES: `"dsml_ignorado": r"\[DSML\] tool calls como texto: IGNORADOS"`.

## Tests (`tests/test_smoke.py`, append)

- `dsml_con_presupuesto_agotado` con un content con prefijo útil + markup:
  tools=None → contenido cortado antes del markup + avisar True; con
  tools ≠ None → contenido intacto + avisar False.
- content que es SOLO markup, tools=None → contenido = el mensaje honesto
  (contiene "seguí").
- MARCADORES del banco contiene la clave nueva (import banco.banco).

## Fuera de alcance

No tocar `dsml_a_tool_calls`, `sanitizar`, ni la recuperación con tools
presentes. No cambiar el tope.
