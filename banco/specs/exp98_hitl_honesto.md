# Spec de ejecución — exp/98: el HITL que muestra todo y explica los rechazos

**Estado:** aprobada 2026-10-24 (operador: "acepto" la recomendación). Los dos
agujeros del punto de confianza, con incidentes medidos: el diff de `edit_file`
se recorta a `SALIDA_MAX=4000` ANTES de mostrarse (exp/96: el supervisor aprobó
hunks que nunca vio — removieron `catalogo` y el gate lo cazó) y el rechazo es
`n` a ciegas (exp/96: el chat adivinó mal el motivo y re-propuso la métrica
rota de vuelta).

## Pregunta

¿El punto donde el humano decide puede mostrar la información completa (o
declarar exactamente qué queda oculto) y aceptar el PORQUÉ del rechazo — sin
romper el contrato bool de los callers?

## Diseño (pre-registrado; lo implementa el chat en sesión shadow)

**Fix 1 — el diff honesto** (`modules/coding.py`, `edit_file`):

- La línea de aprobación DECLARA el tamaño real del cambio:
  `¿Aplicar? → {path} ({hunks} hunks, +{agrega}/−{borra})` — contado sobre el
  diff COMPLETO, antes de cualquier recorte. El aprobador ve "6 hunks" aunque
  el panel muestre 2.
- El marcador de recorte declara lo oculto: en vez del "[... diff truncado
  ...]" mudo, el marker dice cuánto quedó sin ver (p. ej.
  `[... diff truncado: Q-quedan sin ver de M líneas ...]` — `recortar_chars`
  acepta el texto del marker; el caller lo arma con la cuenta).
- El CUERPO que viaja al HITL web (_cuerpo[0]) sigue siendo el mostrado
  (declarado).

**Fix 2 — rechazo con motivo** (`utils/aprobaciones.py` + callers):

- `pedir_aprobacion` devuelve una `Decision` (NamedTuple `ok: bool`,
  `motivo: str = ""`) con `__bool__ = ok`: los callers existentes
  (`if not pedir_aprobacion(...)`) siguen funcionando sin tocarse.
- El lector de terminal acepta `n <motivo>` / `no <motivo>`: lo que sigue a la
  primera palabra viaja como `motivo`. `s`/`si`/`y` ignoran el resto. EOF/Ctrl+C
  → rechazo sin motivo (como hoy).
- Los callers que REPORTAN al modelo incluyen el motivo:
  `edit_file` → "RECHAZADO por el usuario: {motivo o 'el archivo no se
  modificó'}"; `run_command` → su mensaje de rechazo con el motivo; ídem
  `write_file`/`modules/escritura.py` si usa el mismo prompt.
- HITL web: v1 sin campo de motivo (declarado — el rechazo web viaja sin
  motivo); la Decision se mantiene uniforme.

## Criterios

- **C1 (parser):** s/si/y → ok; n / no → rechazo sin motivo; "n porque X" →
  rechazo con motivo "porque X"; EOF → rechazo sin motivo; Decision truthiness
  compatible (`if not d` funciona, `if d` funciona).
- **C2 (diff honesto):** con un edit multi-hunk mayor a SALIDA_MAX, el prompt
  declara los hunks y +/− reales y el marcador dice cuánto queda sin ver
  (test capturando el prompt y el output con monkeypatch).
- **C3 (motivo viaja):** rechazo "n <motivo>" en edit_file → el resultado de
  la tool contiene el motivo (test con input mockeado).
- **C4:** gate verde; la suite existente de aprobaciones/policy sin romper
  (el contrato bool lo garantiza).
- **C5 (meta):** sesión shadow — par #13. Con la receta mejorada: el prompt de
  sesión incluye los fallos conocidos del entorno (la mejora #2 del análisis).

## Fuera de alcance (declarado)

Campo de motivo en el HITL web, paginar el diff interactivo (ver hunks a
pedido), cambiar SALIDA_MAX, tocar la política de niveles.

## Resultado (2026-10-24)

C1 ✅ `Decision` (NamedTuple `ok`/`motivo`, `__bool__ = ok`): s/si/y → ok;
n/no → sin motivo; "n porque X" → motivo "porque X" **con su casing original**
(el `.lower()` se aplica solo a la primera palabra — mejora del auditor: un
"no toques Policy.py" no llegaba como "policy.py"); EOF → rechazo sin motivo;
truthiness compatible. C2 ✅ el prompt de `edit_file` declara
`(N hunks, +A/−B)` contados sobre el diff COMPLETO y el marcador dice
"quedan X de Y caracteres sin ver" — **visto funcionando en vivo**: las
aprobaciones de la propia sesión de implementación mostraban "(1 hunks,
+4/−2)". C3 ✅ el motivo viaja al modelo en edit_file, write_file y
run_command ("Motivo del humano: ..."). C4 ✅ gate verde (955 passed + 3
skips) — con una mejora del auditor sobre el diseño: los callers leen el
motivo con `getattr(decision, "motivo", "")`, así el seam `_approve` acepta
bools para siempre (los ~8 mocks existentes de test_policy/test_policy_bypass
siguen andando sin tocarse — R2). C5 ✅ par #13.

Sesión 1 murió con el servidor tmux a mitad (su "s" final no llegó: el árbol
quedó con `_cuenta_diff` llamada pero no definida — restaurada por el auditor
desde el log). Sesión 2 completó escritura.py + tests; un rechazo del
supervisor evitó un fixture con placeholder no-op y un `if False else`
(motivo dado en el rechazo: la mejora de exp/98 funcionando en sí misma).
Fixes del auditor: fixture de C2 con líneas de contexto largas (el diff de 6
hunks con contexto ±3 daba ~2000 chars < SALIDA_MAX — nunca truncaba; hace
falta que las líneas de contexto PESEN, no que haya muchas), wording del
marcador, y el seam tolerante.
