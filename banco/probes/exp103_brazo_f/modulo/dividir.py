"""exp/103, brazo F: el agente se divide (pre-registro: banco/specs/exp103_fractal.md).

`dividir` es `agente(recursivo=True)` del kernel con las tres tools de lectura
del CORE (`desde_fs`: pasan por `run_tool_call`, con su contención de rutas).
Un `Ledger` por proceso, y el bench corre una pregunta por proceso: todas las
llamadas a `dividir` de la corrida y todas sus copias gastan de los mismos 8
(cada ronda y cada copia, X119). La descripción dice qué hace, no cuándo
conviene (N2, N3).

Al salir deja, al lado del directorio de la corrida (la primera raíz
permitida: el bench da una por corrida), `<corrida>-dividir.json` con cuántas
veces se llamó, el saldo y la traza del árbol, para `banco/probes/fractal.py`.
Afuera de la corrida a propósito: adentro contaría como un archivo que creó
el agente. Sin setting propio. Las lecturas del chat mismo no están en
esa traza: el chat no corre sobre el kernel (S9b).
"""
import atexit
import json
import threading
from pathlib import Path

from utils.call_llm import call_llm_agent
from utils.fs_tools import allowed_roots
from utils.kernel import Ctx, Ledger, agente, desde_fs

SALDO = 8
MAX_PROFUNDIDAD = 2
SYSTEM = ("Sos una copia del agente que te llamó. Resolvés la parte del pedido que te pasó "
          "con tools de solo lectura; tu mensaje final es tu resultado para quien te llamó.")
DESCRIPCION = ("Delega una parte autocontenida del pedido a una copia de este agente, con su "
               "propio contexto y las tools de solo lectura (read_file, list_files, search_files). "
               "La copia puede dividirse a su vez. Devuelve la respuesta de la copia.")

_DIVIDIR = agente("dividir", DESCRIPCION, SYSTEM,
                  [desde_fs("read_file"), desde_fs("list_files"), desde_fs("search_files")], recursivo=True)
CTX = Ctx(lambda mensajes, tools: call_llm_agent(mensajes, tools=tools), Ledger(SALDO),
          max_profundidad=MAX_PROFUNDIDAD)
_LLAMADAS = []
_LOCK = threading.Lock()

TOOLS = [_DIVIDIR.esquema]


def dividir(pedido):
    with _LOCK:
        _LLAMADAS.append(pedido)
        paso = f"chat.{len(_LLAMADAS)}"
    argumentos = json.dumps({"pedido": pedido}, ensure_ascii=False)
    CTX.traza.append((0, "dividir", (paso,), argumentos))
    return _DIVIDIR.correr({"id": paso, "paso": paso,
                            "function": {"name": "dividir", "arguments": argumentos}}, CTX)


def ruta_arbol(corrida):
    """Dónde deja la traza una corrida: al lado, nunca adentro."""
    corrida = Path(corrida)
    return corrida.with_name(f"{corrida.name}-dividir.json")


def guardar(ruta=None):
    ruta = ruta or ruta_arbol(allowed_roots()[0])
    datos = {"llamadas_dividir": len(_LLAMADAS), "saldo": CTX.ledger.rondas,
             "llamadas_llm": CTX.ledger.llamadas, "traza": [list(e) for e in CTX.traza]}
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False)
    return ruta


IMPL = {"dividir": dividir}
# Solo el chat F lo importa como `modules.dividir` (el sitecustomize appendea
# `modulo/` a `modules.__path__`). Importado con otro nombre —un test, un
# script— no registra el guardado: si no, al salir escribiría el árbol junto a
# la primera raíz permitida, fuera de la corrida.
if __name__ == "modules.dividir":
    atexit.register(guardar)
