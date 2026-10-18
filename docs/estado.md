# Estado de los hallazgos — deepseek-flow

**Actualizado:** 2026-10-17 · **Contra:** el árbol de `main` (los hallazgos vienen de las
auditorías externas del 2026-10-15; el mapeo A↔H↔R está en
[informes/archivo/2026-10/contraste_auditoria_2026-10-15.md](informes/archivo/2026-10/contraste_auditoria_2026-10-15.md)).

**Reglas de esta tabla:** un hallazgo no puede quedar en ✅ sin un test que lo cubra; un ⏳
lleva el motivo o el PR que lo cierra. Si algo se cierra sin test, se dice explícitamente.

| Id | Alias | Tema | Estado | Evidencia | Test que lo cubre |
|---|---|---|---|---|---|
| A01 | H01 | Bypass del HITL graduado (auto con efectos) | ✅ 2026-10-15 | `utils/policy.py` `_SEPARADORES` + `_FLAGS_PELIGROSOS` | `test_policy_bypass.py` |
| A02 | H04 | Un stream cancelado conservaba tool calls | ✅ 2026-10-15 | `utils/call_llm.py`, `nodes.py` | `test_consolidacion.py` |
| A03 | H05 | El presupuesto retiraba esquemas pero no frenaba nativas | ✅ 2026-10-15 | `nodes.py` (compuerta en el despacho) | `test_consolidacion.py` |
| A04 | H11 | La ruta `aplicada` se registra antes del veto del voto | ✅ 2026-10-16 | `nodes.py` registra la ruta FINAL + campos `voto`/`veto` | `test_pendientes.py` |
| A05 | — | El voto recibe el dict y lo re-envuelve como pregunta | ✅ 2026-10-16 | `nodes.py` pasa `prep_res["pregunta"]` | `test_pendientes.py` |
| A06 | H07 | Sin Laya, el prefiltro recortaba y decía «Laya» | ✅ 2026-10-15 | `utils/contexto.py` (sin juicio, no se recorta) | `test_consolidacion.py` |
| A07 | H07 | El prefiltro puntúa rutas, no el contenido de las notas | ✅ 2026-10-16 | `contexto.elegir_por_laya(texto_de=…)` + `memoria._texto_de_nota` | `test_pendientes.py` |
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
| A27 | H03 | El dispatcher no valida la envoltura de la tool call | ✅ 2026-10-16 | `utils/fs_tools.py` valida y devuelve error de tool | `test_pendientes.py` |
| A28 | H16 | El bench del juez excluía de `cita_ok` el caso que lanzaba | ✅ 2026-10-16 | `bench_juez.py` cuenta cita incumplida | `test_pendientes.py` |
| E1 | — | Un módulo roto tumbaba el chat | ✅ 2026-10-15 | `modules/__init__.py` saltea y avisa colisiones | `test_consolidacion.py` |
| E2 | — | `validar_historial` aceptaba un `tool` huérfano | ✅ 2026-10-15 | `utils/compaccion.py` lo detecta | `test_consolidacion.py` |
| E4 | — | `rm -rf / --no-preserve-root` no se vetaba | ✅ 2026-10-15 | `modules/coding.py` denylist | `test_policy_bypass.py` |
| A29 | — | El modo `auto` seguía symlinks fuera de las raíces (`cat link`, `grep -R`, `find -L`, `cd sub && cat link`) | ✅ 2026-10-17 | `modules/coding._sale_de_raices` symlink/cd-aware + flags de recorrido en `utils/policy.py` | `test_auto_no_sigue_symlinks_fuera_de_raices`, `test_policy_traversal_por_recorrido_de_symlinks_degrada` |
| A30 | — | La escritura atómica escribía un archivo externo vía symlink `<destino>.tmp` | ✅ 2026-10-17 | `utils/fs_tools.escribir_atomico` con `tempfile.mkstemp` (aleatorio, `O_EXCL`) | `test_escribir_atomico_no_sigue_symlink_tmp` |
| A31 | — | Decisiones HITL no persistidas: la tasa real de rechazo no se puede medir | ✅ 2026-10-17 | `utils/aprobaciones.py` emite `tracing.evento_hitl` (tipo/nivel/decisión, sin resumen); el tablero las cuenta | `test_aprobaciones_emite_evento_hitl_sin_contenido`, `test_tablero_genera_reporte` |
| A32 | — | Las trazas no guardan la causa del error (solo nombre + ok/error + segundos) | ✅ 2026-10-17 | `utils/tracing.evento_tool(codigo=...)` + `nodes.codigo_error` (código corto sin contenido) | `test_codigo_error_discrimina_sin_contenido` |
| A33 | — | 41/255 trazas vacías (16%): ensucian denominadores de métricas | ✅ 2026-10-17 | apertura perezosa del trace en `utils/tracing.py` (solo al primer evento); las históricas quedan declaradas | `test_tracing_no_deja_traza_vacia` |
| A34 | — | No había tablero de retrabajo versionado | ✅ 2026-10-17 | `tablero.py` (8 métricas: errores, autocorrección, timeouts, no-progreso, HITL, causas, tendencia, revisión) | `test_tablero_genera_reporte` |
| A35 | — | En streaming, si `exec()` reemplazaba el contenido después del stream (fallback/aviso), el usuario quedaba sin verlo: sesión real terminó sin respuesta visible | ✅ 2026-10-17 | `nodes.AgentStep.exec` imprime `DeepSeek (aviso): …` cuando reemplazó contenido; validado en sesión real (S4) | `test_stream_fallback_vacio_se_imprime` |
| A36 | — | La compacción descartaba la tarea vigente: en loops largos el modelo perdía el pedido ("I need to know what the actual task is", ronda 11) | ✅ 2026-10-17 | `utils/compaccion` recibe `objetivo=` y lo deja en el marcador; `GetQuestion` guarda `shared["_objetivo"]` | `test_compaction_conserva_la_tarea_vigente` |
| A37 | — | El presupuesto de 8/16 rondas no alcanza para auditorías amplias: el modelo lee ~2 archivos por ronda y no llega a sintetizar | ✅ 2026-10-17 (documentado; no hay perfil automático) | README “Alcance y presupuesto”: medio (~20 archivos) entra en 8 rondas; amplio requiere \`MAX_TOOL_ROUNDS>=16\` o acotar; S11 (7/8) vs S10 (16/16) | [live_audit_round6.md](../salidas/auditoria_2026-10/live_audit_round6.md) |
| A38 | — | Al agotarse el presupuesto el modelo sigue emitiendo tool calls (DSML/nativas) en vez de responder; la nota de la anteúltima ronda no alcanza | ✅ 2026-10-17 | `AVISO_CIERRE` efímero en `AgentStep.prep` al retirar tools: S5 respondió en la ronda 8 (antes: silencio) | `test_agotado_fuerza_respuesta_sin_tools` |
| A39 | — | Fricción HITL evitable: `2>/dev/null` en un compuesto de lectura dispara `preguntar` | ⏳ decisión | sesiones S1/S2 | — |
| A40 | — | Los hallazgos del modelo no se verifican antes de afirmarse: sesiones reales dieron 0/3 y 3/11 confirmados; citas de línea imprecisas | ✅ 2026-10-17 (citas; la semántica sigue humana) | `utils/citas.py` verifica archivo:línea contra el disco y `AgentStep._verificar_citas` pide una corrección si no coinciden; en S8: 5/14 → **5/5 citas finales verificadas** | `test_post_verifica_citas_y_corrige`, `test_post_no_corrige_si_las_citas_estan_bien`, `test_verificar_citas_estados` |
| A45 | — | `pytest` está en la whitelist como “solo lee”, pero ejecuta `conftest.py`/plugins y escribe cachés: ejecución de código del repo sin HITL | ✅ 2026-10-17 (riesgo ACEPTADO y documentado; modo estricto `HITL_AUTO=0`) | `utils/policy.py` doc/label corregidos; `_LECTURA` honesto; rótulo histórico del terminal con comentario | `test_explicar_pytest_admite_que_ejecuta_codigo` |
| A46 | — | El verificador marcaba `no_existe` citas abreviadas (`policy.py:88`) | ✅ 2026-10-17 | `_por_nombre_suelto` resuelve el nombre único en el árbol fuente (excluye artefactos) | `test_cita_por_nombre_suelto_unico` |
| A47 | — | Docs desactualizados por nuestros cambios: `aprobaciones` decía “no toca disco” y `riesgo` “0/off” sin “no” | ✅ 2026-10-17 | docstrings corregidos en `utils/aprobaciones.py` y `utils/riesgo.py` | — |
| A48 | — | El verificador solo dispara con formato `archivo:línea`; S7 usó “líneas ~X” y no disparó | ✅ 2026-10-17 | prompt exige `ruta/archivo.py:línea`; S9: 25 citas en formato, **23/23 verificadas**, sin corrección | [live_audit_round4.md](../salidas/auditoria_2026-10/live_audit_round4.md) |
| A49 | — | `utils/riesgo.py` decía que `policy.py` “tiene la denylist que veta lo irreversible”: policy sube fricción, la denylist que veta está en `coding._PROHIBIDOS` | ✅ 2026-10-17 | docstring corregido | — |
| A50 | — | `utils/aprobaciones.py` duplicaba el literal "preguntar" en vez de importar `policy.PREGUNTAR` (contrato por string) | ✅ 2026-10-17 | importa la constante de `utils.policy` | — |
| A51 | — | `utils/citas.py` citaba `policy.py:88` como ejemplo de nombre suelto (línea equivocada) | ✅ 2026-10-17 | ejemplo genérico corregido | — |
| A41 | — | `corte_no_progreso` se registraba como tool ok: inflaba métricas de tools | ✅ 2026-10-17 | `utils/tracing.evento_politica` + uso en `nodes.AgentStep.prep` (accion="politica") | `test_evento_politica_no_se_confunde_con_tool` |
| A42 | — | El resumen de sesión contaba mensajes sintéticos (prefetch/compacción) como preguntas del usuario | ✅ 2026-10-17 | `main._preguntas_reales` excluye `PREFIJO_PREFETCH` y `PREFIJO_COMPACCION` | `test_preguntas_reales_ignora_prefetch_y_compaccion` |
| A43 | — | Doc `laya_routing` decía "en force" y el modo se llama `enforce` | ✅ 2026-10-17 | `utils/laya_routing.py:219` | — |
| A44 | — | `policy` descartaba `2>&1` como substring del comando, no como token (el doc dice token) | ✅ 2026-10-17 | `_sin_dup_stderr`: solo el token exacto; lo pegado a un argumento degrada por prudencia | `test_policy_2and1_se_descarta_como_token_no_substring` |
| A52 | — | `citas.extraer` truncaba rangos `N-M` al primer número y validaba como si el rango entero existiera | ✅ 2026-10-17 | `CITAS_RE` captura `line2` y `verificar_citas` valida ambos extremos | `test_verificar_citas_rango` |
| A53 | — | `policy.explicar` decía “la misma política que clasificar”; la explicación usa el primer token del string completo | ✅ 2026-10-17 | docstring precisa: el nivel sale de clasificar, la explicación describe el primer token (compuestos pueden nombrar un segmento inocente) | — |
| A54 | — | `compaccion.validar_historial` promete “assistant previo” y solo valida el inmediatamente anterior | ✅ 2026-10-17 | docstring precisado | — |
| A55 | — | Nombres de ejemplo en prosa (`archivo.py:10-20`) se tomaban como citas reales y disparaban corrección | ✅ 2026-10-17 | `_PLACEHOLDERS` excluye nombres de ejemplo | `test_citas_placeholder_no_cuentan` |
| A56 | — | `run_tool_call` coercionaba a `str()` (dict → repr Python) sin documentarlo | ✅ 2026-10-17 | contrato de salida documentado (`str()`; tools deben devolver texto) | `test_run_tool_call_coerciona_el_retorno_a_str` |
| A57 | — | `laya.preguntar_lote` / `_confianza`: docs imprecisos sobre degradación y fallback de confianza | ✅ 2026-10-17 | `preguntar_lote` propaga (degrada el llamador); `_confianza` aclara que el fallback es margen y no calibra | — |
| A58 | — | `citas.extraer` contaba un archivo nombrado sin `:línea` como `:0` → falsos `linea_fuera` y correcciones innecesarias | ✅ 2026-10-17 | solo cuenta `archivo:línea` o rango; mención suelta no es cita | `test_mencionar_archivo_sin_linea_no_es_cita` |
| A59 | — | `votacion.mayoria`: el doc decía “mitad entera por arriba”; el default es piso absoluto 2 | ✅ 2026-10-17 | doc corregido (piso absoluto, no proporcional) | `test_votacion_mayoria_piso_absoluto` |
| A60 | — | `citas` marcaba `ok` una cita resuelta por nombre suelto sin avisar que sustituye el archivo | ✅ 2026-10-17 | flag `resuelto_por_nombre` + detalle en el reporte (se mantiene `ok` a propósito) | — |
| A61 | — | `contexto.py` promete “mismo truncamiento y MISMO orden que la versión secuencial”; no hay versión secuencial en el módulo | ✅ 2026-10-17 | comentario corregido: truncado fijo y orden declarado; única implementación es la de lote | — |
| A62 | — | La verificación de citas no cubría `.jsonl`: el chat citó `.runs/*.jsonl:5` y quedaba sin chequear | ✅ 2026-10-18 | `CITAS_RE` cubre `jsonl|csv|log` (orden de alternancia corregido) | `test_verificar_citas_jsonl` |
| A63 | — | Bench del juez en regresión (70,6% vs 94,1%): el `Draft` leía solo las primeras 200 líneas y los archivos crecieron (`list_files`, `sanitizar`, `COMPACTION_CHARS` quedaban afuera) | ✅ 2026-10-18 | `juez._contexto_extra`: ventanas dirigidas después de la línea 200; full bench post-fix: **100% respuesta_ok** | `test_juez_draft_lee_simbolos_mas_alla_del_excerpt` |
| A64 | — | Caso `supervisor-umbral` del bench obsoleto: esperaba `LAYA_UNSURE_HIGH_SUPERVISOR` en `supervisor.py`, pero v2 movió el despacho a `sonda_supervisor.py` | ✅ 2026-10-18 | caso actualizado a `sonda_supervisor.py` + baseline regenerado con revisión (backup del anterior en artifacts) | `bench_juez` (caso ✅/✅) |
| A65 | — | `cita_ok` 87,5%: el modelo cita el inicio del bloque / líneas abreviadas en vez de la línea exacta que exige el grading | ⏳ parcial | prompt de línea EXACTA + anclaje determinista (`_anclar_citas`: literal/negrita/símbolo, ±30 líneas). Full bench: **100% respuesta / 87,5% cita**; los fallos **rotan** entre casos (a2a, vision): no es regresión, es flakiness del grading exacto | `test_juez_draft_pide_cita_exacta`, `test_juez_ancla_citas_a_literal_y_simbolo` |
| X1 | — | Un test daba por bueno el recorte del prefiltro | ✅ 2026-10-15 | contrato corregido en `tests/test_memoria.py::test_memoria_prefiltro_actua` | `test_consolidacion.py` |
| X2 | — | `rag_search` heredaba el recorte sin juicio | ✅ 2026-10-15 | misma `elegir_por_laya` | `test_consolidacion.py` |
| X3 | — | La limpieza del banco puede salir del repo | ✅ 2026-10-16 | `banco.objetivo_scratch`: solo dentro de `RAIZ` | `test_pendientes.py` |
| X4 | — | `memory_save` del mismo título el mismo día pisa la nota | ✅ 2026-10-16 | `modules/memoria.py` sufijo incremental (A26 intacto) | `test_pendientes.py` |
| X5 | H19 | El README describía un harness que ya no existe | ✅ 2026-10-15 | README (29 tools, supervisor v2, `ver_pdf`) | `test_docs_sin_deriva.py` |
| X6 | H20 | No hay CI que corra el gate | ✅ 2026-10-16 | `.github/workflows/calidad.yml` + badge en el README (verde al primer push) | — |
| X9 | H19 | Rutas absolutas del autor y `.env` de otro proyecto | ✅ 2026-10-16 | `{RAIZ}`/`{HOME}` en 62 escenarios/specs · `LEER_BMO_ENV=0` · `heartbeat.example.jsonl` | `test_pendientes.py` |
| X7 | — | `requirements.txt` fija `ruff==0.17.1` y el entorno tiene 0.15.15 | ⏳ entorno | verificado: la 0.17.1 da «All checks passed» | — |
| X8 | H02 | `escribir_salida` pisa archivos dentro de las raíces sin HITL | ⏳ decisión | los flujos de la CLI reescriben a propósito; el chat ya no pisa (A09) | `test_pendientes.py` (lado chat) |
| — | H16 | El juez verifica 5 citas, no toda la verdad | límite deliberado | `juez.py` `MAX_CITAS` | — |
| — | H20 | La suite no es un gate integral por contrato | ✅ 2026-10-16 | `./calidad.sh` en CI con 3 palancas (ruff · C901 de las fronteras · 518 tests) | `test_contratos.py` + `.github/workflows/calidad.yml` |

## Abiertos, con su dueño

Los seis hallazgos de código (A04, A05, A07, A27, X3, X4) y todo H20 (X6 + el
gate integral) se cerraron el 2026-10-16. Queda:

| Id | Qué falta | Dueño |
|---|---|---|
| X7 | `python3 -m pip install --user 'ruff==0.17.1'` (o bajar el pin) | operador |
| X8 | Decidir si el chat debe no-clobber también en los defaults | operador |
| — | H16: el juez verifica 5 citas, no toda la verdad (límite deliberado) | diseño |
