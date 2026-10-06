# Spec exp/8 — parte 3: correcciones tras el gate rojo + nota de cascada

## Contexto (medido)

`_setting` lee en cascada `PROJECT_ENV` (nuestro .env) y después `BMO_ENV`
(bmo/.env). bmo/.env:12 tiene `LAYA_UNSURE_HIGH=0.7` (la ley heredada), que
ENMASCARA el default nuevo 0.85 del código: el test nuevo falló porque en
este entorno veredicto(0.84) da "met" (0.7 de bmo), y el guarda-contratos
de la sonda no conocía la entrada voto_en_router.

## 1. `tests/test_smoke.py` — REESCRIBIR test_split_umbrales_router_y_voto

Reemplazar el test completo por esta versión (monkeypatch controla el
entorno — el contrato real es que la PROPIA setting manda, y que el voto
no hereda la del router):

```python
def test_split_umbrales_router_y_voto(monkeypatch):
    """exp/8: la compuerta del router (LAYA_UNSURE_HIGH) y la del voto
    (LAYA_UNSURE_HIGH_VOTO) son settings SEPARADAS. El test fija el entorno
    con monkeypatch porque _setting lee en cascada nuestro .env y el de bmo
    (BMO_ENV tiene LAYA_UNSURE_HIGH=0.7 heredado, que enmascara el default
    0.85 del código — medido: sin fijar la env, veredicto(0.84) da met)."""
    from utils.laya import veredicto

    # la setting del router manda sobre cualquier cascada
    monkeypatch.setenv("LAYA_UNSURE_HIGH", "0.85")
    assert veredicto(0.84) == "uncertain"
    assert veredicto(0.85) == "met"
    monkeypatch.setenv("LAYA_UNSURE_HIGH", "0.7")
    assert veredicto(0.75) == "met"
    # el voto consulta con su propio alto explícito: nunca hereda al router
    assert veredicto(0.75, alto=0.7) == "met"
    assert veredicto(0.84, alto=0.7) == "met"
```

## 2. `tests/test_sonda_laya.py` — guarda-contratos con la entrada nueva

En el test que assertiona `set(ESPECIFICACIONES) == {...}`, agregar
"voto_en_router" al conjunto esperado, y agregar un assert de que esa
entrada tiene `"esperado_de": "necesita_herramientas"` (su verdad de
terreno vive en la clave de la pregunta ORIGINAL del test del router, no
en la del voto).

## 3. `docs/design.md` — una línea al final de la sección exp/8

Al final de la sección "### exp/8 — la compuerta del router, decidida por
datos..." (después del bullet del caveat n=30), agregar:

```
- Descubrimiento de activación: `_setting` lee en cascada nuestro .env y
  el de bmo (BMO_ENV) — bmo/.env trae LAYA_UNSURE_HIGH=0.7 heredado, que
  enmascara el default del código. La compuerta 0.85 se activa fijando
  LAYA_UNSURE_HIGH=0.85 en el .env del proyecto (documentado en
  .env.example).
```

## Reglas

Solo estas 3 operaciones. No tocar .env ni .env.example ni nodes.py.
