"""Juicio oculto de la aceptación v1 (T2): `-m` solo detrás de un python.

No vive en el árbol que ve el agente: `banco/probes/aceptacion_v1.py` lo copia
a la copia limpia de `73b05fe` junto con el `fable_judge.py` del run y lo corre
con pytest. Los cinco primeros comandos son el test real de X179; el resto son
controles de la misma clase que un parche por nombre no cubre.
"""
import pytest

import fable_judge

MALOS = [
    "bash -m pytest",
    "sh -m pytest",
    "node -m pytest",
    "env -m pytest",
    "bash -m ruff check .",
    "bash -m pytest -q",
    "node -m coverage run",
    "env -m http.server",
]

BUENOS = [
    "python3 -m pytest",
    "python -m pytest",
    "python3 -m ruff check .",
    "python -m ruff check .",
    "pytest -q",
    "ruff check .",
    "python3 -m pytest tests/test_fable_judge_claims.py -q",
]


@pytest.mark.parametrize("comando", MALOS)
def test_un_programa_que_no_es_python_no_usa_m(comando):
    assert fable_judge.permitido_rerun(comando) is False


@pytest.mark.parametrize("comando", BUENOS)
def test_el_control_de_python_y_pytest_sigue_igual(comando):
    assert fable_judge.permitido_rerun(comando) is True
