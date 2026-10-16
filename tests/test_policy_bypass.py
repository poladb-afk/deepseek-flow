"""Guardas del HITL graduado: los bypass medidos en la auditoría no vuelven.

Reconstruido a partir de la especificación §7 de
docs/informes/correcciones_deepseek_flow.md — el archivo original del autor
(tests/test_policy_bypass.py, 39 casos) no se entregó con el patch.
Cubre: separadores que el shell ejecuta (\n, &), flags que vuelven escritor a
un comando de la whitelist, la denylist dura y la contención de raíces de
run_command.
"""
import json

import pytest
from conftest import RAIZ

from modules import coding
from utils import policy


@pytest.mark.parametrize("comando, esperado", [
    ("ls\nrm -rf ~", "confirmar_doble"),
    ("cat a & rm -rf b", "confirmar_doble"),
    ("find . -delete", "preguntar"),
    ("find . -exec rm {} \\;", "preguntar"),
    ("find / -fprint /tmp/x", "preguntar"),
    ("git diff --output=/tmp/x", "preguntar"),
    ("sort -o salida.txt a", "preguntar"),
    ("python3 -m pytest -p plugin_malo", "preguntar"),
    ("pytest --basetemp=/", "preguntar"),
    ("echo hola\ntouch marcador", "preguntar"),
    ("ls & touch marcador", "preguntar"),
])
def test_policy_bypass_cerrados(comando, esperado):
    """Los separadores y los flags peligrosos ya no caen en 'auto'."""
    assert policy.clasificar(comando) == esperado


@pytest.mark.parametrize("comando", [
    "ls",
    "pytest -q",
    "cd /x && python3 -m pytest tests/ -q",
    "grep -r x . 2>&1",
    "find . -name '*.py' | sort -rn | head -5",
    "git log --oneline",
])
def test_policy_lectura_legitima_sigue_auto(comando):
    """Sin regresiones: la lectura legítima sigue sin fricción."""
    assert policy.clasificar(comando) == "auto"


def _tool_call(comando):
    return {
        "role": "assistant",
        "tool_call_id": "t1",
        "function": {
            "name": "run_command",
            "arguments": json.dumps({"command": comando}),
        },
    }


@pytest.mark.parametrize("comando", [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf $HOME",
    "rm -r -f /",
    "sudo rm -rf /",
    "/bin/rm -rf /",
    ":(){ :|:& };:",
    "ls\nrm -rf ~",
])
def test_denylist_veta(comando):
    """La denylist dura veta sin pedir aprobación."""
    assert coding._vetar_comando_prohibido(_tool_call(comando))


@pytest.mark.parametrize("comando", [
    "rm -rf ./build",
    "rm -rf /tmp/mio",
    "rm -f x",
    "echo hola",
])
def test_denylist_no_veta_borrados_acotados(comando):
    """Borrados acotados no se vetan: caen en la fricción normal."""
    assert coding._vetar_comando_prohibido(_tool_call(comando)) is None


def test_auto_fuera_de_raices_pregunta(monkeypatch):
    """'auto' solo lee DENTRO del proyecto: fuera de las raíces pide s/n."""
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(RAIZ))
    monkeypatch.setattr(coding, "_approve", lambda *a, **k: False)
    salida = coding.run_command("cat /etc/passwd")
    assert "RECHAZADO" in salida


def test_auto_dentro_de_raices_sigue_auto(monkeypatch):
    """La misma lectura dentro de las raíces no gana fricción."""
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(RAIZ))
    monkeypatch.setattr(coding, "_approve", lambda *a, **k: False)
    assert coding.run_command("cat README.md").startswith("exit 0")
