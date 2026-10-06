# Spec: heartbeat con tarea tipo triaje (exp/17)

(Motivo: el triaje de trazas es determinista — cablearlo como tarea
nocturna NO debe pasar por el supervisor ni gastar una sola llamada LLM.
La ley del heartbeat "la noche es finita" se extiende: las tareas
deterministas corren directo.)

## 1. `heartbeat.py`

### `correr(tarea)` — branch por tipo

Al inicio de `correr`, si `tarea.get("tipo") == "triaje"`:

```python
    if tarea.get("tipo") == "triaje":
        import triaje_trazas

        destino_dir = (RAIZ / tarea["salida"]).parent
        informe = triaje_trazas.main(["--salida", str(destino_dir)])
        return {"ok": True, "informe": str(informe), "seg": round(time.time() - inicio, 1)}
```

(ajustá el cuerpo al código real; `main` de triaje_trazas debe devolver
`md_path` — ver punto 2. El resto de correr() queda igual: default =
supervisor.)

### Docstring del módulo

Agregar una línea al bloque de formato: las tareas aceptan `"tipo"`:
default = supervisor reactivo (LLM); `"tipo": "triaje"` = determinista,
cero llamadas LLM (el triaje de trazas escribe `triaje_trazas_<fecha>.md`
al lado de la salida declarada).

## 2. `triaje_trazas.py` — `main` devuelve la ruta

Al final de main: `return md_path` (antes solo imprimía). Sin tocar nada más.

## 3. `heartbeat.jsonl` — la tarea nueva (append)

```json
{"tipo": "triaje", "tarea": "Triaje de trazas: qué vale la pena auditar hoy", "salida": "salidas/heartbeat/triaje.md", "cada_horas": 24}
```

## 4. Test (append en tests/test_minar_errores.py)

`correr` con tarea tipo triaje (tmp_path no sirve: raíces permitidas —
usá salida="salidas/banco"): monkeypatch NO necesario (el triaje es
código puro sobre .runs real). Asserts: resultado["ok"] is True, el
informe existe (Path(resultado["informe"]).is_file()) y contiene
"Límite honesto". Y el default: correr() SIN tipo llama a supervisar —
monkeypatch de supervisor.supervisar devolviendo un path fake para
verificar que la rama default NO cambió (con tarea sin "tipo").

## Fuera de alcance

No tocar vencidas(), el estado, ni las tareas existentes del jsonl. No
correr el heartbeat real (--ahora corre las tareas LLM; la verificación
en vivo es del conductor).
