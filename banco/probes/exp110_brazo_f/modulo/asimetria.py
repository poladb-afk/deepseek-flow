"""exp/110, brazo F: los tres hijos especialistas del chat (instrumento, no producto).

Pre-registro: `banco/specs/exp110_asimetria.md` (X148); contrato del montaje:
`salidas/exp110/montaje_contrato.md`. Aplica cuatro parches al proceso del chat:

1. **Menú**: `nodes.herramientas_de` devuelve las tools reales + los tres hijos.
2. **Ley 1**: `nodes.ActuarChat.post` cobra a `turno` el gasto de los hijos de
   la ronda —el chat deriva su saldo de `turno` (X140), así que sin esto la
   proyección del próximo `PasoChat.prep` lo perdería (desviación de
   instrumento declarada en el spec).
3. **Inventario del juez**: suma los tres nombres a `juez._inventario_tools()`;
   si no, un borrador que los mencione se lee como herramienta inventada (X135).
4. **Traza**: captura el `Ctx` del chat y al salir escribe, al lado del
   directorio de la corrida, `<corrida>-asimetria.json` para
   `banco/probes/exp110.py` (adopción, Ley 1 y la traza del árbol).

Fuera de `banco/probes/` no se toca nada: es instrumento, no producto, y el
brazo A corre sin este directorio en el `PYTHONPATH`.
"""
import atexit
import json
import threading
from pathlib import Path

from utils.fs_tools import allowed_roots
from utils.kernel import agente, desde_fs

SYSTEM_BARRIDO = ("Sos el hijo de barrido: recorrés el alcance y devolvés un índice de los "
                  "archivos relevantes, por ruta. No escribís ni ejecutás nada.")
SYSTEM_LECTURA = ("Sos el hijo de lectura: extraés hechos textuales de los archivos que te piden "
                  "y los devolvés con `ruta:línea`. No escribís ni ejecutás nada.")
SYSTEM_SINTESIS = ("Sos el hijo de síntesis: armás el borrador de una parte del informe con citas "
                   "verificables. No escribís ni ejecutás nada.")

HIJOS = [
    agente("barrido", "Explora el alcance de un pedido y devuelve un índice de rutas relevantes.",
           SYSTEM_BARRIDO, [desde_fs("list_files"), desde_fs("search_files")]),
    agente("lectura", "Extrae hechos textuales de archivos concretos y los devuelve con ruta:línea.",
           SYSTEM_LECTURA, [desde_fs("read_file")]),
    agente("sintesis", "Arma el borrador de una parte de un informe con citas verificables.",
           SYSTEM_SINTESIS, [desde_fs("read_file"), desde_fs("search_files")]),
]
NOMBRES = [hijo.nombre for hijo in HIJOS]
DELEGACIONES = dict.fromkeys(NOMBRES, 0)
_LOCK = threading.Lock()
_CTX = None
_INSTALADO = False


def _contar(hijo):
    """Envuelve `correr` del hijo para contar adopción por tool (con lock: las
    lecturas de una ronda corren en hilos)."""
    original = hijo.correr

    def correr(llamada, ctx):
        with _LOCK:
            DELEGACIONES[hijo.nombre] += 1
        return original(llamada, ctx)

    hijo.correr = correr


def _parchear_menu(nodes):
    original = nodes.herramientas_de

    def herramientas_de(shared):
        return original(shared) + HIJOS

    nodes.herramientas_de = herramientas_de


def _parchear_ley1(nodes):
    original = nodes.ActuarChat.post

    def post(self, shared, prep_res, exec_res):
        resultado = original(self, shared, prep_res, exec_res)
        actual = nodes.turno(shared)
        # Lo que gastaron los hijos de esta ronda entra en la fuente del chat
        # (turno) para que el saldo del árbol sea uno solo (Ley 1).
        actual["rondas"] = max(actual["rondas"],
                               nodes.presupuesto(shared) - self.ctx.ledger.rondas - 1)
        return resultado

    nodes.ActuarChat.post = post


def _parchear_juez():
    import juez

    original = juez._inventario_tools

    def _inventario_tools():
        return set(original()) | set(NOMBRES)

    juez._inventario_tools = _inventario_tools


def _parchear_ctx(nodes):
    original = nodes.PasoChat.__init__

    def init(self, ctx, tools, **kwargs):
        global _CTX
        original(self, ctx, tools, **kwargs)
        _CTX = ctx

    nodes.PasoChat.__init__ = init


def ruta_asimetria(corrida):
    """Dónde deja su archivo una corrida: al lado, nunca adentro."""
    corrida = Path(corrida)
    return corrida.with_name(f"{corrida.name}-asimetria.json")


def guardar(ruta=None):
    if _CTX is None:
        return None
    ruta = Path(ruta) if ruta else ruta_asimetria(allowed_roots()[0])
    datos = {
        "montado": True,
        "tools": list(NOMBRES),
        "delegaciones": dict(DELEGACIONES),
        "llamadas_llm": _CTX.ledger.llamadas,
        "saldo": _CTX.ledger.rondas,
        "traza": [list(entrada) for entrada in _CTX.traza],
    }
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False)
    return ruta


def instalar(nodes):
    """Aplica los cuatro parches una sola vez (lo llama el `sitecustomize`)."""
    global _INSTALADO
    if _INSTALADO:
        return
    for hijo in HIJOS:
        _contar(hijo)
    _parchear_menu(nodes)
    _parchear_ley1(nodes)
    _parchear_juez()
    _parchear_ctx(nodes)
    atexit.register(guardar)
    _INSTALADO = True
