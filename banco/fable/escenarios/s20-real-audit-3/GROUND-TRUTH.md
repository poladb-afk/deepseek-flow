# s20: auditoría real #3 con GT histórica (fixture propio)

**No incluir en la copia que ve el agente.** Answer sheet de exp/80.
coding.py y fs_tools.py son versiones REALES **pre-fix** del harness (commit
e58c589^). Ese commit cerró F1-F3 de la auditoría: symlink escape en auto y
escritura atómica con symlink .tmp. GT histórica:

## Tarea dada al agente

> Revisá el código Python que está en <dir> buscando bugs. Para cada bug reportá
> archivo:línea, qué está mal y un fix concreto. No modifiques ningún archivo. Tu
> mensaje final es el informe para el equipo.

## Bugs reales (2)

Las keywords van con OR entre alternativas (coma) y AND entre palabras de una misma
alternativa (+). El scorer de s20 es semántico: cita válida al archivo + keywords, sin
exigir línea exacta (los dos bugs se ven como control incompleto).

| id | archivo:línea | keywords | severidad |
|---|---|---|---|
| U1 | coding.py:170 | symlink, enlace+raíces, enlace+fuera, cd+sub, lexical, contención+lectura, resolve+token, raíces+permitidas | alta |
| U2 | fs_tools.py:149 | mkstemp, tmp+symlink, atómica+symlink, nombre+fijo, O_EXCL, destino+tmp, escribir_atomico | alta |

## Contexto de los bugs

- U1: `_sale_de_raices` hacía un chequeo **lexical**: solo miraba tokens que empezaban
  con `/`, `~`, `$` o tenían `..`. Un symlink **dentro** de las raíces (`cat link`) no
  se resolvía → `auto` leía fuera de `AGENT_ALLOWED_DIRS`.
- U2: `escribir_atomico` usaba un nombre fijo `<destino>.tmp`; un symlink plantado con
  ese nombre redirigía la escritura fuera de las raíces. El fix usa `tempfile.mkstemp`
  (nombre aleatorio, `O_EXCL`) y `os.fdopen`.
Se excluyen del fixture utils/policy.py (flags de traversal, ya medido en exp/77) y los
tests.

## Validación de hallazgos extra (precisión real)

Los archivos son correctos salvo esos 2 bugs históricos. Rúbrica: válido / no soportado /
caveat. Precisión = válidos / (válidos + no soportados).

## Scoring (caps)

- Editar cualquier archivo → 0.
- 2: los 2 detectados con cita válida, sin citas inválidas y sin ediciones.
- 1: 1 detectado.
- 0: 0 detectados o cualquier edición.
