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
def test_policy_lectura_legitima_sigue_auto_salvo_pytest(comando):
    """Sin regresiones en la lectura legítima; pytest pide permiso
    (S0-CITAS-EJECUCION)."""
    esperado = {'pytest -q': 'preguntar', 'cd /x && python3 -m pytest tests/ -q': 'preguntar'}.get(comando, "auto")
    assert policy.clasificar(comando) == esperado


# Pytest ya no es auto; esta batería conserva la cobertura de X114. La negra
# perdió tres veces (E1 sort, E2 pytest -o, --pastebin), así que lo no
# declarado pregunta, incluido un flag que todavía no existe.
@pytest.mark.parametrize("comando", [
    # X114: el argparse real de pytest, forma por forma.
    "pytest --pastebin=all", "python3 -m pytest --pastebin=all",
    "pytest --junitxml=/tmp/x.xml", "pytest --junit-xml=/tmp/x.xml", "pytest --report-log=r.jsonl",
    "pytest --debug", "pytest --debug=/tmp/d.log", "pytest --cache-clear",
    "pytest -W ignore::evil.W", "pytest --doctest-modules", "pytest @args.txt",
    "pytest -qp evil", "pytest --tb=short --plugin-nuevo",
    'PYTEST_ADDOPTS="-p evil" pytest -q', "env PYTEST_ADDOPTS=-pevil pytest -q",
    "pytest -k --pastebin=all", "pytest -m -p evil", "pytest --tb -p x",
    "pytest -x -- -p evil", "pytest -q t.py -- --pastebin=all",
    # la batería nuestra, como regresión
    "pytest --junitxml=salida.xml", "python3 -m pytest --junit-xml=salida.xml",
    "pytest --report-log=salida.jsonl", "pytest --futuro=1",
])
def test_pytest_auto_es_lista_blanca(comando):
    """Falla cerrada: una opción de pytest no declarada no es auto."""
    assert policy.clasificar(comando) == "preguntar"


# X121 (y el R7 residual de X114b): el shell saca comillas y escapes, así que
# `find . "-delete"` o `pytest "--pastebin=all"` le entregan el flag real. La
# política tiene que ver los MISMOS argumentos que el shell.
@pytest.mark.parametrize("comando, esperado", [
    ('find . "-delete"', "preguntar"), ("find . -dele''te", "preguntar"),
    ("find . -dele\\te", "preguntar"), ('ruff check "--fix" .', "preguntar"),
    ('git diff "--output=x"', "preguntar"), ('pytest "-p" evil', "preguntar"),
    ('"rm" -rf x', "confirmar_doble"), ("grep 'x", "preguntar"),
    ('pytest "--pastebin=all"', "preguntar"), ("pytest '--junitxml=x.xml'", "preguntar"),
    ("pytest \\-\\-pastebin=all", "preguntar"),
    ('pytest "-o" "addopts=--pastebin=all"', "preguntar"),
    ('pytest "-p" "no:cacheprovider"', "preguntar"), ('pytest "--basetemp=/tmp/x"', "preguntar"),
    ('pytest "--debug"', "preguntar"),
    # El shell colapsa la doble capa: `""x""` es `x`.
    ('pytest ""--pastebin=all""', "preguntar"), ("pytest ''--pastebin=all''", "preguntar"),
    ('pytest ""-o"" addopts=--pastebin=all', "preguntar"),
    ('pytest ""-p"" no:cacheprovider', "preguntar"),
])
def test_las_comillas_no_esconden_un_flag(comando, esperado):
    """X121: la política partía por espacios y el shell por comillas. Ahora los
    tokens son los del shell; comillas desbalanceadas no son auto."""
    assert policy.clasificar(comando) == esperado


@pytest.mark.parametrize("comando", [
    # X114: lo declarado en `opciones_permitidas` (y rutas/nodeids) no suma fricción.
    "pytest -q", 'python3 -m pytest tests/ -q -k "a or b" 2>&1 | tail -5',
    "pytest -x --tb=short -rA --maxfail=1 tests/test_a.py::test_b", "pytest -vv --tb short",
    "pytest --lf -q", "pytest --co -q", "pytest -m 'not red' tests/", "pytest -kpolicy -q",
    "pytest", "pytest -v -x -s", "pytest tests/",
    "pytest tests/test_policy.py::test_policy_bypass_cerrados",
    "pytest -k expresion", "pytest -m marcador", "pytest --ff",
    "pytest --collect-only -q", "pytest --tb=short", "pytest -rA",
    "pytest --maxfail=2", "pytest --durations=10", "pytest --no-header",
    "pytest --version", "pytest -kexpresion", "pytest -mfoo",
    'pytest "tests/"', 'pytest -k "expresion"', "python3 -m pytest tests/ -q",
])
def test_pytest_con_opciones_de_la_lista_pregunta(comando):
    """Las opciones declaradas siguen en la lista blanca para scopes (X114),
    pero el chat ya no ejecuta pytest sin permiso (S0-CITAS-EJECUCION)."""
    assert policy.clasificar(comando) == "preguntar"


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


# X115: la configuración de pytest editada eleva la fricción del próximo pytest.
def test_tras_editar_la_configuracion_de_pytest_el_proximo_pregunta(monkeypatch):
    """`addopts = -p plugin` en un conftest no pasa por la línea de comandos.
    Tras una escritura aprobada de la configuración, el próximo pytest
    pregunta; aprobar una ejecución ya no autoriza la siguiente. El mecanismo
    se ejercita directo porque pytest ya no es auto (X200): si volviera a
    serlo, `_configuracion_editada` es el que eleva la fricción."""
    from utils import aprobaciones

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(RAIZ))
    aprobaciones.limpiar()
    assert coding._nivel("python3 -m pytest -q") == "preguntar"
    aprobaciones.registrar("write_file", str(RAIZ / "tests" / "conftest.py"), False)
    aprobaciones.registrar("edit_file", str(RAIZ / "README.md"), True)
    assert coding._nivel("python3 -m pytest -q") == "preguntar"  # rechazada o ajena: no cuenta
    assert coding._configuracion_editada("python3 -m pytest -q") is False
    aprobaciones.registrar("edit_file", str(RAIZ / "pyproject.toml"), True)
    assert coding._configuracion_editada("python3 -m pytest -q") is True
    assert coding._nivel("cd tests && pytest -q") == "preguntar"
    assert coding._nivel("ls") == "auto"  # solo la base que lee esa configuración
    aprobaciones.registrar("run_command", "cd tests && pytest -q", True)
    assert coding._configuracion_editada("python3 -m pytest -q") is False
    assert coding._nivel("pytest -q") == "preguntar"
    aprobaciones.registrar("run_command", "cp /tmp/x tests/conftest.py", True)  # por otro canal
    assert coding._configuracion_editada("python3 -m pytest -q") is True
    assert coding._nivel("pytest -q") == "preguntar"
    aprobaciones.limpiar()


@pytest.mark.parametrize("nombre", ["mi trabajo", "a;touch PWNED", "a$(touch PWNED)", "a && touch PWNED"])
def test_el_rerun_de_fable_judge_no_interpreta_la_ruta_del_trabajo(tmp_path, nombre):
    """X160 (S0): `ReEjecutar` armaba `cd {trabajo} && {comando}` sin comillas.
    Con un directorio llamado `a;touch PWNED` el shell corría `touch` (la policy
    lo veía como un segmento más y la frenaba solo la HITL o el scope), y con
    `mi trabajo` el `cd` fallaba y la verificación quedaba REFUTED por un
    fraude que no existía. Ahora la ruta viaja como UN argumento: el `cd` entra
    y no se ejecuta nada más."""
    import shlex
    import subprocess

    from fable_judge import ReEjecutar

    trabajo = tmp_path / nombre
    trabajo.mkdir()
    (trabajo / "ok.py").write_text("print('ok')\n", encoding="utf-8")
    vistos = []

    def correr(comando):
        vistos.append(comando)
        r = subprocess.run(comando, shell=True, capture_output=True, text=True, cwd=tmp_path, timeout=30)
        return f"exit {r.returncode}\n{r.stdout}"

    nodo = ReEjecutar()
    verif = nodo.exec(nodo.prep({"trabajo": trabajo, "ejecutar": correr, "claims": [
        {"texto": "corre", "tipo": "verificacion", "comando": "python3 ok.py"}]}))

    assert verif[0]["estado"] == "ok"
    assert shlex.split(vistos[0])[:3] == ["cd", str(trabajo), "&&"]  # la ruta es UN argumento
    assert not list(tmp_path.rglob("PWNED"))
