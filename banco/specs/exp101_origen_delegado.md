# Spec de ejecución — exp/101: el origen `delegado` para las etiquetas de riesgo

**Estado:** aprobada 2026-10-25 (operador: "Acepto" el orden propuesto — el fix
del origen primero, antes de que la delegación crezca).

## El hueco

Las corridas del conductor (exp/99–100) heredan origen `terminal` para TODO.
Para el PAR de routing eso es correcto (la etiqueta del par es el uso observado
de tools, no el s/n — el par #14 lo celebró). Pero la ETIQUETA del juez de
riesgo (exp/44) ES el s/n: en una corrida delegada lo decide el **scope del
conductor, no un humano**. Es la misma contaminación que X18 cerró para el
banco — y `delegar` existe para que esa clase de corrida se vuelva frecuente.

**Estado real del log (medido antes de la spec):** 0 filas contaminadas hoy —
`write_file`/`edit_file` no observan riesgo (solo `run_command` en banda
`preguntar`/`confirmar_doble`) y las verificaciones de las corridas de hoy
fueron `cat`/`ls` (nivel `auto`). La exposición son los `run_command` no
whitelisteado que el conductor apruebe por scope a partir de ahora.

## Diseño (pre-registrado)

- `utils/riesgo.origen_etiqueta()` — nueva: la procedencia de la ETIQUETA.
  Con `DELEGADO=1` → `"delegado"`; si no, lo que diga `origen()`.
  `registrar()` pasa a usar `origen_etiqueta()`.
- `origen()` **NO se toca**: es la procedencia del PAR de routing
  (`laya_routing` la importa); las delegadas siguen contando `terminal` para
  la flywheel.
- `delegar.env_delegar()` fija `DELEGADO=1` (junto a THREADS_DIR; sigue sin
  `BANCO`).
- `banco/probes/estado_riesgo.py`: fila de display `delegado` junto a la de
  `banco` (no cuentan para el criterio ≥300/≥100).

## Criterios (pre-registrados)

- **C1 (tests):** con `DELEGADO=1` la etiqueta es `delegado` y el `origen()`
  de routing SIGUE `terminal` (el pinneo del contrato de la flywheel);
  `registrar` escribe `origen_etiqueta`; `estado_riesgo.estado` excluye
  `delegado` de las orgánicas y la cuenta aparte; `env_delegar` pone
  `DELEGADO=1` y sigue sin `BANCO`.
- **C2:** `./calidad.sh` verde completo.
- **C3 (e2e real, n=1):** una corrida delegada cuya tarea incluya un
  `run_command` de banda `preguntar` (p. ej. `du`) aprobado por scope → la
  fila nueva en `salidas/riesgo.jsonl` dice `"origen": "delegado"` y el probe
  la cuenta en la fila de no-cuentan.
- **C4 (docs):** bitácora exp/101, fila en estado.md, una línea en design.md.

## Fuera de alcance

- Re-etiquetar filas históricas (no hay: 0 contaminadas, medido).
- Cambiar el criterio de readiness o la flywheel.
