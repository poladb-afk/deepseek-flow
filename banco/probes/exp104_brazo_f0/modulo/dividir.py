"""exp/104, brazo F0: el esquema del `dividir` del exp/103, con implementación inerte.

El esquema se arma con el MISMO `agente()` y las MISMAS constantes del exp/103,
así que es el del exp/103 byte a byte (462 B en
`json.dumps(esquema, ensure_ascii=False)`): el brazo aísla el efecto del texto
del menú, no el loop fractal. Si el modelo llama a la tool, devuelve el error y
no ejecuta nada (el runner cuenta las llamadas como dato de validez).

Al salir deja, al lado de la corrida, `<corrida>-exp104.json` con las llamadas;
igual que en el exp/103, afuera del directorio de la corrida.
"""
import atexit
import json
import threading
from pathlib import Path

from utils.fs_tools import allowed_roots
from utils.kernel import agente, desde_fs

SYSTEM = ("Sos una copia del agente que te llamó. Resolvés la parte del pedido que te pasó "
          "con tools de solo lectura; tu mensaje final es tu resultado para quien te llamó.")
DESCRIPCION = ("Delega una parte autocontenida del pedido a una copia de este agente, con su "
               "propio contexto y las tools de solo lectura (read_file, list_files, search_files). "
               "La copia puede dividirse a su vez. Devuelve la respuesta de la copia.")

ESQUEMA = agente("dividir", DESCRIPCION, SYSTEM,
                 [desde_fs("read_file"), desde_fs("list_files"), desde_fs("search_files")],
                 recursivo=True).esquema
TOOLS = [ESQUEMA]
_LLAMADAS = []
_LOCK = threading.Lock()


def dividir(pedido=None, **_):
    """Inerte: registra la llamada y devuelve el error. No corre nada."""
    with _LOCK:
        _LLAMADAS.append(str(pedido or "")[:2000])
    return "ERROR: herramienta no disponible"


def ruta_registro(corrida):
    """El registro de llamadas cae al lado de la corrida, nunca adentro."""
    corrida = Path(corrida)
    return corrida.with_name(f"{corrida.name}-exp104.json")


def guardar(ruta=None):
    ruta = ruta or ruta_registro(allowed_roots()[0])
    datos = {"llamadas": len(_LLAMADAS), "pedidos": list(_LLAMADAS[:20])}
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False)
    return ruta


IMPL = {"dividir": dividir}
# Solo el chat del brazo lo importa como `modules.dividir` (el sitecustomize
# appendea `modulo/` a `modules.__path__`): importado con otro nombre no
# registra el guardado ni escribe fuera de la corrida.
if __name__ == "modules.dividir":
    atexit.register(guardar)
