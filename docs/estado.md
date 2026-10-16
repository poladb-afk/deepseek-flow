# Estado de los hallazgos — deepseek-flow

**Actualizado:** 2026-10-16 · **Contra:** el árbol de `main` (los hallazgos vienen de las
auditorías externas del 2026-10-15; el mapeo A↔H↔R está en
[informes/archivo/2026-10/contraste_auditoria_2026-10-15.md](informes/archivo/2026-10/contraste_auditoria_2026-10-15.md)).

**Reglas de esta tabla:** un hallazgo no puede quedar en ✅ sin un test que lo cubra; un ⏳
lleva el motivo o el PR que lo cierra. Si algo se cierra sin test, se dice explícitamente.

| Id | Alias | Tema | Estado | Evidencia | Test que lo cubre |
|---|---|---|---|---|---|
| A01 | H01 | Bypass del HITL graduado (auto con efectos) | ✅ 2026-10-15 | `utils/policy.py` `_SEPARADORES` + `_FLAGS_PELIGROSOS` | `test_policy_bypass.py` |
| A02 | H04 | Un stream cancelado conservaba tool calls | ✅ 2026-10-15 | `utils/call_llm.py`, `nodes.py` | `test_consolidacion.py` |
| A03 | H05 | El presupuesto retiraba esquemas pero no frenaba nativas | ✅ 2026-10-15 | `nodes.py` (compuerta en el despacho) | `test_consolidacion.py` |
| A04 | H11 | La ruta `aplicada` se registra antes del veto del voto | ⏳ abierto | `nodes.py`: `registrar_decision` antes de `voto_confirmacion_router` | — |
| A05 | — | El voto recibe el dict y lo re-envuelve como pregunta | ⏳ abierto | `nodes.py`: `voto_confirmacion_router(prep_res)` | — |
| A06 | H07 | Sin Laya, el prefiltro recortaba y decía «Laya» | ✅ 2026-10-15 | `utils/contexto.py` (sin juicio, no se recorta) | `test_consolidacion.py` |
| A07 | H07 | El prefiltro puntúa rutas, no el contenido de las notas | ⏳ abierto | `utils/contexto.py` `{"bloque": str(unidad)}` | — |
| A08 | H06 | La memoria seguía symlinks al leer | ✅ 2026-10-15 | `modules/memoria.py` (sin enlaces) | `test_consolidacion.py` |
| A09 | H02 | `evals(salida=…)` escribía fuera de las raíces | ✅ 2026-10-15 | `modules/evals.py` `_arg` + no-clobber | `test_consolidacion.py` |
| A10 | H10 | El bench del router no medía la política real | ✅ 2026-10-16 | `evals.correr_bench` usa `decide`/`ruta_aplicada` | `test_pendientes.py` |
| A11 | H10 | `comparar_baseline` reventaba con bench degradado | ✅ 2026-10-15 | `evals.py` devuelve SIN BENCH | `test_consolidacion.py` |
| A12 | — | Un fallo de inferencia Laya abortaba el supervisor | ✅ obsoleto | Supervisor v2 ya no usa Laya (`sonda_supervisor.py`) | — |
| A13 | H15 | NaN en el umbral aprobaba «directo» | ✅ 2026-10-15 | `utils/laya_routing.py` valida rango | `test_consolidacion.py` |
| A14 | H08 | El LIMIT de SQL no era un tope real | ✅ 2026-10-15 | `modules/db.py` (entero positivo, sin comentarios) | `test_consolidacion.py` |
| A15 | R08 | `memory_search` exigía `query` y el esquema no | ✅ 2026-10-15 | `modules/memoria.py` `query=""` | `test_consolidacion.py` |
| A16 | H11 | La traza marcaba `exit 1` y RECHAZADO como ok | ✅ 2026-10-15 | `nodes.py` `ok=` según resultado | `test_consolidacion.py` |
| A17 | H12 | La compacción borraba la tarea activa sin respaldarla | ✅ 2026-10-16 | `utils/compaccion.zona_fria` + respaldo en `memoria/` | `test_pendientes.py` |
| A18 | H09 | Effective N no toleraba JSON de forma inválida | ✅ 2026-10-16 | `effective_n.py` usa `leer_registro` | `test_pendientes.py` |
| A19 | H09 | Reusar el flow de Effective N congelaba los params | ✅ 2026-10-16 | `effective_n.py` `set_params` por corrida | `test_pendientes.py` |
| A20 | H03 | Un hook PRE que lanza dejaba pasar la tool | ✅ 2026-10-15 | `utils/fs_tools.py` fail-closed | `test_consolidacion.py` |
| A21 | — | Cancelar el HITL web dejaba el pedido pendiente | ✅ 2026-10-14 | `utils/hitl_web.py` `finally` (exp/49b) | `test_pendientes.py` |
| A22 | H11 | Las duraciones anidadas se sumaban como pared | ✅ 2026-10-16 | `evals.costo_traza` (pared / inclusivo / anidados) | `test_pendientes.py` |
| A23 | H15 | El lote de Laya no tenía tope | ✅ 2026-10-16 | `utils/laya.py` `LAYA_BATCH_SIZE` | `test_pendientes.py` |
| A24 | H14 | El tope de checkpoints se aplicaba tras cargar | ✅ 2026-10-16 | `utils/laya.py` desaloja antes | `test_pendientes.py` |
| A25 | H19 | El log de preguntas guarda texto en claro | ✅ documentado 2026-10-15 | README «Privacidad y datos locales» (default sigue 1: alimenta la calibración) | `test_docs_sin_deriva.py` |
| A26 | H06 | El resumen de sesión seguía un symlink colgante | ✅ 2026-10-15 | `modules/memoria.py` `guardar_nota` | `test_consolidacion.py` |
| A27 | H03 | El dispatcher no valida la envoltura de la tool call | ⏳ abierto | `utils/fs_tools.py` `tool_call["function"]` (sin camino de producción: `historiar` siempre escribe las claves) | — |
| A28 | H16 | El bench del juez excluía de `cita_ok` el caso que lanzaba | ✅ 2026-10-16 | `bench_juez.py` cuenta cita incumplida | `test_pendientes.py` |
| E1 | — | Un módulo roto tumbaba el chat | ✅ 2026-10-15 | `modules/__init__.py` saltea y avisa colisiones | `test_consolidacion.py` |
| E2 | — | `validar_historial` aceptaba un `tool` huérfano | ✅ 2026-10-15 | `utils/compaccion.py` lo detecta | `test_consolidacion.py` |
| E4 | — | `rm -rf / --no-preserve-root` no se vetaba | ✅ 2026-10-15 | `modules/coding.py` denylist | `test_policy_bypass.py` |
| X1 | — | Un test daba por bueno el recorte del prefiltro | ✅ 2026-10-15 | `tests/test_smoke.py` contrato corregido | `test_consolidacion.py` |
| X2 | — | `rag_search` heredaba el recorte sin juicio | ✅ 2026-10-15 | misma `elegir_por_laya` | `test_consolidacion.py` |
| X3 | — | La limpieza del banco puede salir del repo | ⏳ abierto | `banco/banco.py` `RAIZ / path` con ruta absoluta o `..` | — |
| X4 | — | `memory_save` del mismo título el mismo día pisa la nota | ⏳ abierto | `modules/memoria.py` (nombre por fecha+slug) | — |
| X5 | H19 | El README describía un harness que ya no existe | ✅ 2026-10-15 | README (29 tools, supervisor v2, `ver_pdf`) | `test_docs_sin_deriva.py` |
| X6 | H20 | No hay CI que corra el gate | ⏳ PR 7 del plan | `calidad.sh` es manual | — |
| X9 | H19 | Rutas absolutas del autor y `.env` de otro proyecto | ✅ 2026-10-16 | `{RAIZ}`/`{HOME}` en 62 escenarios/specs · `LEER_BMO_ENV=0` · `heartbeat.example.jsonl` | `test_pendientes.py` |
| X7 | — | `requirements.txt` fija `ruff==0.17.1` y el entorno tiene 0.15.15 | ⏳ entorno | verificado: la 0.17.1 da «All checks passed» | — |
| X8 | H02 | `escribir_salida` pisa archivos dentro de las raíces sin HITL | ⏳ decisión | los flujos de la CLI reescriben a propósito; el chat ya no pisa (A09) | `test_pendientes.py` (lado chat) |
| — | H16 | El juez verifica 5 citas, no toda la verdad | límite deliberado | `juez.py` `MAX_CITAS` | — |
| — | H20 | La suite no es un gate integral por contrato | ⏳ PR 7 | 509 tests + gate manual | — |

## Abiertos, con su dueño

| Id | Qué falta | Dueño |
|---|---|---|
| A04 | Registrar la ruta FINAL después del voto (y guardar la propuesta aparte) | sin asignar |
| A05 | Pasar `prep_res["pregunta"]` al voto en vez del dict | sin asignar |
| A07 | Mandar contenido acotado de la nota al clasificador, no la ruta | sin asignar |
| A27 | Validar envoltura (id/function/name) antes de los hooks | sin asignar |
| X3 | Contener el `scratch` del banco (`Path(path).resolve()` dentro de `RAIZ`) | sin asignar |
| X4 | No pisar la nota del día (sufijo incremental como el resumen de sesión) | sin asignar |
| X6 | CI (`.github/workflows/calidad.yml`) | PR 7 del plan |
| X7 | `python3 -m pip install --user 'ruff==0.17.1'` (o bajar el pin) | operador |
| X8 | Decidir si el chat debe no-clobber también en los defaults | operador |
