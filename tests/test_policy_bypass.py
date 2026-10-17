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


def test_sale_de_raices_flags_con_ruta_y_tokens_sin_igual(monkeypatch, tmp_path):
    """_sale_de_raices normaliza --flag=/ruta; un flag simple (-la) no rompe
    y un token con '=' que no es flag no se interpreta como ruta.
    Evidencia: 11 mutantes sobrevivientes (Fase 1, M3)."""
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.chdir(tmp_path)  # cwd dentro de las raíces (semántica de producción)
    assert coding._sale_de_raices("cat --out=/etc/passwd") is True
    assert coding._sale_de_raices("cat --out=" + str(tmp_path / "ok.txt")) is False
    assert coding._sale_de_raices("ls -la") is False
    assert coding._sale_de_raices("cat KEY=/etc/passwd") is False
    assert coding._sale_de_raices("cat /etc/passwd") is True


def test_run_command_ls_la_dentro_de_raices_sigue_auto(monkeypatch):
    """Integración: un flag sin '=' llega a _sale_de_raices y el modo auto
    completo ejecuta sin preguntar. Evidencia: mutantes que hacían estallar
    el bucle de tokens sobrevivían (Fase 1, M3)."""
    def no_preguntar(*_a, **_k):
        raise AssertionError("auto no debe pedir aprobación")

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(RAIZ))
    monkeypatch.setenv("HITL_AUTO", "1")
    monkeypatch.setattr(coding, "_approve", no_preguntar)
    assert coding.run_command("ls -la").startswith("exit 0")


def test_auto_no_sigue_symlinks_fuera_de_raices(monkeypatch, tmp_path):
    """El modo auto solo vale DENTRO de las raíces: un symlink dentro de la
    raíz que apunta afuera no puede servir para leer afuera sin aprobación.
    Evidencia: auditoría F2 — `cat link` clasificaba auto y leía el secreto
    de afuera; `cd sub && cat link` lo mismo con el cwd cambiado."""
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    afuera = tmp_path / "afuera"
    afuera.mkdir()
    (afuera / "secreto.txt").write_text("SECRETO-FUERA", encoding="utf-8")
    (raiz / "readme.txt").write_text("dentro", encoding="utf-8")
    (raiz / "link").symlink_to(afuera / "secreto.txt")
    (raiz / "sub").mkdir()
    (raiz / "sub" / "link2").symlink_to(afuera / "secreto.txt")

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(raiz))
    monkeypatch.chdir(raiz)

    assert coding._sale_de_raices("cat link") is True
    assert coding._sale_de_raices("cd sub && cat link2") is True
    assert coding._sale_de_raices("cat readme.txt") is False  # control
    assert coding._nivel("cat link") == "preguntar"

    monkeypatch.setattr(coding, "_approve", lambda *a, **k: False)
    salida = coding.run_command("cat link")
    assert salida.startswith("RECHAZADO")
    assert "SECRETO-FUERA" not in salida
