"""Tests de `utils.convergencia.seco` (exp/96, C1): la pieza pura que decide
si una ronda del supervisor no aportó material nuevo."""

import pytest

from utils.convergencia import seco


def test_iguales_es_seco():
    assert seco("leyó a.py y encontró 3 funciones", "leyó a.py y encontró 3 funciones") is True


def test_normaliza_espacios():
    assert seco("leyó   a.py\n y b.py", " leyó a.py y   b.py ") is True


def test_casi_igual_sobre_el_umbral_es_seco():
    a = "1 read_file(path=a.py) -> 3 funciones y 2 clases en el módulo"
    b = "1 read_file(path=a.py) -> 3 funciones y 2 clases en el modulo"
    assert seco(a, b, umbral=0.95) is True


def test_distintos_bajo_el_umbral_no_es_seco():
    assert seco("1 read_file(path=a.py) -> 3 funciones", "2 search_files(glob=*.md) -> 42 archivos") is False


def test_umbral_borde():
    """El ratio exacto del par: por encima del propio ratio da seco, por
    encima de él no. El borde es '>=' — el ratio igual al umbral cuenta."""
    import difflib

    a, b = "leyó a.py", "leyó b.py"
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    assert seco(a, b, umbral=ratio) is True
    assert seco(a, b, umbral=ratio + 1e-9) is False


def test_vacios():
    assert seco("", "") is True
    assert seco("", "   \n ") is True
    assert seco("", "leyó a.py") is False


@pytest.mark.parametrize("umbral", [0.9, 0.95, 0.99])
def test_umbral_es_parametro(umbral):
    """El umbral se respeta tal cual: el par y su ratio se calculan, y con un
    umbral apenas por debajo del ratio da seco, apenas por encima no."""
    import difflib

    a = "leyó a.py y encontró tres funciones" * 5
    b = a + " y nada más"
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    assert seco(a, b, umbral=ratio) is True
    assert seco(a, b, umbral=ratio + 1e-6) is False
    assert seco(a, "zy" * 30, umbral=umbral) is False
