"""exp/110, brazo F: monta los tres hijos especialistas en el chat (instrumento).

Mismo patrón que `exp103_brazo_f/sitecustomize.py`: el env del brazo F pone este
directorio en `PYTHONPATH`; Python corre este archivo al arrancar y solo en el
proceso del chat (`main.py` del repo) importa `nodes` COMPLETO —así `discover()`
ya corrió y los parches no se pierden—, suma `modulo/` a `sys.path` e instala
`asimetria.instalar(nodes)`. El brazo A corre sin este `PYTHONPATH`: no ve ni
los hijos ni los parches.

Contrato: `salidas/exp110/montaje_contrato.md`; pre-registro:
`banco/specs/exp110_asimetria.md` (X148). Nada de producto se toca.
"""
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]


def montar(argv):
    """True si `argv` es el chat del repo y quedó montado el instrumento."""
    if not argv or Path(argv[0]).resolve() != RAIZ / "main.py":
        return False
    if str(RAIZ) not in sys.path:
        sys.path.insert(0, str(RAIZ))  # el directorio del script todavía no está en sys.path
    import nodes  # el producto completo primero: discover() ya corrió

    if str(AQUI / "modulo") not in sys.path:
        sys.path.insert(0, str(AQUI / "modulo"))
    import asimetria  # pyright: ignore[reportMissingImports]  (vive en modulo/, sumado a sys.path acá)

    asimetria.instalar(nodes)
    return True


montar(getattr(sys, "argv", None))
