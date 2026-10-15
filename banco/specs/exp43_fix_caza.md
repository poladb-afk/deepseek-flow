# Fix de la caza exp/43 — H1 y H2 (mecánico)

La auditoría dirigida (`exp43-caza`, patrón exp/19) encontró y verificó dos
bugs reales. Este spec los cierra. No tocar nada más.

## H1 — el gate del log no cubre al pendiente ni al print

`nodes.py`, `LayaRouter.post`: el pendiente se setea solo con
`config.modo == "shadow" and p_directo is not None` — SIN mirar
`LAYA_LOG_DECISIONES`. Con el gate apagado, `registrar_decision` no escribe,
`registrar_resultado` tampoco, pero el `print` de `AgentStep.post` SÍ corre:
el banco contaría `etiqueta_ambiental×1` sin ninguna línea en el log (el
patrón del Fix 10: un contador que mide el print, no el registro).

Fix EXACTO — la condición pasa a incluir el gate:

```python
        if (
            config.modo == "shadow"
            and p_directo is not None
            and _setting("LAYA_LOG_DECISIONES", "1") == "1"
        ):
            shared["_router_pendiente"] = id_decision
```

(`_setting` ya está importado arriba en nodes.py. Con esto: sin línea de
decisión no hay pendiente, no hay resultado, no hay print — el marcador
cuenta líneas escritas o nada.)

## H2 — el marcador del banco matchea prosa ecoada

`banco/banco.py`, `MARCADORES`: `\[router\] etiqueta ambiental` matchea el
literal del CÓDIGO FUENTE (el f-string de nodes.py) cuando un agente lo lee
y lo cita — la sesión de caza es el peor caso. Fix: anclar a la forma real
CON DÍGITOS (el template del código tiene `{etiqueta}`/`{rondas}` y no
matchea):

```python
    "etiqueta_ambiental": r"\[router\] etiqueta ambiental: (directo|herramientas) \(\d+ rondas\)",
```

Y el candado (lección Fix 10, patrón de los vetos): fixture NEGATIVO en
`tests/test_banco.py` — la línea template del código fuente
(`[router] etiqueta ambiental: {etiqueta} ({rondas} rondas)`) NO matchea el
marcador; la línea real (`  [router] etiqueta ambiental: directo (0 rondas)`)
sigue matcheando. Seguir el patrón de negativos que ya usa el test de
marcadores para los vetos.

## Tests (`tests/test_laya_routing.py`)

- Gate apagado: shadow + probabilidades + `LAYA_LOG_DECISIONES=0` → el post
  NO deja pendiente en shared y no escribe línea (estilo monkeypatch de
  `test_shadow_con_probabilidades_deja_el_pendiente_igual_al_id`).

## Candado final

`python3 -m pytest tests/ -q` verde (hoy 333) y ruff limpio en lo tocado.
