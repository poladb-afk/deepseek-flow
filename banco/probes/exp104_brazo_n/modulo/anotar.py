"""exp/104, brazo N: control de "una tool más del mismo tamaño" (465 B).

`anotar` guarda una nota en un registro de la sesión que NO vuelve al contexto.
La descripción es la fija del pre-registro y no habla de delegar, dividir ni de
otro agente: lo único que aporta al menú es un esquema de tamaño comparable al
de `dividir` (462 B; 465/462 = 1,006). Si el modelo la llama, confirma y no
ejecuta nada más.

Al salir deja, al lado de la corrida, `<corrida>-exp104.json` con las llamadas.
"""
import atexit
import json
import threading
from pathlib import Path

from utils.fs_tools import allowed_roots

DESCRIPCION = ("Guarda una nota de texto libre en el registro de esta sesión y devuelve una "
               "confirmación. No lee, no busca ni modifica archivos, y no ejecuta nada. La "
               "nota no vuelve al contexto: solo queda registrada para quien revise la "
               "sesión después.")
ESQUEMA = {
    "type": "function",
    "function": {
        "name": "anotar",
        "description": DESCRIPCION,
        "parameters": {
            "type": "object",
            "required": ["nota"],
            "properties": {"nota": {"type": "string",
                                    "description": "La nota a registrar en texto libre"}},
        },
    },
}
TOOLS = [ESQUEMA]
_NOTAS = []
_LOCK = threading.Lock()


def anotar(nota=""):
    """Inerte: registra la nota en memoria y confirma, sin volver al contexto."""
    with _LOCK:
        _NOTAS.append(str(nota or "")[:2000])
    return "Nota registrada."


def ruta_registro(corrida):
    """El registro de notas cae al lado de la corrida, nunca adentro."""
    corrida = Path(corrida)
    return corrida.with_name(f"{corrida.name}-exp104.json")


def guardar(ruta=None):
    ruta = ruta or ruta_registro(allowed_roots()[0])
    datos = {"llamadas": len(_NOTAS), "notas": list(_NOTAS[:20])}
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False)
    return ruta


IMPL = {"anotar": anotar}
if __name__ == "modules.anotar":
    atexit.register(guardar)
