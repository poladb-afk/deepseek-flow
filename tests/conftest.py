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
# La verificación de citas puede hacer una llamada LLM de corrección: en tests
# se apaga por default (determinismo y costo); el test que la ejercita la prende.
os.environ.setdefault("CITAS_VERIFICAR", "0")


@pytest.fixture(autouse=True)
def _router_sin_calibracion_local(monkeypatch):
    """La calibración del router del `.env` local no cambia los veredictos de
    la suite: al aplicar exp/45 (enforce + calibración ambiental) 2 tests de
    bench medían la política con q en vez de la compuerta fija. Los tests que
    prueban la calibración la fijan explícitamente (monkeypatch de `_setting`
    o calibración de tmp). El .env real sigue mandando en el chat."""
    monkeypatch.setenv(
        "LAYA_CALIBRACION_ROUTER", str(RAIZ / ".calibracion-env-local-inexistente.jsonl")
    )


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
