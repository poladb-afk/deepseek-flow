# Spec exp/11 — docs: sección design + entrada roadmap

## 1. `docs/design.md` — después de la sección exp/9

(Insertar después del bloque que termina con "...que el modelo no
puede autodiagnosticar." — texto textual):

```
### exp/11 — scope de aprobación por path en el banco (2026-10-06)

Riesgo operacional medido: en la sesión exp8-aplicar el harness propuso
editar el `.env` real fuera de spec y solo el timing lo frenó — el driver
del banco aprobaba TODO el HITL del turno sin mirar el objetivo.

El driver ahora parsea el objetivo de cada prompt HITL y responde con la
política solo si está dentro del alcance declarado por el escenario
(`permitir:` prefijos de rutas, `permitir_comandos:` prefijos de
comandos). Fuera de alcance → "n" automático + evento
`hitl-fuera-de-alcance` con el objetivo. Una DENYLIST DURA del conductor
aplica por encima de cualquier scope: `.env`, `.git/`, `memoria/`,
`git push`, `rm -rf` — jamás aprobables por el driver. Sin claves de
scope, todo está permitido salvo la denylist (compatibilidad).

Auto-prueba en vivo (escenario exp11-autoprueba): escribir un archivo
dentro del scope → aprobado y creado; intentar agregar un comentario a
`.env` vía edit_file → el driver rechazó solo (evento con motivo
"denylist"), el modelo reportó el rechazo como dato, y el hash del
`.env` quedó intacto. 3/3 turnos OK.
```

## 2. `docs/roadmap.md` — al final de la sección "## Ciclo de experimentos exp/"

(Append después de la entrada exp/9 — texto textual):

```
- **exp/11 ✅ mergeada** — scope de aprobación por path en el banco:
  el driver del banco parsea el objetivo de cada HITL y solo aprueba
  dentro del scope del escenario; denylist dura del conductor (.env,
  .git/, memoria/, git push, rm -rf). Auto-prueba en vivo: el ataque al
  .env se rechazó solo (evento hitl-fuera-de-alcance), el permitido
  corrió. Sección en design.md.
```

## Reglas

Solo estas 2 operaciones textuales.
