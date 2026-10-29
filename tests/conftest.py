"""Raíces, entorno y utilidades compartidas por toda la suite.

Esto vivía copiado en cada archivo de test (ocho copias del mismo
`RAIZ = Path(__file__)...` + `sys.path.insert`). Acá está una sola vez:
pytest carga `conftest.py` ANTES que cualquier módulo de test, así que para
cuando un test hace `from utils import ...` la raíz del proyecto ya está en
el path."""
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
# Raíces deterministas para los tests (el default portable es CWD). Es el
# PROPIO repo, no su abuelo: con `RAIZ.parent.parent` el resultado de los tests
# dependía de en qué carpeta clonaste (en `/tmp/<repo>` el abuelo es `/` y la
# contención de rutas quedaba desactivada; E8 de exp/68, corregido en exp/69).
os.environ.setdefault("AGENT_ALLOWED_DIRS", str(RAIZ))

# Recursos del entorno: el marker en pyproject nombra el RECURSO (selección:
# -m git) y el skipif de acá el MOTIVO cuando falta. En los tests van juntos:
# @pytest.mark.git + @requiere_git (el skipif solo NO agrega el marker).
# El repo usa git para el ratchet, pero la suite tiene que poder correr desde
# un zip sin `.git`.
GIT = shutil.which("git")
REPO_GIT = GIT is not None and (RAIZ / ".git").exists()
requiere_git = pytest.mark.skipif(GIT is None, reason="requiere git")
requiere_repo_git = pytest.mark.skipif(
    not REPO_GIT, reason="requiere git y el repo inicializado")

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
        "AGENT_ALLOWED_DIRS", f"{RAIZ}:{tmp_path_factory.getbasetemp()}"
    )


@pytest.fixture(autouse=True)
def _bookkeeping_y_memoria_en_tmp(tmp_path_factory, monkeypatch):
    """La suite NO escribe los logs ni la biblioteca de PRODUCCIÓN (exp/71).

    Medido antes de aislar: `tests/test_policy.py` solo (24 tests) tardaba
    24,4 s con 2,98 GiB de RSS porque los HITL no-auto tomaban el
    `LAYA_MODEL_RIESGO` del `.env` y cargaban el checkpoint del juez; y dejaba
    8 filas con `origen=terminal` en `salidas/riesgo.jsonl` (541 acumuladas,
    indistinguibles del juicio humano). Además `test_compaccion` compactaba su
    historial sintético y respaldaba la zona fría en `memoria/`: 157 de los 243
    respaldos de la biblioteca eran su fixture `pedido 0...` (57.591 B).

    Los tests que prueban estos caminos fijan su propia ruta (o parchean
    `_setting`) después: este fixture solo pone el DEFAULT en tmp.
    `THREADS_DIR` se sumó al cerrar exp/71: los checkpoints de resume también son
    estado del operador y la suite los dejaba en `salidas/threads/`."""
    base = tmp_path_factory.getbasetemp()
    monkeypatch.setenv("LAYA_MODEL_RIESGO", "0")  # nunca el checkpoint real
    monkeypatch.setenv("RIESGO_ARCHIVO", str(base / "riesgo.jsonl"))
    monkeypatch.setenv("PREGUNTAS_ARCHIVO", str(base / "preguntas.jsonl"))
    monkeypatch.setenv("LAYA_LOG_ARCHIVO", str(base / "routing.jsonl"))
    monkeypatch.setenv("MEMORIA_DIR", str(base / "memoria"))
    monkeypatch.setenv("MEMORIA", "1")  # el `.env` del operador no cambia la suite
    monkeypatch.setenv("THREADS_DIR", str(base / "threads"))  # resume fuera del repo


@pytest.fixture(autouse=True)
def _sin_el_aprobador_del_operador(monkeypatch):
    """La suite no hereda el canal de aprobación de quien la corre.

    Medido (cierre de H1, 2026-10-26): cuando el modelo corre `pytest` dentro
    de un chat del banco o del conductor, el proceso hereda `HITL_SCOPE` y
    `por_scope` contestaba los HITL que los tests esperaban de su `input()`
    falso: 3 tests fallaban solo ahí, un `mkdir no_se_debe_crear` se APROBÓ
    y quedó en la raíz, y el turno `correr-tests` de friccion-auto dio
    `no-hecha` porque el modelo vio 24 passed en vez de 26. Los tests que
    prueban el scope o el HITL web lo fijan ellos (monkeypatch: gana el último)."""
    monkeypatch.delenv("HITL_SCOPE", raising=False)
    monkeypatch.setenv("HITL_WEB", "0")


def tc(nombre, args):
    """Tool call con la envoltura exacta que arma el modelo (OpenAI)."""
    return {"id": "call_x", "type": "function",
            "function": {"name": nombre, "arguments": json.dumps(args)}}
