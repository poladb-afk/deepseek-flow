# Mapa del repo para agentes

Índice de navegación del repo: qué hay, en qué orden se lee y dónde vive cada
guardrail. No reemplaza a `AGENTS.md`, que es el contrato; si algo de acá lo
contradice, gana `AGENTS.md`. Este archivo tampoco repite el contrato: apunta.

## Estructura

| Zona | Qué es | Dónde |
|---|---|---|
| Producto | El harness: CLI y grafo del chat | `main.py` (subcomandos en la sección "CLI completo" de `README.md`), `nodes.py`, `flow.py`; el loop es `utils/kernel.py` |
| Transversal | Lo que todas las piezas comparten | `utils/` (policy, `call_llm`, `kernel`, `fs_tools`, `tracing`). Solo lo que usa el producto: lo compartido del laboratorio vive en `instrumentos.py` (X165) |
| Capacidades | Una capacidad = un archivo con `TOOLS`, `IMPL` y `HOOKS` | `modules/` (agregar es dejarlo, quitar es borrarlo: P3) |
| Skills | Texto que se activa por regex | `skills/*.yaml` |
| Medición | Benches, sondas y specs pre-registradas; el producto no lo conoce (P3) | `banco/` (`specs/`, `probes/`, `escenarios/`), `bench_juez.py`, `evals.py`, `tablero.py`, `replay.py`, `instrumentos.py` |
| Contrato | Lo que un agente lee antes de tocar | `AGENTS.md` y `docs/` |
| Guardrails | Lo que hace cumplir el contrato | `calidad.sh`, `ratchet.py`, `tests/`, `.github/workflows/calidad.yml` |
| Artefactos | Salidas de corrida: no se trackean | `salidas/`, `.modelos/`, `.runs/`, `memoria/`, `trazas.db` (`tests/test_higiene_repo.py`) |

`docs/` en una línea cada uno: `docs/handoff.md` (estado y cola de la sesión),
`docs/principios.md` (la constitución), `docs/estado.md` (el tablero vivo de
hallazgos), `docs/design.md` (lo que es verdad hoy), `docs/elegancia.md` (la
forma que se persigue y los ratchets), `docs/bitacora.md` (cómo se llegó; los
meses cerrados en `docs/bitacora/`) y `docs/roadmap.md` (qué falta).
`docs/agents/` suma este mapa, el issue tracker, las etiquetas de triage y el
layout de dominio; `docs/informes/` es evidencia (informes e histórico).

## Orden de lectura

El de los docs es el de la sección "Antes de tocar nada" de `AGENTS.md` y no se copia acá para no derivar:
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
| Medir un cambio de conducta | Una spec en `banco/specs/` primero —pre-registrar antes de medir, el Método de `AGENTS.md`—, después el bench |
| Saber qué gate te va a frenar | La sección de abajo |

## Dónde viven los guardrails

- **`calidad.sh`**: el gate, cuatro palancas —ruff (higiene), C901 en las
  fronteras de seguridad, ratchet (métricas contra baseline) y pytest—. Verde
  con exit 0, y no se corre un subconjunto (R1).
- **`ratchet.py` + `ratchets/baseline.json`**: cada métrica tiene dirección;
  empeorar exige la clave del operador (`ratchets/clave_operador.sha256`,
  R6 y el Método de `AGENTS.md`). Mejorar lo baja solo.
- **`tests/`**: `tests/test_inventario.py` (R2, el total no baja),
  `tests/test_deriva_reglas.py` y `tests/test_docs_sin_deriva.py` (R3, los
  docs no mienten), `tests/test_contratos.py` (R8),
  `tests/test_estilo_humano.py` (R9/R10), `tests/test_policy.py` y
  `tests/test_policy_bypass.py` (R7), `tests/test_handoff.py` (el handoff,
  los principios y este mapa citan cosas que existen) y
  `tests/test_higiene_repo.py` (artefactos trackeados y tope de tamaño).
- **`.github/workflows/calidad.yml`**: el mismo gate en CI.
- **Seguridad**: la política vive en `utils/policy.py` con sus datos en
  `utils/politica_comandos.json`; falla cerrada y HITL graduado (S0). Los
  tests de S0 están repartidos por frontera; la tabla de abajo es el índice.
- **Bypasses prohibidos**: la lista por nombre está en `AGENTS.md`, sección
  "Bypasses prohibidos". No hay atajo: el gate es la única salida.

## S0 por frontera: dónde está cada candado

Un índice, no una copia: cada frontera de S0 con el test que la cuida (los
tests viven junto a su pieza; moverlos a un archivo único rompería ese
orden y la foto del inventario sin ganar nada). `tests/test_handoff.py`
verifica que cada test citado acá exista.

| Frontera | Qué se cuida | Tests |
|---|---|---|
| Política de comandos | Lista blanca para `auto`, negra para lo irreversible, composición y comillas | `test_policy_bypass_cerrados`, `test_pytest_auto_es_lista_blanca`, `test_las_comillas_no_esconden_un_flag`, `test_lo_que_descarta_trabajo_pide_doble_confirmacion` |
| La política no valida | El chat no arranca con datos rotos o ausentes | `test_falla_cerrada_si_los_datos_no_validan`, `test_falla_cerrada_si_el_archivo_falta_o_no_es_json` |
| Ganchos PRE | Un gancho que lanza bloquea, no deja pasar | `test_hook_pre_que_lanza_falla_cerrado`, `test_hook_pre_denylist_veta_antes_de_ejecutar` |
| Contención de rutas | Por componente, sin symlinks; ningún flujo escribe fuera | `test_contencion_de_rutas`, `test_una_raiz_no_cubre_a_su_hermana_con_el_mismo_prefijo`, `test_auto_no_sigue_symlinks_fuera_de_raices`, `test_ningun_flujo_escribe_fuera_de_las_raices`, `test_heartbeat_no_crea_nada_fuera_de_las_raices` |
| HITL web | Origen loopback, un POST solo resuelve su pedido, cuerpo validado | `test_hitl_web_rechaza_post_cross_origin`, `test_hitl_web_post_tardio_no_contamina_el_siguiente`, `test_pagina_de_pedidos_con_host_ajeno_no_muestra_tokens`, `test_content_length_malo_se_rechaza_sin_decidir` |
| Webhook y chat web | Token en tiempo constante, origen, sesión+token del SSE | `test_token_valido_en_tiempo_constante`, `test_webhook_con_origin_ajeno_no_registra_nada`, `test_chat_con_origin_ajeno_no_abre_sesion`, `test_stream_con_token_malo_no_entrega_la_salida` |
| Delegación por scope | El scope falla cerrado; lo doble nunca pasa solo | `test_el_scope_falla_cerrado`, `test_la_doble_confirmacion_real_no_se_aprueba_por_scope`, `test_plan_respuesta_lo_que_descarta_trabajo_nunca_pasa_solo` |
| Copias y supervisor | Una copia hereda los frenos; el supervisor no saltea la negra | `test_un_rechazo_del_humano_llega_igual_al_chat_al_supervisor_y_a_una_copia`, `test_un_hijo_no_puede_tener_tools_que_el_padre_no_tiene`, `test_supervisor_no_puede_saltear_el_denylist` |
| Re-run de `fable_judge` | La ruta del trabajo viaja como argumento | `test_el_rerun_de_fable_judge_no_interpreta_la_ruta_del_trabajo` |
