# AGENTS.md — contrato para agentes en deepseek-flow

Este repo es un **harness de agente sobre PocketFlow**: código Python de un
producto que se mide (trazas, benches, evals) más docs que son contrato. Si
sos un agente programando acá, este archivo es la puerta de entrada; el
detalle vive en `docs/` (se lee bajo demanda).

**Presupuesto de contexto:** este archivo se mantiene corto a propósito
(≤ 160 líneas) porque es contexto de *cada* request. No lo infles: el
detalle va a `docs/`.

## Antes de tocar nada

Leé, en este orden, lo que aplique:

1. `docs/estado.md` — el tablero vivo: un hallazgo por fila (A/H/R/X) con
   estado, evidencia y el test que lo cubre. **Empezá por acá.**
2. `docs/design.md` — lo que es verdad hoy: grafos, contratos de `shared`,
   leyes/límites y el diseño de cada pieza.
3. `docs/bitacora.md` — cómo se llegó acá: cada experimento con su medición.
   Si tu cambio contradice una medición, decilo explícitamente.
4. `docs/roadmap.md` — qué falta y en qué orden.

Si el pedido toca un flujo, un módulo o una policy: buscá su sección en
`docs/design.md` **antes** de leer el código.

## Reglas no negociables (cada una tiene un gate)

El patrón es el de git-agent-ratchet: una regla sin enforcement es una
sugerencia, y la prosa no frena a un agente en la vuelta seis. Cada fila
nombra el gate que la hace cumplir.

| # | Regla | Gate que la hace cumplir |
|---|---|---|
| R1 | El gate va verde antes de decir "listo": `./calidad.sh` (ruff · C901 · ratchet · pytest). No se corre un subconjunto y se declara verde. | `calidad.sh` |
| R2 | No se borra, mueve ni saltea un test para pasar el gate. El inventario es la foto del PR 4; el ratchet cuenta el total y no deja que baje. | `tests/test_inventario.py`, `ratchet.py` |
| R3 | Los docs no pueden mentir: tool count, CLI, settings, paths y tests citados tienen que existir. | `tests/test_docs_sin_deriva.py`, `tests/test_deriva_reglas.py` |
| R4 | Todo hallazgo ✅ del tablero cita el test que lo cubre, y ese test existe de verdad. | `tests/test_deriva_reglas.py` |
| R5 | Los helpers privados no se bifurcan: si `_foo` ya existe en otro archivo, extraelo a `utils/` en vez de copiarlo. | `ratchet.py` (helpers duplicados) |
| R6 | El baseline del ratchet solo se mueve hacia la mejora; editarlo a mano es bypass. | `ratchet.py` (guardia con `HUMAN_RATCHET_BYPASS_KEY`) |
| R7 | La seguridad no se relaja: HITL, contención de paths y política de comandos se tocan con tests de bypass. | `tests/test_policy_bypass.py`, `tests/test_policy.py` |
| R8 | Los contratos congelados (dispatch, voto, prefiltro) no cambian sin regenerar su sha1 y justificarlo. | `tests/test_contratos.py` |
| R9 | El código se escribe para humanos: mínimo que funciona, sin defensas/abstracciones/docstrings no pedidos, sin banners decorativos; los `except` amplios no crecen. | `tests/test_estilo_humano.py`, `ratchet.py` |

## Cómo trabajar (reglas blandas, todavía sin gate)

- **Parche mínimo**: el cambio más chico y seguro que cumple el pedido. Nada
  de refactors amplios, renombres masivos ni "de paso arreglo esto otro".
- **No inventes requisitos**: si el pedido es ambiguo, preguntá al operador
  antes de asumir.
- **Evidencia antes que opinión**: si cambiás comportamiento, medí (bench,
  banco, trazas) y dejá la medición en la bitácora. El informe no reemplaza
  al test; el test no reemplaza la medición.
- **Dependencias**: el repo es deliberadamente mínimo (stdlib salvo lo
  justificado en `requirements.txt`). Una dependencia nueva necesita motivo
  medido, no comodidad.
- **Docs en el mismo paso**: hallazgo nuevo → fila en `docs/estado.md`;
  cambio de contrato → `docs/design.md`; medición → `docs/bitacora.md`.
  Cambiar código sin actualizar el doc que lo describe es deriva.
- **Comentarios**: en español y explican el PORQUÉ (ley medida, bug
  histórico, decisión de diseño). No los reformatees ni los acortes "por
  estilo": son parte de la evidencia.
- **Citas honestas**: en tus reportes citá `ruta/archivo.py:línea` y
  verificá la línea antes de afirmarla; lo no verificado se declara no
  verificado.
- **Commits**: convención del repo `tipo(ámbito): resumen` (docs/test/fix/
  feat), cuerpo con la medición y el gate corrido.
- **Idioma**: docs, comentarios, nombres de tests y mensajes en español
  rioplatense, como el resto del repo.

## Código: forma humana (evidencia, no opinión)

El código generado por agentes tiene una firma medible: más verboso, más
defensivo, más duplicado (papers y fuentes en
`docs/informes/codigo_ia_vs_humano_2026-10-19.md`). La forma se pide y se
gatea, no se "revisa después":

- **Pirámide antes de escribir**: ¿necesita existir? → ¿ya está en el repo
  (`utils/`, `modules/`)? → ¿stdlib? → ¿feature nativa? → ¿dependencia ya
  instalada? → mínimo que funciona + un test si tiene lógica. (Ponytail)
- **El tell #1 es reimplementar**: antes de crear `_foo`, buscá el helper
  existente; el ratchet cuenta los bifurcados. Lazy sobre la solución, nunca
  sobre leer el código que tocás.
- **Defensas solo en la frontera de confianza**: validación de entrada,
  seguridad y accesibilidad NO se recortan; `except` amplio con motivo visible
  (`# noqa: BLE001 (motivo)`), nunca mudo; acotarlo a la excepción real es
  siempre mejor.
- **Docstrings para el porqué**, no para repetir el nombre; comentarios que
  agregan información, no que narran la línea siguiente.
- **Nada de banners decorativos, código muerto "por si acaso", ni `_v2` en
  paralelo**: si algo se reemplaza, se reemplaza.

## Bypasses prohibidos (por nombre)

Un agente con un gate rojo va a buscar el camino que lo ponga verde. Estos
son los que este repo ya conoce y no acepta:

- Editar `ratchets/baseline.json` a mano (solo el ratchet lo baja al mejorar).
- Editar `tests/inventario_tests.txt` para "arreglar" un rojo.
- Marcar `skip`/`xfail` sin el marker que declara el recurso que falta.
- Comentar etapas de `calidad.sh` o del workflow de CI para pasar.
- `--no-verify` / `git commit -n` cuando haya hooks.
- Exportar `HUMAN_RATCHET_BYPASS_KEY` o correr `--actualizar` por tu cuenta:
  es decisión del operador humano, no del agente.
- Bajar `MAX_TOOL_ROUNDS` o endurecer/relajar `HITL_AUTO` como "fix" de un
  test: la seguridad y el presupuesto son contrato de producto.

## Definición de terminado

- [ ] `./calidad.sh` verde (las cuatro palancas) y su salida pegada en el reporte.
- [ ] El cambio tiene test (nuevo o existente) y su nombre está citado.
- [ ] Si tu cambio bajó la métrica del ratchet, `ratchets/baseline.json` va
      en el mismo commit (el gate lo reescribe solo).
- [ ] El código pasa `tests/test_estilo_humano.py` y no suma `except` amplios
      (ratchet) ni banners.
- [ ] docs actualizados según el tipo de cambio (estado / design / bitácora).
- [ ] Reporte final: qué cambiaste, qué corriste, qué quedó afuera.
