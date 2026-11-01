# Mapa del repo para agentes

Índice de navegación del repo: qué hay, en qué orden se lee y dónde vive cada
guardrail. No reemplaza a `AGENTS.md`, que es el contrato; si algo de acá lo
contradice, gana `AGENTS.md`. Este archivo tampoco repite el contrato: apunta.

## Estructura

| Zona | Qué es | Dónde |
|---|---|---|
| Producto | El harness: CLI y grafo del chat | `main.py` (subcomandos en `README.md:170-188`), `nodes.py`, `flow.py` |
| Transversal | Lo que todas las piezas comparten | `utils/` (policy, `call_llm`, `kernel`, `fs_tools`, `tracing`) |
| Capacidades | Una capacidad = un archivo con `TOOLS`, `IMPL` y `HOOKS` | `modules/` (agregar es dejarlo, quitar es borrarlo: D2) |
| Skills | Texto que se activa por regex | `skills/*.yaml` |
| Medición | Benches, sondas y specs pre-registradas; el producto no lo conoce (D14) | `banco/` (`specs/`, `probes/`, `escenarios/`), `bench_juez.py`, `evals.py`, `tablero.py`, `replay.py` |
| Contrato | Lo que un agente lee antes de tocar | `AGENTS.md` y `docs/` |
| Guardrails | Lo que hace cumplir el contrato | `calidad.sh`, `ratchet.py`, `tests/`, `.github/workflows/calidad.yml` |
| Artefactos | Salidas de corrida: no se trackean | `salidas/`, `.modelos/`, `.runs/`, `memoria/`, `trazas.db` (`tests/test_higiene_repo.py`) |

`docs/` en una línea cada uno: `handoff.md` (estado y cola de la sesión),
`principios.md` (la constitución), `estado.md` (el tablero vivo de hallazgos),
`design.md` (lo que es verdad hoy), `elegancia.md` (la forma que se persigue y
los ratchets), `bitacora.md` (cómo se llegó) y `roadmap.md` (qué falta).
`docs/agents/` suma este mapa, el issue tracker, las etiquetas de triage y el
layout de dominio; `docs/informes/` es evidencia (informes e histórico).

## Orden de lectura

El de los docs es el de `AGENTS.md:14-25` y no se copia acá para no derivar:
handoff y principios, después el tablero, después lo vigente y la bitácora.
Antes de leer código por un flujo, un módulo o una policy, buscá su sección en
`docs/design.md`.

Si ya sabés qué buscás:

| Necesitás | Andá a |
|---|---|
| Qué falta y qué se decidió | `docs/handoff.md` |
| Si algo ya se midió, falló o se revirtió | `docs/estado.md` (fila por hallazgo) y `docs/bitacora.md` |
| Tocar un nodo o un contrato de `shared` | La sección de `docs/design.md`, después el código |
| Agregar o quitar una capacidad | `docs/design.md` (módulos); un test nuevo se suma al inventario |
| Medir un cambio de conducta | Una spec en `banco/specs/` primero (M3), después el bench |
| Saber qué gate te va a frenar | La sección de abajo |

## Dónde viven los guardrails

- **`calidad.sh`**: el gate, cuatro palancas —ruff (higiene), C901 en las
  fronteras de seguridad, ratchet (métricas contra baseline) y pytest—. Verde
  con exit 0, y no se corre un subconjunto (R1).
- **`ratchet.py` + `ratchets/baseline.json`**: cada métrica tiene dirección;
  empeorar exige la clave del operador (`ratchets/clave_operador.sha256`,
  R6/M5). Mejorar lo baja solo.
- **`tests/`**: `test_inventario.py` (R2, el total no baja),
  `test_deriva_reglas.py` y `test_docs_sin_deriva.py` (R3, los docs no
  mienten), `test_contratos.py` (R8), `test_estilo_humano.py` (R9/R10),
  `test_policy.py` y `test_policy_bypass.py` (R7), `test_handoff.py` (la
  constitución cita cosas que existen) y `test_higiene_repo.py` (artefactos
  trackeados y tope de tamaño).
- **`.github/workflows/calidad.yml`**: el mismo gate en CI.
- **Seguridad**: la política vive en `utils/policy.py` con sus datos en
  `utils/politica_comandos.json`; falla cerrada y HITL graduado (D11).
- **Bypasses prohibidos**: la lista por nombre está en `AGENTS.md`, sección
  "Bypasses prohibidos". No hay atajo: el gate es la única salida.
