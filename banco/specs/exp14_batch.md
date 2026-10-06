# Spec: predict_batch en el pre-filtro (exp/14)

(Motivo medido: el A/B de exp/13 midió ~7 s por consulta de ranking —
`_puntuar` llama a Laya UNA vez por bloque, secuencialmente: 18 bloques ×
~360 ms. El paquete trae `predict_batch` (un forward compartido) que no
usamos, y el default MEMORIA_PREFILTRO=1 ya está activo en producción:
cada memory_search con >8 matches paga ese costo secuencial.)

## 1. `utils/laya.py` — `preguntar_lote` (la versión en lote de preguntar)

```python
def preguntar_lote(estados, preguntas, setting="LAYA_MODEL"):
    """La versión en lote de preguntar(): los MISMOS contratos evaluados
    sobre N estados en forward(s) compartido(s) (Agent.predict_batch).
    Devuelve una lista alineada con estados: [{id_pregunta: (respuesta,
    confianza)}]. Misma ley de degradación: si algo falla, lanza — el
    llamador (contexto._puntuar) cae al default seguro."""
    with _lock:  # reentrante, igual que preguntar: agente() lockea de nuevo
        resultados = agente(setting).predict_batch(list(estados), preguntas, lang="es")
    salida = []
    for r in resultados:
        fila = {}
        for qid, resp in r["answers"].items():
            fila[qid] = (resp.get("choice", resp.get("answer")), _confianza(resp))
        salida.append(fila)
    return salida
```

(NOTA: `_confianza` es el helper interno existente — renombralo a uso
directo; preguntar() y preguntar_lote comparten la extracción.)

## 2. `utils/contexto.py` — `_puntuar` en UNA llamada

Reemplazar el bucle for por: armar la lista `estados` completa (mismo
truncamiento: consulta[:1000], bloque[:2000], MISMO orden), UNA llamada a
`utils.laya.preguntar_lote(estados, contrato, setting_modelo)`, y mapear
los puntajes con la misma fórmula (confianza si "si", 1-confianza si "no").
El try/except que devuelve None ante cualquier fallo queda EXACTO (la ley
de hierro no cambia: sin batch disponible o con error → default seguro).

## 3. Tests (append en tests/test_smoke.py)

- `preguntar_lote` con monkeypatch de `agente` devolviendo un fake con
  predict_batch que devuelve 2 resultados con answer_confidence distintas:
  verifica alineamiento por índice y la extracción (respuesta, confianza).
- `_puntuar` con monkeypatch de `utils.contexto`... (el import es dentro
  de la función: patchear `utils.laya.preguntar_lote`) con 4 unidades →
  puntajes correctos por la fórmula si/no, y con preguntar_lote lanzando →
  None (default seguro intacto).

## Fuera de alcance

No tocar preguntar(), veredicto(), los consumidores (memoria/rag), ni
cambiar umbrales/defaults.
