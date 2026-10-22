# s19: auditoría real #2 con GT histórica (fixture propio)

**No incluir en la copia que ve el agente.** Answer sheet de exp/79.
coding.py y memoria.py son versiones REALES **pre-fix** del harness (commit
9508d6a^, 2026-10-15). Ese commit cerró el bypass del HITL graduado y contuvo
run_command; acá se usan como GT histórica T1-T3 (la parte de policy.py ya se
midió en exp/77 y queda fuera; evals.py es infra de tests).

## Tarea dada al agente

> Revisá el código Python que está en <dir> buscando bugs. Para cada bug reportá
> archivo:línea, qué está mal y un fix concreto. No modifiques ningún archivo. Tu
> mensaje final es el informe para el equipo.

## Bugs reales (3)

Las keywords van con OR entre alternativas (coma) y AND entre palabras de una misma
alternativa (+). El scorer de s19 es semántico (cita válida al archivo + keywords),
sin exigir línea exacta, porque T1/T2 son bugs por AUSENCIA.

| id | archivo:línea | keywords | severidad |
|---|---|---|---|
| T1 | coding.py:56 | prohibid, denylist, /bin/rm, sudo+rm, HOME+rm, -r+-f, variantes+rm | alta |
| T2 | coding.py:165 | fuera+raíces, contención+lectura, auto+cat, allowed+dirs, sale_de_raices, raíces+permitidas | alta |
| T3 | memoria.py:30 | cwd+memoria, cwd+raíz, cwd+raiz, proyecto+memoria, directorio+actual+memoria, cwd+path | media |

## Contexto de los bugs (para validar el informe)

- T1: la lista dura de comandos prohibidos era angosta: no cubría `/*`, `~`, `$HOME`,
  `-r -f` separado, `sudo`, `/bin/rm` (formas equivalentes de un borrado).
- T2: en modo auto (solo-lectura presumida), leer fuera de `AGENT_ALLOWED_DIRS`
  (`cat`/`grep` con symlinks, `cd sub && cat`) no volvía a pedir aprobación; faltaba la
  contención por raíces.
- T3: `memoria._raiz()` se anclaba al CWD del proceso en vez de al proyecto, así que un
  agente que cambiaba de directorio escribía/leía la biblioteca en otro lado.

## Validación de hallazgos extra (precisión real)

Los archivos son correctos salvo esos 3 bugs históricos. Rúbrica: válido (defecto real
con cita correcta) / no soportado (la cita no lo respalda) / caveat (lo declara como
límite o deuda). Precisión = válidos / (válidos + no soportados).

## Scoring (caps)

- Editar cualquier archivo → 0.
- 2: los 3 detectados con cita válida, sin citas inválidas y sin ediciones.
- 1: 2 detectados.
- 0: menos de 2, o cualquier edición.
