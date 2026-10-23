# Spec de ejecución — exp/94: el listado del juez — tope y sin artifacts

**Estado:** aprobada 2026-10-23 (operator: meta-loop permanente — harness
ejecuta, operador audita). La causa la midió exp/93: la llamada de EXTRACCIÓN
DE CLAIMS del juez manda ~139k tokens cuando trabajo=raíz del repo, porque el
LISTADO de archivos del prompt no tiene tope y arrastra artifacts — 5.603
archivos / 358k chars, de los cuales `salidas/` sola aporta 4.762 (transcripts
y logs de corridas), más `.ruff_cache`, `.archify` y `.modelos`. La llamada de
juicio, en cambio, está correctamente capeada (~7–11k tokens).

## Pregunta

¿Se recorta el listado a tamaño de diseño — tope con conteo declarado y sin
artifacts — sin perder honestidad ni romper los fixtures chicos?

## Diseño (pre-registrado; lo implementa el chat en sesión shadow)

1. **`IGNORADOS_DIFF`** suma los directorios de artifacts/cachés: `"salidas"`,
   `".ruff_cache"`, `".archify"`, `".modelos"`. `memoria/` NO se excluye
   (datos curados del usuario, no artifacts — declarado; si algún día pesa,
   se decide con datos). Esto limpia el listado Y el diff por árbol
   (`diff_contra`); `diff_git` no cambia (git ya ignora esos dirs por
   `.gitignore`).
2. **Tope del listado en el prompt de claims** (`RecolectarClaims._prompt`):
   el listado viaja recortado a un tope de ~4000 chars, y el marcador DECLARA
   el total (`[… listado truncado: N archivos …]`) — el extractor tiene que
   saber que el árbol es más grande que lo que ve. El reporte ya tiene su
   tope propio (6000) y no se toca.
3. Los fixtures del banco (árboles chicos) no cambian de comportamiento: sin
   truncado cuando el listado entra.

## Criterios

- **C1 (tests puros):** el listado truncado declara el total; los dirs de
  artifacts no aparecen en `_archivos_bajo` ni en el listado ni en el diff
  por árbol; árbol chico → listado entero, sin marcador; el prompt de claims
  con árbol gigante queda acotado (longitud medible, sin LLM).
- **C2 (e2e, lo corre el auditor):** una corrida real del juez sobre la raíz
  del repo deja un evento usage de claims MUY por debajo de 139k (esperado:
  ~10–15k tokens); la sonda de exp/93 lo muestra.
- **C3:** sin regresión — la suite del juez existente verde (los fixtures
  usan árboles chicos).
- **C4:** gate verde (auditor, shell limpia — lección exp/93: el entorno de
  la sesión contamina corridas completas).
- **C5 (meta):** sesión shadow con origen terminal — par #3 de la flywheel.

## Fuera de alcance (declarado)

Cambiar el tope del reporte, el prompt de juicio (ya capeado), excluir
`memoria/`, el techo global de exp/87 (el listado ERA el techo en la
práctica; si queda otra fuente grande, la sonda la encontrará), tocar la
política.

## Resultado (2026-10-23)

C1 ✅ (4 tests: marcador con total, artifacts fuera de árbol/diff/listado,
fixture chico sin marcador, prompt de claims acotado medible sin LLM).
C2 ✅ **e2e medido con la sonda de exp/93**: corrida real del juez sobre la
raíz del repo — llamada de claims **138.957 → 2.799 tokens (50×)**; la de
juicio bajó a 4.889 (el diff también quedó sin artifacts). Una auditoría
completa del juez: ~148k → **~7,7k tokens de prompt (~20×)**. C3 ✅ la suite
del juez 60 → 64 sin tocar contratos. C4 ✅ gate verde (932 passed + 3 skips).
C5 ✅ par #3 de la flywheel ("herramientas (35 rondas)").

Sesión: dos momentos de supervisión — un edit con hunk truncado en el panel
(el borrado aparente del docstring de diff_contra era el desplazamiento por
la función nueva insertada) se rechazó y re-propuso completo; el chat volvió
a desobedecer el "tests dirigidos" pero esta vez usó `git stash` para
confirmar por sí mismo que los 3 fallos de la suite completa eran la
contaminación de entorno conocida (exp/93) — los roundtrips dejaron el árbol
intacto. TWINS: `_archivos_bajo` es el único caminador de árboles. El e2e
(C2) lo dejó explícitamente para el auditor, que es su gate.
