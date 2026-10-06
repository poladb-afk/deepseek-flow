# Spec: scope de aprobación por path en el banco (exp/11)

(Motivo medido: en la sesión exp8-aplicar el harness propuso editar el
`.env` real fuera de spec y solo el timing lo frenó — el driver aprobaba
TODO el HITL del turno sin mirar el objetivo.)

## Objetivo

El driver del banco deja de aprobar a ciegas: parsea el objetivo de cada
prompt HITL y solo responde con la política del turno si el objetivo está
DENTRO del alcance declarado por el escenario. Fuera de alcance → "n"
automático + evento registrado. Una denylist dura del conductor aplica
por encima de cualquier scope.

## Cambios en `banco/banco.py`

### 1. Esquema del escenario

Claves nuevas (opcionales), a nivel escenario (aplican a todos los turnos):
- `permitir:` — lista de PREFIJOS de rutas aprobadas (write_file/edit_file).
- `permitir_comandos:` — lista de PREFIJOS de comandos aprobados (run_command).
Sin esas claves, todo está permitido SALVO la denylist dura (compatibilidad
con los escenarios existentes).

### 2. Denylist dura del conductor (constante)

- Rutas: `.env`, `.git/`, `memoria/` — jamás aprobables por el driver,
  sin importar el scope (match por substring en la ruta).
- Comandos: `git push`, `rm -rf`, `rm -fr` — ídem.

### 3. Función PURA `decision_hitl(prompt, buffer_reciente, permitir=None, permitir_comandos=None)`

Devuelve dict {tipo, objetivo, dentro, motivo}:
- `tipo` ∈ {"escritura", "comando", "desconocido"}.
- Escritura: el prompt matchea `→ (\S+) \(s/n\)` (¿Escribir?/¿Aplicar?) →
  objetivo = la ruta. dentro=False si: ruta toca la denylist de rutas, o
  `permitir` está definido y NINGÚN prefijo matchea. motivo: "denylist"
  o "fuera-de-scope".
- Comando: el prompt matchea `¿Ejecutar? \(s/n\)` → el objetivo es el
  COMANDO, extraído del buffer reciente: la última línea con contenido
  anterior al prompt que NO sea el banner `── run_command` ni la línea
  `↳ ...` (la explicación). dentro=False si: comando empieza con algo de
  la denylist de comandos, o `permitir_comandos` definido y ningún prefijo
  matchea.
- Desconocido: ni escritura ni comando (p. ej. prompt nuevo) → dentro=True
  con motivo "no-parseable" (mejor el flujo sigue y la política decide;
  el evento queda registrado para revisar).

### 4. Integración en el loop de turnos

Donde hoy se responde el HITL con la política: primero
`decision = decision_hitl(ultima_linea, ventana_reciente, permitir, permitir_comandos)`.
Si `dentro` → enviar la respuesta de la política (como hoy). Si NO →
enviar "n" y loguear evento `"hitl-fuera-de-alcance"` con
{objetivo, motivo, turno}. El conteo hitl del turno sigue contando.

### 5. Tests (`tests/test_banco.py`, agregar)

Casos con FIXTURES REALES (líneas textuales de transcripts de sesiones
anteriores, p. ej. `¿Escribir? → /home/.../prueba_banco/hola.txt (s/n):`):
- ruta dentro del scope (`permitir: ["/tmp/prueba", "/proy/prueba_scope"]`)
  → dentro=True.
- ruta fuera → dentro=False, motivo "fuera-de-scope".
- `.env` SIEMPRE fuera, incluso si alguien pusiera el prefijo en permitir
  (usa un permitir que contenga el directorio del .env para probarlo).
- comando dentro de permitir_comandos ("cd /x && python3 -m pytest") con
  prefijo "cd" → dentro=True.
- comando "git push origin main" con buffer de ejemplo → dentro=False,
  motivo "denylist".
- extracción del comando desde un buffer de ejemplo real (banner + ↳ +
  comando + prompt).
- prompt no-parseable → dentro=True, motivo "no-parseable".
- escenario del esquema: las claves nuevas son opcionales (cargar uno de
  banco/escenarios/ sin ellas sigue válido).

## Fuera de alcance

No tocar el chat, nodes, módulos, ni el .env. La denylist es del DRIVER
(el chat sigue con su propia política HITL intacta).
