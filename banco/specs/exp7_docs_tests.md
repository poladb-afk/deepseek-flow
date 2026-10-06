# Spec exp/7 — parte 2: tests, documentación de la evidencia y fixes de exactitud

(Aplica el harness. Todo el contenido textual está DADO acá: no se inventa
nada, se aplica. Cuatro operaciones de archivo + lecturas necesarias.)

## 1. Crear `tests/test_sonda_laya.py`

Tests deterministas de las funciones puras de sonda_laya.py (sin cargar
ningún modelo). Estilo del proyecto: docstring corto en español, asserts
explícitos. Casos:

- `tabla_confiabilidad` con casos sintéticos: conf 0.55, 0.75, 0.90, 0.99
  (uno por bucket) → n=1 por bucket; el caso conf=0.70 exacto cae en
  [0.70, 0.85) (borde inferior inclusivo); un caso conf=0.40 queda FUERA
  de la tabla (la suma de n < total — lo cubre la curva, no la tabla).
- `curva_compuerta` con 4 casos (2 correctos de conf 0.9, 1 incorrecto de
  conf 0.8, 1 correcto de conf 0.5): en t=0.5 cobertura 1.0 y precisión
  0.75; en t=0.85 cobertura 0.5, precisión 1.0; `n_locales` exactos.
- `ece_local`: casos perfectamente calibrados (conf 0.75 con acierto
  0.75: tres correctos y uno incorrecto con conf .75 cada uno) → ECE 0.0;
  casos descarriados (conf 1.0, todos incorrectos) → ECE 1.0.
- `ESPECIFICACIONES` tiene exactamente las claves router/voto/supervisor/
  base con las preguntas necesita_herramientas / confirma_herramientas /
  elegir_proxima / necesita_herramientas (guarda-contrato, como los sha1).

## 2. Editar `sonda_laya.py` — solo el comentario de BORDES

La línea-comentario que dice que BORDES produce "5 buckets" está mal:
produce 4. Reemplazar por un comentario que diga: 4 buckets sobre
[0.5, 1.0]; los casos con conf < 0.5 quedan fuera de la tabla (la curva
de compuerta los cubre). NO tocar nada más del archivo.

## 3. Insertar sección en `docs/design.md`

Ubicación: inmediatamente DESPUÉS del final de la sección "### Laya — el
router del chat, afinado" (la que contiene la tabla del ciclo de fine-tune
y los 7 hallazgos medidos), ANTES del siguiente encabezado "### ".
Contenido EXACTO (texto textual, no parafrasear):

```
### Laya: estado de la evidencia (exp/7, 2026-10-06)

Auditoría con vara propia (`sonda_laya.py`, un checkpoint por proceso,
ECE local de 10 bins sobre answer_confidence; artefactos en
`salidas/evals/laya_evidencia_*.json` con git-sha):

| checkpoint | crudo | ECE | p50 CPU | carga fría | RSS pico |
|---|---|---|---|---|---|
| router_flow-1k | 27/30 | 0.066 | 190 ms | 9.7 s | 2.86 GiB |
| router_voto | 27/30 | 0.119 | 232 ms | 9.7 s | 2.86 GiB |
| supervisor_dispatch-1k | 14/24 | 0.209 | 500 ms | 10.1 s | 2.86 GiB |
| base multilingual | 16/30 | 0.300 | 203 ms | 9.9 s | 2.86 GiB |

- La sonda reproduce los artefactos previos: router 27/30 · ECE 0.066 =
  results.json del checkpoint y bench_router.json; supervisor 14/24 = r4;
  base 16/30 = results base. La cadena de evidencia cierra en CPU local.
- El "~0 s" heredado es en realidad ~0.2 s en CPU (supervisor ~0.5 s con
  18 opciones): órdenes de magnitud más barato que una llamada remota,
  pero ni gratis ni instantáneo.
- RSS por proceso 2.86 GiB (no los 615 MB del archivo): la ley "un
  checkpoint por proceso" ahora tiene número — dos procesos ya suman
  5.7 GiB.
- La compuerta 0.9 del supervisor es EXACTAMENTE la rodilla precisión=100%
  de la curva propia (8/24 locales, 8/8 correctos); debajo de 0.85 la
  precisión cae a 0.818. El umbral heredado de las leyes de bmo coincide
  con el punto óptimo medido.
- Router a 0.7: cobertura 0.90 / precisión 0.963; a 0.85: 0.833 / 1.000
  (mata el falso-directo "mundial", conf 0.831). La banda 0.7–0.85 es la
  sobrecargada (gap −0.32). La decisión de umbral es exp/8.
- Semántica verificada en el código del paquete: answer_confidence =
  max(p) post-temperatura (la calibrada); confidence = entropía
  normalizada (NO calibrada). Clamp de temperaturas [0.5, 5.0]: el router
  trae choice=0.5 exacto (el mínimo del clamp); el sesgo del clamp es
  conservador (probabilidades menos extremas → más uncertain → lado
  seguro). Decisión: NO re-ajustar temperaturas con 54 casos — sería
  fabricar evidencia.
```

## 4. Fixes de exactitud (2 ediciones puntuales)

- `utils/laya.py`, docstring del módulo: donde dice "22/24 con compuerta
  contra 12/24 del base multilingual (medido, design.md)", reemplazar por
  "27/30 crudo con ECE 0.066 (reproducible: python3 sonda_laya.py router;
  el 22/24 histórico era el test de 24 casos previo a la curaduría)".
- `.env.example`: buscar la mención de "22/24" y aplicar el mismo
  reemplazo textual.

## Fuera de alcance

No tocar settings, umbrales, .env (el real), ni ningún otro archivo. No
correr la sonda (las mediciones ya están hechas).
