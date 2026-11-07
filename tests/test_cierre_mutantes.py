"""X183, cierre: los tests que matan a los 33 mutantes vivos de S0.

Cada fila/test corresponde a un mutante concreto del instrumento
(`banco/probes/mutantes_s0.py`); el id va en el `ids` de cada parametrize o en
el docstring. Validación del cierre: con el mutante real aplicado en un
worktree aparte, este archivo da rojo (y verde sobre el árbol sano).

Las 13 equivalencias no viven acá: las audita el Auditor con su motivo
(identidad algebraica, rama muerta, reformateo sin cambio de nivel, o no-op
tragado por el `suppress`).
"""
import json
import stat
from types import SimpleNamespace

import pytest

import utils.aprobaciones as aprobaciones
from utils import fs_tools, policy
from utils.aprobaciones import Pedido, dentro_de_scope, pedir_aprobacion, por_scope

CONFIG_PYTEST = {"conftest.py", "pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml",
                 "pyproject.toml", "setup.cfg", "tox.ini"}


# --- utils/policy.py ---

@pytest.mark.parametrize(("comando", "nivel"), [
    ("git -- push", policy.CONFIRMAR_DOBLE),
    ("git --frobnicate push", policy.CONFIRMAR_DOBLE),
    ("git -C. push", policy.CONFIRMAR_DOBLE),
    ("git checkout --conflict=diff3 x", policy.PREGUNTAR),
    ("git status --force", policy.AUTO),
    ("git switch --force", policy.CONFIRMAR_DOBLE),
    ("git status drop", policy.AUTO),
    ("git stash --quiet drop", policy.CONFIRMAR_DOBLE),
], ids=["443", "446-global-salta-2", "449-global-pegado", "468-cortos",
        "476-switch-en-otro-sub", "476-switch-or-and", "478-stash-en-otro-sub",
        "479-480-stash-con-flag"])
def test_git_globales_y_descartes_no_se_esconden(comando, nivel):
    assert policy.clasificar(comando) == nivel


@pytest.mark.parametrize(("comando", "nivel"), [
    ("sudo -- rm -rf /", policy.CONFIRMAR_DOBLE),
    ("git checkout -b rama a.py", policy.CONFIRMAR_DOBLE),
], ids=["362-doble-guion", "405-posicional-tras-rama"])
def test_envoltorios_y_posicionales_de_git(comando, nivel):
    assert policy.clasificar(comando) == nivel


@pytest.mark.parametrize(("comando", "nivel"), [
    ("pytest -kfoo --pastebin=all", policy.PREGUNTAR),
    ("pytest -k foo --pastebin=all", policy.PREGUNTAR),
], ids=["262-valor-pegado-0", "271-toma-valor-2"])
def test_opciones_de_pytest_con_valor(comando, nivel):
    assert policy.clasificar(comando) == nivel


@pytest.mark.parametrize(("comando", "configuracion"), [
    ('pytest "sin cerrar', CONFIG_PYTEST),
    ("python3 -m pytest -q", CONFIG_PYTEST),
], ids=["279-comillas-rotas", "280-base-de-3-tokens"])
def test_configuracion_de_pytest(comando, configuracion):
    assert policy.configuracion(comando) == configuracion


def test_el_global_pegado_de_git_es_legible_para_el_scope():
    """430: `-C.` (global con el valor pegado) resuelve como el global declarado."""
    assert dentro_de_scope("comando", "git -C. status", comandos=["git"])[0] is True


def test_un_global_desconocido_de_git_es_ilegible():
    """446-True→False: un global que la política no declara marca ilegible."""
    assert policy.ilegible("git --frobnicate status") is True


def test_el_scope_no_aprueba_un_compuesto_parcialmente_declarado():
    """571 all→any: con un segmento declarado y otro no, el scope no aprueba."""
    assert policy.declarado("ls && curl x") is False


# --- utils/aprobaciones.py: el scope sin humano y la terminal ---

def _scope(tmp_path, **datos):
    """Scope JSON en tmp; por defecto, con su JSONL de eventos al lado."""
    ruta = tmp_path / "scope.json"
    ruta.write_text(json.dumps({"eventos": str(tmp_path / "eventos.jsonl"), **datos}),
                    encoding="utf-8")
    return ruta


def _ultimo_evento(tmp_path):
    return json.loads((tmp_path / "eventos.jsonl").read_text(encoding="utf-8").splitlines()[-1])


def test_el_scope_no_aprueba_un_compuesto_parcialmente_cubierto():
    """152 all→any: si un segmento no está cubierto, el compuesto no entra."""
    assert dentro_de_scope("comando", "pytest; ruff check .", comandos=["pytest"]) == (
        False, "fuera-de-scope")


def test_el_scope_aprueba_si_no_dice_aprobar(tmp_path):
    """170 True→False: sin `aprobar` el escenario no rechaza (el default aprueba)."""
    d = por_scope(Pedido("¿?", tipo="comando", objetivo="ls"), _scope(tmp_path, comandos=["ls"]))
    assert d.ok is True and d.motivo == ""


def test_el_escenario_que_rechaza_no_aprueba(tmp_path):
    """171 False→True: `aprobar: false` rechaza el pedido, no lo aprueba."""
    d = por_scope(Pedido("¿?", tipo="comando", objetivo="ls"),
                  _scope(tmp_path, aprobar=False, comandos=["ls"]))
    assert d.ok is False and d.motivo == "el-escenario-rechaza"


def test_el_tope_por_defecto_es_doce(tmp_path):
    """172 12→13: con doce pedidos previos, sin `max` declarado, ya no aprueba."""
    (tmp_path / "eventos.jsonl").write_text("{}\n" * 12, encoding="utf-8")
    d = por_scope(Pedido("¿?", tipo="comando", objetivo="ls"), _scope(tmp_path, comandos=["ls"]))
    assert d.ok is False and d.motivo == "tope"


def test_el_scope_crea_la_carpeta_de_sus_eventos(tmp_path):
    """177 parents=True→False: el JSONL puede vivir en carpetas nuevas."""
    eventos = tmp_path / "a" / "b" / "eventos.jsonl"
    ruta = tmp_path / "scope.json"
    ruta.write_text(json.dumps({"eventos": str(eventos), "comandos": ["ls"]}), encoding="utf-8")
    d = por_scope(Pedido("¿?", tipo="comando", objetivo="ls"), ruta)
    assert d.ok is True and eventos.exists()


def test_el_ts_del_evento_va_en_milisegundos(tmp_path, monkeypatch):
    """179 3→4: el JSONL guarda milisegundos, no diezmilésimas."""
    monkeypatch.setattr(aprobaciones, "time", SimpleNamespace(time=lambda: 1700000000.1234))
    por_scope(Pedido("¿?", tipo="comando", objetivo="ls"), _scope(tmp_path, comandos=["ls"]))
    assert _ultimo_evento(tmp_path)["ts"] == round(1700000000.1234, 3)


def test_el_objetivo_del_evento_se_acota_a_300(tmp_path):
    """180 300→301: el registro no crece con un objetivo de 301 chars."""
    por_scope(Pedido("¿?", objetivo="x" * 301), _scope(tmp_path))
    assert len(_ultimo_evento(tmp_path)["objetivo"]) == 300


def test_el_jsonl_del_scope_conserva_el_texto(tmp_path):
    """181 ensure_ascii=False→True: el JSONL se lee como texto, sin escapes."""
    por_scope(Pedido("¿?", tipo="comando", objetivo="ls ñandú"), _scope(tmp_path, comandos=["ls"]))
    assert "ñandú" in (tmp_path / "eventos.jsonl").read_text(encoding="utf-8")


def test_el_prompt_del_scope_se_flushea(tmp_path, monkeypatch):
    """184 flush=True→False: el prompt sale ya, sin quedar en el buffer."""
    kwargs = []
    monkeypatch.setattr(aprobaciones, "print", lambda *a, **k: kwargs.append(k), raising=False)
    por_scope(Pedido("¿?", tipo="comando", objetivo="ls"), _scope(tmp_path, comandos=["ls"]))
    assert kwargs == [{"flush": True}]


def test_un_scope_ilegible_no_aprueba(tmp_path, monkeypatch):
    """202 False→True: un HITL_SCOPE que no se puede leer es rechazo."""
    ruta = tmp_path / "scope.json"
    ruta.write_text("{no es json", encoding="utf-8")
    monkeypatch.setenv("HITL_SCOPE", str(ruta))
    d = pedir_aprobacion(Pedido("¿?", tipo="comando", objetivo="ls"))
    assert d.ok is False and d.motivo == "scope-invalido"


def test_una_respuesta_que_no_es_si_ni_no_rechaza(monkeypatch):
    """217 False→True: en la terminal, lo que no es s/n no aprueba."""
    monkeypatch.setattr("builtins.input", lambda *_: "quizás")
    assert pedir_aprobacion(Pedido("¿?", tipo="comando", objetivo="ls")).ok is False


# --- utils/fs_tools.py ---

def test_escribir_salida_crea_carpetas_anidadas(tmp_path, monkeypatch):
    """144 parents=True→False: dos niveles nuevos se crean."""
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    destino, err = fs_tools.escribir_salida(str(tmp_path / "a" / "b" / "out.md"), "x")
    assert err is None and destino.read_text(encoding="utf-8") == "x"


def test_el_error_de_escritura_lleva_el_strerror(tmp_path, monkeypatch):
    """147 strerror or e: el mensaje lleva el motivo del sistema, no el repr."""
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    (tmp_path / "archivo").write_text("ocupado", encoding="utf-8")
    _, err = fs_tools.escribir_salida(str(tmp_path / "archivo" / "hijo.md"), "x")
    assert err.startswith("no se pudo escribir ") and "Errno" not in err


def test_escribir_atomico_publica_con_modo_0644(tmp_path):
    """170 0o644→0o645: un archivo nuevo no nace ejecutable."""
    destino = tmp_path / "nuevo.md"
    fs_tools.escribir_atomico(destino, "x")
    assert stat.S_IMODE(destino.stat().st_mode) == 0o644


def test_run_tool_call_sin_id_devuelve_cadena_vacia():
    """517 or→and: un tool call sin `id` no inventa un "None"."""
    r = fs_tools.run_tool_call({"function": {"name": "demo", "arguments": "{}"}},
                               extra_impls={"demo": lambda: "ok"})
    assert r["tool_call_id"] == ""
