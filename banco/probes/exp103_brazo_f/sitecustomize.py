"""exp/103, brazo F: monta `dividir` en el chat sin tocar `modules/`.

Los módulos se descubren por archivo: uno en `modules/` les daría `dividir`
también a A y A+. El brazo F pone este directorio en PYTHONPATH y Python corre
este archivo al arrancar; solo en el proceso del chat (`main.py` del repo)
suma `modulo/` al paquete `modules`. Los demás procesos que hereden el
entorno (los scripts y el pytest de los fixtures) no cambian.
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
