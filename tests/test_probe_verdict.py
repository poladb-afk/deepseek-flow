"""Candado del probe del verdict (banco/probes/verdict_juez.py).

Fix de la revisión: el probe COPIABA el contrato (`VERDICTS_VALIDOS`) en vez
de importarlo — el candado del repo dice que los contratos existentes se
importan, no se copian. Y ya había derivado en las DOS direcciones: aceptaba
un `problems` que no es lista (producción lo rechaza) y rechazaba la
canonicalización str/strip/lower (producción la acepta).

Los esperados de CASOS son literales del contrato (fuente independiente): no
se recalculan con la misma llamada que el probe hace, que sería tautológico.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from banco.probes import verdict_juez as vj  # noqa: E402

# (crudo del Judge, ¿producción lo acepta?, etiqueta esperada del probe)
CASOS = [
    ("```yaml\nverdict: ok\n```", True, "ok"),
    ("```yaml\nverdict: retry\n```", True, "retry"),
    ("```yaml\nverdict: ' OK '\n```", True, "ok"),
    ("```yaml\nverdict: needs_changes\n```", False, None),
    ('```yaml\nverdict: ok\nproblems: "no es lista"\n```', False, None),
]


def test_probe_verdict_usa_el_contrato_de_produccion():
    """El probe clasifica con el mismo contrato que producción: los dos casos
    que la copia local acertaba mal (canonicalización y `problems` no-lista)
    quedan clavados acá."""
    for crudo, esperado, shape in CASOS:
        info = vj.clasificar(crudo)
        assert info["valido"] is esperado, f"{crudo!r} -> {info}"
        if shape is not None:
            assert info["shape"] == shape, f"{crudo!r} -> {info}"
