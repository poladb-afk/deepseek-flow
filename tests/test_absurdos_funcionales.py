"""Absurdos funcionales del HITL graduado y de la votación (revisión 2026-10-21).

Cada caso fue reproducido contra el código antes del arreglo: la política
clasificaba por la FORMA del comando y no por su efecto. Ver
docs/informes/evidencia_absurdos_funcionales.md.
"""
import pytest
from conftest import RAIZ

from modules import coding
from utils import policy
from utils.votacion import mayoria


@pytest.mark.parametrize("comando", [
    "sort -S 100K --compress-program=./payload.sh big.txt",  # ejecutaba payload.sh en auto
    "pytest -q -o addopts=-pplugmalo",                       # cargaba el plugin en auto
    "pytest -q --override-ini=addopts=-pplugmalo",
    "tail -f log.txt",                                       # colgaba hasta TIMEOUT_S
    "tail -F log.txt",
])
def test_whitelist_no_deja_ejecutar_ni_colgar(comando):
    assert policy.clasificar(comando) == "preguntar"


@pytest.mark.parametrize("comando", [
    "rm -r -f x", "rm -Rf x", "rm -fR x", "rm -rF x", "rm -FR x", "rm --recursive --force x",
    "sudo rm -rf x", "sudo -u root rm -rf x", "/bin/rm -rf x", "env rm -rf x",
    "env -i rm -rf x", "env -i A=b rm -rf x", "command rm -rf x",
    "nice -n 10 rm -rf x", "nice -10 rm -rf x", "timeout 5 rm -rf x",
    "git -C . push", "git -c user.name=x push origin main", "sudo git push",
    "ls && rm -r -f x", "cd /tmp && rm --recursive --force x",
])
def test_destructivo_pide_doble_aunque_cambie_la_forma(comando):
    assert policy.clasificar(comando) == "confirmar_doble"


@pytest.mark.parametrize("comando, esperado", [
    ("rm -r x", "preguntar"),           # recursivo sin forzar: un solo s/n, como antes
    ("rm -f x", "preguntar"),
    ("git log --grep push", "auto"),    # 'push' como argumento no es el subcomando
    ("tail -n 20 log.txt", "auto"),
    ("sort archivo.txt", "auto"),
    ("pytest -q", "auto"),
    ("sudo cat README.md", "preguntar"),  # el envoltorio no se come la fricción
    ("nice -n 10 cat README.md", "preguntar"),
])
def test_normalizar_no_sube_friccion_de_mas(comando, esperado):
    assert policy.clasificar(comando) == esperado


@pytest.mark.parametrize("comando, esperado", [
    ("ls && rm -rf /", "borrado recursivo forzado (destructivo)"),
    ("cd /tmp && rm -rf x", "borrado recursivo forzado (destructivo)"),
    ("cat a && git -C . push", "publica commits al remoto (irreversible en el server)"),
    ("sudo rm -rf x", "borrado recursivo forzado (destructivo)"),
    # El texto de solo-lectura usa la forma CRUDA: un `sudo cat` pregunta,
    # así que no debe leerse "solo lee" en el prompt de aprobación.
    ("sudo cat README.md", "efecto no reconocido como solo-lectura: pide aprobación"),
    ("tail -f x", "flag que escribe, ejecuta o no termina: pide aprobación"),
])
def test_explicar_nombra_el_segmento_que_fija_el_nivel(comando, esperado):
    assert policy.explicar(comando) == esperado


def test_auto_fuera_de_raices_sigue_preguntando(monkeypatch):
    """El hallazgo inicial 'cat ~/.ssh lee sin aprobación' era FALSO: run_command
    lo sube a preguntar con _sale_de_raices. Desde la auditoría 2026-10-26 la
    policy además marca `~` y `$` como opacos; las rutas absolutas siguen
    dependiendo SOLO de la segunda capa, que es la que se clava acá."""
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(RAIZ))
    for comando in ("find / -name '*.pem'", "git diff --no-index /etc/passwd README.md"):
        assert policy.clasificar(comando) == "auto"
        assert coding._nivel(comando) == "preguntar", comando
    for comando in ("cat ~/.ssh/id_rsa", "grep -r secreto ~", "cat $HOME/.bashrc"):
        assert policy.clasificar(comando) == "preguntar", comando
        assert coding._sale_de_raices(comando) is True, comando


def test_mayoria_empate_usa_el_desempate():
    assert mayoria(["a", "a", "b", "b"], desempate="b") == "b"
    assert mayoria(["a", "a", "b", "b", "c"], desempate="c") == "c"
    assert mayoria(["a", "a", "b"], desempate="b") == "a"  # sin empate: gana la mayoría


def test_nivel_es_el_que_decide_run_command(monkeypatch):
    """Los tres huecos llegan también al punto donde run_command decide
    ejecutar (`_nivel`), que es lo que mira antes de `_ejecutar`."""
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(RAIZ))
    for comando in ("sort -S 100K --compress-program=./payload.sh big.txt",
                    "pytest -q -o addopts=-pplugmalo",
                    "tail -f log.txt"):
        assert coding._nivel(comando) == "preguntar", comando


def test_run_command_no_ejecuta_los_flags_peligrosos(monkeypatch):
    """E2E del flujo: con la clasificación arreglada, run_command NO llega a
    `_ejecutar` para esos comandos (y sí ejecuta un auto legítimo)."""

    def aprobar(command, nivel):
        return (nivel == "auto", "" if nivel == "auto" else "RECHAZADO")

    ejecutados = []
    monkeypatch.setattr(coding, "_aprobar", aprobar)
    monkeypatch.setattr(coding, "_ejecutar", lambda command: ejecutados.append(command) or "ok")

    for comando in ("sort -S 100K --compress-program=./payload.sh big.txt",
                    "pytest -q -o addopts=-pplugmalo",
                    "tail -f log.txt",
                    "rm -Rf x"):
        assert coding.run_command(comando) == "RECHAZADO", comando
    assert ejecutados == [], "un comando peligroso llegó a _ejecutar"
    assert coding.run_command("ls") == "ok"
    assert ejecutados == ["ls"]
