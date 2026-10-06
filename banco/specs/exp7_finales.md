# Spec exp/7 — parte 3: los TRES pendientes, con anclas exactas (cero exploración)

## 1. `docs/design.md` — insertar el bloque de DATOS textual

Insertá EXACTAMENTE este bloque INMEDIATAMENTE DESPUÉS del párrafo que
termina con "Un checkpoint por nombre: router, voto, supervisor y base
(referencia)." y ANTES de la línea "## Cómo crecer desde aquí" (debe quedar
una línea en blanco antes y después del bloque):

```
### Laya: estado de la evidencia (exp/7, 2026-10-06)

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
  conservador. Decisión: NO re-ajustar temperaturas con 54 casos.
```

## 2. `utils/laya.py` — reemplazo textual del docstring

OLD (fragmento de la línea 4-5): `22/24 con compuerta contra 12/24 del base multilingual (medido, design.md)`
NEW: `27/30 crudo con ECE 0.066 (reproducible: python3 sonda_laya.py router; el 22/24 histórico era el test de 24 casos previo a la curaduría)`

## 3. `.env.example` — reemplazo textual

OLD (línea 53): `# Checkpoint afinado para el router (task router_flow de bmo; 22/24 con`
(seguía en la línea siguiente — reemplazá SOLO la parte "22/24 con compuerta" de esa frase por "27/30 crudo ECE 0.066 con compuerta", conservando el resto de las dos líneas tal cual)

## Reglas

Tres operaciones, sin leer nada más que lo necesario para verificar los
anclajes. Nada de paráfrasis: texto textual donde está dado.
