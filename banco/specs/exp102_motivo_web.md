# Spec de ejecución — exp/102: el motivo del rechazo también viaja por el HITL web

**Estado:** aprobada 2026-10-25 (operador: "Acepto" la cola chica — el campo
de motivo era el PENDING declarado de la v1 de exp/98: "el rechazo web viaja
sin motivo").

## El hueco

`pedir_aprobacion` con `HITL_WEB=1` llama a `hitl_web.aprobar()` y envuelve
su bool: `Decision(bool(...))` — el motivo se pierde. En la terminal el
rechazo `n <motivo>` viaja al modelo (exp/98); desde el navegador el rechazo
llega mudo y el modelo vuelve a adivinar.

## Diseño (pre-registrado)

- El form de **Rechazar** de la página gana un campo de texto `motivo`
  (opcional, ~1 línea); el de Aprobar no cambia (el parser ignora el resto
  en los YES de todos modos).
- `_post_decision` parsea `motivo` del cuerpo del form con
  `unquote_plus` (el navegador manda URL-encoded) y lo acota a 300 chars;
  queda en `pedido.motivo`. La página de gracias lo muestra (escapado).
- `hitl_web.aprobar()` pasa a devolver una **`Decision`** (ok + motivo; el
  timeout y todo error siguen siendo `Decision(False)` sin motivo — default
  seguro intacto). `pedir_aprobacion` devuelve esa Decision tal cual.
- Los tests existentes que asumen bool de `aprobar()` se adaptan al
  contrato extendido (mismo movimiento que exp/98 con `Decision`): su
  intención protectora no se toca (timeout ⇒ rechazo, CSRF ignorado, POST
  tardío no contamina, puerto roto ⇒ default seguro).

## Criterios (pre-registrados)

- **C1 (tests):** rechazo web con motivo → `Decision(False, <motivo>)` y
  `pedir_aprobacion` lo devuelve entero; rechazo sin motivo → `Decision(False,
  "")`; aprobación ignora el motivo; la página sirve el campo; URL-encoding
  decodificado (espacios, `+`, acentos); motivo acotado a 300; los cuatro
  tests de contención siguen verdes con el contrato nuevo.
- **C2:** `./calidad.sh` verde completo.
- **C3 (e2e manual, declarado):** server real `python3 main.py webhook` +
  POST con curl del form de rechazo con motivo — verificado en la corrida de
  esta spec, sin fixture permanente (la suite ya ejerce el server real).
- **C4 (docs):** bitácora exp/102, fila en estado.md, docstrings corregidos
  (el "v1 sin motivo" de aprobaciones/hitl_web ya no es verdad).

## Fuera de alcance

- El diff paginado a pedido (la otra mitad de la cola chica): sigue
  pendiente, necesita diseño de UX propio.
- Motivo en la aprobación (no solo el rechazo): el parser lo descarta por
  contrato.
