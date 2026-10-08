"""Guard: ningún grafo termina en vacío (exp/39).

Recorre los flujos REALES del registro de utils/viz.py y falla si algún nodo
puede devolver una acción que no tiene arista — la clase de bug que cerraba el
chat en silencio ("Flow ends: X not found", medido con el router de Laya).
Revisa también debate y rag, que se construyen inline y no están en el
registro, contra su propio fuente.

Terminales permitidos: un nodo sin aristas solo si está en TERMINALES.
Agregar uno nuevo pasa a ser una decisión explícita, no un accidente.
"""
import inspect
import re
from pathlib import Path

import pytest

from utils.viz import FLOWS

RAIZ = Path(__file__).resolve().parent.parent

# Nodos que LEGÍTIMAMENTE cierran un flujo (producen la salida del pipeline).
TERMINALES = {
    "ExitChat",      # chat: despedida
    "WriteReport",   # informe / effective_n: escribe el markdown
    "Entregar",      # juez: entrega la respuesta verificada
    "Sintetizar",    # supervisor: síntesis final
    "Fin",           # research: cierre
    "ReduceGlobal",  # auditoría: reduce global
    "CorrerJuez",    # juez_lote: la corrida en lote (AsyncNode)
    "Flow",          # effective_n_multi: el contenedor batch
}
NO_ACCIONES = {"ERROR", "None", "True", "False"}


def _fuente_propia(clase, nombre):
    """El fuente del método definido por el PROYECTO, no el del framework.

    PocketFlow define `BaseNode.post` como pass-through (`return exec_res`):
    leerlo marcaría a cualquier nodo que no overridea post. Se camina la MRO y
    se corta en el primer dueño real del método."""
    for base in clase.__mro__:
        if nombre in base.__dict__:
            fn = base.__dict__[nombre]
            if getattr(fn, "__module__", "").startswith("pocketflow"):
                return None      # heredado del framework: no es una acción del nodo
            try:
                return inspect.getsource(fn)
            except (OSError, TypeError):
                return None
    return None


def _devoluciones(clase, metodos):
    """(literales, variables) que devuelven esos métodos del nodo."""
    literales, variables = set(), set()
    for nombre in metodos:
        fuente = _fuente_propia(clase, nombre)
        if fuente is None:
            continue
        literales |= set(re.findall(r'return\s+"([A-Za-z_]+)"', fuente))
        literales |= set(re.findall(r'return\s+\(\s*"([A-Za-z_]+)"', fuente))
        variables |= set(re.findall(r'return\s+([a-z_][A-Za-z_0-9]*)\s*$', fuente, re.M))
    return literales - NO_ACCIONES, variables


def _recorrer(flujo):
    """Los nodos alcanzables desde el start (lo que el framework ejecuta)."""
    vistos, orden, pendientes = set(), [], [flujo.start_node]
    while pendientes:
        nodo = pendientes.pop()
        if id(nodo) in vistos:
            continue
        vistos.add(id(nodo))
        orden.append(nodo)
        pendientes.extend(nodo.successors.values())
    return orden


@pytest.mark.parametrize("nombre", sorted(FLOWS))
def test_ningun_nodo_devuelve_una_accion_sin_arista(nombre):
    """Una acción devuelta por post() tiene que estar cableada, y tiene que ser
    LITERAL: si viene de una variable (una etiqueta del modelo) no hay forma de
    verificar el cableado — ese fue el bug del router."""
    for nodo in _recorrer(FLOWS[nombre]()):
        clase = type(nodo)
        aristas = set(nodo.successors)
        literales, variables = _devoluciones(clase, ("post", "post_async"))
        huerfanas = sorted(a for a in literales if a not in aristas and a != "default")
        assert not huerfanas, (
            f"{nombre}: {clase.__name__} puede devolver {huerfanas} y sus aristas son {sorted(aristas)}"
        )
        assert not variables, (
            f"{nombre}: {clase.__name__}.post devuelve la variable {sorted(variables)}: "
            "una acción tiene que ser literal y estar cableada"
        )


@pytest.mark.parametrize("nombre", sorted(FLOWS))
def test_los_terminales_son_los_previstos(nombre):
    for nodo in _recorrer(FLOWS[nombre]()):
        if not nodo.successors:
            assert type(nodo).__name__ in TERMINALES, (
                f"{nombre}: {type(nodo).__name__} quedó sin aristas y no es un terminal conocido"
            )


def test_los_flujos_inline_no_tienen_acciones_sueltas():
    """debate y rag no están en el registro (se construyen dentro de sus
    funciones): se revisan contra su propio fuente."""
    for modulo in ("debate.py", "rag.py"):
        texto = (RAIZ / modulo).read_text(encoding="utf-8")
        cableadas = set(re.findall(r'-\s*"([a-z_]+)"\s*>>', texto)) | {"default"}
        devueltas = set(re.findall(r'return\s+"([a-z_]+)"', texto))
        sueltas = sorted(devueltas - cableadas)
        assert not sueltas, f"{modulo}: devuelve {sueltas} sin arista declarada"


def test_el_router_no_devuelve_una_accion_fuera_de_contrato(monkeypatch):
    """El caso que motivó el guard: una etiqueta del checkpoint fuera de
    contrato no puede cerrar el Flow en silencio."""
    import nodes
    from utils import laya

    monkeypatch.setattr(laya, "disponible", lambda *a, **k: True)
    monkeypatch.setattr(
        laya, "preguntar",
        lambda *a, **k: {"necesita_herramientas": ("uso_herramientas", 0.97)},
    )
    assert nodes.LayaRouter().post({}, "¿q?", ("uso_herramientas", 0.97)) == "herramientas"

