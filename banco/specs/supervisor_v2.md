# Supervisor v2 — el despacho se simplifica (el bench aplicado)

El bench midió (2026-10-13, `salidas/evals/bench_supervisor_2026-10-13.md`):
el supervisor reactivo gasta **65 llamadas remotas / 358 s** donde un agente
plano con tool-calling nativo resuelve LO MISMO (6/6 ambos) en **14 / 26 s**
— mismas herramientas, mismo presupuesto. El valor del supervisor nunca
estuvo en el Choose (Laya + mayoría 2-de-3): está en las LEYES de código
(vetos, caché, presupuesto, fallo-como-feedback, anti-recursión). Esta spec
aplica ese veredicto: **un paso = UNA llamada que elige herramienta Y args
juntos**, con las leyes intactas. El menú congelado de 18 opciones y el
checkpoint LAYA_MODEL_SUPERVISOR se jubilan (los procesos del supervisor y
del heartbeat dejan de cargar 2.86 GiB).

## 1. `supervisor.py` — el nuevo bucle (reemplaza ElegirSiguiente/EjecutarPaso)

Mantener EXPORTS que consumen otros: `supervisar(tarea, salida)`,
`PREGUNTA_DESPACHO`/`elegir_con_deepseek` SE MUDAN (ver §3), `_TODAS`,
`REGISTRO`, `create_supervisor_flow` (bench y heartbeat los usan), y los
helpers de leyes que sobrevivan.

El flujo nuevo (Flow de la casa, con guard de calles muertas):

```
UnPaso ──tool──▶ Ejecutar ──default──▶ UnPaso
UnPaso ──answer/sintetizar──▶ Sintetizar
```

- **UnPaso** (max_retries=3, wait=5): `prep` arma `messages` + `tools` —
  tools retiradas al llegar a `MAX_PASOS=5` rondas (la ley del chat: el
  modelo debe cerrar). `exec` llama `call_llm_agent(messages, tools)` (LA
  llamada del paso: elige y argumenta junto). `post`: con `tool_calls` →
  "tool"; sin ellas → "sintetizar" (el contenido es el cierre parcial que
  Sintetizar puede reusar). El historial VIAJA COMPLETO entre pasos (ya no
  hay hechos recortados de 160 chars: el modelo ve los resultados reales —
  la ganancia del agente plano).
- **Ejecutar**: por cada tool_call → `fs_tools.run_tool_call` (el único
  camino con hooks, igual que hoy) PERO con las guardas de ley ANTES de
  despachar (§2); el resultado (o el texto de la guarda) vuelve como
  mensaje `role=tool` — el canal fallo-como-feedback de siempre; después
  arma el hecho de auditoría con `hecho_de` (se conserva) para la sección
  "Pasos" del informe.
- **Sintetizar**: igual que hoy (informe + sección "Pasos"), con el
  material de `resultados`/`hechos` de siempre.

El system prompt del sub-agente: corto y tarea-primero (estilo casa): la
tarea del usuario, "resolvé con las tools disponibles, tenés un presupuesto
de MAX_PASOS rondas", CWD, y el catálogo son los schemas (nada de menú en
prosa). El `shared` semilla: `{"tarea", "salida", "messages": [system,
user], "rondas": 0, "fallos": {}, "exitosas": [], "previas": {}, "hechos":
[], "resultados": []}`.

## 2. Las leyes, como guardas PURAS del ejecutor (testeables sin LLM)

Se conservan y se testean directo (adaptando los tests existentes de
vetadas/repetidas a la nueva forma):

- `guarda_vetada(herramienta, fallos)` → None si puede correr; si llegó a
  `MAX_FALLOS_POR_HERRAMIENTA=2`: el TEXTO de resultado
  `"ERROR: herramienta vetada en esta corrida (falló 2 veces) — elegí otra
  o cerrá"` (NO se ejecuta; el texto es el feedback).
- `guarda_repetida((herramienta, clave), previas, exitosas, sin_args)` →
  None si corre; si es llamada idéntica a una exitosa previa: el RESULTADO
  CACHEADO (reutilizado, marcado); si es sin-args ya exitosa o la misma
  firma dos veces: texto de veto como el de arriba.
- Contadores se actualizan DESPUÉS de ejecutar (éxito limpia fallos,
  registro en previas/exitosas) — la semántica de hoy.
- Anti-recursión (L1): `_TODAS` sigue excluyendo run_supervisor.

## 3. `sonda_supervisor.py` — el instrumento de evidencia sobrevive

`PREGUNTA_DESPACHO` y `elegir_con_deepseek` SE MUDAN a sonda_supervisor.py
(último consumidor: mide el checkpoint jubilado como evidencia histórica).
Importarlos de supervisor pasa a importarlos de sí misma; el resto de la
sonda intacto (corre contra checkpoint por args, como siempre).

## 4. Tests

- Adaptar los que referencian el flujo viejo (test_smoke: contrato sha1 del
  despacho se saca de la lista congelada — el contrato ahora vive en la
  sonda y su congelamiento se testea ALLÍ; vetadas/repetidas → contra las
  guardas puras; test_grafos: la forma nueva del flujo con sus aristas
  `tool`/`answer`/`sintetizar`).
- Nuevos: UnPaso retira tools al tope (prep con rondas=MAX → tools None);
  Ejecutar con tool vetada NO llama a run_tool_call (fake contador) y el
  mensaje tool lleva el texto de veto; idéntica exitosa reutiliza caché;
  Sintetizar escribe informe con sección Pasos.
- `supervisar` E2E con `call_llm_agent` fake (2 rondas de tools + cierre):
  el informe final y las métricas de shared cierran.

## 5. `.env.example` + docs

- `.env.example`: las líneas de LAYA_MODEL_SUPERVISOR /
  LAYA_UNSURE_HIGH_SUPERVISOR se comentan como JUBILADAS por el bench (el
  checkpoint queda para la sonda, pasado por args).
- `docs/design.md`: sección "Supervisor v2" (ver §7 de esta spec no — la
  escribe el conductor con los números del bench).

## Candado final

`python3 -m pytest tests/ -q` verde (hoy 350; pueden bajar si se jubilan
tests del despacho — cada baja se nombra en el reporte) y ruff limpio. La
corrida E2E con LLM real la hace el conductor.
