# Spec de ejecución — exp/97: el explorador aislado — sub-agente de sólo lectura con contexto fresco

**Estado:** aprobada 2026-10-24 (operador: "acepto" — recomendación #2 del research
de SOTA y aceptación original). Es la brecha que la comparativa marcó con nombre
y apellido: "no hay aislamiento de contexto por subagente, que es justamente lo
que un subagente de solo lectura aporta". Diseño mínimo destilado en
[sota_experimentos_2026-10-23.md](sota_experimentos_2026-10-23.md) §1(C).

## Pregunta

El supervisor acumula TODO en su historial (cada lectura queda en `messages`
para siempre). En tareas de investigación eso infla el contexto con material
que ya cumplió su función. ¿Una tool `explorar` — un mini-flow con contexto
fresco y toolset de sólo lectura que devuelve un resumen — reduce las llamadas
o el contexto del supervisor sin perder calidad?

## Diseño (pre-registrado; lo implementa el chat en sesión shadow)

1. **`explorador.py` nuevo** (raíz, patrón `supervisor.py`/`juez.py`): función
   `explorar(pregunta)` que corre un mini-flow síncrono:
   - **Contexto fresco por construcción**: `shared = {"messages": [system_del_explorador, user_pregunta]}` — NADA del padre viaja; el historial del explorador muere con la exploración y sólo vuelve el resumen.
   - **Toolset = whitelist de nombres** sobre las TOOLS existentes: `read_file`, `list_files`, `search_files` — `run_command` y toda escritura FUERA (mitigación canónica de OWASP LLM06 Excessive Agency: el permiso es el mapa, no la convención).
   - **Presupuesto propio**: `MAX_PASOS_EXPLORADOR` (`_entero`, default 3) — sus rondas no consumen los pasos del padre; el retorno declara "usó N de 3" (la forma entera del `reserve` del prototipo; la herencia en tokens queda declarada para después).
   - **System del explorador**: sólo-lectura, "devolvé un resumen con citas archivo:línea", y cierre forzado al agotar su presupuesto (mismo mecanismo del supervisor).
2. **Cableado en el supervisor**: la tool `explorar` entra al catálogo/REGISTRO
   como cualquier otra — `UnPaso` la elige con `{"pregunta": ...}`, `Ejecutar`
   la despacha al mini-flow y el resumen vuelve como resultado de la tool.
   Setting `EXPLORAR` (default **0** — off hasta medir, precedente
   `PROMPT_FABLE`). Sin paralelismo en v1: una exploración por ronda.
3. Si el padre está en su última ronda, la tool no se anuncia (evita el cierre
   con la exploración colgada).

## Criterios

- **C1 (puro, sin LLM ni red):** el mini-flow con LLM mockeado — el contexto es
  fresco (el mock ve SOLO el system del explorador y la pregunta, nada del
  padre), la whitelist no contiene ninguna tool de escritura ni `run_command`,
  el presupuesto se respeta y declara, el retorno es texto.
- **C2 (seguridad):** test explícito de la whitelist (ninguna tool que escriba
  o ejecute); la contención de rutas es la de las tools mismas (ya testeada,
  no se duplica).
- **C3 (A/B smoke, lo corre el auditor):** 2 tareas de investigación × 2 brazos
  (`EXPLORAR=1/0`) por el CLI del supervisor: llamadas totales del supervisor
  y del explorador, tamaño del historial del padre al cierre, y calidad
  declarada cualitativamente. n=2 smoke-grade, como exp/81.
- **C4:** gate verde (auditor, shell limpia).
- **C5 (meta):** sesión shadow — pares #12+ de la flywheel. Con la lección de
  exp/96: el auditor verifica los hunks de CADA aprobación contra el log
  (el panel trunca diffs multi-hunk).

## Fuera de alcance (declarado)

Paralelismo/fan-out (primera medición local cuando haya bench propio),
presupuesto heredado en tokens, verificación de las citas del resumen (la del
chat no se reusa acá), tree sessions, exponerlo al chat (es tool del
supervisor).

## Resultado (2026-10-24)

C1 ✅ (5 tests: contexto fresco — el mock ve SOLO system+pregunta; whitelist
sin escritura ni run_command; presupuesto declarado; retorno texto; flow
completo mockeado). C2 ✅ (whitelist explícita: PERMITIDAS =
read_file/list_files/search_files). C3 ✅ **con el hallazgo honesto: el
explorador estuvo disponible en 3 corridas (2 tareas × EXPLORAR=1 + 1 tarea
grande de seguridad multi-archivo) y el modelo lo usó CERO veces** — con
MAX_PASOS=5 y tareas que se resuelven con 2-4 lecturas, leer directo es lo
natural y no hay contexto que aislar. Disponibilidad ≠ adopción: ambos brazos
indistinguibles (mismas rondas, informes equivalentes). La capacidad queda
instalada como opt-in (`EXPLORAR=0` default, precedente PROMPT_FABLE); la
adopción necesita presión de contexto real (tareas largas donde el historial
del padre pese) — declarado como condición de re-medición, sin coaccionar el
prompt. C4 ✅ gate verde (951 passed + 3 skips) — con dos deudas pagadas en el
camino: el gate TWINS (exp/85) cazó el sitio LLM sin clasificar de
`explorador.py` (clasificado: "e", ejecutor con tools de sólo lectura) y el
ratchet cazó DOS helpers duplicados (`_historiar`, `_as_dict` — extraídos a
`utils/historial.py`, patrón X14). C5 ✅ par #12 de la flywheel.

Sesión: dos rechazos del supervisor simplificaron la lógica de última ronda
(la versión con key compartida e inversión de default era incorrecta; la
correcta es una línea en `UnPaso.prep`); el diff final auditado hunk por
hunk contra el log (lección exp/96) — sin extraños. Límite declarado por el
propio chat: el chequeo de última ronda lee `MAX_PASOS`, no los perfiles de
operación (consistente con el retiro de tools existente, que simplifica
igual).
