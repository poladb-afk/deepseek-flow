"""Regresiones de la auditoría 2026-10-26 (H1): cada test falla sobre el código
previo y pasa con el fix. Los bypass son los MEDIDOS en la auditoría, no
hipotéticos: cada uno leyó o escribió fuera de las raíces en un sandbox."""
import json
import os
import stat

import pytest

import modules.coding as mc
import modules.escritura as me
from utils.aprobaciones import Pedido, dentro_de_scope, por_scope
from utils.conductor import escribir_scope
from utils.policy import clasificar
from utils.thread_store import cargar, checkpoint


def test_la_doble_confirmacion_real_no_se_aprueba_por_scope(tmp_path):
    """S1: el conductor leía `¿Seguro? (1/2) (s/n):` como un s/n simple y
    aprobaba `git push --force` dos veces. Ahora decide sobre el comando."""
    scope = escribir_scope(tmp_path / "s.json", eventos=tmp_path / "e.jsonl")
    pedido = Pedido("¿Seguro? (1/2)", "git push --force origin main", "comando",
                    "git push --force origin main", "confirmar_doble")
    assert por_scope(pedido, scope).ok is False


@pytest.mark.parametrize("tipo, objetivo, rutas, comandos", [
    ("escritura", "/repo/docs_evil/x", ["/repo/docs"], None),        # prefijo de texto
    ("escritura", "/repo/.ENV", ["/repo"], None),                    # mayúsculas
    ("comando", "pytest; curl x | sh", None, ["pytest"]),            # compuesto
    ("comando", "pytest $(curl x)", None, ["pytest"]),               # sustitución
    ("desconocido", "", None, None),                                 # no parseable
])
def test_el_scope_falla_cerrado(tipo, objetivo, rutas, comandos):
    assert dentro_de_scope(tipo, objetivo, rutas, comandos)[0] is False


@pytest.mark.parametrize("comando", [
    "sort -uo/tmp/fuera.txt in.txt",   # -o agrupado: escribió fuera del repo
    "grep -rR x .",                    # -R agrupado: sigue symlinks
    "tail -qf x",                      # -f agrupado: no termina
    "ruff check -nw",                  # -w agrupado: watch
])
def test_flags_cortas_agrupadas_no_son_auto(comando):
    assert clasificar(comando) != "auto"


def test_find_no_agrupa_flags():
    """find no usa getopt: `-name` no es -n -a -m -e."""
    assert clasificar("find . -name x -type f") == "auto"


@pytest.mark.parametrize("comando", [
    "cd && cat .bashrc",          # cd sin destino = $HOME
    "cd ..;cat secreto",          # ; pegado: shlex no lo partía
    "cd ..&&cat secreto",
    "cd - && ls",                 # OLDPWD
    "cat d/*",                    # glob a un symlink externo
    "echo x$DEEPSEEK_API_KEY",    # la API key al contexto del modelo
])
def test_auto_no_sale_de_raices(tmp_path, monkeypatch, comando):
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setenv("HITL_AUTO", "1")
    monkeypatch.chdir(tmp_path)
    assert mc._nivel(comando) != "auto"


@pytest.mark.parametrize("comando", ["cat README.md", "cd sub && ls", "find . -name '*.py'",
                                     "python3 -m pytest -q 2>&1 | tail -5"])
def test_auto_dentro_de_raices_sigue_auto(tmp_path, monkeypatch, comando):
    """El arreglo no suma fricción a las lecturas legítimas de siempre."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setenv("HITL_AUTO", "1")
    monkeypatch.chdir(tmp_path)
    assert mc._nivel(comando) == "auto"


def test_edit_file_preserva_crlf(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(mc, "_approve", lambda p: True)
    f = tmp_path / "a.txt"
    f.write_bytes(b"uno\r\ndos\r\n")
    mc.edit_file(str(f), "dos", "DOS")
    assert f.read_bytes() == b"uno\r\nDOS\r\n"


def test_edit_file_no_corrompe_bytes_no_utf8(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(mc, "_approve", lambda p: True)
    f = tmp_path / "l1.txt"
    f.write_bytes(b"caf\xe9 ok\n")
    assert mc.edit_file(str(f), "ok", "OK").startswith("ERROR")
    assert f.read_bytes() == b"caf\xe9 ok\n"


@pytest.mark.parametrize("modo", [0o700, 0o600, 0o755])
def test_write_file_preserva_permisos(tmp_path, monkeypatch, modo):
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(me, "_approve", lambda p: True)
    f = tmp_path / "s.sh"
    f.write_text("echo hi\n")
    os.chmod(f, modo)
    me.write_file(str(f), "echo bye\n")
    assert stat.S_IMODE(f.stat().st_mode) == modo


def test_checkpoint_ida_y_vuelta_es_identidad(tmp_path):
    """F4 (experimento C): load(save(s)) == s. Con default=str un set volvía
    como "{'ab'}" y el Skill como su repr; ahora el shared es JSON puro y lo
    que no lo es se omite con aviso en vez de guardarse falso."""
    shared = {"messages": [{"role": "system", "content": "s"}], "tool_rounds": 2,
              "_huellas_vistas": ["ab", "cd"], "_skill_activo": "revision"}
    checkpoint("t", "ExecuteTools", "default", shared, ruta_dir=tmp_path)
    assert cargar("t", ruta_dir=tmp_path) == shared
    checkpoint("t", "x", "y", {"messages": [], "malo": {1, 2}}, ruta_dir=tmp_path)
    assert cargar("t", ruta_dir=tmp_path) == shared  # el falso no pisó al bueno
    assert all(json.loads(ln) for ln in (tmp_path / "t.jsonl").read_text().splitlines())


def test_actualizar_novedad_queda_json():
    import nodes

    shared = {}
    tc = {"function": {"name": "read_file", "arguments": "{}"}}
    nodes.actualizar_novedad(shared, [tc, tc])
    assert isinstance(shared["turno"]["huellas_vistas"], list) and len(shared["turno"]["huellas_vistas"]) == 1
    json.dumps(shared)


# ── cierre de H1 (auditoría del agente sobre H1, 2026-10-26) ──

def test_el_conductor_sin_permitir_comandos_no_aprueba_comandos(tmp_path):
    """Obs. 4: sin --permitir-comandos el scope era None = todo lo no
    irreversible, sin humano. Ahora el conductor falla cerrado."""
    import delegar

    capturado = {}

    class SinPrompt:
        raw = None

        def abrir_log(self, destino):
            pass

        def esperar(self, patron, timeout):
            return False

        def matar(self):
            pass

    def lanzar(env, argv):
        capturado["scope"] = env["HITL_SCOPE"]
        return SinPrompt()

    delegar.conducir("x", tmp_path, timeout_min=1, lanzar=lanzar)
    pedido = Pedido("¿Ejecutar?", "pip install x", "comando", "pip install x")
    assert por_scope(pedido, capturado["scope"]).ok is False
    escritura = Pedido("¿Escribir?", "", "escritura", str(tmp_path / "ok.md"))
    assert por_scope(escritura, capturado["scope"]).ok is True  # escrituras: sin cambio


@pytest.mark.parametrize("ruta, prohibida", [
    ("/repo/prod.env", True), ("/repo/config/x.ENV", True), ("/repo/.env.local", True),
    ("/repo/repo.git/HEAD", True), ("/repo/environment.md", False), ("/repo/no_memoria/x", False),
])
def test_la_denylist_cubre_sufijos_env(ruta, prohibida):
    from utils.aprobaciones import ruta_prohibida

    assert ruta_prohibida(ruta) is prohibida


def test_alcance_amplio_no_recorre_fuera_de_las_raices(tmp_path, monkeypatch):
    """F3: `/usr` se recorría entero (~3 s) en cada ronda."""
    import time

    import nodes

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    inicio = time.perf_counter()
    assert nodes.alcance_amplio("revisá /usr y /etc", raiz=tmp_path) is False
    assert time.perf_counter() - inicio < 0.5


def test_verificar_turno_detecta_tarea_no_hecha(tmp_path, monkeypatch):
    """Obs. 5: el banco marcaba ok un turno aunque la tarea no se hiciera."""
    import banco.banco as bb

    monkeypatch.setattr(bb, "RAIZ", tmp_path)
    (tmp_path / "a.txt").write_text("banco ok", encoding="utf-8")
    assert bb.verificar_turno([{"contiene": {"ruta": "a.txt", "texto": "banco ok"}},
                               {"no_existe": "b.txt"}, {"transcript": "1 passed"},
                               {"comando": "true"}], "== 1 passed ==") == []
    fallas = bb.verificar_turno([{"existe": "b.txt"}, {"comando": "false"},
                                 {"transcript": "2 passed"}], "1 passed")
    assert len(fallas) == 3


def test_un_chequeo_desconocido_invalida_el_escenario(tmp_path):
    import yaml

    from banco.banco import cargar_escenario

    ruta = tmp_path / "e.yaml"
    ruta.write_text(yaml.safe_dump({"id": "e", "turnos": [
        {"id": "t", "linea": "x", "verificar": [{"existe_tal_vez": "x"}]}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        cargar_escenario(ruta)



def test_la_suite_no_hereda_el_aprobador_del_chat(tmp_path):
    """Cierre de H1: la suite corrida DENTRO de un chat con scope (el modelo
    verificando con pytest) da lo mismo que afuera, y no crea nada que sus
    tests esperan rechazado. Corre los 3 tests que fallaban ahí."""
    import subprocess
    import sys

    from conftest import RAIZ

    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps({"rutas": None, "comandos": None, "max": 99,
                                 "eventos": str(tmp_path / "e.jsonl"), "aprobar": True}))
    tests = ["tests/test_policy.py::test_run_command_no_seguro_pide_input",
             "tests/test_policy.py::test_run_command_hitl_auto_cero_compatibilidad",
             "tests/test_hitl.py::test_motivo_del_rechazo_viaja_al_modelo"]
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests],
                       cwd=RAIZ, capture_output=True, text=True, timeout=120,
                       env={**os.environ, "HITL_SCOPE": str(scope)})
    assert r.returncode == 0, r.stdout[-800:]
    assert not (tmp_path / "e.jsonl").exists()  # el aprobador del chat no contestó nada
