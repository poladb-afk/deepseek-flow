# Spec: `sonda_laya.py` — auditoría de evidencia de los checkpoints de Laya

(exp/7 — la escribe el revisor; la aplica el harness. Objetivo: convertir
afirmaciones heredadas en mediciones propias, con un checkpoint por proceso.)

## Objetivo

Una sonda determinista (SIN LLM, SIN red, SIN DeepSeek) que corre el test
etiquetado de UN checkpoint de Laya y produce la evidencia que hoy falta:
ECE propio, tabla de confiabilidad por bucket de confianza, curva de
compuerta (cobertura vs precisión por umbral), latencia local en CPU y
RSS pico del proceso.

## Uso

    python3 sonda_laya.py router        # .modelos/router_flow-1k + test router (30 casos)
    python3 sonda_laya.py voto          # .modelos/router_voto + test voto (30 casos)
    python3 sonda_laya.py supervisor    # .modelos/supervisor_dispatch-1k + test supervisor (24)
    python3 sonda_laya.py base          # .modelos/laya-multilingual + test router (referencia)

LEY DE RAM: exactamente UN checkpoint por proceso. El script carga, mide,
escribe resultados y TERMINA. No hay modo multi-checkpoint ni servidor.

## Mapeo (contratos EXISTENTES — importarlos, no copiarlos)

| nombre | checkpoint | test (bmo) | pregunta | estado por caso |
|---|---|---|---|---|
| router | .modelos/router_flow-1k | /home/roquedb/Documentos/00_IA/bmo/train/tasks/router_flow_test.jsonl | nodes.PREGUNTA_ROUTER ["necesita_herramientas"] | {"pregunta": fields["pregunta"]} |
| voto | .modelos/router_voto | .../router_voto_test.jsonl | nodes.PREGUNTA_VOTO ["confirma_herramientas"] | {"pregunta": fields["pregunta"]} — VERIFICAR el formato real del archivo antes de asumir campos |
| supervisor | .modelos/supervisor_dispatch-1k | .../supervisor_dispatch_test.jsonl | supervisor.PREGUNTA_DESPACHO ["elegir_proxima"] | {"tarea": fields["tarea"], "hechos": fields.get("hechos", "")} |
| base | .modelos/laya-multilingual | mismo test que router | nodes.PREGUNTA_ROUTER | ídem router |

Formato de los tests: jsonl, un caso por línea: {"id", "fields": {...},
"answers": {"<pregunta>": "<etiqueta esperada>"}} (igual que ya leen
evals.py y sonda_router.py — reusar el parseo si conviene).

## Requisitos

1. **Carga**: usar `utils.laya.agente(setting)` con un setting propio
   (p. ej. setear `os.environ["SONDA_LAYA_CKPT"] = <path>` y llamar
   `agente("SONDA_LAYA_CKPT")`) — así se heredan HF_HUB_OFFLINE antes del
   import, el caché de errores y el RLock. Medir APARTE el tiempo de carga
   en frío (segundos) y el de inferencia por caso (ms).

2. **Por caso**: elección cruda, `answer_confidence` (la calibrada —
   utils.laya.preguntar ya la devuelve como confianza), correcto/incorrecto
   contra answers, y latencia ms de esa inferencia.

3. **Métricas globales** (funciones PURAS, importables y testeables):
   - `tabla_confiabilidad(casos, bordes)` — acierto y conteo por bucket de
     answer_confidence. Bordes default: [0.5, 0.7, 0.85, 0.95] (5 buckets).
   - `curva_compuerta(casos, umbrales)` — por umbral t en
     [0.5, 0.55, ..., 0.95]: `cobertura` = fracción de casos con
     conf >= t (los que se decidirían locales), `precision` = acierto
     entre esos casos, `ahorro` = cobertura (1 llamada local por caso).
   - `ece(casos)` — con `laya.ece_score` si la firma lo permite, si no con
     una implementación local de 10 bins sobre answer_confidence
     (documentar cuál se usó).

4. **RAM**: reportar `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss`
   (KB en Linux) como "RSS pico" en la salida.

5. **Salidas** (por corrida):
   - `salidas/evals/laya_evidencia_<nombre>.md` — informe: resumen (crudo,
     ECE, latencia p50/p95 de inferencia, carga fría, RSS pico), tabla de
     confiabilidad, curva de compuerta completa, y los fallos con su
     confianza exacta (caso, esperado, obtenido, conf).
   - `salidas/evals/laya_evidencia_<nombre>.json` — máquina: fecha iso,
     git sha (subprocess de `git rev-parse --short HEAD`), checkpoint,
     n casos, score crudo, ece, p50/p95, carga_ms, rss_max_kb,
     tabla_confiabilidad, curva_compuerta, fallos. Patrón: bench_router.json.

6. **Estilo**: patrón sonda_router.py / sonda_supervisor.py — standalone en
   la raíz, comentarios en español explicando el PORQUÉ, main(argv=None)
   con argparse. SIN tocar ningún otro archivo del proyecto.

## Fuera de alcance (no hacer)

- No entrenar, no ajustar temperaturas, no llamar a DeepSeek, no tocar
  .env, no modificar utils/laya.py ni los contratos.
- No correr los cuatro checkpoints en un mismo proceso (ley OOM medida).
