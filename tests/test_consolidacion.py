"""Regresión de la consolidación 2026-10-15 (defectos A01–A11 + estabilidad).

Cada test reproduce el defecto MEDIDO en el árbol previo y fija la conducta
corregida. Sin red, sin LLM, sin Laya."""
import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS

import pytest


# 1 prefiltro
def test_prefiltro_memoria_sin_laya_no_recorta_ni_miente(tmp_path, monkeypatch):
    """Medido: 12 notas que matchean → 8 con '[prefiltro Laya: 12 → 8]' SIN
    Laya cargada. Ahora: las 12 y sin aviso."""
    import modules.memoria as mem
    import utils.laya as ul

    monkeypatch.setattr(ul, "disponible", lambda setting=None: False)
    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORIA_PREFILTRO", "1")
    monkeypatch.setenv("MEMORIA_PREFILTRO_N", "8")
    for i in range(12):
        (tmp_path / f"n{i:02}.md").write_text("tema x\n", encoding="utf-8")
    out = mem.memory_search("tema")
    assert "(12 líneas)" in out
    assert "prefiltro Laya" not in out


def test_prefiltro_rag_sin_laya_no_recorta(monkeypatch):
    import modules.rag as rag
    import utils.laya as ul

    monkeypatch.setattr(ul, "disponible", lambda setting=None: False)
    monkeypatch.setenv("RAG_PREFILTRO", "1")
    monkeypatch.setenv("RAG_PREFILTRO_N", "1")
    salida = ("3 fragmentos; top 3:\n\n--- a.py (score 0.5) ---\nA\n\n"
              "--- b.py (score 0.4) ---\nB\n\n--- c.py (score 0.3) ---\nC")
    assert rag._prefiltrar("q", salida, 3) == salida


# 2 evals
def test_evals_salida_fuera_de_raices_se_rechaza(tmp_path, monkeypatch):
    import evals as ev
    import modules.evals as mod

    dentro = tmp_path / "dentro"
    (dentro / "runs").mkdir(parents=True)
    fuera = tmp_path / "fuera"
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(dentro))
    monkeypatch.setattr(ev, "correr_bench", lambda agente=None: ({"score": None}, "x"))
    monkeypatch.setattr(ev, "informe_markdown", lambda *a, **k: "# x")
    r = mod.evals(dir_runs=str(dentro / "runs"), salida=str(fuera))
    assert r.startswith("ERROR: ruta fuera")
    assert not fuera.exists()
    ok = mod.evals(dir_runs=str(dentro / "runs"), salida=str(dentro / "out"))
    assert ok.startswith("Informe de evals generado") and any((dentro / "out").glob("*.md"))


# 3/4 memoria
def test_resumen_sesion_no_sigue_symlink_colgante(tmp_path, monkeypatch):
    import modules.memoria as mem

    biblio = tmp_path / "mem"
    biblio.mkdir()
    fuera = tmp_path / "fuera.md"
    os.symlink(fuera, biblio / f"sesion_{date.today().isoformat()}.md")
    monkeypatch.setenv("MEMORIA_DIR", str(biblio))
    destino = mem.guardar_resumen_sesion("resumen")
    assert not fuera.exists(), "no debe crear el archivo fuera de memoria/"
    assert destino is not None and destino.parent == biblio.resolve() and not destino.is_symlink()


def test_memory_search_no_sigue_symlinks(tmp_path, monkeypatch):
    import modules.memoria as mem

    biblio = tmp_path / "mem"
    biblio.mkdir()
    (tmp_path / "privado.md").write_text("MARCADOR_PRIVADO\n", encoding="utf-8")
    os.symlink(tmp_path / "privado.md", biblio / "enlace.md")
    (biblio / "propia.md").write_text("nota propia\n", encoding="utf-8")
    monkeypatch.setenv("MEMORIA_DIR", str(biblio))
    r = mem.memory_search("MARCADOR_PRIVADO")
    assert "L1: MARCADOR_PRIVADO" not in r and "enlace.md" not in r
    assert "propia.md" in mem.memory_search("propia")


def test_memory_save_no_pisa_symlink(tmp_path, monkeypatch):
    import modules.memoria as mem

    biblio = tmp_path / "mem"
    biblio.mkdir()
    fuera = tmp_path / "fuera.md"
    os.symlink(fuera, biblio / f"nota_{date.today().isoformat()}_x.md")
    monkeypatch.setenv("MEMORIA_DIR", str(biblio))
    assert mem.memory_save("x", "y").startswith("ERROR")
    assert not fuera.exists()


def test_memory_search_sin_argumentos_lista(tmp_path, monkeypatch):
    """El schema dice query opcional: run_tool_call con {} no debe dar TypeError."""
    import modules.memoria as mem
    from utils.fs_tools import run_tool_call

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    (tmp_path / "a.md").write_text("x\n", encoding="utf-8")
    r = run_tool_call({"id": "1", "function": {"name": "memory_search", "arguments": "{}"}},
                      mem.IMPL)
    assert r["content"].startswith("Biblioteca de memoria")


# 6 presupuesto
@pytest.mark.parametrize("contenido", [None, "cierre parcial"])
def test_presupuesto_agotado_ignora_tool_calls_nativos(monkeypatch, contenido):
    import nodes

    monkeypatch.setenv("CHAT_STREAM", "0")
    msg = NS(content=contenido, tool_calls=[NS(id="1", function=NS(name="read_file", arguments="{}"))])
    monkeypatch.setattr(nodes, "call_llm_agent", lambda m, t: msg)
    shared = {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
              "tool_rounds": 99}
    accion = nodes.AgentStep()._run(shared)
    assert accion == "answer"
    ultimo = shared["messages"][-1]
    assert "tool_calls" not in ultimo
    assert ultimo["content"] == (contenido or nodes.MENSAJE_DSML_AGOTADO)


def test_stream_cortado_no_despacha_tool_calls(monkeypatch):
    import utils.call_llm as cl

    frag = NS(index=0, id="c1", function=NS(name="run_command", arguments='{"comm'))
    chunks = [NS(choices=[NS(delta=NS(content=None, tool_calls=[frag]))])]

    def stream():
        yield from chunks
        raise KeyboardInterrupt

    class Cliente:
        chat = NS(completions=NS(create=lambda **k: stream()))

    monkeypatch.setattr(cl, "_client", lambda: Cliente())
    monkeypatch.setenv("CHAT_STREAM_INTERRUPT", "1")
    r = cl.call_llm_agent_stream([{"role": "user", "content": "x"}], tools=[{}])
    assert r.tool_calls is None


def test_stream_completo_descarta_fragmento_sin_nombre(monkeypatch):
    import utils.call_llm as cl

    buenos = NS(index=0, id="c1", function=NS(name="read_file", arguments="{}"))
    rotos = NS(index=1, id=None, function=NS(name=None, arguments="{}"))
    chunks = [NS(choices=[NS(delta=NS(content=None, tool_calls=[buenos, rotos]))])]

    class Cliente:
        chat = NS(completions=NS(create=lambda **k: iter(chunks)))

    monkeypatch.setattr(cl, "_client", lambda: Cliente())
    r = cl.call_llm_agent_stream([{"role": "user", "content": "x"}], tools=[{}])
    assert [tc.function.name for tc in r.tool_calls] == ["read_file"]


# 7 sql
@pytest.fixture
def base(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    con = sqlite3.connect(p)
    con.execute("create table t(x)")
    con.executemany("insert into t values(?)", [(i,) for i in range(2000)])
    con.commit()
    con.close()
    monkeypatch.setenv("DB_PATH", str(p))
    import modules.db as db

    return db


def _filas(r):
    return r.count("\n") - 1


def test_sql_tope_por_defecto(base):
    assert _filas(base.sql("select * from t")) == 50


@pytest.mark.parametrize("q", ["select * from t LIMIT -1", "select * from t limit 0-1",
                               "select * from t limit 10-11", "select * from t limit 0",
                               "select * from t limit (select -1)"])
def test_sql_limit_no_positivo(base, q):
    assert base.sql(q).startswith("ERROR")


@pytest.mark.parametrize("q", ["select * from t -- limit", "select * from t /* limit */"])
def test_sql_sin_comentarios(base, q):
    assert base.sql(q).startswith("ERROR: sin comentarios")


def test_sql_techo_duro(base):
    assert _filas(base.sql("select * from t limit 5000")) == base.MAX_FILAS_DURO


def test_sql_conexion_solo_lectura(base):
    con = base._con()
    with pytest.raises(sqlite3.OperationalError):
        con.execute("insert into t values (1)")
    con.close()


@pytest.mark.parametrize("q", ["select * from t limit 10", "select * from t limit 10 offset 5",
                               "select * from t limit 5, 10", "select * from (select * from t limit 3)"])
def test_sql_limit_legitimo(base, q):
    assert not base.sql(q).startswith("ERROR")


def test_sql_literal_con_doble_guion_sigue_valido(base):
    assert not base.sql("select * from t where x = '--' ").startswith("ERROR")


# 8 baseline
def test_comparar_baseline_con_bench_degradado(tmp_path):
    import evals as ev

    ruta = tmp_path / "b.json"
    ruta.write_text(json.dumps({"score": 0.9, "ece": 0.05}), encoding="utf-8")
    r = ev.comparar_baseline({"score": None, "ece": None, "estado": "no disponible"}, ruta=ruta)
    assert r["veredicto"] == "SIN BENCH"


# 10 umbral
@pytest.mark.parametrize("valor", ["nan", "1.5", "-0.1", "inf", "abc"])
def test_umbral_invalido_usa_default(monkeypatch, valor):
    from utils.laya_routing import config_router, config_voto, decide

    monkeypatch.setenv("LAYA_UNSURE_HIGH", valor)
    monkeypatch.setenv("LAYA_UNSURE_HIGH_VOTO", valor)
    monkeypatch.delenv("LAYA_CALIBRACION_ROUTER", raising=False)
    cfg = config_router()
    assert cfg.umbral == 0.85 and config_voto().umbral == 0.7
    propuesta, _, _ = decide({"choice": "directo",
                              "probabilities": {"directo": 0.51, "herramientas": 0.49}}, cfg)
    assert propuesta == "herramientas"


# 11 mcp
def test_mcp_server_envuelve_por_run_tool_call(monkeypatch):
    import inspect

    import mcp_server
    from utils.fs_tools import HOOKS_PRE

    corrio = []

    def impl(command):
        corrio.append(command)
        return "corrió"

    monkeypatch.setitem(HOOKS_PRE, "zz_cmd", [lambda tc: "ERROR: vetado (test)"])
    f = mcp_server.envolver("zz_cmd", impl, {"zz_cmd": impl})
    assert list(inspect.signature(f).parameters) == ["command"]  # FastMCP arma el schema de acá
    assert f(command="rm -rf /") == "ERROR: vetado (test)" and not corrio


# estabilidad
def test_discover_saltea_modulo_roto(tmp_path, monkeypatch, capsys):
    import modules

    roto = Path(modules.__path__[0]) / "zz_roto_test.py"
    roto.write_text("raise ImportError('a propósito')\n", encoding="utf-8")
    try:
        tools, impls = modules.discover()
        assert "run_command" in impls
        assert "zz_roto_test no cargó" in capsys.readouterr().err
    finally:
        roto.unlink()
        sys.modules.pop("modules.zz_roto_test", None)


def test_validar_historial_detecta_tool_huerfano():
    from utils.compaccion import validar_historial

    assert validar_historial([{"role": "system", "content": "s"},
                              {"role": "tool", "tool_call_id": "x", "content": "r"}])
    valido = [{"role": "system", "content": "s"},
              {"role": "assistant", "content": None,
               "tool_calls": [{"id": "a", "type": "function", "function": {"name": "f", "arguments": "{}"}}]},
              {"role": "tool", "tool_call_id": "a", "content": "r"}]
    assert validar_historial(valido) == []


@pytest.mark.parametrize("contenido, ok", [
    ("exit 0\nbien", True), ("exit 1\nmal", False), ("exit -9\n", False),
    ("RECHAZADO por el usuario", False), ("ERROR: x", False), ("Escrito: a.py", True),
    ("exit 10 años de historia", False),
])
def test_traza_ok_refleja_exit_y_rechazo(contenido, ok):
    from nodes import resultado_ok

    assert resultado_ok(contenido) is ok


@pytest.mark.parametrize("cmd", ["rm -rf / --no-preserve-root", "rm -rf --no-preserve-root /"])
def test_denylist_no_preserve_root_en_cualquier_orden(cmd):
    from modules.coding import _PROHIBIDOS

    assert _PROHIBIDOS.search(cmd)
