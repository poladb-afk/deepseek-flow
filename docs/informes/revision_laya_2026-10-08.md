# Revisión de la integración de Laya — 2026-10-08

Auditoría de **solo lectura** sobre `utils/laya.py` y sus cuatro puntos de uso,
las sondas de medición, `evals.py` y el paquete `laya` v0.3.20 instalado. El
objetivo no era celebrar la integración sino enumerar sus bordes: qué pasa
cuando el checkpoint no está, cuando el path es relativo, cuando la inferencia
se cuelga o cuando el juicio local no ocurrió pero el código lo aparenta.

**Resumen en una frase:** Laya está bien aislada como *acelerador* (todo
llamador tiene camino de degradación), pero tres bordes no están cubiertos —
el router sin try/except, el pre-filtro que etiqueta un juicio inexistente y
los paths relativos de dos checkpoints— y el resto son límites de operación
(RAM, locks, release incompleta) que conviene tener escritos.

## 1. Los cuatro puntos de uso

| # | Punto | Entrada | Salida | Umbral | Si Laya no está |
|---|---|---|---|---|---|
| 1 | Router del chat (`nodes.py:402-441`) | `{"pregunta": texto[:1000]}` | `directo` / `herramientas` | `LAYA_UNSURE_HIGH`=0.85 | `("herramientas", 0.0)` |
| 2 | Voto de confirmación (`nodes.py:363-399`) | `{"pregunta": texto[:1000]}` | `directo` / `herramientas` | `LAYA_UNSURE_HIGH_VOTO`=0.7 | mini-llamada DeepSeek |
| 3 | Choose del supervisor (`supervisor.py:169-231`) | `{"tarea", "hechos"}` (15 líneas) | 17 tools + `finish` | `LAYA_UNSURE_HIGH_SUPERVISOR`=0.9 | DeepSeek + mayoría 2-de-3 |
| 4 | Pre-filtro de contexto (`utils/contexto.py:65-108`) | `{"consulta", "bloque"}` × N | ranking | sin umbral | `unidades[:max_unidades]` |

El contrato del fine-tune se respeta byte a byte (los cuatro `PREGUNTA_*` están
congelados por sha1 en los tests y las sondas los importan en vez de
copiarlos), y `veredicto()` colapsa a `met` / resto en los tres call sites.

## 2. Evidencia medida (sonda propia, CPU local)

| checkpoint | n | crudo | ECE | p50 | carga fría | RSS |
|---|---|---|---|---|---|---|
| router_flow-1k | 30 | 27/30 | 0.0658 | 190 ms | 9.7 s | 2.86 GiB |
| router_voto | 30 | 27/30 | 0.1188 | 232 ms | 9.7 s | 2.86 GiB |
| supervisor_dispatch-1k | 24 | 14/24 | 0.2085 | 500 ms | 10.1 s | 2.86 GiB |
| router_prefiltro | 28 | 22/28 | 0.0906 | 362 ms | 11.6 s | 2.86 GiB |
| base multilingual | 30 | 16/30 | 0.3002 | 203 ms | 9.9 s | 2.86 GiB |

Puntos de operación elegidos por curva: router 0.85 (cobertura 0.833,
precisión 1.000), voto 0.70 (0.833 / 0.960), supervisor 0.90 (0.333 / 1.000 =
la rodilla exacta), pre-filtro 0.75-0.80 (precisión 1.000). Ahorro del router:
83% de las decisiones sin mini-llamada de confirmación. Lote del pre-filtro
(`predict_batch`): 3.2× warm, decisiones idénticas 14/14. A/B del pre-filtro:
poda 18→2 archivos (89%) de contexto, 0 llamadas API.

## 3. Riesgos, por severidad

### Cubrir antes de confiar en el camino Laya

1. **El router no está protegido.** `LayaRouter()` se instancia sin
   `max_retries` (`flow.py:16`) y su `exec` no envuelve `preguntar` en
   try (`nodes.py:415-421`): una excepción de inferencia (OOM, tokenizer,
   versión) **mata el chat**. Voto, pre-filtro y supervisor sí degradan.
2. **Recall silencioso en el pre-filtro.** `_puntuar` devuelve `None` sin
   lanzar (`utils/contexto.py:107`) y `elegir_por_laya` entrega las primeras
   N (`:76-77`), así que los consumidores no distinguen "no hubo juicio" de
   "el juicio eligió las primeras N": `modules/memoria.py:118-120` compara
   longitudes e imprime `[prefiltro Laya: 11 → 8 archivos]` **aunque Laya
   nunca estuvo**, y las notas fuera de esos 8 dejan de buscarse. El docstring
   de `contexto.py:7-11` promete "entran TODOS los chunks". El test del no-op
   simula un `raise`, no el `None` real: ese camino no está cubierto.
3. **Paths relativos en dos checkpoints.** `LAYA_MODEL_VOTO` y
   `LAYA_MODEL_PREFILTRO` (`.env:22,29`) se resuelven contra el CWD, no
   contra la raíz del repo: desde otra carpeta no existen → camino de red sin
   timeout (punto 4) y, si falla, error cacheado para todo el proceso.
4. **Cuelgue de red en la carga, sin timeout.** `HF_HUB_OFFLINE` se activa
   solo si `Path(clave).exists()` y con `setdefault` (`utils/laya.py:37-42`);
   con un repo id o un path inexistente, `import laya` + `laya.load` van a la
   red sin cota (el downloader de HF cuelga en esta máquina, medido).

### Límites de operación

5. **Sin timeout de inferencia** ni cancelación: un `system_one` colgado
   bloquea la conversación entera.
6. **RLock global único** (`utils/laya.py:22`): serializa la inferencia de
   todos los settings; el lote del pre-filtro ocupa el lock durante N estados.
7. **Caché de errores permanente por setting** (`_errores`): un fallo
   transitorio deja `disponible()` en False para toda la vida del proceso.
8. **Hasta 4 checkpoints en un mismo proceso** (router + voto + pre-filtro +
   supervisor in-process) ≈ 11 GiB teóricos, contra la ley medida de "un
   checkpoint por proceso" (2.86 GiB cada uno).
9. **La release cubre 2 de 5 checkpoints** (`descargar_modelos.sh`): un clon
   nuevo no tiene voto, pre-filtro ni base, y degrada en silencio (con el
   efecto del punto 2).
10. **Carga perezosa bloqueante y sin aviso**: la primera pregunta paga ~10-12 s
    bajo el lock, y el `[laya] ...` se imprime después de inferir; no hay
    warm-up.
11. **Pre-filtro sin cota de lote**: `max_unidades` acota la salida, no la
    entrada; el forward escala con N unidades.

### Contratos y medición

12. **La salida del router no se valida** (`nodes.py:441`): una etiqueta
    fuera de contrato no encuentra arista y el chat termina en silencio. El
    supervisor sí valida y cae a DeepSeek.
13. **El contrato congelado no valida el checkpoint en disco**: un checkpoint
    viejo/nuevo se nota por calidad, no por un chequeo.
14. **`LAYA_UNSURE_LOW` es un setting muerto**: `veredicto` distingue
    `not met` de `uncertain` (`utils/laya.py:101-104`) pero los tres
    consumidores solo comparan `== "met"`. Está documentado en
    `.env.example` como si importara.
15. **El ECE de los informes no es el del paquete**: `sonda_laya.ece` le pasa
    listas a `laya.ece_score` (aritmética numpy) → `TypeError` capturado →
    **siempre** cae al fallback local de 10 bins, y hay dos ECE locales con
    bordes distintos (`evals.py:70-88` vs `sonda_laya.py:162-183`).
16. **Extracción silenciosa de `None`** (`utils/laya.py:69-72`): un contrato
    que no sea `choice` devuelve `(None, conf)`; en el pre-filtro ese `None`
    se penaliza como `1.0 - conf`.
17. **Configuración por cascada no evidente**: `_setting` lee el `.env` del
    proyecto y después el de bmo; un valor heredado enmascara el default
    (exp/8). `.env.example` muestra dos valores contradictorios comentados
    para `LAYA_UNSURE_HIGH`.
18. **El action space del despacho está congelado en 18 opciones**
    (`supervisor.py:83-111`): las tools nuevas llegan por el catálogo de
    DeepSeek, nunca por Laya (decisión aceptada, pero conviene saberlo).

## 4. Cobertura de tests del camino Laya

`tests/test_sonda_laya.py` (métricas puras) y en `tests/test_smoke.py`: aristas
del chat, mayoría 2-de-3, Laya segura sin gasto, sha1 de los cuatro contratos,
bench que degrada sin Laya, linter con/sin router, los tres niveles del voto,
pre-filtro (no-op, orden, actúa), split de umbrales, lote y `_puntuar`.

**Lo que no está cubierto y es el hueco real:** el `None` del pre-filtro (punto
2) y la excepción de inferencia en el router (punto 1).
