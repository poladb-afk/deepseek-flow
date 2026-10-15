# Spec de CIERRE exp/43 — mecánica, código literal (tercera sesión)

Dos sesiones dejaron el join INERTE por el mismo idiom: `id_decision =
registrar_decision(...)` no puede funcionar (esa función no devuelve nada —
bookkeeping que traga sus errores). Esta spec es MECÁNICA: el código va
literal; aplicalo donde dice, sin rediseñar. Lo que ya está en disco y NO se
toca: `registrar_resultado` (utils/laya_routing.py, correcta), y TODO el
bloque del voto (`config_voto`, `decide_voto`, `banco/probes/calibrar_voto.py`,
`tests/test_voto_router.py` — quedó verde y queda como está).

## A. `nodes.py` — tres ediciones EXACTAS

### A1. `LayaRouter.post` — el id se genera ANTES y viaja DENTRO del evento

Hoy dice (aprox.):

```python
        id_decision = registrar_decision(
            {
                "modo": config.modo,
                "propuesta": propuesta,
```

Reemplazar por (ojo: `registrar_decision` pasa a llamarse SIN capturar retorno):

```python
        from uuid import uuid4

        id_decision = uuid4().hex[:8]
        registrar_decision(
            {
                "modo": config.modo,
                "id": id_decision,
                "propuesta": propuesta,
```

Y donde hoy hace:

```python
        shared["_id_decision"] = id_decision
        shared["_rondas_inicio"] = shared.get("tool_rounds", 0)
```

reemplazar por:

```python
        if config.modo == "shadow" and p_directo is not None:
            shared["_router_pendiente"] = id_decision
```

(`tool_rounds` ya se resetea POR PREGUNTA en `GetQuestion.post`: no hace
falta ningún delta. En enforce la etiqueta no vale — directo retira las
tools y mediría la política, no al modelo.)

### A2. `AgentStep.post` — cierre SOLO al responder

Reemplazar el bloque exp/43 actual (el que llama
`registrar_resultado(shared.get("_id_decision"), ... - shared.get("_rondas_inicio", 0))`)
por:

```python
        pendiente = shared.pop("_router_pendiente", None)
        if pendiente is not None:
            from utils.laya_routing import registrar_resultado

            rondas = shared.get("tool_rounds", 0)
            registrar_resultado(pendiente, rondas)
            etiqueta = "herramientas" if rondas else "directo"
            print(colorear(f"  [router] etiqueta ambiental: {etiqueta} ({rondas} rondas)", "info"))
```

(`colorear` ya está importado arriba en nodes.py. Con `tool_calls` este
código NO corre — el pop solo vive en el camino del answer.)

### A3. `GetQuestion.post` — huerfanos

Junto al reset de presupuesto (`shared["tool_rounds"] = 0` etc.), agregar:

```python
        shared.pop("_router_pendiente", None)
```

## B. `banco/banco.py`

En `MARCADORES`, agregar la entrada:

```python
    "etiqueta_ambiental": r"\[router\] etiqueta ambiental",
```

## C. `banco/probes/etiquetar_ambiental.py` — NUEVO (código puro, sin LLM)

Docstring breve (qué es la etiqueta ambiental + el límite honesto: mide lo
que DeepSeek HIZO, no lo que necesitaba) y:

- Función PURA `unir(lineas)`: recibe las líneas ya parseadas del routing log
  y devuelve las filas de calibración. Reglas EXACTAS:
  - las líneas con `"evento": "resultado"` se indexan por `id`;
  - una línea de decisión con `p_directo` numérico y con su `resultado` emite:
    `{"ts": <ts de la decisión>, "pregunta": <solo si la línea la trae>,
    "laya": <propuesta>, "conf": p_directo si propuesta == "directo" sino
    1 - p_directo, "etiqueta": "herramientas" si uso_tools sino "directo",
    "correcto": propuesta == etiqueta, "fuente": "etiqueta ambiental exp/43"}`;
  - decisiones sin resultado (ciclo abortado) o sin `p_directo` (respuesta
    inválida): se saltan;
  - resultado huérfano (id sin decisión): se ignora.
- CLI: `--ruta` (default `salidas/routing.jsonl`), `--salida` (default
  `banco/calibracion_ambiental_FECHA.jsonl` con FECHA = date.today().isoformat()).
  Escribe incremental, imprime n y el balance etiqueta directo/herramientas.

## D. `tests/test_laya_routing.py` — APPEND (estilo monkeypatch existente)

Los 6 grupos de la sección 5 de `banco/specs/exp43_etiqueta_ambiental.md`:
registrar_resultado (línea/gate/ruta rota), pendiente==id del jsonl en
shadow, sin pendiente en enforce y con p_directo None, consumo en answer
(0 y 3 rondas; con tool_calls sobrevive), limpieza en GetQuestion, y la
tabla de verdad de `unir` (los 4 casos propuesta × uso_tools + salteos).

## E. `.env.example`

En el bloque de `LAYA_MODO`, dos líneas: shadow ahora JUNTA ETIQUETAS
(decisión + resultado unidas por id) para calibrar con tráfico real vía
`banco/probes/etiquetar_ambiental.py`; con `LAYA_LOG_PREGUNTA=1` la etiqueta
lleva la pregunta.

## Candado final

`python3 -m pytest tests/ -q` verde (hoy: 324 passed) y ruff limpio en lo
tocado. No modificar: voto (config_voto/decide_voto/calibrar_voto/
test_voto_router), decide/ruta_aplicada/registrar_decision/registrar_resultado.
