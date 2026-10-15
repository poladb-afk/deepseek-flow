# exp/49b — HITL web multi-pendiente: dos aprobaciones en paralelo (factor 7, fase B)

Corte pendiente de exp/47: "dos HITL en paralelo sin bloqueo". Hoy
`utils/hitl_web.py` acepta UN pedido a la vez (`threading.Event` único,
puerto fijo 8765): dos procesos del chat pelean el puerto y dentro de un
proceso un segundo pedido espera al primero. La arista formal `AskHuman`
queda diferida (la sustancia durable ya está en exp/49; ceremonia hasta que
duela — decisión del conductor documentada).

## 1. `utils/hitl_web.py` — pendientes MÚLTIPLES + puerto elástico

- El server mantiene un DICT de pendientes: `token → {titulo, cuerpo,
  evento}` — cada pedido con SU `threading.Event` y SU resultado. `aprobar(titulo,
  cuerpo)` crea un token (uuid4().hex[:8] o contador atómico), registra el
  pendiente, imprime la URL CON token y espera SOLO su evento (timeout
  `HITL_WEB_TIMEOUT` → False, default seguro de siempre).
- `GET /` lista TODOS los pendientes (cada uno con su título, `<pre>` del
  cuerpo y DOS forms Aprobar/Rechazar que postean a `/decision?token=…`);
  `POST /decision?token=…&respuesta=s|n` resuelve SOLO ese (evento.set con
  el veredicto). Token desconocido/expirado → 404 claro.
- **Puerto elástico**: si 8765 está ocupado (Otro proceso), probar
  8766..8765+5; si ninguno, degradar a False como hoy (nunca romper la
  acción). La URL efectiva se imprime UNA vez por server.
- Solo stdlib (http.server + threading), como siempre. Un solo server
  perezoso POR PROCESO; los pendientes son cross-hilo dentro del proceso.

## 2. Compatibilidad

- La firma `aprobar(titulo, cuerpo) -> bool` NO cambia (los módulos
  escritura/coding no se tocan). El timeout y el default seguro idénticos.
- `utils/aprobaciones.py` (historial) no cambia.

## 3. Tests (`tests/test_hitl_web.py` NUEVO o append donde vivan los de
hitl_web; sin red real: server en un hilo con puerto 0… NO — puerto fijo
alto de test, o mejor: probar el DICT/endpoint con el server real levantado
en 127.0.0.1:0 no sirve para el POST; usar un puerto libre elegido por el
test con socket bind provisional. Estilo de los tests de a2a: http.server
real en hilo, requests contra él.)

1. Dos `aprobar` en dos hilos → ambos pendientes listados en `GET /`;
   `POST /decision` del token A no resuelve el B (el B sigue esperando) y
   sí el A con el veredicto correcto.
2. Token desconocido → 404; timeout → False.
3. Puerto ocupado: levantar un socket en el puerto base → el server arranca
   en base+1 (verificar el puerto efectivo).

## 4. `.env.example`

Dos líneas en el bloque HITL web: múltiples pedidos simultáneos listados en
una sola página; si el puerto está ocupado prueba los siguientes (URL
impresa).

## Candado final

pytest verde (hoy 403) y ruff. El E2E con dos chats reales en paralelo lo
corre el conductor.
