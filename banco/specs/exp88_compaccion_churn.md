# Spec de ejecución — exp/88: la compacción rodante no puede escupir respaldos por ronda

**Estado:** ejecutada el 2026-10-22; C1-C3 OK. Evidencia: la sesión real del operador
(`salidas/threads/20261022_170938_47360.jsonl`: 19 compacciones, 19 respaldos en `memoria/`,
contexto estable en 60–75k, kill del usuario en la ronda 5/8).

## Diagnóstico (medido en esa sesión)

Con la ventana caliente sola por encima de `COMPACTION_CHARS`, compactar la zona fría no puede
bajar el total: cada ronda envejece 3–4 mensajes (resultados de tools grandes — read_file de
archivos enteros), la huella cambia, la compacción dispara de nuevo y funciona como **ventana
rodante**: el contexto queda acotado (~62–75k en vez de crecer libre) PERO:

- **Cada disparo escribió un respaldo de la zona fría en `memoria/`** — 19 archivos en ~5
  minutos (la dedupe de X37 solo salta zonas idénticas; las rodantes siempre difieren). Es la
  enfermedad de X37 (143 respaldos) recreada por otra puerta.
- El operador no tiene señal de POR QUÉ el contexto no baja: la masa está en la ventana
  caliente y ningún aviso lo dice.

`deep_research` NO es el causista: devuelve ruta + instrucción de leer por read_file (el
informe va a disco). La masa son resultados de `read_file` de archivos enteros acumulados en
los últimos mensajes.

## Fixes (cada uno con test)

- **F1 — respaldo solo de lo irrecuperable**: `_respaldar_zona_fria` NO escribe cuando la zona
  fría no contiene NINGÚN mensaje `user` (solo assistant/tool): los resultados de tools se
  re-obtienen re-corriendo la tool y la prosa del asistente es derivada; lo irrecuperable es lo
  que escribió el usuario. La primera compacción de una conversación larga (que sí contiene
  preguntas viejas) se respalda como siempre (A17 intacto para lo que importa). El marcador
  sigue siendo honesto: solo promete respaldo si existe.
- **F2 — el diagnóstico visible**: cuando tras compactar el historial resultante SIGUE por
  encima del tope, se imprime UNA vez por sesión `[compacción] la ventana caliente sola supera
  el tope (N chars): la compacción no puede bajarlo — recortá lecturas o subí
  COMPACTION_CHARS`. Sin este aviso, el operador ve el marcador repetirse sin entender.

## Fuera de alcance (declarado)

Recortar los resultados de tools VIEJOS dentro de la ventana caliente (la solución de fondo al
costo de contexto: trae riesgo de romper los invariantes assistant+tools y no lo pide el
defecto reportado); cap nuevo a read_file; cambiar VENTANA_DEFAULT.

## Criterios

- **C1:** tests sin LLM: zona fría sin mensajes user → `guardar_nota` NO se llama; con
  mensaje user → se llama (A17 preservado); el aviso de F2 sale una vez y no por ronda.
- **C2:** simulación determinista de la sesión del operador (historial sintético con tool
  results grandes, varias rondas de prep): respaldos escritos = solo los de zonas con user;
  el marcador de compacción puede aparecer por ronda (es la ventana rodante funcionando) pero
  `memoria/` no crece por ella.
- **C3:** gate verde.


## Resultado (2026-10-22)

C1 ✅ (zona sin user no llama a guardar_nota; con user sí — A17 intacto; el
aviso sale una vez); C2 ✅ (la simulación de la sesión: 3 rondas de prep con
tools gigantes → 0 respaldos, 1 aviso); C3 ✅ gate verde (888 tests). El
ratchet de anidación cazó el primer intento (el aviso sumaba un nivel en
AgentStep.prep) y se extrajo a helper — la unión del gate funcionó como
diseño. Deuda declarada: recortar tool results VIEJOS de la ventana caliente
(la solución de fondo al costo de contexto).
