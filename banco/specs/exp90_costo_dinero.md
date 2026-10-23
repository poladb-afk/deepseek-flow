# Spec de ejecución — exp/90: el costo en dinero (sesión y por pregunta)

**Estado:** aprobada 2026-10-23 (lote de "cosas chicas" del operador, tras el
inventario de pendientes). Es el follow-up que exp/89 dejó fuera de alcance.

## Pregunta

exp/89 hizo los tokens first-class (usage por llamada, evento `llm`, reporte
`[tokens]`) pero sin dinero el dato no decide nada: ¿cuánto cuesta una pregunta
del chat?, ¿la cirugía de la ventana caliente (deuda de fondo de exp/88) se
paga con lo que ahorra?, y —clave para esa decisión— ¿qué parte del historial
reenviado cada ronda es cache hit (DeepSeek lo activa solo, ~50× más barato)
y qué parte paga tarifa llena?

## Diseño (pre-registrado)

- **Desglose por modelo** al lado del acumulador de exp/89: `USO_POR_MODELO`
  con {llamadas, prompt, completion, cache_hit, cache_miss}. El modelo lo pasa
  CADA sitio de llamada (el que viajó en el request). Split de cache: si el
  usage trae `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens` se usan tal
  cual; si no (proveedor genérico, mocks), todo el prompt cuenta como
  cache_miss — techo conservador, nunca subestima.
- **Precios**: `utils/costos.py` PURO (sin env ni imports privados): tabla
  off-peak por 1M tokens al 2026-10-23 — deepseek-flash (0,003 hit / 0,15
  miss / 0,60 output), deepseek-v4-pro (0,022 / 0,66 / 1,98); deepseek-chat y
  deepseek-reasoner a precio Flash (la doc oficial factura los nombres legacy
  a precio Flash). Fuente: api-docs.deepseek.com (tabla JS; cruzada contra dos
  réplicas el mismo día). Pico (LU-VI 01:00–04:00 y 06:00–10:00 UTC) es
  exactamente el DOBLE: se cotiza off-peak y se declara. Override:
  `PRECIO_TOKENS` (JSON {modelo: [hit, miss, out]}); basura → aviso + defaults
  (patrón `_entero`).
- **Por pregunta**: `GetQuestion.post` snapshotea el desglose; la pregunta
  ANTERIOR se cierra con el delta cuando llega la siguiente (vuelve por
  "answer" → ask). La última la cierra el reporte de salida. El resumen de
  memoria del exit corre FUERA de toda pregunta: cuenta en el total de sesión
  y en ninguna pregunta (declarado, los totales pueden no sumar exacto).
- **Reporte** (misma línea de exp/89 + dinero): `[tokens] sesión: N llamadas —
  P prompt + C completion (~$X)` y debajo `[tokens] por pregunta: K — t1 / t2
  … tokens (~$ …)`; una línea por modelo solo si hubo más de uno. Modelo sin
  precio de lista: tokens sin `$` y el nombre a la vista.
- **Traza**: el evento `llm` NO cambia (pt/ct sin contenido, contrato F4).
  Sin modelo por llamada en la traza, evals no puede valorar en dinero
  (declarado; la columna de evals queda en tokens).

## Criterios

- **C1:** tests sin red — desglose por modelo desde el camino simple y el de
  streaming; split hit/miss cuando el usage lo trae y todo-miss cuando no;
  `precios` con defaults / override válido / basura (aviso y defaults);
  `delta_desglose` puro; `GetQuestion.post` cierra la pregunta anterior;
  `_reporte_tokens` imprime dinero y por pregunta con USO/USO_POR_MODELO
  falsos.
- **C2:** e2e mínimo: un turno real del chat imprime `~$` > 0 y la línea por
  pregunta.
- **C3:** gate verde (ruff 0.17.1 del pin; ratchet; inventario con los ids
  nuevos; `.env.example` con PRECIO_TOKENS — lo exige el test de deriva).
- **C4:** sin regresión de exp/89: `uso_de_sesion()` plano intacto, evento
  `llm` con la misma firma, los tres tests de exp/89 sin editar su contrato.

## Fuera de alcance (declarado)

Dinero en el informe de evals (la traza no lleva modelo), horario pico en
runtime (off-peak documentado), costo por ronda dentro de una pregunta,
presupuesto por tokens (recién con datos de uso real).

## Resultado (2026-10-23)

C1 ✅ (11 tests en test_costos.py + 3 en test_llm.py + 1 en test_chat_flujo.py;
los tres de exp/89 sin tocar). C2 ✅ e2e real ×2: `~$0.0001` por pregunta
directa (5.005 prompt + 3 completion) y `~$0.0000` en la segunda corrida con
cache caliente — mismos 5.004 tokens. C3 ✅ gate verde (906 passed + 3 skips;
tests_definidos 878→893, ratchet auto-rewritten; el par de tests de precios
inválidos parametrizado por el gate de test slop). C4 ✅ `uso_de_sesion()` y
el evento `llm` intactos. **Hallazgo:** los 5.009 tokens fijos de exp/89 son
system (328) + esquemas de las 30 tools — prefijo estable servido >93% como
cache hit en la segunda corrida. El argumento DINERO de la deuda de exp/88
queda más débil; quedan contexto, latencia y misses al expirar el cache.
Declarado: 3 filas de preguntas de test en el log orgánico (exp/71 spirit).
