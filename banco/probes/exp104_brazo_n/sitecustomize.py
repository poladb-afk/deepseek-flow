"""exp/104, montaje del brazo: monta su tool inerte en el chat sin tocar `modules/`.

Es el montaje del exp/103 (`5e8c792`) tal cual, con una copia por brazo: cada
brazo pone SU directorio en PYTHONPATH y Python corre este archivo al arrancar;
solo en el proceso del chat (`main.py` del repo) suma `modulo/` al paquete
`modules`. Los demás procesos que hereden el entorno (los scripts y el pytest
de los fixtures) no cambian. Así la tool de un brazo no se ve en el otro ni en
A, sin settings nuevos.
"""
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]


def montar(argv):
    """True si `argv` es el chat del repo y quedó montado `modulo/`."""
    if not argv or Path(argv[0]).resolve() != RAIZ / "main.py":
        return False
    if str(RAIZ) not in sys.path:
        sys.path.insert(0, str(RAIZ))  # el directorio del script todavía no está en sys.path
    import modules

    if str(AQUI / "modulo") not in modules.__path__:
        modules.__path__.append(str(AQUI / "modulo"))
    return True


montar(getattr(sys, "argv", None))
