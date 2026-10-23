"""Costo en dinero del uso de tokens (exp/90) — CÓDIGO PURO, sin env ni red.

El reporte que usa esta tabla cotiza OFF-PEAK y con `~`: en horario pico
(LU-VI 01:00–04:00 y 06:00–10:00 UTC) la tabla oficial cobra exactamente el
doble. No se cotiza por reloj a propósito — sería precisión falsa: cambia la
franja, el modelo o la tabla y el número miente igual; el orden de magnitud
es lo que tiene que decidir el operador.

El split de cache importa acá: DeepSeek activa el cache de contexto solo, y
el historial que el chat reenvía cada ronda (la señal de exp/88) paga la
tarifa hit (~50× menos que miss) cuando el proveedor la reporta. Sin split
reportado, `_contabilizar` ya contó todo el prompt como miss: techo
conservador, nunca subestima.
"""

import json

# (cache hit, cache miss, completion) USD por 1M tokens, OFF-PEAK, al
# 2026-10-23. Fuente: api-docs.deepseek.com/quick_start/pricing (la tabla se
# renderiza por JS; verificada el mismo día contra costgoat.com y
# activepieces.com). deepseek-chat y deepseek-reasoner son nombres legacy
# que la propia documentación factura a precio Flash.
PRECIOS_MILLON = {
    "deepseek-flash": (0.003, 0.15, 0.60),
    "deepseek-chat": (0.003, 0.15, 0.60),
    "deepseek-reasoner": (0.003, 0.15, 0.60),
    "deepseek-v4-pro": (0.022, 0.66, 1.98),
}


def precios(override=None):
    """La tabla de precios, pisada por `override` (JSON {modelo:
    [hit, miss, completion]} por 1M — el setting PRECIO_TOKENS). Basura o
    forma equivocada → aviso y defaults: un .env mal tipeado no puede tumbar
    el reporte (mismo criterio que `_entero`). PURA: el setting lo lee el
    llamador."""
    tabla = dict(PRECIOS_MILLON)
    if not override:
        return tabla
    try:
        crudo = json.loads(override)
        pares = {}
        for modelo, valores in crudo.items():
            hit, miss, salida = (float(v) for v in valores)
            pares[str(modelo)] = (hit, miss, salida)
    except (ValueError, TypeError, AttributeError):
        print("  [config] PRECIO_TOKENS no es {modelo: [hit, miss, "
              "completion]} válido → uso los precios por default")
        return tabla
    tabla.update(pares)
    return tabla


def costo_desglose(desglose, tabla=None):
    """(USD, modelos_sin_tarifa) de un desglose por modelo. Los modelos sin
    tarifa no suman y se devuelven aparte: el reporte los muestra sin $ en
    vez de mentir con un número."""
    tabla = tabla if tabla is not None else PRECIOS_MILLON
    total = 0.0
    sin_tarifa = [m for m in desglose if m not in tabla]
    for modelo, fila in desglose.items():
        if modelo not in tabla:
            continue
        hit, miss, salida = tabla[modelo]
        total += (fila["cache_hit"] * hit + fila["cache_miss"] * miss
                  + fila["completion"] * salida) / 1_000_000
    return total, sin_tarifa


def delta_desglose(inicio, actual):
    """El uso ENTRE dos snapshots por modelo — cierra una pregunta: lo que
    costó desde que se hizo hasta que se respondió. PURA.

    Clamp en 0: el acumulador es por PROCESO; tras un resume el snapshot
    rehidratado puede ser más grande que el acumulador nuevo (arrancó de
    cero) y el delta daría negativo — un costo negativo es siempre ruido."""
    delta = {}
    for modelo, fila in actual.items():
        previo = inicio.get(modelo) or {}
        delta[modelo] = {k: max(0, v - previo.get(k, 0)) for k, v in fila.items()}
    return delta
