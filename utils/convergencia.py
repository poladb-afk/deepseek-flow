"""Convergencia textual: ¿la ronda nueva aportó material nuevo?

`seco` es la pieza PURA de exp/96: dado el texto de los hechos de una ronda
y el de la anterior, dice si el segundo no agregó nada. Cero dependencias
fuera de stdlib (difflib) — la aritmética de strings ya alcanza y así la
telemetría del supervisor no arrastra nada.

El umbral es de RATIO de difflib, no de tokens: dos textos distintos en el
detalle pero con la misma forma (mismo listado, distinto número) dan ratio
alto y cuentan como secos. Es deliberado — lo que se mide es si el loop
aprendió algo, no si cambió un dígito.
"""
import difflib

UMBRAL_SECO = 0.95


def normalizar(texto):
    """Colapsa todos los espacios (y saltos de línea) a uno solo."""
    return " ".join((texto or "").split())


def seco(a, b, umbral=UMBRAL_SECO):
    """True si `b` no aporta nada nuevo sobre `a`.

    Iguales tras normalizar espacios → True. Si no, ratio de similitud de
    difflib >= umbral. Dos vacíos son iguales (True): no hay material nuevo.

    >>> seco("leyó a.py", "  leyó   a.py ")
    True
    >>> seco("leyó a.py", "borró b.py")
    False
    """
    na, nb = normalizar(a), normalizar(b)
    if na == nb:
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= umbral
