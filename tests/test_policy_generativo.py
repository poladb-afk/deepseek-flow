"""X182: propiedades de la política de comandos con datos generados.

Entre X169 y X174 aparecieron cuatro huecos de S0, todos buscándolos a mano.
Estos tests los buscan solos (hypothesis, semilla fija para que el gate sea
determinista):

- **Contra bash real.** El oráculo es lo que bash EJECUTA, no lo que dice el
  texto: cada comando corre en un bash sin perfil con binarios falsos que solo
  anotan su argv (sin efectos, en un directorio temporal). Si bash corre algo
  destructivo (`rm -rf`, `git push`, `git reset --hard`, `git clean -f`, `git
  stash drop`, `git branch -D`, `git checkout --`), la política tiene que pedir
  doble confirmación y el scope sin humano no lo puede aprobar.
- **Sobre la política sola:** un compuesto nunca es más permisivo que su
  segmento más peligroso, lo irreversible siempre es doble y un scope sin
  prefijos no aprueba nada.
"""
import contextlib
import os
import shutil
import subprocess

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from utils import policy
from utils.aprobaciones import dentro_de_scope

ORDEN = {policy.AUTO: 0, policy.PREGUNTAR: 1, policy.CONFIRMAR_DOBLE: 2}
PELIGRO = ["rm -rf /", "rm -fr x", "git push", "git reset --hard", "git clean -fdx", "git stash drop",
           "git branch -D x", "git checkout -- .", "sudo rm -rf x"]
LECTURA = ["ls", "ls -la", "cat x.py", "git status", "git log", "pwd", "echo hola", "head x", "wc -l x"]
CRUDO = [";", "&&", "||", "|", "&", "\n", "\r", "\t", " ", "\\\n", "$(", ")", "`", "``", "$()", "'", '"', "\\",
         "*", "~", "{", "}", "<", ">", "2>&1", "#", "\u00a0", ";;", "|&", "&>", "!", "\\ ", "$'\\n'"]
SCOPE_AMPLIO = ["ls", "cat", "git", "echo", "pwd", "head", "wc", "grep", "rm", "sudo"]
BINARIOS = ["rm", "git", "ls", "cat", "wc", "grep", "head", "pwd", "sudo", "env", "timeout", "find", "bash", "sh"]

_pegado = st.lists(st.sampled_from(CRUDO), min_size=1, max_size=3).map("".join)
COMANDOS = st.one_of(
    st.builds(lambda a, s, b: a + s + b, st.sampled_from(LECTURA), _pegado, st.sampled_from(PELIGRO)),
    st.builds(lambda b, s, f: b + s + f, st.sampled_from(PELIGRO), _pegado, st.sampled_from(["", " x", " #"])),
)
GENERADO = settings(max_examples=400, derandomize=True, deadline=None, database=None,
                    suppress_health_check=list(HealthCheck))


@pytest.fixture(scope="module")
def bash_espia(tmp_path_factory):
    """(correr, registro): un PATH con binarios que solo anotan su argv."""
    base = tmp_path_factory.mktemp("bash_espia")
    registro = base / "argv"
    for nombre in BINARIOS:
        binario = base / nombre
        binario.write_text(f'#!/bin/bash\nprintf "%s\\037" {nombre} "$@" >> "{registro}"; printf "\\036" >> "{registro}"\n')
        binario.chmod(0o755)

    def correr(comando):
        registro.write_bytes(b"")
        trabajo = base / "trabajo"
        shutil.rmtree(trabajo, ignore_errors=True)
        trabajo.mkdir()
        with contextlib.suppress(subprocess.TimeoutExpired):
            subprocess.run(["/bin/bash", "--norc", "--noprofile", "-c", comando], cwd=trabajo,
                           env={"PATH": str(base), "HOME": str(trabajo)}, capture_output=True, timeout=5)
        return [[p.decode("utf-8", "replace") for p in linea.split(b"\x1f")][:-1]
                for linea in registro.read_bytes().split(b"\x1e") if linea]
    return correr


def _destructivo(argv):
    """El argv ejecutado descarta trabajo (la lista doble, leída sobre lo que corrió)."""
    a = argv[1:] if argv[:1] == ["sudo"] else argv
    if a[:1] == ["rm"]:
        cortos = "".join(x[1:] for x in a[1:] if x.startswith("-") and not x.startswith("--"))
        return ("r" in cortos.lower() or "--recursive" in a) and ("f" in cortos or "--force" in a)
    s = a[1:] if a[:1] == ["git"] else []
    return bool(s) and (s[0] == "push" or (s[0] == "reset" and "--hard" in s) or s[:2] in (["stash", "drop"],)
                        or (s[0] == "clean" and any("f" in x for x in s[1:] if x.startswith("-")))
                        or (s[0] == "branch" and "-D" in s) or (s[0] == "checkout" and "--" in s))


@pytest.mark.skipif(not os.path.exists("/bin/bash"), reason="requiere /bin/bash")
@GENERADO
@given(comando=COMANDOS)
def test_lo_que_bash_corre_destructivo_pide_doble_y_el_scope_no_lo_aprueba(bash_espia, comando):
    corrido = [argv for argv in bash_espia(comando) if argv and _destructivo(argv)]
    if corrido:
        assert policy.clasificar(comando) == policy.CONFIRMAR_DOBLE, (comando, corrido[0])
        assert dentro_de_scope("comando", comando, comandos=SCOPE_AMPLIO)[0] is False, comando


@pytest.mark.parametrize("comando", ["git push\\\n", "git reset --hard\\\n\\\n", "r\\\nm -rf /",
                                     "git pu\\\nsh", "git push`` x", "git stash drop``",
                                     "pwd;``git checkout -- .", "git push$()", "git push$(echo)"])
def test_continuacion_de_linea_y_sustitucion_vacia_no_esconden_lo_irreversible(comando):
    """Los casos que encontró el generador (X182), fijos: bash une `\\` + salto
    de línea y borra una sustitución vacía; la política ahora también."""
    assert policy.clasificar(comando) == policy.CONFIRMAR_DOBLE
    assert policy.irreversible(comando)


_ARGUMENTOS = ["-la", "-r", "-f", "-rf", "--force", "-c", "x.py", ".", "/", "--hard", "push", "reset", "clean",
               "-fdx", "stash", "drop", "-D", "checkout", "--", "status", "-C", "-m", "pytest", "--fix", "-delete"]
_BASES = ["ls", "cat", "rm", "git", "pytest", "python3", "ruff", "find", "sed", "bash", "sudo", "env", "timeout"]
_SEGMENTO = st.builds(lambda b, a: " ".join([b, *a]), st.sampled_from(_BASES),
                      st.lists(st.sampled_from(_ARGUMENTOS), max_size=4))
_COMPUESTO = st.builds(lambda s, sep: sep.join(s), st.lists(_SEGMENTO, min_size=1, max_size=3),
                       st.sampled_from([" && ", " || ", " ; ", " | ", " & ", "\n"]))


@settings(max_examples=1000, derandomize=True, deadline=None, database=None)
@given(comando=_COMPUESTO)
def test_las_propiedades_de_la_politica_se_cumplen_en_cualquier_composicion(comando):
    nivel = policy.clasificar(comando)
    assert all(ORDEN[policy.clasificar(s)] <= ORDEN[nivel] for s in policy.segmentos(comando)), comando
    assert not policy.irreversible(comando) or nivel == policy.CONFIRMAR_DOBLE, comando
    assert dentro_de_scope("comando", comando, comandos=[])[0] is False, comando
    bases = [s.split()[0] for s in policy.segmentos(comando)]
    if dentro_de_scope("comando", comando, comandos=bases)[0]:
        assert not policy.irreversible(comando) and not policy.opaco(comando), comando
