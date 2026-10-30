"""Votación por mayoría: la mecánica genérica del 2-de-3 (y N-de-M).

El patrón majority-vote del cookbook, en su parte contable — quién
orquesta los votos (el supervisor: DeepSeek×2 con framing distinto +
Laya crudo) es quien llama. Leyes: mayoría = minimo votos coincidentes
(piso ABSOLUTO, default 2; NO es la mitad proporcional del total: con 5
votos, 2 coincidentes ya cuentan como mayoría); sin mayoría gana el desempate
(una convención explícita, nunca un azar). SIN desempate pasado, el
fallback es el más votado — que con todos los votos distintos es el
PRIMERO en aparecer (orden de inserción de Counter): determinista, pero
convención del llamador. En producción siempre se pasa desempate
(supervisor.py y banco/probes/sonda_supervisor.py pasan el voto directo).
"""
from collections import Counter


def mayoria(votos, desempate=None, minimo=2):
    """La opción con `minimo` votos coincidentes; sin ella, el desempate.

    >>> mayoria(["sql", "sql", "finish"])
    'sql'
    >>> mayoria(["sql", "db_schema", "finish"], desempate="sql")
    'sql'
    """
    conteo = Counter(votos)
    if not conteo:
        return desempate
    (opcion, n), *resto = conteo.most_common()
    empate = bool(resto) and resto[0][1] == n
    if n >= minimo and not empate:
        return opcion
    return desempate if desempate is not None else opcion
