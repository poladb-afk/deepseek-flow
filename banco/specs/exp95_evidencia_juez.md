# Spec de ejecución — exp/95: la evidencia del juez también se verifica

**Estado:** aprobada 2026-10-23 (operador: "avancemos" — meta-loop permanente).
El caso que la motiva está medido y documentado: en el re-juicio de exp/92 el
juez REFUTÓ con un fraude cuya evidencia citaba código que NO EXISTE
(`if tok in flags: return True` — el matcher real siempre tuvo el chequeo de
`=`). El operador lo desarmó verificando empíricamente; sin ese paso, se
habría "corregido" código correcto. La ironía es el argumento: el método fable
dice "un reporte es claims, no evidencia" — la evidencia del PROPIO juez hoy
se toma al pie de la letra.

## Pregunta

¿Una capa determinística que verifique las CITAS de la evidencia de cada
fraude contra los materiales que el juicio vio — y marque las que no matchean
— hace al veredicto seguro de ejecutar sin chequeo manual?

## Diseño (pre-registrado; lo implementa el chat en sesión shadow)

- **Función PURA** `verificar_evidencia(fraudes, materiales)` en
  `fable_judge.py`:
  - De la `evidencia` de cada fraude se extraen los spans entre backticks
    (`...`) — el formato que el propio juez usa cuando cita código, flags,
    funciones, comandos.
  - Cada span se busca en `materiales` (el corpus que el juicio vio: diff +
    contenido de archivos nuevos + fuentes + reporte + salidas de las
    re-ejecuciones), con normalización de espacios (una cita con otro
    espaciado sigue siendo una cita).
  - Un fraude con algún span que no aparece en ningún material queda MARCADO:
    `evidencia no verificada`. Sin spans (prosa pura) no se marca — no hay
    nada que verificar y el ruido cuesta más que la señal.
- **La marca es informativa, no compuerta**: el veredicto NO cambia por la
  marca (un fraude con evidencia no verificada puede ser verdadero — el
  operador decide con el dato a la vista, mismo espíritu que
  `resuelto_por_nombre` en `utils/citas.py`).
- **Cableado**: corre en el paso determinista (Verdictar o donde el flujo
  tenga el juicio Y los materiales a mano); la tabla de fraudes del veredicto
  muestra la marca por fila.
- Declarado: no se verifica prosa sin comillas; no se toca el prompt de
  juicio ni la compuerta.

## Criterios

- **C1 (tests puros):** span presente en el diff → sin marca; span inventado
  (el caso exp/92 textual) → marcado; cita con espaciado distinto matchea;
  múltiples fraudes con marcado mixto; prosa sin spans no se marca; sin
  fraudes → no-op.
- **C2 (flujo con LLM mockeado):** un juicio que devuelve un fraude con
  evidencia fabricada produce un veredicto cuya tabla muestra la marca — y
  el VEREDICTO no cambia por la marca.
- **C3 (e2e, auditor):** una corrida real del juez sobre un diff real muestra
  el estado de verificación por fraude en la salida (barata desde exp/94:
  ~7,7k tokens).
- **C4:** gate verde (auditor, shell limpia).
- **C5 (meta):** sesión shadow con origen terminal — par #4 de la flywheel.

## Fuera de alcance (declarado)

Cambiar el veredicto por la marca, verificar prosa sin comillas, extraer
spans de otros formatos (indentación, comillas simples), tocar la allowlist
de re-ejecución, el prompt de juicio.

## Resultado (2026-10-23)

C1 ✅ (spans presentes sin marca; el caso textual de exp/92 marcado; espaciado
normalizado; mixtos; prosa sin spans; sin fraudes no-op — más un test de
consistencia prompt↔corpus). C2 ✅ (LLM mockeado: cita inventada
`cleanup_db.py` → "evidencia NO verificada" visible y el veredicto NO cambia;
la compuerta sigue forzando REFUTED con verificación fallida). C3 ✅ con una
vuelta inesperada: la corrida real usó el reporte VIEJO de exp/92 contra el
diff NUEVO de exp/95 — el juez refutó con precisión la deriva reporte↔diff
(84 vs 66 passed; "el reporte describe fix 1/fix 2 pero el diff no los
contiene"; scope creep real), y las 4 evidencias genuinas quedaron SIN marca:
cero falsos positivos sobre evidencia real. C4 ✅ gate verde desde shell
limpia (934 passed + 3 skips — confirma que los 3 fallos que vio la sesión
eran su propia contaminación de entorno). C5 ✅ TRES pares (#4, #5, #6 — la
spec contaba uno): la tarea necesitó tres sesiones.

Sesiones: (1) plan sin código (39 rondas de exploración, 11/11 citas); (2) la
pieza pura + compuerta — dos RECHAZOS del supervisor evitaron daño real: un
edit que quitaba el `"veredicto": "refuted"` forzado de la compuerta (regresión
F1/exp/87) y, tras el rechazo, la reestructura correcta (verificación en la
rama de paso, forzado intacto); (3) corpus con los MISMOS recortes del prompt
(helper compartido `_reporte_prompt`), marcado por fila en el veredicto y los
tests. El diseño de marca informativa (no compuerta) se mantuvo en las tres.
