"""Raíces, entorno y utilidades compartidas por toda la suite.

Esto vivía copiado en cada archivo de test (ocho copias del mismo
`RAIZ = Path(__file__)...` + `sys.path.insert`). Acá está una sola vez:
pytest carga `conftest.py` ANTES que cualquier módulo de test, así que para
cuando un test hace `from utils import ...` la raíz del proyecto ya está en
el path."""
import json
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
# raíces deterministas para los tests (el default portable es CWD)
os.environ.setdefault("AGENT_ALLOWED_DIRS", str(RAIZ.parent.parent))


@pytest.fixture(autouse=True)
def _permitir_salidas_de_tmp(tmp_path_factory, monkeypatch):
    """Las salidas de los flujos pasan por la contención de AGENT_ALLOWED_DIRS
    (exp/26): el tmp de pytest se declara como raíz permitida para que los
    tests sigan escribiendo ahí. Los tests que PRUEBAN la contención fijan su
    propio AGENT_ALLOWED_DIRS después (monkeypatch: gana el último setenv)."""
    monkeypatch.setenv(
        "AGENT_ALLOWED_DIRS", f"{RAIZ.parent.parent}:{tmp_path_factory.getbasetemp()}"
    )


def tc(nombre, args):
    """Tool call con la envoltura exacta que arma el modelo (OpenAI)."""
    return {"id": "call_x", "type": "function",
            "function": {"name": nombre, "arguments": json.dumps(args)}}
