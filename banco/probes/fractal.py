"""La división de un árbol del kernel, medida sobre su traza (P2 Ley 2 y P4).

Sin LLM ni red: lee `Ctx.traza` (profundidad, tool, dirección, argumentos).
La dirección es el camino de ids de tool call desde la raíz, así que una copia
es la llamada cuyo id prefija las llamadas de otras.

- **Alcance** de un nodo: las rutas (`path` de los argumentos) que leen él y
  todas sus copias.
- **D** de un nodo que se dividió: la solución de Σ rᵢᴰ = 1 (ecuación de
  Moran), con rᵢ = |alcance de la copia i| / |alcance del nodo|. D ≈ 1: las
  copias se repartieron el alcance; D > 1: lo releyeron; D < 1: el nodo leyó
  parte por su cuenta. Una copia con todo el alcance del padre da D infinito.
- **Fallas topológicas** (las de DIG, arXiv 2603.00309, que se ven en una
  traza): `rama_vacia` (una copia que no hizo nada: terminó antes de empezar),
  `subproblema_repetido` (dos copias hermanas con el mismo pedido) y
  `reruteo` (una copia que delegó todo en una sola copia sin leer nada).
  La terminación faltante no se ve acá: el saldo la impide (Ley 1). Una
  copia rechazada (sin saldo o en la profundidad máxima) también queda como
  `rama_vacia`: para DIG es una terminación temprana, y el saldo la explica.
"""
import json
import math


def _rutas(argumentos):
    try:
        args = json.loads(argumentos or "{}")
    except (ValueError, TypeError):
        return set()
    ruta = args.get("path") if isinstance(args, dict) else None
    return {ruta} if isinstance(ruta, str) and ruta else set()


def arbol(traza, agentes):
    """{dirección: {"tool", "args", "hijos": [direcciones de copias], "propias": int}}
    para la raíz `()` y cada llamada a una tool de `agentes`."""
    nodos = {(): {"tool": None, "args": "", "hijos": [], "propias": 0}}
    for _, tool, direccion, args in traza:
        if tool in agentes:
            nodos.setdefault(direccion, {"hijos": [], "propias": 0})
            nodos[direccion].update(tool=tool, args=args)
    for _, tool, direccion, _ in traza:
        padre = direccion[:-1]
        if tool in agentes:
            nodos[padre]["hijos"].append(direccion)
        else:
            nodos[padre]["propias"] += 1
    return nodos


def alcance(traza, direccion):
    """Las rutas que leen el nodo y sus copias."""
    n = len(direccion)
    return set().union(*(_rutas(a) for _, _, d, a in traza if d[:n] == direccion and len(d) > n))


def dimension(fracciones, tolerancia=1e-9):
    """D tal que Σ rᵢᴰ = 1. Infinito si una copia tiene todo el alcance."""
    rs = [r for r in fracciones if r > 0]
    if not rs:
        return None
    if any(r >= 1 for r in rs):
        return math.inf
    bajo, alto = 0.0, 1.0
    while sum(r ** alto for r in rs) > 1:  # Σ rᴰ baja con D: se acota arriba
        alto *= 2
    while alto - bajo > tolerancia:
        medio = (bajo + alto) / 2
        bajo, alto = (medio, alto) if sum(r ** medio for r in rs) > 1 else (bajo, medio)
    return (bajo + alto) / 2


def medir(traza, agentes):
    """La división de cada nodo que se dividió y las fallas del árbol."""
    nodos = arbol(traza, set(agentes))
    divisiones, fallas = {}, []
    for direccion, nodo in nodos.items():
        total = alcance(traza, direccion)
        hijos = nodo["hijos"]
        if hijos and total:
            divisiones[direccion] = dimension([len(alcance(traza, h)) / len(total) for h in hijos])
        if direccion and not hijos and not nodo["propias"]:
            fallas.append(("rama_vacia", direccion))
        if direccion and len(hijos) == 1 and not nodo["propias"]:
            fallas.append(("reruteo", direccion))
        pedidos = [nodos[h]["args"] for h in hijos]
        fallas += [("subproblema_repetido", h) for h, p in zip(hijos, pedidos, strict=True)
                   if pedidos.count(p) > 1]
    return {"divisiones": divisiones, "fallas": sorted(fallas)}
