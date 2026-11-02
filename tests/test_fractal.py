"""La división de un árbol del kernel, medida sobre su traza (X124)."""
import json
import math
from types import SimpleNamespace as NS

import pytest

from banco.probes import fractal
from utils.kernel import Ctx, Ledger, Tool, agente, correr

ARCHIVOS = ["a.py", "b.py", "c.py", "d.py"]


def _llamada(nombre, n, **args):
    return NS(id=f"{nombre}-{n}", function=NS(name=nombre, arguments=json.dumps(args)))


def _leer():
    esquema = {"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}
    return Tool("read_file", esquema, lambda llamada, ctx: "ok", "lectura")


def _arbol(reparto):
    """La raíz divide en una copia por pedido de `reparto`; cada copia lee los
    archivos de su pedido y responde."""
    def llm(mensajes, tools=None):
        pedido = mensajes[1]["content"]
        if any(m["role"] == "tool" for m in mensajes) or not tools:
            return NS(content="listo", tool_calls=None)
        if pedido == "todo":
            return NS(content=None, tool_calls=[_llamada("dividir", i, pedido=json.dumps(p))
                                                for i, p in enumerate(reparto)])
        archivos = json.loads(pedido)
        if not archivos:
            return NS(content="nada", tool_calls=None)
        return NS(content=None, tool_calls=[_llamada("read_file", i, path=a) for i, a in enumerate(archivos)])

    dividir = agente("dividir", "d", "s", [_leer()], recursivo=True)
    ctx = Ctx(llm, Ledger(20), max_profundidad=2)
    correr("s", "todo", [dividir], ctx, wait=0)
    return fractal.medir(ctx.traza, ["dividir"])


@pytest.mark.parametrize(("reparto", "d"), [
    ([ARCHIVOS[:2], ARCHIVOS[2:]], 1.0),                      # partes disjuntas que cubren: D = 1
    ([ARCHIVOS[:1], ARCHIVOS[1:2], ARCHIVOS[2:]], 1.0),       # asimétrico y disjunto: también D = 1
    ([ARCHIVOS[:3], ARCHIVOS[1:]], math.log(2) / math.log(4 / 3)),  # se solapan: D > 1
    ([ARCHIVOS, ARCHIVOS[:1]], math.inf),                     # una copia relee todo
])
def test_d_mide_si_las_copias_se_repartieron_el_alcance(reparto, d):
    """Ley 2 de P2: Σ rᵢᴰ = 1. El árbol asimétrico y disjunto da 1 igual que el
    simétrico: la forma es libre, lo que mide D es el solapamiento."""
    (raiz, valor), = _arbol(reparto)["divisiones"].items()
    assert raiz == () and valor == pytest.approx(d, rel=1e-6)


def test_las_fallas_topologicas_se_ven_en_la_traza():
    """DIG: una copia que no hizo nada y dos hermanas con el mismo pedido."""
    fallas = _arbol([ARCHIVOS[:2], ARCHIVOS[:2], []])["fallas"]
    assert [tipo for tipo, _ in fallas] == ["rama_vacia", "subproblema_repetido", "subproblema_repetido"]
    assert _arbol([ARCHIVOS[:2], ARCHIVOS[2:]])["fallas"] == []


def test_una_copia_que_delega_todo_en_otra_es_reruteo():
    traza = [(2, "read_file", ("1.x-0", "1.y-0", "1.r-0"), '{"path": "a.py"}'),
             (1, "dividir", ("1.x-0", "1.y-0"), '{"pedido": "a"}'),
             (0, "dividir", ("1.x-0",), '{"pedido": "a"}')]
    assert ("reruteo", ("1.x-0",)) in fractal.medir(traza, ["dividir"])["fallas"]


def test_ids_repetidos_entre_rondas_no_se_confunden():
    """Ataque al instrumento: el DSML numera los ids desde 0 en cada ronda.
    Dos copias en rondas distintas con el mismo id son dos ramas, no una."""
    def llm(mensajes, tools=None):
        pedido, rondas = mensajes[1]["content"], sum(1 for m in mensajes if m["role"] == "assistant")
        if pedido == "todo" and rondas < 2:
            return NS(content=None, tool_calls=[NS(id="dsml-0", function=NS(
                name="dividir", arguments=json.dumps({"pedido": json.dumps(ARCHIVOS[rondas * 2:rondas * 2 + 2])})))])
        if pedido != "todo" and rondas == 0:
            return NS(content=None, tool_calls=[NS(id="dsml-0", function=NS(
                name="read_file", arguments=json.dumps({"path": a}))) for a in json.loads(pedido)])
        return NS(content="listo", tool_calls=None)

    dividir = agente("dividir", "d", "s", [_leer()], recursivo=True)
    ctx = Ctx(llm, Ledger(20), max_profundidad=2)
    correr("s", "todo", [dividir], ctx, wait=0)
    medido = fractal.medir(ctx.traza, ["dividir"])
    assert medido == {"divisiones": {(): pytest.approx(1.0)}, "fallas": []}


def test_dimension_de_los_casos_borde():
    assert fractal.dimension([]) is None
    assert fractal.dimension([0.5]) == pytest.approx(0, abs=1e-6)       # una copia con la mitad: D = 0
    assert fractal.dimension([0.5, 0.5]) == pytest.approx(1)
    assert fractal.dimension([1 / 3] * 3) == pytest.approx(1)
