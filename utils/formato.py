"""Formato de números para los informes markdown (una sola fuente).

Estaba copiado en cuatro piezas de la CLI. La versión de `triaje_trazas`
formatea un valor que YA viene en porcentaje (73.4 → "73.4%"): vive ahí con
otro nombre porque su unidad es distinta; `pct` recibe la fracción.
"""


def pct(fraccion):
    """Una fracción (0.734) como porcentaje legible ("73.4%"); None → "—"."""
    return f"{fraccion * 100:.1f}%" if fraccion is not None else "—"
