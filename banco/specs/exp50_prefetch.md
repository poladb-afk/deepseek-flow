# exp/50 — pre-fetch como política declarativa (apéndice 13 del 12-factor)

Corte pre-registrado en exp/47: "A/B pre-fetch ON/OFF: ≥1 ronda menos sin
subir errores". El material lo dice plano: "if you already know what tools
you'll want the model to call, JUST CALL THEM DETERMINISTICALLY". Hoy el
pre-fetch existe ad-hoc en 2 sitios (juez, catálogo de memoria); acá pasa a
POLÍTICA declarativa del chat. Ley de ausencia de la casa: sin match la
pieza es no-op (igual que el pre-filtro de contexto).

## 1. `utils/prefetch.py` — NUEVO (puro, sin LLM)

- Setting `PREFETCH` (default "1"); "0" apaga TODO.
- **v1: UNA regla** (la tabla es una LISTA de reglas para crecer, pero hoy
  entra una sola — no especular): `archivos_mencionados` — si la pregunta
  del usuario menciona RUTAS que existen dentro del perímetro
  (`AGENT_ALLOWED_DIRS` vía `utils.rutas`/`fs_tools` — reusar el resolvedor
  de contención que ya existe, NO reimplementar), pre-leer cada una (máx
  `PREFETCH_MAX_ARCHIVOS=2`) con las primeras líneas (máx
  `PREFETCH_MAX_LINEAS=80`).
- `def decidir(pregunta) -> list[tuple[path, contenido]]` PURA en su lógica
  de matching (regex de rutas `[\w./-]+\.[A-Za-z]{1,4}` sobre la pregunta,
  contención, existencia); I/O mínima (leer el archivo) pero JAMÁS lanza —
  error de lectura → esa ruta se salta.
- `def mensaje(prefetches) -> str | None`: el texto user-role con prefijo
  FIJO `[pre-fetch]` (patrón compacción): por cada archivo,
  `[pre-fetch] {path} (primeras {n} líneas):\n{contenido}`. None si no hay
  nada — sin match no hay mensaje (ley de ausencia).

## 2. `nodes.py` + `flow.py` — el nodo

- `class PreFetch(Node)`: `prep` = última pregunta (el último mensaje user
  del historial); `exec` = `decidir(...)`; `post` = si hay mensaje, lo
  APPENDEA a `shared["messages"]` como `{"role": "user", "content": ...}`
  (user tras user es legal para la API; NO rompe los invariantes —
  candado: `validar_historial` verde antes y después). Siempre devuelve
  "continue" (una arista, sin decisión).
- `flow.py`: `ask - "continue" >> prefetch >> router` (y en la rama sin
  router: `ask - "continue" >> prefetch >> step`). El nodo NO se pasa dos
  veces por la misma pregunta: corre una vez por mensaje user nuevo (está
  entre GetQuestion y el paso — la estructura del grafo ya lo garantiza).
- Terminal: si pre-fetchea, imprime `colorear(f"  [pre-fetch] {path}", "info")`
  por archivo (transparencia). Marcador banco: `"prefetch": r"\[pre-fetch\]"`
  + fixture real/negativo (template del código NO matchea — lección H2).

## 3. Interacción con el resto (leer antes de escribir)

- El mensaje `[pre-fetch]` entra ANTES de la decisión del router: el router
  lee `shared["messages"][-1]` — que pasaría a ser el MENSAJE PREFETCH, no
  la pregunta. FIX OBLIGATORIO: `LayaRouter.prep` debe tomar el último
  mensaje user que NO sea prefetch (saltear los que empiezan con el prefijo
  `[pre-fetch]`). Lo mismo `voto_confirmacion_router` (recibe la pregunta
  por parámetro — el llamador ya la tiene limpia si LayaRouter.prep la
  extrajo bien) y `utils/estado_sesion.recordar_usuario` (GetQuestion.post
  siembra la PREGUNTA — ya es limpio, no tocar).
- Compacción: el mensaje prefetch es un user normal del historial — la
  zona fría lo compacta como a cualquiera. OK.

## 4. Tests (`tests/test_prefetch.py` NUEVO)

1. `decidir`: pregunta con ruta existente del repo → 1 tupla con contenido;
   ruta inexistente → vacío; ruta FUERA del perímetro → vacío (contención);
   sin rutas → vacío; más de MAX rutas → recortada a MAX.
2. `mensaje`: forma del texto con prefijo, y None sin matches.
3. Nodo: shared con pregunta con archivo → post appendea el mensaje y
   devuelve "continue"; `validar_historial` verde antes y después; con
   PREFETCH=0 no toca el historial.
4. `LayaRouter.prep` con historial que termina en pregunta + prefetch →
   devuelve LA PREGUNTA (no el mensaje prefetch).
5. Marcador banco: positiva la línea real, negativo el template del código.

## 5. `.env.example`

Bloque PREFETCH / PREFETCH_MAX_ARCHIVOS / PREFETCH_MAX_LINEAS — dos líneas
de qué es y la ley de ausencia.

## Candado final

`python3 -m pytest tests/ -q` verde (hoy 392) y ruff. El A/B con banco lo
corre el conductor (escenarios ya en disco).
