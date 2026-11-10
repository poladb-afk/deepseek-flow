"""S0-CITAS-EJECUCION: pytest requiere autorización por ejecución de código."""
import pytest

from utils import policy
from utils.aprobaciones import dentro_de_scope


@pytest.mark.parametrize("comando", [
    "pytest -q", "python3 -m pytest tests/ -q", "python -m pytest", "/usr/bin/pytest -q",
    "command pytest -q", "env pytest -q", "pytest --collect-only", "pytest --version",
    "cd . && pytest -q", "pytest -q 2>&1 | tail -5", "pytest -q && ruff check .",
])
def test_las_formas_de_pytest_requieren_autorizacion(comando):
    assert policy.clasificar(comando) == policy.PREGUNTAR


@pytest.mark.parametrize("decision", [False, True], ids=["rechazo", "aprobacion"])
def test_pytest_consulta_al_aprobador_antes_del_ejecutor(monkeypatch, decision):
    from modules import coding

    monkeypatch.setenv("HITL_AUTO", "1")
    pedidos = []
    ejecuciones = []

    def aprobar(pedido):
        pedidos.append(pedido)
        return decision

    def ejecutar(comando):
        ejecuciones.append(comando)
        return "exit 0\nresultado controlado"

    monkeypatch.setattr(coding, "_approve", aprobar)
    monkeypatch.setattr(coding, "_ejecutar", ejecutar)
    resultado = coding.run_command("pytest -q")
    assert len(pedidos) == 1 and pedidos[0].objetivo == "pytest -q"
    assert ejecuciones == (["pytest -q"] if decision else [])
    assert resultado.startswith("exit 0") is decision


@pytest.mark.parametrize("comandos, permitido", [(None, False), ([], False), (["pytest"], True)])
def test_scope_debe_cubrir_la_ejecucion_de_tests(comandos, permitido):
    assert dentro_de_scope("comando", "pytest -q", comandos=comandos)[0] is permitido


def test_autorizar_pytest_no_autoriza_cualquier_opcion():
    assert not dentro_de_scope("comando", "pytest -p plugin", comandos=["pytest"])[0]
    assert not dentro_de_scope("comando", "pytest --pastebin=all", comandos=["pytest"])[0]
