# Pre-registro — fase 5b de elegancia: las directivas y los skills, por descripción (S7/S8)

**Estado:** pre-registrado el 2026-10-30 (X110), ANTES de escribir el código.
Cambia conducta: entra solo si pasa el A/B de abajo. No se retoca después de
ver resultados (un cambio va como desvío declarado en la bitácora).

## Lo que hay hoy (medido al escribir esto)

- **Tres directivas en `main.py`**, cada una con su setting:
  `DIRECTIVA_FORMA` (279 chars, `PROMPT_FORMA`, default 1),
  `DIRECTIVA_FABLE` (1.208, `PROMPT_FABLE`, default 0) y
  `DIRECTIVA_AUDITORIA` (735, `PROMPT_AUDITORIA`, default 0). Con el texto
  fijo del `system_prompt` (526) suman los 2.748 del ratchet.
- **Dos skills** (`skills/revision.yaml`, `skills/tdd.yaml`) que se activan
  por una `condicion`: una regex en español sobre la pregunta. Medido sin
  LLM sobre el escenario nuevo: la de `revision` dispara en **1 de 4**
  positivos — "Review the code…" y "Mirá …: ¿ves algo que esté mal?" no
  la activan. Es el mismo defecto que la regex de palabras de la 4b-mín
  (F1: cambiar el idioma o la redacción rompe la decisión), en YAML, donde
  el ratchet no la ve.
- **El skill recorta las tools** del turno a su subset. `utils/skills.py` ya
  dice que no es una frontera de seguridad; y quitar tools en caliente es lo
  que *Context engineering* (Manus, en las fuentes de `elegancia.md`) dice
  no hacer.

## Evidencia de cada directiva

| directiva | experimentos | lo medido | qué pasa en la 5b |
|---|---|---|---|
| forma | exp/51, `deepseek-flash` (el modelo de hoy) | SLOC −77 %, docstrings −100 %, sin errores de sintaxis | **se queda en el system prompt**: S8 la sostiene con el modelo actual. Sale su setting (el A/B se cerró) |
| auditoría | exp/77–80 | s18: recall 3,67 → 5,00 (único fixture con hueco); s19 y s20 en techo; en exp/80 creó un temporal en 1 de 3 | **pasa a skill** `auditoria-seguridad`, con el texto de la directiva tal cual |
| fable | exp/72, exp/73 | sin lift: −0,33 en la única trampa que discrimina (s2) y +0,33 sin poder estadístico | **decisión del operador** (abajo) |

## Qué cambia

1. **Activación por descripción** (Agent Skills, divulgación progresiva).
   Un módulo nuevo `modules/skills.py` ofrece la tool `usar_skill(id)`. Su
   descripción trae el catálogo: `id: descripcion` de cada YAML. Esa
   descripción es estable en la sesión, así que no rompe el KV-cache. El
   modelo decide si el pedido la necesita. La tool imprime
   `[skill] <id> activo — <descripción>` (el marcador del banco no cambia) y
   devuelve las instrucciones como resultado. No se usa Laya: es una
   dependencia opcional (sin ella, ningún skill se activaría) y este juicio
   no tiene checkpoint entrenado.
2. **Se borran** el campo `condicion` de los YAML, `skill_para`, el nodo
   `Skills`, el campo `tools:` con `filtrar_tools`, `turno["skill"]` y el
   setting `SKILLS`. Para quitar el mecanismo se borra el módulo, como con
   cualquier capacidad (F5). El grafo vuelve a
   `GetQuestion → PreFetch → Contexto → AgentStep`.
3. **Directivas**: `DIRECTIVA_AUDITORIA` sale de `main.py` y pasa a
   `skills/auditoria-seguridad.yaml`, texto idéntico. `system_prompt()`
   pierde sus tres perillas y sus tres settings. `DIRECTIVA_FORMA` queda
   fija; la sonda de exp/51 arma su brazo "sin forma" quitando la constante
   del texto, del lado del laboratorio.

## Decisión que necesito antes del código: fable

- **(a) Borrarla** (mi recomendación). Dos A/B sin lift, y en la única
  trampa que discrimina el brazo B fue peor que A. Producción ya la tiene
  apagada, así que borrarla no cambia el chat. Las sesiones de self-fix que
  la prendían (exp/83, exp/91) siguen pudiendo pegar el método en el pedido.
- **(b) Pasarla a skill `metodo-fable`.** Hay que sumar al A/B las 5 trampas
  de exp/72 (s1, s2, s3, s7, s9) ×3 por brazo, unas 30 corridas más, con el
  criterio de que la 5b no empeore ninguna trampa. El riesgo es que el
  modelo la cargue en s2.

## Riesgos que el banco tiene que medir

1. **Que no se cargue cuando hace falta**: hoy la regex es determinista;
   ahora decide el modelo.
2. **Que se cargue de más**: una carga es una ronda de tools, y la 3b exige 0
   rondas en las preguntas directas.
3. **El costo del catálogo**: unos 300 chars más en la descripción de las
   tools, en cada llamada.
4. **Sin el recorte de tools**, que una revisión edite o cree archivos.
5. **La auditoría pasa a activarse sola**: en la práctica queda prendida por
   default en los pedidos de auditoría. exp/79 pedía evidencia de que el
   efecto generaliza antes de hacerlo y no la consiguió (fixtures en techo).
   El A/B tiene que mostrar que no empeora s19 y s20.

## Instrumento

- `banco/escenarios/fase5b-disparo.yaml`: 4 positivos (revisión en
  español, en inglés y parafraseada; auditoría de seguridad) y 3 negativos
  (haiku, concepto, leer y resumir).
- `banco/probes/fase5b.py`: qué skill se cargó en cada turno, desde los
  eventos `turno-fin` y el transcript, y el criterio 1. Predicción de la
  base, medida al escribir esto (`test_la_regex_de_hoy_dispara_en_uno_de_cuatro_positivos`):
  **1 de 4**.
- Los que ya existen: `exp55-skills`, `exp56b-skill-revision-on`,
  `bench_fable.py` (s18, s19, s20), `fase3b-directas` y
  `tokens_runs.py` para USD y rondas.
- **Cada brazo en su worktree, con su `.runs` desde el principio**, igual que
  en la 3b.

## Corridas

| brazo | árbol | corridas |
|---|---|---|
| base | HEAD previo a la 5b (`e8898c3` o el que corresponda) | ver abajo |
| 5b | el PR de la 5b | ver abajo |

En cada brazo: `fase5b-disparo` ×3, `exp55-skills` ×1,
`exp56b-skill-revision-on` ×3, `fase3b-directas` ×3, y s18, s19 y s20 ×3
con `bench_fable.py`. En la base, la auditoría va con `--brazos A`
(producción de hoy, sin checklist) y también `--brazos D` como referencia;
en la 5b, `--brazos A` (sin env: lo que hay es lo que decide). Son 34
sesiones por brazo, más 9 de la referencia D.

## Criterios (todos)

1. **Disparo**: en la 5b, en cada una de las 3 corridas de
   `fase5b-disparo`, al menos 3 de 4 positivos cargan el skill correcto, y
   0 cargas en los negativos entre las 3 corridas.
2. **Preguntas directas**: `fase3b-directas` en la 5b sigue cumpliendo el
   criterio 1 de la 3b (≥ 10/12 con 0 rondas en las 3 corridas, ninguna con
   más de 1), con 0 cargas de skill, y USD ≤ **1,15 ×** la base (mediana).
   El 1,15 cubre el catálogo.
3. **Revisión** (`exp56b-skill-revision-on`, el valor medido del skill era
   bajar el ruido): en la 5b se carga `revision` en ≥ 2 de 3; issues
   detectados ≥ base − 0,5; palabras ≤ 1,2 × base; 0 citas inválidas; 0
   archivos tocados.
4. **Auditoría con hueco (s18)**: recall de la 5b ≥ recall de la base A +
   1,0, con R1 y R3 en ≥ 2 de 3 seeds (el criterio de exp/78), y el skill
   cargado en ≥ 2 de 3.
5. **Auditoría en techo (s19, s20)**: recall de la 5b ≥ base A, y **0
   ediciones ni archivos nuevos** en las 6 corridas (el efecto lateral de
   exp/80).
6. **`exp55-skills`** sigue igual: revisión dispara, el haiku no.
7. `ruff`, ratchet y suite en verde.

Si falla 1 o 4, el skill no se activa por descripción con este modelo, y la
regex no vuelve: se vuelve a este documento con el dato. Si falla 2, el
catálogo cuesta más de lo que vale. Si fallan 3 o 5, el recorte de tools sí
protegía algo, y eso se discute con el dato antes de reponerlo.

## Efecto esperado en los ratchets (no es criterio)

- `texto_de_prompt` 2.748 → **805** (526 + 279). La meta de ≤ 800 **no se
  alcanza con la 5b**: le faltan 5 chars, y recortar el prompt para llegar
  al número sería trampa al ratchet. Lo que propongo: meta = 805 (lo fijo
  más la forma, sostenida por exp/51), o sacar la forma con su propio A/B.
  Lo decide el operador.
- `settings_leidos` 58 → **54** (`PROMPT_FORMA`, `PROMPT_FABLE`,
  `PROMPT_AUDITORIA`, `SKILLS`).
- `nodos_largos` y `vocabulario_hardcodeado` sin cambio. La regex de los YAML
  sale, pero el ratchet no la contaba.

## Fuera de alcance

Escribir skills nuevos, cambiar el texto de alguno o endurecer el checklist
("no crees temporales", que propuso exp/80). Cada uno es su propio PR, con
su dato.
