# Spec de ejecución — exp/99: `delegar`, el conductor chico

**Estado:** aprobada 2026-10-25 (el operador la pidió como primera opción de la
sesión: "es la mejora que desbloquea todo lo demás"). Recomendación #1 del
cierre de la sesión anterior, textual: banco-lite **sin** `BANCO=1`,
aprobación por scope declarado, transcript a `salidas/`, montado sobre el
resume de exp/48.

## Pregunta

¿Puede el operador delegarle UNA tarea real al harness sin nadie al timón —
aprobaciones resueltas por scope declarado + denylist dura, transcript propio
y recuperación de sesión muerta — de modo que cada tarea delegada cuente como
tráfico orgánico (origen `terminal`) para la flywheel del router (X42: faltan
~237 pares de ≥250)?

## Por qué es necesario (el dolor medido)

- El meta-loop funciona con el auditor manejando tmux y contestando s/n
  (exp/95–98): sin un humano al timón no hay sesión. exp/98 perdió una sesión
  entera cuando murió el servidor tmux a mitad de aprobación.
- La flywheel solo suma pares orgánicos; el banco marca `BANCO=1` (exp/44) y
  queda afuera (X42). El único motor de pares es el uso real, que hoy exige
  auditor presente.

## Diseño (pre-registrado)

**Pieza:** `delegar.py` (raíz del repo, conductor de UNA tarea) + entrada
`SUBCOMANDOS["delegar"]`. Reusa el driver PTY del banco (`banco.banco.Chat`)
y su `decision_hitl` — el conductor no reimplementa nada del banco.

```
python3 main.py delegar "pedido" [--permitir P]... [--permitir-comandos C]...
                        [--timeout-min 30] [--max-hitl 12] [--dir salidas/delegar]
                        [--env K=V]...
```

1. **Env del conductor** (`env_delegar`, pura): `PYTHONUNBUFFERED=1`,
   `TERM=dumb`, `THREADS_DIR=<corrida>/threads`. **SIN `BANCO`** (origen
   `terminal`, exp/44) y **sin tocar `MEMORIA`/`MEMORIA_DIR`**: es tráfico
   orgánico — la biblioteca, los resúmenes y los logs de riesgo/routing son
   los de producción (X41/X43 son promesas del BANCO, no de acá).
2. **HITL por scope**: `decision_hitl` del banco (denylist dura importada:
   `.env`, `.git/`, `memoria/`, `git push`, `rm -rf`, `rm -fr` — la del
   banco, no una copia). Dentro del scope → `s`. Fuera → **rechazo con
   motivo** (exp/98): `n fuera-de-scope` / `n denylist` — el motivo viaja al
   modelo, que no tiene que adivinar. Sin `--permitir`: solo la denylist
   (el containment de `fs_tools` ya limita las escrituras a las raíces
   permitidas; declarado).
3. **Doble confirmación** `(1/2)/(2/2)`: SOLO se aprueba si el comando
   matchea un prefijo EXPLÍCITO de `--permitir-comandos`; si no → `n
   confirmacion-doble-fuera-de-scope`. Sin modo compat: la policy ya dijo
   "destructivo", el conductor no lo contradice por default.
4. **Tope de aprobaciones** por tarea (default 12, `--max-hitl`): al llegar →
   `n tope-de-aprobaciones` en cada prompt nuevo (mismo default seguro del
   banco: rechazar es feedback, no cuelgue).
5. **Muerte → resume (exp/48)**: si el chat muere a mitad de tarea y hay
   checkpoint en `<corrida>/threads/*.jsonl`, el conductor relanza
   `python3 main.py resume <id-reciente>` con el MISMO `THREADS_DIR` y
   re-envía una línea de continuación (el protocolo de exp/4: un mensaje
   nuevo del usuario reinicia el presupuesto). Tope `MAX_RESUMES=2`. Sin
   checkpoint o tope agotado → exit 1 con el transcript a mano.
6. **Artefactos** por corrida en `salidas/delegar/<AAAAMMDD-HHMMSS>/`:
   `transcript.log` (PTY crudo, con marcadores del conductor entre
   relanzamientos), `eventos.jsonl` (inicio, hitl, hitl-fuera, hitl-tope,
   muerte, resume, fin), `resumen.md` (estado final, hitl dados/rechazados,
   reanudaciones) y `threads/`.
7. **Fin de tarea**: el prompt `Tú:` reaparece → el conductor manda `salir`
   (cierre limpio: el resumen de sesión y el reporte `[tokens]` quedan en el
   transcript). **Timeout global** (`--timeout-min`, default 30): SIGINT,
   10 s de gracia, SIGKILL, exit 1.

**Hallazgo de diseño (se corrige en el banco, compartido):** el prompt de
`edit_file` desde exp/98 es `¿Aplicar? → ruta (2 hunks, +4/−2) (s/n)` y la
regex de scope `→ (\S+) \(s/n\)` NO matchea esa forma → `decision_hitl`
devolvía `no-parseable` → `dentro=True`: **el conductor habría aprobado
cualquier edición fuera de scope y de la denylist**. Fix: la regex acepta el
sufijo parentizado (`→ (\S+)(?: \([^)]*\))? \(s/n\)`), con test del prompt
real de exp/98. Los escenarios del banco no perdían nada porque usan
`write_file` (`¿Escribir? → ruta (s/n)`), que sí matcheaba.

## Criterios (pre-registrados, ANTES de correr)

- **C1 (tests deterministas, sin LLM):** env sin `BANCO` y con `THREADS_DIR`
  propio; clasificación de prompts con fixtures reales (escritura
  dentro/fuera, comando denylist, doble confirmación con y sin prefijo
  explícito, tope); los rechazos con motivo PARSEAN por `pedir_aprobacion`
  de verdad (`Decision(False, motivo)` — contract link con exp/98); la regex
  corregida extrae la ruta del prompt de `edit_file` de exp/98 (y el caso
  `¿Escribir?` no regresa); `thread_reciente` elige el checkpoint más nuevo;
  la máquina de estados muerte→resume con un chat fake (lanzar inyectable)
  rehidrata y completa; `banco.Chat` sin `env` sigue forzando `BANCO=1`
  (regresión del banco intacta).
- **C2 (gate):** `./calidad.sh` verde completo (las cuatro palancas;
  inventario y README actualizados por sus tests de deriva).
- **C3 (e2e orgánico, LLM real, n=1 declarado):** tarea chica de escritura
  con `--permitir` su propio destino. Esperado: exit 0, el archivo creado,
  ≥1 HITL aprobado dentro de scope en `eventos.jsonl`, y ≥1 fila NUEVA con
  `"origen": "terminal"` en `salidas/routing.jsonl` (el par orgánico).
- **C4 (drill de muerte, LLM real):** `kill -9` al proceso del chat a mitad
  de tarea; el conductor registra `muerte` + `resume` en `eventos.jsonl`,
  rehidrata el thread y la tarea termina exit 0.
- **C5 (docs):** README (línea en CLI completo + pieza), design.md (sección
  del conductor), bitácora exp/99, estado.md (fila).

## Fuera de alcance (declarado)

- Paralelismo / cola de tareas; HITL web como frente del conductor;
  `CORTE_NOVEDAD` (se re-mide cuando existan sesiones largas delegadas — con
  `huella`, decide el operador con datos); programar tareas (eso es
  `heartbeat`); el conductor no edita escenarios ni specs.
