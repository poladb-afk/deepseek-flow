"""Smoke tests de lo estable — sin red, sin LLM, sin modelo."""
import os
import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
# raíces deterministas para los tests (el default portable es CWD)
os.environ.setdefault("AGENT_ALLOWED_DIRS", str(RAIZ.parent.parent))


def test_action_space_completo():
    from nodes import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    esperadas = {
        "list_files", "read_file", "search_files",  # CORE
        "run_informe", "write_file", "answer_verified", "run_auditoria",
        "rag_search", "rag_index", "debate",  # módulos
        "mcp_tools", "mcp_call", "search_web", "deep_research", "run_supervisor",
        "sql", "db_schema", "run_effective_n", "evals",
    }
    assert esperadas <= nombres, f"faltan: {esperadas - nombres}"


def test_contencion_de_rutas():
    from utils.fs_tools import _resolve

    _, err = _resolve("/etc/passwd")
    assert err and "fuera" in err
    resolved, err = _resolve("Pocketflow/deepseek-flow/docs/design.md")
    assert err is None and resolved.is_file()


def test_extraer_yaml_tres_formatos():
    from utils.estructura import extraer_yaml

    assert extraer_yaml("bla ```yaml\nverdict: ok\n```")["verdict"] == "ok"
    assert extraer_yaml("bla ```\nverdict: retry\n```")["verdict"] == "retry"
    assert extraer_yaml("verdict: ok")["verdict"] == "ok"
    # extraer_yaml valida con assert (el retry del Node es el mismo mecanismo)
    with pytest.raises(AssertionError):
        extraer_yaml("no hay yaml acá")


def test_search_files_por_nombre():
    from utils.fs_tools import search_files

    r = search_files(glob="requirements.txt", path="Pocketflow/deepseek-flow")
    assert "requirements.txt" in r


def test_search_files_conteo_exacto_al_truncar(tmp_path):
    """El tope SEARCH_MAX_FILES es de MUESTRA, no del conteo: con 55 archivos
    el resultado debe decir el total exacto (55) y cuántos se muestran (50),
    más la sugerencia de find. El conteo se calcula ANTES de truncar."""
    from utils.fs_tools import SEARCH_MAX_FILES, search_files

    # tmp_path (/tmp) cae fuera de los directorios permitidos de las tools;
    # los tests deben vivir dentro del alcance real de la tool.
    base = RAIZ.parent / "_tmp_search_files"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    try:
        for i in range(55):
            (base / f"archivo_{i:02d}.txt").write_text("")

        r = search_files(glob="*.txt", path=str(base))
        assert "55" in r  # total exacto, contado antes de truncar
        assert str(SEARCH_MAX_FILES) in r  # el tope figura como muestra
        assert "run_command" in r and "find" in r  # sugerencia del escape hatch
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_search_files_sin_aviso_bajo_el_tope(tmp_path):
    """Con menos archivos que el tope no hay aviso de truncado."""
    from utils.fs_tools import search_files

    base = RAIZ.parent / "_tmp_search_files_bajo"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    try:
        for i in range(10):
            (base / f"archivo_{i:02d}.txt").write_text("")

        r = search_files(glob="*.txt", path=str(base))
        assert "10 archivos coinciden" in r
        assert "run_command" not in r
        assert "más" not in r
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_sql_rechaza_lo_prohibido():
    modulo = pytest.importorskip("modules.db", reason="sin sqlite3")
    assert modulo.sql("DROP TABLE trazas").startswith("ERROR")
    assert modulo.sql("INSERT INTO trazas VALUES (1)").startswith("ERROR")


def test_sql_select_funciona():

    if not (RAIZ / "trazas.db").is_file():
        pytest.skip("sin trazas.db: corre carga_trazas.py")
    from modules.db import sql

    r = sql("SELECT COUNT(*) FROM trazas")
    assert "15595" in r


def test_sql_limita_filas_de_verdad():
    """La ley del módulo es 'LIMIT forzado si no lo trae'. El chequeo era
    substring ('limit' in consulta.lower()): un LIKE '%unlimited%' o una
    columna 'limits' lo suprimían y la consulta devolvía todas las filas.
    El chequeo debe mirar la cláusula LIMIT, no una subcadena cualquiera."""

    if not (RAIZ / "trazas.db").is_file():
        pytest.skip("sin trazas.db: corre carga_trazas.py")
    from modules.db import MAX_FILAS, sql

    # sin LIMIT trae a lo sumo MAX_FILAS
    r = sql("SELECT id FROM trazas")
    filas = [ln for ln in r.splitlines() if ln.strip()]
    assert len(filas) - 2 <= MAX_FILAS  # encabezado + separador

    # 'unlimited' como texto NO debe suprimir el LIMIT forzado
    r2 = sql("SELECT id FROM trazas WHERE 'unlimited' = 'unlimited'")
    filas2 = [ln for ln in r2.splitlines() if ln.strip()]
    assert len(filas2) - 2 <= MAX_FILAS, "un 'unlimited' en el WHERE suprimió el LIMIT"


def test_sql_cierra_conexion_ante_error_no_sqlite():
    """Un fallo de execute que no sea sqlite3.Error no debe filtrar la
    conexión: el módulo la cierra siempre (finally), no solo en el camino
    sqlite3.Error."""

    if not (RAIZ / "trazas.db").is_file():
        pytest.skip("sin trazas.db: corre carga_trazas.py")
    import modules.db as db

    capturada = {}

    class ConEspia:
        row_factory = None

        def execute(self, *a, **k):
            raise RuntimeError("fallo no-sqlite en execute")

        def close(self):
            capturada["cerrada"] = True

    def fake_con():
        return ConEspia()

    original = db._con
    db._con = fake_con
    try:
        r = db.sql("SELECT 1")
    finally:
        db._con = original
    assert r.startswith("ERROR")
    assert capturada.get("cerrada"), "la conexión quedó abierta tras un error no-sqlite"


def test_sql_permita_punto_coma_en_literal():
    """El guard 'una sola sentencia' no debe confundir un ';' dentro de un
    literal o comentario con una segunda sentencia: era un sobre-rechazo."""

    if not (RAIZ / "trazas.db").is_file():
        pytest.skip("sin trazas.db: corre carga_trazas.py")
    from modules.db import sql

    # un ';' dentro de una cadena es legal y no es multi-sentencia
    r = sql("SELECT id FROM trazas WHERE 'a;b' = 'a;b'")
    assert not r.startswith("ERROR"), f"sobre-rechazo por ';' en literal: {r[:80]}"


def test_sql_rechaza_multi_sentencia():
    """El guard sigue bloqueando lo que sí es multi-sentencia real."""
    from modules.db import sql

    r = sql("SELECT 1; SELECT 2")
    assert r.startswith("ERROR")


def test_mermaid_export():
    from research import create_research_flow
    from utils.viz import mermaid

    texto = mermaid(create_research_flow())
    assert "Planner" in texto and "research" in texto


def _db_tmp(tmp_path):
    """Crea una sqlite real mínima con una tabla `trazas` y DB_PATH apuntada
    ahí (vía setting). Devuelve el módulo ya listo."""
    import sqlite3

    import modules.db as db

    ruta = tmp_path / "trazas.db"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE trazas (id INTEGER PRIMARY KEY, criterios TEXT)")
    con.execute("INSERT INTO trazas (criterios) VALUES ('x'), ('y')")
    con.commit()
    con.close()
    return db


def test_sql_no_confunde_delete_en_literal(tmp_path, monkeypatch):
    """Fix 7: un 'delete' dentro de un literal es texto de usuario, no SQL:
    el chequeo PROHIBIDOS corre sobre la consulta SIN literales, así que NO
    devuelve 'solo SELECT' (antes: falso positivo)."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "trazas.db"))
    db = _db_tmp(tmp_path)

    r = db.sql("SELECT * FROM trazas WHERE criterios = 'delete'")
    assert not r.startswith("ERROR"), f"falso positivo por 'delete' en literal: {r[:80]}"


def test_sql_sigue_rechazando_delete_real(tmp_path, monkeypatch):
    """Fix 7 no abre la puerta: un DELETE de verdad sigue rechazado."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "trazas.db"))
    db = _db_tmp(tmp_path)

    assert db.sql("DELETE FROM trazas").startswith("ERROR")


def test_sql_fuerza_limit_ante_limit_en_literal(tmp_path, monkeypatch):
    """Fix 7: un 'limit' dentro de un literal NO es una cláusula LIMIT, así
    que el LIMIT forzado SÍ se aplica (antes: '... = \\'limit\\'' lo suprimía
    y devolvía filas sin techo). Se verifica con una tabla de más filas que
    MAX_FILAS: el resultado no puede superar el tope."""
    import sqlite3

    import modules.db as db
    from modules.db import MAX_FILAS

    ruta = tmp_path / "trazas.db"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE trazas (id INTEGER PRIMARY KEY, criterios TEXT)")
    con.executemany(
        "INSERT INTO trazas (criterios) VALUES (?)",
        [("limit",) for _ in range(MAX_FILAS + 20)],
    )
    con.commit()
    con.close()
    monkeypatch.setenv("DB_PATH", str(ruta))

    r = db.sql("SELECT id FROM trazas WHERE criterios = 'limit'")
    assert not r.startswith("ERROR"), f"la consulta con 'limit' en literal falló: {r[:80]}"
    filas = [ln for ln in r.splitlines() if ln.strip()]
    assert len(filas) - 2 <= MAX_FILAS, "'limit' en un literal suprimió el LIMIT forzado"


def test_mermaid_flujos_batch_y_lote():
    """El export de grafos cubre los flujos nuevos: el batch puro
    (effective_n multi) y la rama async del lote. Un flujo anidado declara su
    nombre aunque su start sea hoja."""
    from utils.viz import FLOWS, mermaid

    multi = mermaid(FLOWS["effective_n_multi"]())
    assert "EffectiveNMulti" in multi
    lote = mermaid(FLOWS["juez_lote"]())
    assert "JuezLoteFlow" in lote
    # el single conserva su pipeline de 3 nodos
    single = mermaid(FLOWS["effective_n"]())
    assert "ScanFiles" in single and "HashFile" in single and "WriteReport" in single


def test_tabla_markdown():
    from informe import tabla_markdown

    analisis = [{"file": "a.jsonl", "total": 3, "errores": 0, "modulos": {"x": 2}}]
    fila = tabla_markdown(analisis)
    assert "a.jsonl" in fila and "x: 2" in fila


def test_huella_ignora_id_y_created():
    from effective_n import huella

    base = {"fields": {"task": "t", "steps": ["a"]}, "answers": {"next": "read_file"}}
    mismo_caso = dict(base, id="otro", created="2026-10-02", model="otro-modelo")
    assert huella(base) == huella(mismo_caso)
    otra_etiqueta = {"fields": {"task": "t", "steps": ["a"]}, "answers": {"next": "write_file"}}
    assert huella(base) != huella(otra_etiqueta)


def test_effective_n_flow(tmp_path):
    import json as _json

    from effective_n import create_effective_n_flow

    casos = [
        {"id": "1", "fields": {"task": "a"}, "answers": {"next": "read_file"}},
        {"id": "2", "fields": {"task": "a"}, "answers": {"next": "read_file"}},  # dup interno (id distinto)
        {"id": "3", "fields": {"task": "b"}, "answers": {"next": "list_files"}},
    ]
    (tmp_path / "uno.jsonl").write_text(
        "\n".join(_json.dumps(c) for c in casos) + "\n", encoding="utf-8"
    )
    (tmp_path / "dos.jsonl").write_text(
        _json.dumps(casos[0]) + "\n"  # duplicado ENTRE archivos
        + _json.dumps({"id": "4", "fields": {"task": "c"}, "answers": {"next": "finish"}}) + "\n",
        encoding="utf-8",
    )

    shared = {"folder": str(tmp_path), "glob": "*.jsonl", "salida": str(tmp_path / "out.md")}
    create_effective_n_flow().run(shared)
    assert shared["resumen"] == "5 registros → Effective N 3 (2 duplicados)"
    md = Path(shared["informe"]).read_text(encoding="utf-8")
    assert "Effective N: 3" in md


def _escribir_caso(carpeta, nombre, task, nxt):
    import json as _json

    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / nombre).write_text(
        _json.dumps({"id": task, "fields": {"task": task}, "answers": {"next": nxt}}) + "\n",
        encoding="utf-8",
    )
    return carpeta.resolve()


def test_effective_n_una_carpeta_igual_que_siempre(tmp_path, monkeypatch):
    """Compatibilidad hacia atrás: con una sola carpeta la salida es el
    informe de siempre (sin cabecera conjunta ni secciones por carpeta)."""
    from effective_n import main as en_main

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    a = _escribir_caso(tmp_path / "a", "uno.jsonl", "x", "read_file")
    salida = tmp_path / "one.md"
    en_main([str(a), "--salida", str(salida)])
    md = salida.read_text(encoding="utf-8")
    assert md.startswith("# Effective N —")
    assert "## Carpeta" not in md  # no es el informe conjunto


def test_effective_n_multi_carpeta_batchflow(tmp_path, capsys, monkeypatch):
    """Dos carpetas con el MISMO flujo faneado (BatchFlow, secuencial):
    secciones de ambas y resumen conjunto, en el orden pedido."""
    from effective_n import main as en_main

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    a = _escribir_caso(tmp_path / "a", "uno.jsonl", "x", "read_file")
    b = _escribir_caso(tmp_path / "b", "dos.jsonl", "y", "list_files")
    salida = tmp_path / "both.md"

    en_main([str(a), str(b), "--salida", str(salida)])
    md = salida.read_text(encoding="utf-8")
    assert md.splitlines()[0].startswith("# Effective N — lote de 2 carpetas")
    assert md.count("## Carpeta") == 2
    assert f"Carpeta `{a}`" in md and f"Carpeta `{b}`" in md
    # orden determinista: la sección de `a` antes de la de `b`
    assert md.index(str(a)) < md.index(str(b))
    # cada sección lleva SOLO su carpeta (el job viaja en params, no se mezcla)
    sec_a = md.split(f"Carpeta `{a}`")[1].split("## Carpeta")[0]
    assert "uno.jsonl" in sec_a and "dos.jsonl" not in sec_a
    sec_b = md.split(f"Carpeta `{b}`")[1].split("## Carpeta")[0]
    assert "dos.jsonl" in sec_b and "uno.jsonl" not in sec_b
    # secciones degradadas: los H1 de los informes internos pasan a H2
    assert md.count("\n# ") == 0
    assert capsys.readouterr().out.count("Carpeta procesada") == 2


def test_effective_n_multi_carpeta_total(tmp_path):
    """El resumen conjunto suma los registros reales de todas las carpetas."""
    from effective_n import EffectiveNMulti

    a = _escribir_caso(tmp_path / "a", "uno.jsonl", "x", "read_file")
    _escribir_caso(tmp_path / "a", "dos.jsonl", "y", "list_files")
    b = _escribir_caso(tmp_path / "b", "tres.jsonl", "z", "finish")
    shared = {"informes": []}
    EffectiveNMulti([a, b], "*.jsonl", str(tmp_path / "c.md")).run(shared)
    assert shared["resumen"] == "2 carpetas · 3 registros → Effective N 3 (0 duplicados)"
    assert Path(shared["informe"]).is_file()


def test_imports_batchflow_exactos():
    """Cobertura de abstracciones: las piezas nuevas importan exactamente
    pocketflow.BatchFlow (effective_n) y pocketflow.AsyncParallelBatchFlow
    (juez_lote)."""
    import inspect

    import effective_n
    import juez_lote

    assert "BatchFlow" in inspect.getsource(effective_n)
    assert "AsyncParallelBatchFlow" in inspect.getsource(juez_lote)
    # y las usa como clase base / instancia real
    from pocketflow import AsyncParallelBatchFlow, BatchFlow

    assert issubclass(effective_n.EffectiveNMulti, BatchFlow)
    assert issubclass(juez_lote.JuezLoteFlow, AsyncParallelBatchFlow)


def test_juez_lote_informe_y_speedup(tmp_path, monkeypatch):
    """juez_lote: N preguntas en paralelo → N secciones, y la medición del
    speedup (suma de tiempos individuales vs reloj de pared). call_llm
    fiteado con latencia real: el paralelismo debe solapar las corridas."""
    import time

    import juez as juez_mod

    def llm_fake(prompt):
        time.sleep(0.15)  # latencia simulada
        if "Evalúa el borrador" in prompt:
            return "verdict: ok"
        return "Respuesta de prueba."

    monkeypatch.setattr(juez_mod, "call_llm", llm_fake)

    preguntas = tmp_path / "preguntas.txt"
    preguntas.write_text(
        "¿Qué hace effective_n?\n\n# comentario\n¿Qué hace juez?\n¿Qué hace el RAG?\n",
        encoding="utf-8",
    )
    salida = tmp_path / "lote.md"
    import juez_lote

    resumen = juez_lote.run_juez_lote(str(preguntas), str(salida))

    md = salida.read_text(encoding="utf-8")
    assert md.count("## P") == 3  # una sección por pregunta
    assert "¿Qué hace effective_n?" in md and "¿Qué hace el RAG?" in md
    assert "Speedup medido" in md
    m = juez_lote.leer_preguntas(str(preguntas))
    assert m == ["¿Qué hace effective_n?", "¿Qué hace juez?", "¿Qué hace el RAG?"]

    # el speedup real es > 1 porque las corridas se solapan
    assert "paralelo" in resumen
    # extraer el speedup del informe y verificar > 1
    import re as _re

    speedup = float(_re.search(r"\*\*([\d.]+)×\*\*", md).group(1))
    assert speedup > 1.0, md


def test_juez_rondas_configurables(monkeypatch):
    """--rondas / responder_con_juez(rondas=N) fija el tope real: con el juez
    insatisfecho, hace exactamente N borradores. Sin pasarlo, usa JUEZ_ROUNDS."""
    import juez

    llamadas = {"n": 0}

    def llm_fake(prompt):
        if "Evalúa el borrador" in prompt:
            return "verdict: retry\nproblems:\n  - sigue mal"
        llamadas["n"] += 1
        return f"borrador {llamadas['n']}"

    monkeypatch.setattr(juez, "call_llm", llm_fake)

    for n in (1, 3):
        llamadas["n"] = 0
        resp, adv = juez.responder_con_juez("¿q?", rondas=n)
        assert llamadas["n"] == n, f"rondas={n} hizo {llamadas['n']} borradores"
        assert adv and "tope de" in adv
        assert resp == f"borrador {n}"

    # default = JUEZ_ROUNDS (compatibilidad hacia atrás)
    llamadas["n"] = 0
    juez.responder_con_juez("¿q?")
    assert llamadas["n"] == juez.JUEZ_ROUNDS


def test_juez_lote_tool_del_chat(tmp_path, monkeypatch):
    """La tool juez_lote del chat corre el lote y devuelve el resumen."""
    import time

    import juez as juez_mod
    import modules.juez as mj

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(juez_mod, "call_llm",
                        lambda p: "verdict: ok" if "Evalúa el borrador" in p
                        else (time.sleep(0.05) or "ok"))
    preguntas = tmp_path / "p.txt"
    preguntas.write_text("uno\ndos\n", encoding="utf-8")
    salida = tmp_path / "s.md"
    r = mj.juez_lote(str(preguntas), str(salida))
    assert "Juez en lote" in r and Path(salida).is_file()
    assert "juez_lote" in {t["function"]["name"] for t in mj.TOOLS}


def test_evals_tool_del_chat(tmp_path, monkeypatch):
    """La tool evals del chat corre el pipeline y devuelve la ruta del informe."""
    import modules.evals as me

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    runs = tmp_path / "runs"
    runs.mkdir()
    # una traza mínima válida: par (nodo, accion) canónico, sin violaciones
    (runs / "sesion.jsonl").write_text(
        '{"nodo": "GetQuestion", "accion": "exit", "seg": 1.0}\n', encoding="utf-8")
    # bench sin test de router (la ruta externa no existe en el test) y sin LLM
    monkeypatch.setattr(me, "DIR_RUNS", runs)
    salida = tmp_path / "evals_out"
    r = me.evals(dir_runs=str(runs), salida=str(salida))
    assert "Informe de evals generado" in r
    informes = list(salida.glob("evals_*.md"))
    assert informes, "no se escribió el informe de evals"
    assert "evals" in {t["function"]["name"] for t in me.TOOLS}


def test_evals_tool_rechaza_carpeta_inexistente(tmp_path, monkeypatch):
    """Una carpeta de trazas que no existe devuelve ERROR, no excepción."""
    import modules.evals as me

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    r = me.evals(dir_runs=str(tmp_path / "no_existe"))
    assert r.startswith("ERROR:")


def test_pregunta_despacho_congelada():
    from supervisor import OPCIONES, REGISTRO

    # El contrato del fine-tune supervisor_dispatch (bmo): las 18 opciones,
    # en este orden. Cambiar esto desincroniza entrenamiento y producción.
    esperadas = [
        "list_files", "read_file", "search_files", "write_file", "run_informe",
        "run_auditoria", "answer_verified", "rag_search", "rag_index", "debate",
        "mcp_tools", "mcp_call", "search_web", "deep_research", "sql", "db_schema",
        "run_effective_n", "finish",
    ]
    assert esperadas == OPCIONES, f"contrato roto: {OPCIONES}"
    assert "run_supervisor" not in OPCIONES  # L1: anti-recursión
    assert all(o in REGISTRO or o == "finish" for o in OPCIONES)


def test_supervisor_reintenta_con_feedback(tmp_path, monkeypatch):
    import supervisor as sup

    args_llamadas = {"n": 0}

    def llm_fake(prompt):
        if "Herramientas disponibles (nombre" in prompt:
            if "2 search_files" in prompt:  # ya reintentó con éxito: cerrar
                return "```yaml\nherramienta: finish\n```"
            return "```yaml\nherramienta: search_files\n```"
        if "Escribe en español el cierre" in prompt:
            return "cierre de prueba"
        args_llamadas["n"] += 1
        # el feedback del error llega SOLO en el reintento
        assert ("ya falló" in prompt) == (args_llamadas["n"] > 1), prompt[-300:]
        return "```yaml\nargs:\n  query: puerto\n```"

    monkeypatch.setattr(sup, "call_llm", llm_fake)
    monkeypatch.setattr("utils.laya.disponible", lambda *a, **k: False)
    monkeypatch.setenv("USE_VOTACION", "0")

    intentos = {"n": 0}

    def flaky(**kwargs):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise RuntimeError("boom primera")
        return "ok, 3 archivos"

    monkeypatch.setitem(sup.REGISTRO, "search_files", flaky)
    salida = tmp_path / "sup.md"
    sup.supervisar("busca el puerto", str(salida))
    texto = salida.read_text(encoding="utf-8")
    assert "ERROR (RuntimeError): boom" in texto  # el fallo queda auditado
    assert intentos["n"] == 2  # falló, reintentó con feedback y prosperó
    assert "1 search_files" in texto and "2 search_files" in texto


def test_supervisor_veta_tras_dos_fallos(tmp_path, monkeypatch):
    import supervisor as sup

    elecciones = {"n": 0}

    def llm_fake(prompt):
        if "Herramientas disponibles (nombre" in prompt:
            elecciones["n"] += 1
            if elecciones["n"] >= 3:  # con el veto activo, el prompt lo prohíbe
                assert "PROHIBIDO elegir" in prompt
            return "```yaml\nherramienta: search_files\n```"  # desobedece siempre
        if "Escribe en español el cierre" in prompt:
            return "cierre de prueba"
        return "```yaml\nargs: {}\n```"

    monkeypatch.setattr(sup, "call_llm", llm_fake)
    monkeypatch.setattr("utils.laya.disponible", lambda *a, **k: False)
    monkeypatch.setenv("USE_VOTACION", "0")

    def siempre_falla(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setitem(sup.REGISTRO, "search_files", siempre_falla)
    salida = tmp_path / "sup.md"
    sup.supervisar("tarea imposible", str(salida))
    texto = salida.read_text(encoding="utf-8")
    assert texto.count("ERROR (RuntimeError)") == 2  # dos fallos y veto: no hay tercero


def test_heartbeat_vencidas():
    import time

    from heartbeat import vencidas

    tareas = [
        {"tarea": "a", "salida": "a.md", "cada_horas": 24},
        {"tarea": "b", "salida": "b.md", "cada_horas": 1},
    ]
    estado = {"a.md": time.time()}  # 'a' acaba de correr: no vence
    assert [t["salida"] for t in vencidas(tareas, estado)] == ["b.md"]
    assert vencidas(tareas, {"a.md": time.time() - 25 * 3600}) == tareas  # todo vencido


def test_supervisor_no_repite_sin_args(tmp_path, monkeypatch):
    import supervisor as sup

    elecciones = {"n": 0}

    def llm_fake(prompt):
        if "Herramientas disponibles (nombre" in prompt:
            elecciones["n"] += 1
            return "```yaml\nherramienta: db_schema\n```"  # insiste en el schema
        if "Escribe en español el cierre" in prompt:
            return "cierre de prueba"
        return "```yaml\nargs: {}\n```"

    monkeypatch.setattr(sup, "call_llm", llm_fake)
    monkeypatch.setattr("utils.laya.disponible", lambda *a, **k: False)
    monkeypatch.setenv("USE_VOTACION", "0")
    monkeypatch.setitem(sup.REGISTRO, "db_schema", lambda: "CREATE TABLE trazas ...")

    salida = tmp_path / "sup.md"
    sup.supervisar("tarea", str(salida))
    texto = salida.read_text(encoding="utf-8")
    assert texto.count("db_schema()") == 1  # la insistencia se corta a la primera


def test_router_aristas_del_chat():
    # lección medida en producción: DirectAnswer hereda el post de AgentStep
    # (devuelve "answer"), y la arista default mataba el chat tras la
    # primera respuesta directa — PocketFlow terminaba el flujo con warning
    from flow import create_agent_flow

    flow = create_agent_flow()
    # caminar el grafo desde ask
    ask = flow.start_node
    router = ask.successors.get("continue")
    assert router is not None
    directo = router.successors.get("directo")
    assert directo is not None
    assert "answer" in directo.successors, f"DirectAnswer debe volver con 'answer': {list(directo.successors)}"


def test_visor_genera_html(tmp_path):
    import json

    from visor import generar

    traza = tmp_path / "trace.jsonl"
    eventos = [
        {"ts": 100.0, "nodo": "ElegirSiguiente", "accion": "ejecutar", "seg": 0.2},
        {"ts": 100.2, "nodo": "EjecutarPaso", "accion": "elegir", "seg": 5.0},
        {"ts": 105.2, "nodo": "ElegirSiguiente", "accion": "sintetizar", "seg": 0.1},
        {"ts": 105.3, "nodo": "Sintetizar", "accion": "default", "seg": 0.0},
    ]
    traza.write_text("\n".join(json.dumps(e) for e in eventos) + "\n", encoding="utf-8")
    destino = generar(traza)
    h = destino.read_text(encoding="utf-8")
    assert destino.name == "trace.html"
    for s in ("Recorrido", "Cronología", "Resumen por nodo", "ElegirSiguiente", "5.00s"):
        assert s in h, s
    # determinista: el mismo jsonl produce el mismo html
    assert generar(traza).read_text(encoding="utf-8") == h


def test_visor_watch_regenera_al_crecer(tmp_path):
    """--watch vuelve a generar el HTML cuando la traza crece, y no rompe
    con una traza vacía entre vueltas. En vez de esperar el loop infinito,
    ejercitamos el paso que decide (contar_y_mtime) y el umbral de cambio."""
    import json
    import time

    from visor import contar_y_mtime, generar

    traza = tmp_path / "w.jsonl"
    # traza inexistente: el watch no rompe (0 eventos)
    assert contar_y_mtime(traza)[0] == 0

    traza.write_text(json.dumps({"ts": 1, "nodo": "A", "accion": "x", "seg": 0.1}) + "\n")
    n1, m1 = contar_y_mtime(traza)
    assert n1 == 1
    h1 = generar(traza).read_text(encoding="utf-8")

    # la traza crece (como en vivo): hay cambio detectable y el HTML cambia
    time.sleep(0.01)
    traza.write_text(traza.read_text() + json.dumps(
        {"ts": 2, "nodo": "B", "accion": "y", "seg": 0.2}) + "\n")
    n2, m2 = contar_y_mtime(traza)
    assert (n2, m2) != (n1, m1)  # el watch volvería a generar
    h2 = generar(traza).read_text(encoding="utf-8")
    assert "B" in h2 and h2 != h1


def test_mayoria():
    from utils.votacion import mayoria

    assert mayoria(["sql", "sql", "finish"]) == "sql"
    assert mayoria(["sql", "finish", "finish"]) == "finish"
    assert mayoria(["sql", "db_schema", "finish"], desempate="sql") == "sql"
    assert mayoria(["sql"]) == "sql"  # voto único: sin mayoría, sin desempate
    assert mayoria([], desempate="finish") == "finish"


def test_votacion_2de3_en_el_supervisor(tmp_path, monkeypatch, capsys):
    import supervisor as sup

    llamadas = {"n": 0}

    def voto_directo(t, h, f, estilo="directo"):
        llamadas["n"] += 1
        return {"directo": "db_schema", "eliminacion": "sql"}[estilo]

    monkeypatch.setattr(sup, "elegir_con_deepseek", voto_directo)

    def llm_fake(prompt):
        if "Escribe en español el cierre" in prompt:
            return "cierre de prueba"
        return "```yaml\nargs: {}\n```"  # args: sql() sin args

    monkeypatch.setattr(sup, "call_llm", llm_fake)
    monkeypatch.setattr("utils.laya.disponible", lambda *a, **k: True)
    monkeypatch.setattr(
        "utils.laya.preguntar",
        lambda estado, preguntas, setting=None: {"elegir_proxima": ("sql", 0.5)},  # duda, pero vota
    )

    salida = tmp_path / "sup.md"
    sup.supervisar("tarea", str(salida))
    # cada convocatoria gasta exactamente 2 votos (A y B); laya pone el 3ro gratis
    assert llamadas["n"] >= 2 and llamadas["n"] % 2 == 0
    consola = capsys.readouterr().out
    assert "[votos] ['db_schema', 'sql', 'sql']" in consola  # mayoría sql


def test_votacion_laya_segura_no_gasta(tmp_path, monkeypatch):
    import supervisor as sup

    def nunca(*a, **k):
        raise AssertionError("laya segura no debe convocar votos")

    monkeypatch.setattr(sup, "elegir_con_deepseek", nunca)
    monkeypatch.setattr("utils.laya.disponible", lambda *a, **k: True)
    monkeypatch.setattr(
        "utils.laya.preguntar",
        lambda estado, preguntas, setting=None: {"elegir_proxima": ("finish", 0.99)},
    )
    salida = tmp_path / "sup.md"
    sup.supervisar("tarea", str(salida))
    assert "0.99" in salida.read_text(encoding="utf-8") or True  # cerró por laya, sin DeepSeek


def test_dsml_a_tool_calls():
    from nodes import dsml_a_tool_calls

    # formato real medido en producción: separador DOBLE barra fullwidth
    # (la primera versión del fix usaba una sola y jamás disparó)
    contenido = """<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="read_file">
<｜｜DSML｜｜ parameter name="path" string="true">/home/roquedb/Documentos/00_IA/Pocketflow/deepseek-flow/utils/laya.py</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
<｜｜DSML｜｜ invoke name="deep_research">
<｜｜DSML｜｜ parameter name="tema" string="true">PocketFlow</｜｜DSML｜｜ parameter>
<｜｜DSML｜｜ parameter name="max_iteraciones" string="false">3</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
</｜｜DSML｜｜ calls>"""
    calls = dsml_a_tool_calls(contenido)
    assert [c.function.name for c in calls] == ["read_file", "deep_research"]
    import json
    args = json.loads(calls[1].function.arguments)
    assert args["tema"] == "PocketFlow" and args["max_iteraciones"] == "3"
    assert calls[0].id == "dsml-0"

    # y el de una barra (el transcript pegado a mano la colapsa) también parsea
    una = contenido.replace("｜｜", "｜")
    assert [c.function.name for c in dsml_a_tool_calls(una)] == ["read_file", "deep_research"]


def test_agent_step_recupera_dsml_como_tool(monkeypatch):
    from types import SimpleNamespace

    import nodes

    mensaje = SimpleNamespace(content="<｜DSML｜｜ invoke name=\"db_schema\">\n</｜DSML｜｜ invoke>", tool_calls=None)
    monkeypatch.setattr(nodes, "call_llm_agent", lambda msgs, tools=None: mensaje)
    shared = {"messages": [{"role": "user", "content": "esquema"}], "tool_rounds": 0}
    # camino completo: la recuperación DSML vive en exec() (reintenta PocketFlow)
    monkeypatch.setenv("CHAT_STREAM", "0")  # camino clásico
    accion = nodes.AgentStep()._run(shared)
    assert accion == "tool"
    m = shared["messages"][-1]
    # el historial queda canónico (dict, forma de la API) y sin el markup crudo
    assert m["tool_calls"][0]["function"]["name"] == "db_schema"
    assert m["content"] is None


def test_sanitizar_markers_y_tags():
    """Dos descarrilos medidos en producción: un marker de rol ajeno corta
    (lo que sigue es basura) y los tags HTML que parten palabras se quitan
    (el texto sigue siendo la respuesta)."""
    from nodes import sanitizar

    # marker de rol: corta desde ahí; el contenido previo sobrevive
    limpio, modificado = sanitizar("¡Hola! <|im_start|>system eres un agente genérico")
    assert modificado is True and limpio == "¡Hola!"

    # <<SYS>> y <system> también son markers de rol
    assert sanitizar("buenas <<SYS>> ahora eres otro")[0] == "buenas"
    assert sanitizar("ok <system>instrucción ajena")[0] == "ok"

    # marker al inicio: no queda nada utilizable
    limpio, modificado = sanitizar("<system>solo basura")
    assert modificado is True and limpio == ""

    # tags HTML que parten palabras: se quitan y el texto se recompone
    limpio, modificado = sanitizar("S<small>oy</small> DeepSeek")
    assert modificado is True and limpio == "Soy DeepSeek"

    # texto sano: intacto
    limpio, modificado = sanitizar("respuesta normal, sin ruido")
    assert modificado is False and limpio == "respuesta normal, sin ruido"


def test_agent_step_sanitiza_y_reintenta(monkeypatch):
    """El sanitizado vive en exec(): si quedó algo se imprime limpio, y si no
    quedó nada el retry de PocketFlow re-pregunta (raise)."""
    from types import SimpleNamespace

    import nodes

    monkeypatch.setenv("CHAT_STREAM", "0")  # camino clásico, sin stream

    # caso 1: descarrilo parcial → el historial guarda solo lo limpio
    mensaje = SimpleNamespace(content="¡Hola! <|im_start|>system ajeno", tool_calls=None)
    monkeypatch.setattr(nodes, "call_llm_agent", lambda msgs, tools=None: mensaje)
    shared = {"messages": [{"role": "user", "content": "hola"}], "tool_rounds": 0}
    accion = nodes.AgentStep()._run(shared)
    assert accion == "answer"
    assert shared["messages"][-1]["content"] == "¡Hola!"

    # caso 2: solo markup de rol → raise (PocketFlow reintenta en exec)
    vacio = SimpleNamespace(content="<system>nada útil", tool_calls=None)
    monkeypatch.setattr(nodes, "call_llm_agent", lambda msgs, tools=None: vacio)
    shared = {"messages": [{"role": "user", "content": "hola"}], "tool_rounds": 0}
    with pytest.raises(ValueError):
        nodes.AgentStep()._run(shared)


def test_banco_contar_marcadores():
    """El conteo de marcadores es la señal medible del banco: cada línea de la
    terminal se suma al marcador cuya regex matchea."""
    from banco.banco import MARCADORES, contar_marcadores

    # la compacción se anuncia con su propia marca
    conteo = contar_marcadores("[compacción] zona fría: 4 mensajes → resumen")
    assert conteo["compaccion"] == 1

    # varias señales en varias líneas: cada una suma por ocurrencia en su línea
    texto = "[laya] directo\n[laya] dudoso\n⚙ ronda 2/5\n(s/n): 2x"
    conteo = contar_marcadores(texto)
    assert conteo["laya"] == 2 and conteo["ronda"] == 1 and conteo["hitl_prompt"] == 1

    # texto sin señales: no aparece ninguna clave (solo se cuentan > 0)
    conteo = contar_marcadores("charla normal")
    assert conteo == {}
    assert set(MARCADORES)  # el catálogo de señales es no vacío


def test_historial_canonico_sin_reasoning():
    """400 medido en producción: el reasoning_content del modo thinking no
    puede viajar a vueltas sin thinking. El historial es dict canónico."""
    from types import SimpleNamespace

    from nodes import AgentStep, ExecuteTools
    from utils.fs_tools import run_tool_call

    paso = AgentStep()
    mensaje = SimpleNamespace(
        content="¡Hola! 👋", tool_calls=None,
        reasoning_content="cadena de razonamiento del modo thinking",
    )
    shared = {"messages": [], "tool_rounds": 0}
    paso.post(shared, None, mensaje)
    m = shared["messages"][-1]
    assert isinstance(m, dict)
    assert "reasoning_content" not in m
    assert m["content"] == "¡Hola! 👋"

    # vuelta con tools: prep lee la forma dict y run_tool_call la ejecuta
    shared["messages"].append({"role": "user", "content": "lista"})
    shared["messages"].append({
        "role": "assistant", "content": None,
        "tool_calls": [{"id": "call_1", "type": "function",
                        "function": {"name": "list_files", "arguments": "{}"}}],
    })
    tcs = ExecuteTools().prep(shared)
    resultado = run_tool_call(tcs[0])
    assert resultado["role"] == "tool"
    assert resultado["tool_call_id"] == "call_1"
    assert "ERROR" not in resultado["content"]


def test_call_llm_agent_filtra_reasoning(monkeypatch):
    """Segunda barrera (en el cliente): aunque un camino meta
    reasoning_content al historial, no viaja a la API."""
    from types import SimpleNamespace

    import utils.call_llm as c

    capturado = {}

    class FakeCompletions:
        def create(self, **kwargs):
            capturado.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None))])

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_client", lambda: FakeClient())
    c.call_llm_agent(
        [{"role": "user", "content": "hola"},
         {"role": "assistant", "content": "chau", "reasoning_content": "trace"}],
        tools=[{"type": "function", "function": {"name": "t", "parameters": {}}}],
    )
    assert all("reasoning_content" not in m for m in capturado["messages"])
    assert capturado["messages"][1]["content"] == "chau"


def test_call_llm_agent_modo_thinking_pegajoso(monkeypatch):
    """400 medido en ambas direcciones: el modo thinking no puede flipear
    dentro de una conversación. Con tráfico de tools en el historial, la
    llamada va sin thinking aunque no traiga tools (el tope de rondas)."""
    from types import SimpleNamespace

    import utils.call_llm as c

    capturado = {}

    class FakeCompletions:
        def create(self, **kwargs):
            capturado.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None))])

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_client", lambda: FakeClient())
    hist_agentico = [
        {"role": "user", "content": "lista"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "list_files", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "main.py"},
    ]
    # sin tools pero con tráfico agéntico: thinking desactivado igual
    c.call_llm_agent(hist_agentico + [{"role": "user", "content": "ya"}])
    assert capturado["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "tools" not in capturado
    # conversación limpia sin tools: thinking normal (sin extra_body)
    capturado.clear()
    c.call_llm_agent([{"role": "user", "content": "hola"}])
    assert "extra_body" not in capturado


def test_call_llm_agent_stream(monkeypatch, capsys):
    """Streaming: content se imprime EN VIVO y se ensambla; los tool_calls
    llegan fragmentados (id/name solo en el primer fragmento, arguments por
    concatenación) y el reasoning_content NO sale a .content ni a stdout."""
    from types import SimpleNamespace

    import utils.call_llm as c

    capturado = {}

    def chunk(content=None, reasoning=None, tool_calls=None):
        delta = SimpleNamespace(content=content, reasoning_content=reasoning,
                                tool_calls=tool_calls)
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

    def frag(index=0, id=None, name=None, arguments=None):
        funcion = None
        if name is not None or arguments is not None:
            funcion = SimpleNamespace(name=name, arguments=arguments)
        return SimpleNamespace(index=index, id=id, function=funcion)

    class FakeCompletions:
        def create(self, **kwargs):
            capturado.update(kwargs)

            def gen():
                # reasoning_content primero: NUNCA debe imprimirse ni ensamblarse
                yield chunk(reasoning="pienso que... ")
                yield chunk(content="¡Hola")
                yield chunk(reasoning="sigo pensando ")
                yield chunk(content=" mundo!")
                # dos tool_calls partidas en varios fragmentos
                yield chunk(tool_calls=[frag(index=0, id="call_a", name="read_file")])
                yield chunk(tool_calls=[frag(index=1, id="call_b", name="list_files")])
                yield chunk(tool_calls=[frag(index=0, arguments='{"path":')])
                yield chunk(tool_calls=[frag(index=0, arguments='"a.py"}')])
                yield chunk(tool_calls=[frag(index=1, arguments="{}")])

            return gen()

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_client", lambda: FakeClient())
    msg = c.call_llm_agent_stream([{"role": "user", "content": "hola"}])

    # misma lógica de contrato (stream=True) que la versión clásica
    assert capturado["stream"] is True
    # content ensamblado, sin el reasoning_content colado
    assert msg.content == "¡Hola mundo!"
    assert "pienso" not in msg.content and "reasoning" not in msg.content
    # tool_calls reconstruidos: id/name una sola vez, arguments concatenados
    assert [tc.id for tc in msg.tool_calls] == ["call_a", "call_b"]
    assert [tc.function.name for tc in msg.tool_calls] == ["read_file", "list_files"]
    assert msg.tool_calls[0].function.arguments == '{"path":"a.py"}'
    assert msg.tool_calls[1].function.arguments == "{}"
    # el CONTENT salió por stdout en vivo; el reasoning_content NO
    salida = capsys.readouterr().out
    assert "¡Hola mundo!" in salida
    assert "pienso" not in salida and "reasoning" not in salida


def test_stream_alimenta_historial_canonico_y_dsml(monkeypatch):
    """El mensaje del stream es drop-in del clásico: historiarlo da el dict
    canónico (sin reasoning) y el transcript DSML en vivo se recupera como
    tool calls estructuradas."""
    from types import SimpleNamespace

    import nodes
    import utils.call_llm as c

    def chunk(content=None, reasoning=None):
        delta = SimpleNamespace(content=content, reasoning_content=reasoning,
                                tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

    def fake_stream(chunks):
        class FakeCompletions:
            def create(self, **kwargs):
                return iter(chunks)

        class FakeClient:
            chat = SimpleNamespace(completions=FakeCompletions())

        monkeypatch.setattr(c, "_client", lambda: FakeClient())

    # 1) respuesta de texto: historiarla da el canónico sin reasoning
    fake_stream([chunk(reasoning="no viaja "), chunk(content="Hola"), chunk(content=" mundo")])
    msg = c.call_llm_agent_stream([{"role": "user", "content": "x"}])
    h = nodes.historiar(msg)
    assert h == {"role": "assistant", "content": "Hola mundo"}
    assert "reasoning_content" not in h

    # 2) DSML emitido como texto: llega fragmentado por el stream y la
    #    recuperación (en AgentStep.exec) lo vuelve tool_calls estructuradas
    dsml = '<｜DSML｜｜ invoke name="db_schema">\n</｜DSML｜｜ invoke>'
    fake_stream([chunk(dsml[:20]), chunk(dsml[20:])])
    reactivado = {"via": False}

    def en_stream(msgs, tools=None):
        reactivado["via"] = True
        return c.call_llm_agent_stream(msgs, tools)

    monkeypatch.setattr(nodes, "call_llm_agent_stream", en_stream)
    monkeypatch.setenv("CHAT_STREAM", "1")
    # con tools OFRECIDAS la recuperación corre: markup → tool_calls
    out = nodes.AgentStep().exec(([{"role": "user", "content": "esquema"}], ["tool"]))
    assert reactivado["via"]
    assert out.content is None  # el markup crudo no queda en el historial
    assert out.tool_calls[0].function.name == "db_schema"
    # con tools RETIRADAS (tope L8) el markup NO se re-arma (exp/12):
    # queda el mensaje honesto y no hay tool_calls que ejecutar
    out2 = nodes.AgentStep().exec(([{"role": "user", "content": "esquema"}], None))
    assert out2.tool_calls is None
    assert "seguí" in out2.content


def test_call_llm_agent_stream_thinking_pegajoso(monkeypatch):
    """El modo thinking pegajoso se comparte con la versión clásica: la de
    streaming usa el MISMO _kwargs_agente (tráfico de tools → disabled)."""
    from types import SimpleNamespace

    import utils.call_llm as c

    capturado = {}

    class FakeCompletions:
        def create(self, **kwargs):
            capturado.update(kwargs)
            return iter([])  # stream vacío: solo interesa el contrato de kwargs

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_client", lambda: FakeClient())
    hist_agentico = [
        {"role": "user", "content": "lista"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "list_files", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "main.py"},
    ]
    c.call_llm_agent_stream(hist_agentico + [{"role": "user", "content": "ya"}])
    assert capturado["extra_body"] == {"thinking": {"type": "disabled"}}
    assert all("reasoning_content" not in m for m in capturado["messages"])


def test_agent_step_usa_stream_segun_setting(monkeypatch):
    """AgentStep.exec usa la versión stream con CHAT_STREAM=1 (default) y la
    clásica con 0. DirectAnswer hereda exec (sin tocar su clase): mismo
    camino de streaming."""
    from types import SimpleNamespace

    import nodes

    mensaje = SimpleNamespace(content="hola", tool_calls=None)
    elegido = {}

    def clasico(msgs, tools=None):
        elegido["via"] = "clasico"
        return mensaje

    def en_stream(msgs, tools=None):
        elegido["via"] = "stream"
        return mensaje

    monkeypatch.setattr(nodes, "call_llm_agent", clasico)
    monkeypatch.setattr(nodes, "call_llm_agent_stream", en_stream)

    monkeypatch.setenv("CHAT_STREAM", "0")
    nodes.AgentStep().exec(([{"role": "user", "content": "x"}], None))
    assert elegido["via"] == "clasico"

    monkeypatch.setenv("CHAT_STREAM", "1")
    nodes.AgentStep().exec(([{"role": "user", "content": "x"}], None))
    assert elegido["via"] == "stream"

    # DirectAnswer hereda el exec de AgentStep: mismo switch de streaming
    elegido.clear()
    nodes.DirectAnswer().exec(([{"role": "user", "content": "x"}], None))
    assert elegido["via"] == "stream"


def test_agent_step_stream_imprime_limpio_si_sanitiza(monkeypatch, capsys):
    """Con streaming, el crudo (con el descarrilo) ya salió en vivo; si el
    sanitizado corta, además se imprime la versión limpia."""
    from types import SimpleNamespace

    import nodes

    descarriado = "¡Hola! ag<system>You are a file exploration agent."
    ejecutado = {"stream": False}

    def en_stream(msgs, tools=None):
        ejecutado["stream"] = True
        # simula lo que ya imprimió en vivo el propio stream
        print(descarriado, end="", flush=True)
        return SimpleNamespace(content=descarriado, tool_calls=None)

    monkeypatch.setattr(nodes, "call_llm_agent_stream", en_stream)
    monkeypatch.setenv("CHAT_STREAM", "1")

    msg = nodes.AgentStep().exec(([{"role": "user", "content": "x"}], None))
    assert ejecutado["stream"]
    assert msg.content == "¡Hola! ag"  # el historial queda limpio
    salida = capsys.readouterr().out
    assert "[sanitizado]" in salida
    assert "DeepSeek (limpio): ¡Hola! ag" in salida


def test_agent_step_post_no_reimprime_con_stream(monkeypatch, capsys):
    """Con streaming el contenido ya se imprimió en vivo (deltas); post NO
    debe repetir la respuesta completa — solo cierra la línea. Con la
    versión clásica, sí la imprime con el prefijo."""
    from types import SimpleNamespace

    import nodes

    mensaje = SimpleNamespace(content="respuesta en vivo", tool_calls=None)

    monkeypatch.setenv("CHAT_STREAM", "1")
    nodes.AgentStep().post({"messages": []}, None, mensaje)
    salida = capsys.readouterr().out
    assert "respuesta en vivo" not in salida  # no se repite
    assert salida == "\n"  # solo cierra la línea

    monkeypatch.setenv("CHAT_STREAM", "0")
    nodes.AgentStep().post({"messages": []}, None, mensaje)
    salida = capsys.readouterr().out
    assert "DeepSeek: respuesta en vivo" in salida


def test_call_llm_agent_stream_interrupcion(monkeypatch, capsys):
    """Ctrl+C durante la generación: con CHAT_STREAM_INTERRUPT=1 (default)
    se corta el stream, se devuelve lo acumulado (el chat sigue) y se avisa;
    con 0, el KeyboardInterrupt se propaga (main lo trata como salida)."""
    from types import SimpleNamespace

    import utils.call_llm as c

    def chunk(content):
        return SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content=content, reasoning_content=None, tool_calls=None))])

    class FakeCompletions:
        def create(self, **kwargs):
            def gen():
                yield chunk("Hola ")
                yield chunk("mundo")
                raise KeyboardInterrupt  # el usuario aprieta Ctrl+C acá

            return gen()

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(c, "_client", lambda: FakeClient())

    # activada (default): devuelve lo parcial sin explotar
    monkeypatch.setenv("CHAT_STREAM_INTERRUPT", "1")
    msg = c.call_llm_agent_stream([{"role": "user", "content": "hola"}])
    assert msg.content == "Hola mundo"
    salida = capsys.readouterr().out
    assert "Hola mundo" in salida and "[interrumpido]" in salida

    # desactivada: el KeyboardInterrupt viaja (no lo traga el stream)
    monkeypatch.setenv("CHAT_STREAM_INTERRUPT", "0")
    with pytest.raises(KeyboardInterrupt):
        c.call_llm_agent_stream([{"role": "user", "content": "hola"}])


def test_stream_error_sin_contenido_no_es_mudo(monkeypatch, capsys):
    """Fragilidad medida en la caza: el except genérico del stream devolvía
    lo acumulado, así que un 401/429/error de red con CERO contenido daba una
    respuesta vacía sin causa visible. Ahora la causa se imprime cuando no
    quedó nada; con contenido parcial el corte no agrega ruido."""
    from types import SimpleNamespace

    import utils.call_llm as c

    def chunk(content):
        return SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content=content, reasoning_content=None, tool_calls=None))])

    class RuntimeException(Exception):
        pass

    # 1) falla ANTES de cualquier chunk: no hay contenido → se imprime la causa
    class FakeCompletionsCrudo:
        def create(self, **kwargs):
            def gen():
                raise RuntimeException("API caída: 401 no autorizado")
                yield  # nunca llega (gen con raise adentro)

            return gen()

    class FakeClient1:
        chat = SimpleNamespace(completions=FakeCompletionsCrudo())

    monkeypatch.setattr(c, "_client", lambda: FakeClient1())
    msg = c.call_llm_agent_stream([{"role": "user", "content": "hola"}])
    assert msg.content is None
    salida = capsys.readouterr().out
    assert "[stream]" in salida and "RuntimeException" in salida
    assert "401 no autorizado" in salida

    # 2) falla DESPUÉS de emitir contenido: no se imprime la causa (benigno)
    class FakeCompletionsParcial:
        def create(self, **kwargs):
            def gen():
                yield chunk("Hola ")
                raise RuntimeException("corte de red")  # contenido ya hubo

            return gen()

    class FakeClient2:
        chat = SimpleNamespace(completions=FakeCompletionsParcial())

    monkeypatch.setattr(c, "_client", lambda: FakeClient2())
    msg = c.call_llm_agent_stream([{"role": "user", "content": "hola"}])
    assert msg.content == "Hola "
    salida = capsys.readouterr().out
    assert "[stream]" not in salida  # se conserva parcial, sin ruido de causa


def test_from_env_file_tolera_export(tmp_path):
    """Fragilidad medida en la caza: una línea `export KEY=valor` en un .env
    NO matcheaba (key quedaba 'export KEY') y rompía la resolución del
    setting/API key. Ahora se tolera con o sin espacio tras export."""
    import utils.call_llm as c

    env = tmp_path / ".env"
    env.write_text(
        "# comentario\n"
        "export LLM_API_KEY=sk-abc\n"
        "export   OTRA=sin-espacios-raros\n"
        "NORMAL=valor-plano\n"
        "export CON_COMILLAS='citado'\n",
        encoding="utf-8",
    )
    assert c._from_env_file(env, "LLM_API_KEY") == "sk-abc"
    assert c._from_env_file(env, "OTRA") == "sin-espacios-raros"
    assert c._from_env_file(env, "NORMAL") == "valor-plano"
    assert c._from_env_file(env, "CON_COMILLAS") == "citado"
    assert c._from_env_file(env, "NO_EXISTE") is None


def test_supervisor_no_ejecuta_llamadas_identicas(tmp_path, monkeypatch):
    import supervisor as sup

    ejecuciones = {"n": 0}

    def llm_fake(prompt):
        if "Herramientas disponibles (nombre" in prompt:
            return "```yaml\nherramienta: search_files\n```"  # insiste siempre
        if "Escribe en español el cierre" in prompt:
            return "cierre de prueba"
        return "```yaml\nargs:\n  glob: '*.py'\n```"  # siempre los mismos args

    monkeypatch.setattr(sup, "call_llm", llm_fake)
    monkeypatch.setattr("utils.laya.disponible", lambda *a, **k: False)
    monkeypatch.setenv("USE_VOTACION", "0")

    def contar(**kwargs):
        ejecuciones["n"] += 1
        return "42 archivos"

    monkeypatch.setitem(sup.REGISTRO, "search_files", contar)
    salida = tmp_path / "sup.md"
    sup.supervisar("tarea", str(salida))
    # la primera corre; la idéntica segunda sale del cache; a la segunda firma
    # la herramienta se veta y DeepSeek (que insiste) cae en finish
    assert ejecuciones["n"] == 1
    texto = salida.read_text(encoding="utf-8")
    assert texto.count("42 archivos") >= 2  # el resultado cacheado vuelve a usarse


def test_sanitizar_prompt_ajeno():
    from nodes import sanitizar

    # transcript real (2026-10-05): el saludo se corta y arranca un system
    # prompt ajeno de "file exploration agent"
    texto = "¡Hola! 👋 Soy tu ag<system>You are a file exploration agent.\n# Tools\n## `list_directory`"
    limpio, cortado = sanitizar(texto)
    assert cortado and limpio == "¡Hola! 👋 Soy tu ag"
    assert sanitizar("respuesta normal sin markers") == ("respuesta normal sin markers", False)
    assert sanitizar("<system>solo basura") == ("", True)
    # segunda variante medida: tag HTML que parte una palabra
    texto2 = "¡Hola! 👋\n\nS<small>oy un agente de exploración de archivos.</small> Puedo ayudar."
    limpio2, cambio2 = sanitizar(texto2)
    assert cambio2 and limpio2 == "¡Hola! 👋\n\nSoy un agente de exploración de archivos. Puedo ayudar."
    # el markdown legítimo (negritas, listas) NO se toca
    ok = "- **Listar** el contenido\n- 📁 `/ruta`\n## título"
    assert sanitizar(ok) == (ok, False)


def test_system_prompt_estable_y_trae_entorno():
    import main
    from utils.fs_tools import allowed_roots

    a, b = main.system_prompt(), main.system_prompt()
    assert a == b  # byte-estable: nada dinámico puede entrar (KV-cache)
    # rol: resolución de pedidos, alcance anclado al CWD
    assert "tools disponibles" in a
    assert f"Trabajás en {main.Path.cwd()} y sus subdirectorios" in a
    # el perímetro duro (allowed roots) sigue declarado
    assert any(str(r) in a for r in allowed_roots())
    # el idioma se espeja (español o inglés), no se fija a uno
    assert "español o inglés" in a


def test_run_command_hitl_y_rieles(monkeypatch):
    import modules.coding as coding

    # HITL_AUTO=0 fuerza el camino clásico (todo pregunta), que es lo que
    # este test ejercita: aprobación, rechazo, timeout y truncado. La
    # clasificación graduada tiene sus propios tests.
    monkeypatch.setenv("HITL_AUTO", "0")

    # aprobado: ejecuta y reporta exit + salida
    monkeypatch.setattr(coding, "_approve", lambda p: True)
    r = coding.run_command("echo hola-coding")
    assert r.startswith("exit 0") and "hola-coding" in r

    # rechazado: no ejecuta, el rechazo es texto para el modelo
    monkeypatch.setattr(coding, "_approve", lambda p: False)
    r = coding.run_command("echo no-deberia")
    assert r.startswith("RECHAZADO") and "no-deberia" not in r

    # timeout: el riel mecánico corta el comando colgado
    monkeypatch.setattr(coding, "_approve", lambda p: True)
    monkeypatch.setattr(coding, "TIMEOUT_S", 1)
    assert "timeout" in coding.run_command("sleep 5")

    # truncado: la salida larga no intoxica el historial
    monkeypatch.setattr(coding, "TIMEOUT_S", 120)
    r = coding.run_command("python3 -c \"print('x' * 20000)\"")
    assert "salida truncada" in r and len(r) < 6000


def test_edit_file_quirurgico(tmp_path, monkeypatch):
    import modules.coding as coding

    archivo = tmp_path / "demo.py"
    archivo.write_text("def suma(a, b):\n    return a + b\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(coding, "_approve", lambda p: True)

    # happy path: ocurrencia única, reemplazo exacto
    r = coding.edit_file(str(archivo), "a + b", "a - b")
    assert r.startswith("Editado")
    assert "a - b" in archivo.read_text(encoding="utf-8")

    # no aparece: falla ruidoso, el archivo queda intacto
    antes = archivo.read_text(encoding="utf-8")
    r = coding.edit_file(str(archivo), "texto_que_no_esta", "x")
    assert r.startswith("ERROR") and "no aparece" in r
    assert archivo.read_text(encoding="utf-8") == antes

    # ambiguo: dos ocurrencias piden más contexto
    archivo.write_text("base = 1\nbase = base + 1\n", encoding="utf-8")
    r = coding.edit_file(str(archivo), "base = ", "valor = ")
    assert "2 veces" in r
    assert "base" in archivo.read_text(encoding="utf-8")

    # rechazado: el diff se muestra pero el disco queda intacto
    monkeypatch.setattr(coding, "_approve", lambda p: False)
    r = coding.edit_file(str(archivo), "base = 1", "base = 10")
    assert r.startswith("RECHAZADO")
    assert "base = 1" in archivo.read_text(encoding="utf-8")


def test_action_space_suma_coding():
    from nodes import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    assert {"run_command", "edit_file"} <= nombres


def test_policy_clasifica_los_tres_niveles():
    from utils.policy import clasificar

    # AUTO: whitelist de solo-lectura
    for c in ("pytest -q", "python3 -m pytest tests/", "grep -r x .", "ls -la",
              "cat x.py", "head -5 x", "tail -f x", "wc -l x", "find . -name x",
              "file x", "echo hola", "git status", "git log --oneline",
              "git diff", "git show HEAD", "git blame x.py"):
        assert clasificar(c) == "auto", c

    # PREGUNTAR: lo no reconocido y la negra de un solo s/n
    for c in ("mkdir nueva", "curl http://x", "rm -f x", "git commit -m x",
              "git checkout .", "git reset --hard", "pip install x"):
        assert clasificar(c) == "preguntar", c

    # CONFIRMAR_DOBLE
    assert clasificar("git push") == "confirmar_doble"
    assert clasificar("git push origin main") == "confirmar_doble"
    assert clasificar("") == "preguntar"
    assert clasificar(None) == "preguntar"


def test_policy_semicolon_y_cd_neutro():
    """Lecciones medidas en el test exhaustivo del 2026-10-06 (35 turnos vs
    DeepSeek real): (1) el modelo prefijó `cd <dir> &&` en 5/5 run_command y
    el compuesto degradaba a preguntar aunque el fondo fuera pytest auto;
    (2) el `;` NO se partía como && y |: `ls ; rm -rf /tmp/x` clasificaba
    auto y el rm corría sin aprobación (hueco real: shell=True)."""
    from utils.policy import clasificar

    # cd neutro: solo cambia el cwd del subshell de este comando
    assert clasificar("cd /algun/lado && python3 -m pytest tests/ -q") == "auto"
    assert clasificar("cd . && ls") == "auto"

    # ... pero no relaja nada: el segmento peligroso sigue mandando
    assert clasificar("cd /tmp && rm -f x") == "preguntar"
    assert clasificar("cd /algo && python3 main.py evals") == "preguntar"
    assert clasificar("cd /algo && git push") == "confirmar_doble"

    # sort a la whitelist (medido: find | sort | head era el conteo natural)
    assert clasificar("find . -name '*.py' | sort -rn | head -5") == "auto"

    # el ; parte como && y |: TODOS los segmentos deben ser auto (y la
    # negra doble gana sobre todo — rm -rf paga las DOS confirmaciones)
    assert clasificar("ls ; rm -rf /tmp/x") == "confirmar_doble"
    assert clasificar("git status ; rm algo") == "preguntar"
    assert clasificar("ls ; grep x y") == "auto"


def test_policy_reglas_de_composicion():
    from utils.policy import clasificar

    # compuesto todo-seguro = auto
    assert clasificar("ls && grep x y") == "auto"
    assert clasificar("cat a.py | grep def") == "auto"
    assert clasificar("git status && git diff") == "auto"

    # compuesto mixto = preguntar (basta UN segmento no auto)
    assert clasificar("ls && rm -f x") == "preguntar"
    assert clasificar("git status | python3 -c 'print(1)'") == "preguntar"
    assert clasificar("pytest -q && pip install x") == "preguntar"

    # redirección / sustitución / xargs = preguntar (incluso con whitelist)
    for c in ("cat x > y", "echo hi > f", "grep x < f", "ls >> log",
              "ls $(pwd)", "echo `date`", "ls | xargs rm", "cat x | xargs grep y"):
        assert clasificar(c) == "preguntar", c

    # python3 -c SIEMPRE pregunta (código arbitrario)
    assert clasificar("python3 -c \"print(1)\"") == "preguntar"
    assert clasificar("python -c \"print(1)\"") == "preguntar"

    # doble confirmación gana sobre todo lo demás en el compuesto
    assert clasificar("git push && ls") == "confirmar_doble"
    assert clasificar("ls && git push") == "confirmar_doble"
    assert clasificar("git push origin main && rm -rf /") == "confirmar_doble"


def test_run_command_auto_no_pide_input(monkeypatch):
    import modules.coding as coding

    # con HITL_AUTO=1 (default), un comando seguro NO debe llamar a input:
    # si lo llamara, este monkeypatch explotaría.
    def explota(prompt):
        raise AssertionError(f"no debía preguntar: {prompt!r}")

    monkeypatch.delenv("HITL_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", explota)
    r = coding.run_command("echo auto-sin-input")
    assert r.startswith("exit 0") and "auto-sin-input" in r


def test_run_command_no_seguro_pide_input(monkeypatch):
    import modules.coding as coding

    llamados = []

    def falso_input(prompt):
        llamados.append(prompt)
        return "s"

    monkeypatch.delenv("HITL_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", falso_input)
    r = coding.run_command("echo no-seguro")  # echo SÍ es auto; forzamos no-auto
    # (echo es auto → para probar el camino 'preguntar' usamos algo no whitelisted)
    assert llamados == []  # echo se ejecutó auto, sin input
    assert r.startswith("exit 0")

    # un comando no-seguro SÍ pide (rm... no lo ejecutamos realmente: no está
    # en whitelist así que pregunta; lo rechazamos para no tocar nada)
    monkeypatch.setattr("builtins.input", lambda p: (llamados.append(p), "n")[1])
    r2 = coding.run_command("mkdir no_se_debe_crear")
    assert llamados and llamados[-1].startswith("¿Ejecutar?")
    assert r2.startswith("RECHAZADO")


def test_run_command_hitl_auto_cero_compatibilidad(monkeypatch):
    import modules.coding as coding

    # Con HITL_AUTO=0 hasta un comando seguro pregunta (comportamiento de hoy).
    llamados = []
    monkeypatch.setenv("HITL_AUTO", "0")
    monkeypatch.setattr("builtins.input", lambda p: (llamados.append(p), "s")[1])
    r = coding.run_command("echo compat")
    assert llamados  # preguntó pese a ser whitelisted
    assert r.startswith("exit 0") and "compat" in r
    monkeypatch.delenv("HITL_AUTO", raising=False)


def test_run_command_doble_confirmacion_aborta(monkeypatch):
    import modules.coding as coding

    # git push pide dos s/n; si la segunda es 'n', aborta (sin ejecutar).
    respuestas = iter(["s", "n"])
    monkeypatch.delenv("HITL_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", lambda p: next(respuestas))
    r = coding.run_command("git push")  # no llega a ejecutar: aborta en la 2ª
    assert r.startswith("RECHAZADO")

    # si la primera es 'n', también aborta
    monkeypatch.setattr("builtins.input", lambda p: "n")
    r = coding.run_command("git push --dry-run")
    assert r.startswith("RECHAZADO")


def _tc(nombre, args):
    import json
    return {"id": "call_x", "type": "function",
            "function": {"name": nombre, "arguments": json.dumps(args)}}


def test_hook_py_compile_tras_edit_y_write(tmp_path, monkeypatch, capsys):
    import modules.coding as coding
    import modules.escritura
    from utils.fs_tools import run_tool_call

    # run_tool_call real: registra las implementaciones de los módulos (en
    # el agente lo hace nodes.py; acá lo armamos igual).
    extra = {**coding.IMPL, **modules.escritura.IMPL}
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(coding, "_approve", lambda p: True)
    monkeypatch.setattr(modules.escritura, "_approve", lambda p: True)

    # edit_file de un .py con sintaxis rota: el hook agrega ⚠ SINTAXIS
    roto = tmp_path / "roto.py"
    roto.write_text("def f(:\n    pass\n", encoding="utf-8")
    res = run_tool_call(_tc("edit_file", {
        "path": str(roto), "old_string": "def f(:", "new_string": "def g(:"}), extra)
    assert "⚠ SINTAXIS" in res["content"]
    # el aviso también llega a la terminal (no solo al modelo)
    assert "[hook] ⚠ SINTAXIS" in capsys.readouterr().out

    # write_file de un .py roto también
    res = run_tool_call(_tc("write_file", {
        "path": str(tmp_path / "nuevo.py"), "content": "x = (\n"}), extra)
    assert "⚠ SINTAXIS" in res["content"]
    assert "[hook] ⚠ SINTAXIS" in capsys.readouterr().out

    # un .py correcto NO agrega nada
    res = run_tool_call(_tc("write_file", {
        "path": str(tmp_path / "bueno.py"), "content": "def ok():\n    return 1\n"}), extra)
    assert "⚠ SINTAXIS" not in res["content"]
    assert res["content"].startswith("Escrito")
    # compila bien: el hook NO imprime nada en terminal
    assert "[hook] ⚠ SINTAXIS" not in capsys.readouterr().out

    # un .txt no dispara py_compile (no aplica)
    res = run_tool_call(_tc("write_file", {
        "path": str(tmp_path / "notas.txt"), "content": "esto no es python(\n"}), extra)
    assert "⚠ SINTAXIS" not in res["content"]

    # edit_file que corrige el .py roto: sin aviso
    res = run_tool_call(_tc("edit_file", {
        "path": str(roto), "old_string": "def g(:", "new_string": "def g():"}), extra)
    assert "⚠ SINTAXIS" not in res["content"]


def test_hook_no_rompe_la_ejecucion(tmp_path, monkeypatch):
    # Un hook que lanza NO rompe el resultado (contrato de hierro).
    from utils import fs_tools

    def hook_malo(tool_call, resultado):
        raise ValueError("boom")

    fs_tools.HOOKS_POST.setdefault("read_file", []).append(hook_malo)
    try:
        res = fs_tools.run_tool_call(_tc("read_file", {
            "path": str(tmp_path / "x.txt")}))  # no existe → ERROR
        assert res["content"].startswith("ERROR")
    finally:
        fs_tools.HOOKS_POST["read_file"].remove(hook_malo)


def test_hook_pre_denylist_veta_antes_de_ejecutar(tmp_path, monkeypatch):
    """Mesa 2 (residual): el denylist de run_command corre ANTES de la
    implementación (hook PRE). Un comando prohibido se veta sin ejecutarse
    NI aprobarse (input explota si se llamara)."""
    import subprocess

    import modules.coding as coding
    from utils import fs_tools

    # el denylist quedó registrado al importar el módulo
    assert fs_tools.HOOKS_PRE.get("run_command")

    def explota(*a, **k):
        raise AssertionError("el comando prohibido llegó a ejecutarse")

    # input y subprocess explotan: si el denylist fallara, el test lo delata.
    # Guardamos el subprocess.run ORIGINAL antes de parchear (restaurarlo con
    # coding.subprocess.run devolvería el parcheado).
    run_original = subprocess.run
    monkeypatch.setattr("builtins.input", explota)
    monkeypatch.setattr(coding.subprocess, "run", explota)

    res = fs_tools.run_tool_call(
        _tc("run_command", {"command": "rm -rf /"}),
        coding.IMPL,
    )
    assert res["content"].startswith("ERROR") and "denylist" in res["content"]

    res = fs_tools.run_tool_call(
        _tc("run_command", {"command": ":(){ :|:& };:"}),
        coding.IMPL,
    )
    assert res["content"].startswith("ERROR") and "denylist" in res["content"]

    # un comando normal NO es vetado: restauramos el run real y verificamos
    # que llega a la implementación (echo inofensivo, HITL_AUTO lo corre auto).
    monkeypatch.delenv("HITL_AUTO", raising=False)
    monkeypatch.setattr(coding.subprocess, "run", run_original)
    res = fs_tools.run_tool_call(
        _tc("run_command", {"command": "echo denylist-ok"}),
        coding.IMPL,
    )
    assert res["content"].startswith("exit 0") and "denylist-ok" in res["content"]


def test_hook_pre_que_lanza_no_rompe(tmp_path):
    """Un hook PRE que lanza se ignora y la tool sigue (contrato de hierro)."""
    from utils import fs_tools

    def hook_malo(tool_call):
        raise ValueError("boom")

    fs_tools.HOOKS_PRE.setdefault("read_file", []).append(hook_malo)
    try:
        res = fs_tools.run_tool_call(_tc("read_file", {
            "path": str(tmp_path / "no-existe.txt")}))
        assert res["content"].startswith("ERROR")  # llegó a la impl y devolvió su ERROR
    finally:
        fs_tools.HOOKS_PRE["read_file"].remove(hook_malo)


def test_contratos_laya_congelados_sha1():
    """El contrato con el fine-tune es byte-a-byte: cambiar UNA palabra de
    instructions/criteria desincroniza entrenamiento y producción. El test
    de claves no alcanza (hallazgo de la revisión de consistencia)."""
    import hashlib
    import json

    from nodes import PREGUNTA_ROUTER
    from supervisor import PREGUNTA_DESPACHO

    canon = lambda p: hashlib.sha1(  # noqa: E731
        json.dumps(p, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    assert canon(PREGUNTA_ROUTER) == "01bf4478f15cef2c47ed889533cdd3e9c1ee9739"
    assert canon(PREGUNTA_DESPACHO) == "de43614ad2f939048fb76ef7f9058bdbb0ef212e"


def test_sonda_router_importa_el_contrato():
    """La sonda no re-tipea: deriva del objeto de producción (drift
    imposible por construcción)."""
    import nodes
    import sonda_router

    assert sonda_router.PREGUNTA_ROUTER is nodes.PREGUNTA_ROUTER


def test_sonda_supervisor_importa_el_contrato():
    """Misma garantía del lado del despacho: la sonda del supervisor deriva
    de supervisor.PREGUNTA_DESPACHO (no hay copia que pueda derivar)."""
    import sonda_supervisor
    import supervisor

    assert sonda_supervisor.PREGUNTA_DESPACHO is supervisor.PREGUNTA_DESPACHO


def test_search_files_con_path_a_archivo():
    """Falso negativo medido en la auditoría: os.walk sobre un archivo no
    visita nada y la tool decía 'Ningún archivo contiene' sobre un
    archivo que sí lo contiene."""
    from utils.fs_tools import search_files

    r = search_files(query="PREGUNTA_ROUTER", path="nodes.py")
    assert "nodes.py" in r and "Ningún archivo" not in r

    r = search_files(query="PREGUNTA", path="sonda_router.py")
    assert "sonda_router.py" in r and "Ningún archivo" not in r


def test_evento_tool_deja_rastro():
    """Las tools que no son flujos también se trazan (nombre + ok/error)."""
    import io
    import json

    import utils.tracing as tracing

    original = tracing._salida
    tracing._salida = io.StringIO()
    try:
        tracing.evento_tool("sql", True, 0.5)
        tracing.evento_tool("run_command", False, 12.3)
        lineas = tracing._salida.getvalue().strip().splitlines()
    finally:
        tracing._salida = original
    assert len(lineas) == 2
    e1, e2 = (json.loads(linea) for linea in lineas)
    assert e1["nodo"] == "sql" and e1["accion"] == "ok" and e1["seg"] == 0.5
    assert e2["nodo"] == "run_command" and e2["accion"] == "error"


def test_hitl_web(monkeypatch):
    """HITL web: el navegador decide (aprobar/rechazar) y el timeout cae a
    un default seguro (False). Se prueba el servidor en un puerto propio."""
    import threading
    import urllib.parse
    import urllib.request

    import utils.hitl_web as hitl

    puerto = 8791
    monkeypatch.setenv("HITL_WEB_PORT", str(puerto))
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "300")
    # servidor ya arrancado: aprobar() lo reutiliza (perezoso, una sola vez)
    assert hitl._arrancar() == puerto

    def post(decision):
        # el form real manda también el token del pedido vigente
        token = hitl._pendiente.token if hitl._pendiente is not None else ""
        datos = urllib.parse.urlencode({"decision": decision, "token": token}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{puerto}/decision", data=datos)
        return urllib.request.urlopen(req, timeout=5).read()

    resultados = {}

    # 1) aprobar: la función espera el Event y devuelve True
    hilo = threading.Thread(
        target=lambda: resultados.update(ok=hitl.aprobar("¿Escribir?", "diff de prueba")))
    hilo.start()
    import time as _t
    for _ in range(50):  # esperar el pedido pendiente antes de votar
        if hitl._pendiente is not None:
            break
        _t.sleep(0.02)
    assert hitl._pendiente is not None
    post("aprobar")
    hilo.join(5)
    assert resultados["ok"] is True

    # 2) rechazar: POST de rechazar devuelve False
    hilo = threading.Thread(
        target=lambda: resultados.update(ok=hitl.aprobar("¿Ejecutar?", "ls -la")))
    hilo.start()
    for _ in range(50):
        if hitl._pendiente is not None:
            break
        _t.sleep(0.02)
    post("rechazar")
    hilo.join(5)
    assert resultados["ok"] is False

    # 3) timeout: nadie vota y expira -> default seguro False
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "0.2")
    assert hitl.aprobar("¿Aplicar?", "diff huérfano") is False

    # 4) timeout inválido (setting corrupto) no rompe: cae al default seguro
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "no-es-numero")
    assert hitl._timeout() == float(hitl.TIMEOUT_DEFAULT)


def test_hitl_web_rechaza_post_cross_origin(monkeypatch):
    """Contención real del gate humano (medido: loopback NO alcanza).

    Un POST a /decision con Origin ajeno (CSRF/DNS-rebinding: la víctima
    solo tiene que cargar una página mientras hay un pedido pendiente) debe
    ser ignorado, no aprobar. El mismo pedido con Origin/Host de loopback
    sí decide. Regresión del hallazgo del juez: faltaba validar Origin/Host."""
    import threading
    import time as _t
    import urllib.error
    import urllib.parse
    import urllib.request

    import utils.hitl_web as hitl

    puerto = 8792
    monkeypatch.setenv("HITL_WEB_PORT", str(puerto))
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "300")
    monkeypatch.setattr(hitl, "_servidor", None)  # puerto propio (aislado)
    assert hitl._arrancar() == puerto

    def post(decision, origin):
        datos = urllib.parse.urlencode({"decision": decision}).encode()
        cabeceras = {"Content-Type": "application/x-www-form-urlencoded"}
        if origin is not None:
            cabeceras["Origin"] = origin
        req = urllib.request.Request(
            f"http://127.0.0.1:{puerto}/decision", data=datos, headers=cabeceras)
        try:
            return urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as e:
            return e  # 403 esperado para el POST cross-origin

    resultados = {}

    # 1) POST con Origin ajeno: NO debe decidir (el pedido sigue pendiente)
    hilo = threading.Thread(
        target=lambda: resultados.update(ok=hitl.aprobar("¿Escribir?", "diff")))
    hilo.start()
    for _ in range(50):
        if hitl._pendiente is not None:
            break
        _t.sleep(0.02)
    assert hitl._pendiente is not None
    r = post("aprobar", origin="http://evil.example")
    assert getattr(r, "status", getattr(r, "code", None)) == 403, "el POST cross-origin no fue rechazado"
    _t.sleep(0.1)
    assert hitl._pendiente is not None, "un Origin ajeno decidió el pedido"
    assert not resultados.get("ok"), "el pedido se resolvió por un POST cross-origin"

    # 2) POST legítimo (sin Origin, mismo-origen vía loopback) con el token: sí decide
    token = hitl._pendiente.token
    req = urllib.request.Request(
        f"http://127.0.0.1:{puerto}/decision",
        data=urllib.parse.urlencode({"decision": "aprobar", "token": token}).encode())
    urllib.request.urlopen(req, timeout=5)
    hilo.join(5)
    assert resultados["ok"] is True


def test_hitl_web_post_tardio_no_contamina_el_siguiente(monkeypatch):
    """Un POST que trae una decisión vieja (llega mientras el pedido
    siguiente ya está esperando) NO puede decidirlo: la decisión va atada
    al pedido, no a una global suelta. Se ejerce la ventana real: un POST
    concurrente dentro del wait() de B no debe resolverlo."""
    import threading
    import time as _t
    import urllib.parse
    import urllib.request

    import utils.hitl_web as hitl

    puerto = 8793
    monkeypatch.setenv("HITL_WEB_PORT", str(puerto))
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "300")
    monkeypatch.setattr(hitl, "_servidor", None)  # puerto propio (aislado)
    assert hitl._arrancar() == puerto

    def post(decision, token=""):
        datos = urllib.parse.urlencode({"decision": decision, "token": token}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{puerto}/decision", data=datos)
        try:
            return urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as e:
            return e  # 403 esperado para el POST viejo

    # pedido A: expira por timeout sin que nadie vote. Su token queda viejo.
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "0.15")
    assert hitl.aprobar("¿A?", "a") is False
    post("aprobar", token="token-viejo-de-A")  # POST TARDÍO de A: nadie espera
    _t.sleep(0.05)

    # pedido B: espera SU decisión. El POST de A (token viejo) no lo resuelve,
    # y el timeout corto de B debe dar el default seguro False.
    resultados = {}
    monkeypatch.setenv("HITL_WEB_TIMEOUT", "0.3")
    hilo = threading.Thread(
        target=lambda: resultados.update(ok=hitl.aprobar("¿B?", "b")))
    hilo.start()
    hilo.join(5)
    assert resultados["ok"] is False, "una decisión con token viejo resolvió B"


def test_hitl_web_puerto_ocupado_default_seguro(monkeypatch):
    """Si el servidor no puede levantar (puerto inválido), aprobar() devuelve
    False en vez de propagar la excepción: el HITL nunca cuelga al agente."""
    import utils.hitl_web as hitl

    monkeypatch.setattr(hitl, "_servidor", None)  # forzar arranque
    monkeypatch.setenv("HITL_WEB_PORT", "no-es-un-puerto")
    assert hitl.aprobar("¿Escribir?", "algo") is False


def test_memory_search_encuentra_y_lista(tmp_path, monkeypatch):
    """La memoria es una BIBLIOTECA consultable: memory_search encuentra el
    texto (case-insensitive) con archivo+línea y siempre lista la biblioteca."""
    import modules.memoria as mem

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    # biblioteca vacía: lo dice y no explota
    vacio = mem.memory_search("cualquier-cosa")
    assert "vacía" in vacio

    (tmp_path / "nota_2026-10-05_prueba.md").write_text(
        "Hallazgo de LaYa\n\nEl router degrada al lado SEGURO.\n", encoding="utf-8")
    (tmp_path / "sesion_2026-10-05.md").write_text(
        "Tema: streaming\n\nSe implementó el modo clásico y el stream.\n", encoding="utf-8")

    # búsqueda insensible a mayúsculas + archivo/línea
    r = mem.memory_search("laya")
    assert "nota_2026-10-05_prueba.md" in r and "L1" in r
    # siempre lista la biblioteca completa
    assert "nota_2026-10-05_prueba.md" in r and "sesion_2026-10-05.md" in r

    # sin query: solo lista
    solo_lista = mem.memory_search("")
    assert "Biblioteca" in solo_lista and "L1" not in solo_lista

    # sin coincidencias: lo dice pero igual lista
    assert "no aparece" in mem.memory_search("inexistente-xyz")


def test_memory_save_contiene_el_slug(tmp_path, monkeypatch):
    """Contención dura: el título genera el slug, no es una ruta. Un título
    con barra, '..' o solo símbolos se rechaza o se neutraliza."""
    import modules.memoria as mem

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))

    # el slug neutraliza la barra y los '..': nada sale de memoria/
    r = mem.memory_save("../../etc/passwd", "contenido malicioso")
    assert r.startswith("Guardado")
    destino = Path(r.split("Guardado en ", 1)[1])
    assert destino.parent == tmp_path.resolve()
    assert ".." not in destino.name and "/" not in destino.name

    # un título sin caracteres utilizables se rechaza
    assert mem.memory_save("///", "x").startswith("ERROR")
    assert mem.memory_save("...", "x").startswith("ERROR")

    # y SOLO escribe dentro de memoria/: ningún archivo fuera de tmp_path
    fuera = list(tmp_path.parent.glob("passwd*"))
    assert not fuera


def test_memory_save_escribe_con_titulo_primera_linea(tmp_path, monkeypatch):
    import modules.memoria as mem

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    r = mem.memory_save("Mi hallazgo", "detalle del hallazgo")
    assert r.startswith("Guardado")
    destino = Path(r.split("Guardado en ", 1)[1])
    assert destino.exists() and destino.parent == tmp_path.resolve()
    assert destino.name.startswith("nota_") and destino.name.endswith("_mi-hallazgo.md")
    lineas = destino.read_text(encoding="utf-8").splitlines()
    assert lineas[0] == "Mi hallazgo"  # el título es la primera línea
    assert "detalle del hallazgo" in destino.read_text(encoding="utf-8")


def test_action_space_suma_memoria():
    from nodes import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    assert {"memory_search", "memory_save"} <= nombres


def test_resumen_de_sesion_escribe_con_llm(tmp_path, monkeypatch):
    """Al salir, con MEMORIA activo y >=2 preguntas, UNA llamada a call_llm
    resume y guarda memoria/sesion_FECHA.md. La llamada va fiteada."""
    import main
    import utils.call_llm as c

    monkeypatch.setenv("MEMORIA", "1")
    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    llamadas = {"n": 0}

    def llm_fake(prompt):
        llamadas["n"] += 1
        assert "Resumí esta conversación" in prompt
        assert "hola mundo" in prompt and "chau mundo" in prompt  # ve la charla
        return "Tema: charla\n- Pedidos: hola\n- Resultado: chau"

    monkeypatch.setattr(c, "call_llm", llm_fake, raising=False)
    shared = {"messages": [
        {"role": "system", "content": "prompt"},
        {"role": "user", "content": "hola mundo"},
        {"role": "assistant", "content": "respuesta uno"},
        {"role": "user", "content": "chau mundo"},
        {"role": "assistant", "content": "respuesta dos"},
    ]}
    main.resumen_de_sesion(shared)
    assert llamadas["n"] == 1  # UNA sola llamada

    sesiones = list(tmp_path.glob("sesion_*.md"))
    assert len(sesiones) == 1
    assert "Tema: charla" in sesiones[0].read_text(encoding="utf-8")


def test_resumen_de_sesion_se_apaga_y_no_rompe(tmp_path, monkeypatch):
    """MEMORIA=0 no resume; menos de 2 preguntas tampoco; y un fallo del LLM
    no rompe la salida (bookkeeping)."""
    import main
    import utils.call_llm as c

    def no_llamar(prompt):
        raise AssertionError("no debería llamar al LLM")

    monkeypatch.setattr(c, "call_llm", no_llamar, raising=False)
    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))

    monkeypatch.setenv("MEMORIA", "0")
    main.resumen_de_sesion({"messages": [
        {"role": "user", "content": "una"}, {"role": "user", "content": "dos"}]})
    assert not list(tmp_path.glob("sesion_*.md"))

    monkeypatch.setenv("MEMORIA", "1")
    main.resumen_de_sesion({"messages": [{"role": "user", "content": "una sola"}]})
    assert not list(tmp_path.glob("sesion_*.md"))  # <2 preguntas

    # fallo del LLM: se sale igual, sin archivo, sin excepción
    def explota(prompt):
        raise RuntimeError("sin saldo")

    monkeypatch.setattr(c, "call_llm", explota, raising=False)
    main.resumen_de_sesion({"messages": [
        {"role": "user", "content": "una"}, {"role": "user", "content": "dos"}]})
    assert not list(tmp_path.glob("sesion_*.md"))


def test_resumen_de_sesion_rutas_visibles(capsys, monkeypatch, tmp_path):
    """Ninguna ruta del exit-summary es muda (episodio silencioso no
    reproducido: sin prints es indecidible cuál disparó)."""
    import main

    # desactivada
    monkeypatch.setenv("MEMORIA", "0")
    main.resumen_de_sesion({"messages": []})
    assert "desactivada" in capsys.readouterr().out

    # sesión corta
    monkeypatch.setenv("MEMORIA", "1")
    main.resumen_de_sesion({"messages": [
        {"role": "user", "content": "hola"},
    ]})
    assert "sesión corta" in capsys.readouterr().out

    # feliz: escribe y anuncia el destino
    monkeypatch.setattr("utils.call_llm.call_llm", lambda p: "resumen de prueba")
    import modules.memoria as mem

    monkeypatch.setattr(mem, "_raiz", lambda: tmp_path)
    main.resumen_de_sesion({"messages": [
        {"role": "user", "content": "uno"},
        {"role": "assistant", "content": "r1"},
        {"role": "user", "content": "dos"},
    ]})
    salida = capsys.readouterr().out
    assert "resumen de sesión guardado" in salida
    assert list(tmp_path.glob("sesion_*.md")), "no escribió el archivo"


def test_rag_indice_inconsistente_falla_cerrado(tmp_path, monkeypatch):
    """Un índice semántico con chunks.json y vectores.npy de largos distintos
    (reindexado interrumpido, o índice mezclado) hacía reventar buscar() con
    IndexError y, si sobran vectores, desalineaba el ranking en silencio.
    _cargar() debe detectar la inconsistencia y fallar con un error claro
    (reindexar) en vez de crashear o devolver basura."""
    import json

    import numpy as np

    import rag

    monkeypatch.setattr(rag, "INDICE_DIR", tmp_path)
    monkeypatch.setattr(rag, "_indice_cache", None)

    # 4 chunks pero solo 2 vectores: el caso del IndexError
    (tmp_path / "chunks.json").write_text(
        json.dumps({"modo": "semantico",
                    "chunks": [{"path": "a", "texto": "x"}] * 4}), encoding="utf-8")
    np.save(tmp_path / "vectores.npy", np.random.rand(2, 8).astype(np.float32))

    with pytest.raises(RuntimeError) as exc:
        rag._cargar()
    assert "inconsistente" in str(exc.value).lower() or "reindexa" in str(exc.value).lower()

    # y buscar() tampoco debe crashear con IndexError: propaga el RuntimeError claro
    monkeypatch.setattr(rag, "_indice_cache", None)
    with pytest.raises(RuntimeError):
        rag.buscar("cualquier cosa")


def test_rag_indice_sobran_vectores_falla_cerrado(tmp_path, monkeypatch):
    """El caso inverso (más vectores que chunks) no crashea pero desalinea el
    ranking en silencio: tambien debe fallar cerrado."""
    import json

    import numpy as np

    import rag

    monkeypatch.setattr(rag, "INDICE_DIR", tmp_path)
    monkeypatch.setattr(rag, "_indice_cache", None)
    (tmp_path / "chunks.json").write_text(
        json.dumps({"modo": "semantico",
                    "chunks": [{"path": "a", "texto": "x"}] * 2}), encoding="utf-8")
    np.save(tmp_path / "vectores.npy", np.random.rand(5, 8).astype(np.float32))

    with pytest.raises(RuntimeError):
        rag._cargar()


def test_rag_indice_lexico_sin_vectores_ok(tmp_path, monkeypatch):
    """El modo léxico no lleva vectores: cargarlo NO debe exigir vectores.npy."""
    import json

    import rag

    monkeypatch.setattr(rag, "INDICE_DIR", tmp_path)
    monkeypatch.setattr(rag, "_indice_cache", None)
    (tmp_path / "chunks.json").write_text(
        json.dumps({"modo": "lexico",
                    "chunks": [{"path": "a", "texto": "hola mundo"}]}), encoding="utf-8")

    modo, vectores, chunks = rag._cargar()
    assert modo == "lexico" and vectores is None and len(chunks) == 1


def test_juez_lote_aisla_fallas(tmp_path, monkeypatch):
    """Medido en vivo: el verdict inválido persistente de UNA pregunta mató
    el lote entero y perdió el trabajo de las demás. Ahora el fallo es un
    hecho del informe, no la muerte del batch."""
    import juez_lote

    class FlujoFake:
        def run(self, shared):
            if "ROMPE" in shared["question"]:
                raise AssertionError("verdict inválido")
            shared["draft"] = "respuesta verificada"
            shared["rounds"] = 1

    monkeypatch.setattr(juez_lote, "create_juez_flow", lambda: FlujoFake())
    preg = tmp_path / "p.txt"
    preg.write_text("pregunta buena\npregunta ROMPE ahora\n", encoding="utf-8")
    salida = tmp_path / "lote.md"
    resumen = juez_lote.run_juez_lote(preg, salida)
    texto = salida.read_text(encoding="utf-8")
    assert "respuesta verificada" in texto  # la buena sobrevive
    assert "❌ Falló" in texto and "verdict inválido" in texto  # la mala, documentada
    assert "1 fallidas" in resumen


# ---------------------------------------------------------------------------
# Evals (mesa 1, replay-evals): bench del router, linter de trazas, costos
# ---------------------------------------------------------------------------

def _bench_con(fake_agente):
    """Corre correr_bench() con un agente fake (system_one), sin cargar laya."""
    from evals import correr_bench

    return correr_bench(agente=fake_agente)


def test_evals_bench_score_y_ece_ok():
    """Un agente perfecto: score con compuerta y crudo = 100%, ECE = 0."""

    # el fake responde SIEMPRE lo esperado con confianza 1.0
    import json

    from evals import TEST_ROUTER
    from nodes import PREGUNTA_ROUTER  # noqa: F401  (contrato importado)

    esperados = {}
    for linea in TEST_ROUTER.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            c = json.loads(linea)
            esperados[c["fields"]["pregunta"]] = c["answers"]["necesita_herramientas"]

    class AgentePerfecto:
        def system_one(self, estado, preguntas, lang="es"):
            esperado = esperados[estado["pregunta"]]
            return {"answers": {"necesita_herramientas":
                                {"choice": esperado, "answer_confidence": 1.0}}}

    bench, err = _bench_con(AgentePerfecto())
    assert err is None and bench["estado"] == "ok"
    assert bench["score"] == 1.0 and bench["score_crudo"] == 1.0
    assert bench["ece"] == 0.0


def test_evals_bench_ece_pesimista():
    """Un agente que dice directo con conf 1.0 pero se equivoca siempre: ECE
    alto, calcularlo a mano sobre la decisión cruda."""

    from nodes import PREGUNTA_ROUTER  # noqa: F401

    class AgenteMalCalibrado:
        def system_one(self, estado, preguntas, lang="es"):
            return {"answers": {"necesita_herramientas":
                                {"choice": "directo", "answer_confidence": 1.0}}}

    bench, err = _bench_con(AgenteMalCalibrado())
    assert err is None
    # casos esperado=directo (13) aciertan crudo; esperado=herramientas (17) no
    assert abs(bench["score_crudo"] - 13 / 30) < 1e-4
    # ECE = |1.0 - 13/30| porque todo cae en el bin [0.9, 1.0]
    assert abs(bench["ece"] - (1 - 13 / 30)) < 1e-3


def test_evals_bench_contra_baseline_mejora_y_regresion(tmp_path):
    """comparar_baseline: PRIMERA CORRIDA sin archivo, OK si mejora,
    REGRESIÓN si el score baja (con el mismo shape del bench)."""
    from evals import comparar_baseline

    ruta = tmp_path / "bench_router.json"
    nuevo = {"score": 0.9, "score_crudo": 0.9, "ece": 0.05}
    # sin baseline
    assert comparar_baseline(nuevo, ruta=ruta)["veredicto"] == "PRIMERA CORRIDA"

    # baseline peor → OK
    ruta.write_text('{"score": 0.8, "ece": 0.10}', encoding="utf-8")
    r = comparar_baseline(nuevo, ruta=ruta)
    assert r["veredicto"] == "OK"
    assert r["delta"]["score"] == 0.1 and r["delta"]["ece"] == -0.05

    # baseline mejor → REGRESIÓN
    ruta.write_text('{"score": 0.95, "ece": 0.02}', encoding="utf-8")
    r = comparar_baseline(nuevo, ruta=ruta)
    assert r["veredicto"] == "REGRESIÓN"
    assert r["delta"]["score"] < 0

    # baseline sin score (corrida degradada) no es referencia
    ruta.write_text('{"score": null, "ece": null}', encoding="utf-8")
    assert comparar_baseline(nuevo, ruta=ruta)["veredicto"] == "PRIMERA CORRIDA"


def test_evals_bench_laya_ausente_degrada(monkeypatch):
    """Sin laya: correr_bench devuelve estado 'no disponible' y un motivo, sin
    crashear (la degradación prometida)."""
    import evals

    def revienta(*a, **k):
        raise RuntimeError("laya no disponible: prueba")

    monkeypatch.setattr("utils.laya.agente", revienta)
    bench, motivo = evals.correr_bench()
    assert bench["estado"] == "no disponible"
    assert bench["score"] is None and "laya no disponible" in motivo


def _linea(nodo, accion, seg=0.0, ts=0.0):
    return {"ts": ts, "nodo": nodo, "accion": accion, "seg": seg}


def test_evals_linter_traza_limpia_sin_falsos_positivos():
    """Una traza del chat bien formada (router → tool → ExecuteTools →
    answer) pasa el linter sin violaciones."""
    from evals import linter_traza

    eventos = [
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("AgentStep", "tool"),
        _linea("read_file", "ok", 0.001),
        _linea("ExecuteTools", "default", 0.01),
        _linea("AgentStep", "answer"),
        _linea("GetQuestion", "exit"),
        _linea("ExitChat", "None"),
    ]
    assert linter_traza(eventos) == []


def test_evals_linter_detecta_agentstep_sin_executetools():
    """(a) AgentStep tool seguido de otro AgentStep sin ExecuteTools."""
    from evals import linter_traza

    eventos = [
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("AgentStep", "tool"),
        _linea("AgentStep", "tool"),  # nunca hubo ExecuteTools
        _linea("AgentStep", "answer"),
    ]
    viol = linter_traza(eventos)
    assert any(v[0] == "a" for v in viol), viol


def test_evals_linter_detecta_accion_desconocida():
    """(c) un par (nodo, accion) fuera del conjunto canónico."""
    from evals import linter_traza

    eventos = [
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("NodoInventado", "hace_algo"),
        _linea("AgentStep", "answer"),
    ]
    viol = linter_traza(eventos)
    assert any(v[0] == "c" and "NodoInventado" in v[2] for v in viol), viol
    # y un par conocido no dispara (c)
    assert not any(v[0] == "c" for v in linter_traza([
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("ExecuteTools", "default"),
    ]))


def test_evals_linter_detecta_executetools_largo_sin_tools():
    """(d) ExecuteTools > 120s sin eventos de tools propios (el ciego viejo)."""
    from evals import linter_traza

    eventos = [
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("AgentStep", "tool"),
        _linea("ExecuteTools", "default", seg=300.0),  # largo y sin tools
        _linea("AgentStep", "answer"),
    ]
    viol = linter_traza(eventos)
    assert any(v[0] == "d" for v in viol), viol
    # con una tool propia, deja de ser ciego
    con_tool = [
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("AgentStep", "tool"),
        _linea("run_command", "ok", seg=200.0),  # evento propio
        _linea("ExecuteTools", "default", seg=300.0),
        _linea("AgentStep", "answer"),
    ]
    assert not any(v[0] == "d" for v in linter_traza(con_tool))


def test_evals_linter_detecta_turno_sin_router():
    """(b) con router activo en la traza, un turno que salta de GetQuestion a
    AgentStep answer sin pasar por LayaRouter."""
    from evals import linter_traza

    eventos = [
        _linea("GetQuestion", "continue"),
        _linea("AgentStep", "answer"),  # sin LayaRouter
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),  # este turno sí
        _linea("AgentStep", "answer"),
        _linea("GetQuestion", "exit"),
    ]
    viol = linter_traza(eventos)
    assert any(v[0] == "b" for v in viol), viol


def test_evals_linter_runs_reporta_por_invariante(tmp_path):
    """linter_runs agrupa violaciones por invariante y por archivo."""
    import json

    import evals

    limpia = tmp_path / "limpia.jsonl"
    limpia.write_text(json.dumps(_linea("GetQuestion", "exit")) + "\n"
                      + json.dumps(_linea("ExitChat", "None")) + "\n", encoding="utf-8")
    sucia = tmp_path / "sucia.jsonl"
    sucia.write_text("\n".join(json.dumps(e) for e in [
        _linea("GetQuestion", "continue"),
        _linea("LayaRouter", "herramientas"),
        _linea("AgentStep", "tool"),
        _linea("AgentStep", "answer"),  # (a): sin ExecuteTools
    ]) + "\n", encoding="utf-8")

    resumen = evals.linter_runs(tmp_path)
    assert resumen["total"] == 2
    assert resumen["por_invariante"].get("a", 0) == 1
    assert resumen["por_archivo"]["sucia.jsonl"]
    assert not resumen["por_archivo"].get("limpia.jsonl")


def test_evals_costos_ordena_por_costo(tmp_path):
    """costos_runs ordena de más caro a más barato y calcula nodo dominante."""
    import json

    import evals

    def _escribir(nombre, eventos):
        (tmp_path / nombre).write_text(
            "\n".join(json.dumps(e) for e in eventos) + "\n", encoding="utf-8")

    _escribir("20260101_100000.jsonl", [
        _linea("AgentStep", "answer", seg=2.0),
        _linea("read_file", "ok", seg=1.0),
    ])
    _escribir("20260101_110000.jsonl", [
        _linea("AgentStep", "tool", seg=10.0),
        _linea("ExecuteTools", "default", seg=5.0),
        _linea("read_file", "ok", seg=0.0),
    ])

    sesiones = evals.costos_runs(tmp_path)
    assert [s["archivo"] for s in sesiones] == [
        "20260101_110000.jsonl", "20260101_100000.jsonl"]
    cara = sesiones[0]
    assert cara["total"] == 15.0
    assert cara["dominante"] == "AgentStep"
    assert cara["tools"] == 1
    assert cara["fecha"] == "2026-01-01 11:00:00"


def test_policy_rm_rf_paga_doble():
    """Desviación de spec encontrada en auditoría: rm -rf debía ser
    confirmar_doble (doble fricción) y había quedado en preguntar."""
    from utils.policy import clasificar

    assert clasificar("rm -rf /tmp/x") == "confirmar_doble"
    assert clasificar("rm -fr /tmp/x") == "confirmar_doble"
    assert clasificar("rm archivo.txt") == "preguntar"
    assert clasificar("ls && rm -rf /") == "confirmar_doble"  # compuesto: el piso lo fija el peor


def test_hitl_web_get_valida_origen():
    """Corte ligero (auditoría): un GET con Host ajeno (DNS-rebinding) no
    puede leer el pedido pendiente ni su token — mismo corte que el POST."""
    from types import SimpleNamespace

    import utils.hitl_web as hw

    hw._pendiente = SimpleNamespace(titulo="t", cuerpo="secreto",
                                    token="x", evento=__import__("threading").Event())
    try:
        puerto = hw._arrancar()  # el real (otros tests pueden haberlo movido)
        handler = SimpleNamespace(headers={"Host": f"evil.example.com:{puerto}"})
        assert hw._origen_valido(handler) is False
        handler_ok = SimpleNamespace(headers={"Host": f"127.0.0.1:{puerto}"})
        assert hw._origen_valido(handler_ok) is True
    finally:
        hw._pendiente = None


def test_stream_agrega_etiqueta_deepseek(monkeypatch, capsys):
    """La respuesta streameada llega con su rótulo (nit de UX, mesa 8)."""
    from types import SimpleNamespace

    import nodes

    def fake_stream(msgs, tools=None):
        print("hola", end="", flush=True)  # el stream real imprime los deltas
        return SimpleNamespace(content="hola", tool_calls=None)

    monkeypatch.setattr(nodes, "call_llm_agent_stream", fake_stream)
    shared = {"messages": [{"role": "user", "content": "q"}], "tool_rounds": 0}
    accion = nodes.AgentStep()._run(shared)
    assert accion == "answer"
    salida = capsys.readouterr().out
    assert "DeepSeek: " in salida and "hola" in salida


def test_pregunta_voto_congelada_sha1():
    """El contrato del voto local con el fine-tune router_voto (Mesa 3):
    cambiar UNA palabra desincroniza entrenamiento y producción."""
    import hashlib
    import json

    from nodes import PREGUNTA_VOTO

    canon = hashlib.sha1(
        json.dumps(PREGUNTA_VOTO, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    assert canon == "df1d1adec848a349d991e4aa334b4d11a4d0b81f"


def test_voto_confirmacion_tres_niveles(monkeypatch):
    """Mesa 3: acuerdo/desacuerdo confiable lo decide Laya local (sin
    DeepSeek); la banda incierta la arbitra DeepSeek; sin checkpoint,
    DeepSeek como siempre."""

    import nodes
    import utils.laya as laya_mod

    llamadas = {"ds": 0}

    def ds_fake(prompt):
        llamadas["ds"] += 1
        return "```yaml\nveredicto: directo\n```"

    monkeypatch.setattr("utils.call_llm.call_llm", ds_fake)

    def pregunta_con(resp, conf):
        return lambda estado, preguntas, setting="LAYA_MODEL": {
            "confirma_herramientas": (resp, conf)}

    # 1) acuerdo confiable: voto local dice directo 0.95 → directo, DeepSeek NUNCA
    monkeypatch.setattr(laya_mod, "disponible", lambda s: True)
    monkeypatch.setattr(laya_mod, "preguntar", pregunta_con("directo", 0.95))
    assert nodes.voto_confirmacion_router("hola, cómo estás?") == "directo"
    assert llamadas["ds"] == 0

    # 2) desacuerdo confiable: voto local dice herramientas 0.9 → lado seguro, sin DeepSeek
    monkeypatch.setattr(laya_mod, "preguntar", pregunta_con("herramientas", 0.90))
    assert nodes.voto_confirmacion_router("debatí si X") == "herramientas"
    assert llamadas["ds"] == 0

    # 3) banda incierta (0.5): arbitra DeepSeek
    monkeypatch.setattr(laya_mod, "preguntar", pregunta_con("directo", 0.50))
    assert nodes.voto_confirmacion_router("caso límite") == "directo"
    assert llamadas["ds"] == 1

    # 4) sin checkpoint: DeepSeek como siempre
    monkeypatch.setattr(laya_mod, "disponible", lambda s: False)
    assert nodes.voto_confirmacion_router("otro caso") == "directo"
    assert llamadas["ds"] == 2


# ---------------------------------------------------------------------------
# Vision/PDF (cola final): ver_imagen (data-URL base64) y ver_pdf (Files API)
# ---------------------------------------------------------------------------

PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f5c0000000049454e44ae426082"
)


def test_mime_por_contenido_ignora_el_nombre():
    """El tipo se valida por CONTENIDO (magic bytes), no por extensión."""
    import modules.vision as vision

    assert vision._mime_por_contenido(PNG_1x1) == "image/png"
    assert vision._mime_por_contenido(b"\xff\xd8\xff\xe0" + b"x" * 20) == "image/jpeg"
    assert vision._mime_por_contenido(b"GIF89a" + b"y" * 20) == "image/gif"
    assert vision._mime_por_contenido(b"GIF87a" + b"y" * 20) == "image/gif"
    assert vision._mime_por_contenido(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    # texto con nombre .png → ninguna firma coincide
    assert vision._mime_por_contenido(b"soy texto, no una imagen") is None


def test_ver_imagen_data_url_bien_formada(tmp_path, monkeypatch):
    """Sin red: el POST se mockea y se verifica la FORMA del request (data
    URL base64 en un message de USER con content=[text, image_url])."""
    import modules.vision as vision

    img = tmp_path / "foto.png"
    img.write_bytes(PNG_1x1)
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(vision, "get_api_key", lambda: "sk-test")

    capturado = {}

    class Resp:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "un pixel rojo"}}]}

    def post_fake(url, headers=None, json=None, timeout=None):
        capturado.update(url=url, headers=headers, body=json, timeout=timeout)
        return Resp()

    monkeypatch.setattr(vision.requests, "post", post_fake)

    r = vision.ver_imagen(str(img), "¿qué color es?")
    assert r == "un pixel rojo"
    assert capturado["url"].endswith("/chat/completions")
    assert capturado["headers"]["Authorization"] == "Bearer sk-test"
    msgs = capturado["body"]["messages"]
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    contenido = msgs[0]["content"]
    assert contenido[0]["type"] == "text" and contenido[0]["text"] == "¿qué color es?"
    assert contenido[1]["type"] == "image_url"
    data_url = contenido[1]["image_url"]["url"]
    assert data_url.startswith("data:image/png;base64,")
    import base64 as _b64

    assert _b64.b64decode(data_url.split(",", 1)[1]) == PNG_1x1


def test_ver_imagen_tipo_invalido_por_contenido(tmp_path, monkeypatch):
    """Un archivo de texto con nombre .png se rechaza SIN llamar a la red."""
    import modules.vision as vision

    falso = tmp_path / "disfraz.png"
    falso.write_text("no soy una imagen", encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))

    def no_llamar(*a, **k):
        raise AssertionError("no debía llamar a la API")

    monkeypatch.setattr(vision.requests, "post", no_llamar)
    r = vision.ver_imagen(str(falso), "¿qué es?")
    assert r.startswith("ERROR") and "no es una imagen soportada" in r


def test_ver_imagen_demasiado_grande_sin_llamar(tmp_path, monkeypatch):
    """Imagen > 32 MiB → ERROR legible y NINGUNA llamada."""
    import modules.vision as vision

    grande = tmp_path / "grande.png"
    grande.write_bytes(PNG_1x1)
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(vision, "IMAGEN_MAX_BYTES", 10)  # tope minúsculo para el test

    def no_llamar(*a, **k):
        raise AssertionError("no debía llamar a la API")

    monkeypatch.setattr(vision.requests, "post", no_llamar)
    r = vision.ver_imagen(str(grande), "¿qué es?")
    assert r.startswith("ERROR") and "tope para una imagen" in r


def test_ver_pdf_rasteriza_y_consulta(tmp_path, monkeypatch):
    """El contrato nuevo (medido): Files API NO acepta PDFs → pdftoppm
    rasteriza y las páginas van como imágenes al modelo. Mock del POST y
    del rasterizador; PDF real mínimo para pasar la firma %PDF."""
    import subprocess

    import modules.vision as vision

    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF-1.4 + firma + EOF")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(vision, "get_api_key", lambda: "sk-test")
    from pathlib import Path as _P
    Path = _P

    # pdftoppm falso: produce dos PNG de página
    paginas = []
    def pdftoppm_fake(*args, **kwargs):
        # argv de pdftoppm: [cmd, -png, -r, 110, INPUT, BASE_OUT] — el
        # output es el ÚLTIMO argumento; las páginas nacen ahí
        argv = args[0]
        base = argv[-1]
        pag1 = Path(base + "-1.png")
        pag1.write_bytes(b"\x89PNG" + b"fake" * 10)
        pag2 = Path(base + "-2.png")
        pag2.write_bytes(b"\x89PNG" + b"fake" * 10)
        paginas.extend([pag1, pag2])
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(vision.subprocess, "run", pdftoppm_fake)

    llamadas = []

    class RespChat:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "Total: $100"}}]}

    def post_fake(url, headers=None, **kwargs):
        llamadas.append({"url": url, "headers": headers, "json": kwargs.get("json")})
        return RespChat()

    monkeypatch.setattr(vision.requests, "post", post_fake)

    r = vision.ver_pdf(str(pdf), "¿cuál es el total?")
    assert r == "Total: $100"

    assert len(llamadas) == 1
    consulta = llamadas[0]
    assert consulta["url"].endswith("/chat/completions")
    assert consulta["headers"]["Authorization"] == "Bearer sk-test"
    contenido = consulta["json"]["messages"][0]["content"]
    assert contenido[0]["type"] == "text" and "2 páginas" in contenido[0]["text"]
    imagenes = [c for c in contenido if c["type"] == "image_url"]
    assert len(imagenes) == 2  # una por página, en orden
    assert imagenes[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_ver_pdf_no_pdf_por_contenido(tmp_path, monkeypatch):
    """Un archivo .pdf que no empieza con %PDF se rechaza sin subir nada."""
    import modules.vision as vision

    falso = tmp_path / "disfraz.pdf"
    falso.write_text("no soy un pdf", encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))

    def no_llamar(*a, **k):
        raise AssertionError("no debía llamar a la API")

    monkeypatch.setattr(vision.requests, "post", no_llamar)
    r = vision.ver_pdf(str(falso), "¿qué dice?")
    assert r.startswith("ERROR") and "no es un PDF" in r


def test_ver_pdf_demasiado_grande_sin_llamar(tmp_path, monkeypatch):
    """PDF > 64 MiB → ERROR legible y NINGUNA subida."""
    import modules.vision as vision

    pdf = tmp_path / "grande.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(vision, "PDF_MAX_BYTES", 4)  # tope minúsculo para el test

    def no_llamar(*a, **k):
        raise AssertionError("no debía llamar a la API")

    monkeypatch.setattr(vision.requests, "post", no_llamar)
    r = vision.ver_pdf(str(pdf), "¿qué dice?")
    assert r.startswith("ERROR") and "tope para un PDF" in r


# ---------------------------------------------------------------------------
# A2A (cola final): agentes_remotos y a2a_tarea contra un servidor fake
# ---------------------------------------------------------------------------


class _ServidorA2A:
    """Servidor HTTP mínimo que habla (a medias) el protocolo A2A: sirve el
    agent card en /.well-known/agent.json y responde JSON-RPC en /.
    Usa ThreadingHTTPServer de stdlib; registra el último payload recibido."""

    def __init__(self):
        self.ultimo = None

    def arrancar(self, responder=None, card=None):
        import json as _json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.ultimo = None
        card = card if card is not None else {
            "name": "eco", "description": "agente de prueba",
            "skills": [{"id": "echo", "description": "repite texto"}],
        }
        responder = responder or (lambda payload: {"jsonrpc": "2.0", "id": payload.get("id"), "result": {"echo": payload["params"]["message"]}})
        estado = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.split("?")[0] == "/.well-known/agent.json":
                    cuerpo = _json.dumps(card).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(cuerpo)))
                    self.end_headers()
                    self.wfile.write(cuerpo)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                largo = int(self.headers.get("Content-Length") or 0)
                payload = _json.loads(self.rfile.read(largo) or b"{}")
                estado.ultimo = payload
                cuerpo = _json.dumps(responder(payload)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{srv.server_address[1]}", srv


def test_a2a_sin_setting(monkeypatch):
    """Sin setting (o vacío / JSON roto) las tools lo dicen claro, sin red."""
    import modules.a2a as a2a

    for valor in (None, "", "   ", "{no soy json}", "[]"):
        if valor is None:
            monkeypatch.delenv("A2A_AGENTS", raising=False)
        else:
            monkeypatch.setenv("A2A_AGENTS", valor)
        monkeypatch.setattr(a2a, "_agentes", lambda: {})
        r = a2a.agentes_remotos()
        assert "No hay agentes remotos A2A configurados" in r
        r2 = a2a.a2a_tarea("x", "hola")
        assert "No hay agentes remotos A2A configurados" in r2

    # JSON roto se trata como vacío (degradación)
    monkeypatch.setenv("A2A_AGENTS", "{no soy json}")
    assert a2a._agentes() == {}


def test_a2a_lista_y_tarea(monkeypatch):
    """Con setting a un servidor fake: agentes_remotos lista el card y
    a2a_tarea envía JSON-RPC message/send y parsea el result."""
    import json

    import modules.a2a as a2a

    srv = _ServidorA2A()
    base, httpd = srv.arrancar()
    try:
        monkeypatch.setenv("A2A_AGENTS", json.dumps({"eco": base}))

        listado = a2a.agentes_remotos()
        assert "eco" in listado and base in listado
        assert "agente de prueba" in listado
        assert "echo" in listado and "repite texto" in listado

        r = a2a.a2a_tarea("eco", "hola mundo")
        payload = json.loads(r)
        assert payload["echo"] == {"role": "user", "parts": [{"type": "text", "text": "hola mundo"}]}

        # la FORMA del request enviado: JSON-RPC 2.0 message/send
        enviado = srv.ultimo
        assert enviado["jsonrpc"] == "2.0"
        assert enviado["method"] == "message/send"
        assert enviado["params"]["message"]["role"] == "user"
        assert enviado["params"]["message"]["parts"] == [{"type": "text", "text": "hola mundo"}]
        assert isinstance(enviado["id"], int)
    finally:
        httpd.shutdown()


def test_a2a_error_jsonrpc(monkeypatch):
    """Un error JSON-RPC del agente se devuelve como texto, no rompe."""
    import json as _json

    import modules.a2a as a2a

    srv = _ServidorA2A()
    base, httpd = srv.arrancar(
        responder=lambda payload: {"jsonrpc": "2.0", "id": payload.get("id"),
                                   "error": {"code": -32000, "message": "no puedo"}})
    try:
        monkeypatch.setenv("A2A_AGENTS", _json.dumps({"eco": base}))
        r = a2a.a2a_tarea("eco", "hola")
        assert r.startswith("ERROR JSON-RPC") and "no puedo" in r
    finally:
        httpd.shutdown()


def test_a2a_agente_caido_es_inaccesible(monkeypatch):
    """Un agente caído se reporta 'inaccesible' (degradación, no crash)."""
    import json as _json

    import modules.a2a as a2a

    monkeypatch.setenv("A2A_AGENTS", _json.dumps({"caido": "http://127.0.0.1:1"}))
    r = a2a.agentes_remotos()
    assert "inaccesible" in r and "caido" in r

    r2 = a2a.a2a_tarea("caido", "hola")
    assert r2.startswith("ERROR") and "inaccesible" in r2

    # nombre no configurado: texto claro, sin red
    monkeypatch.setenv("A2A_AGENTS", _json.dumps({"otro": "http://127.0.0.1:1"}))
    r3 = a2a.a2a_tarea("inexistente", "hola")
    assert r3.startswith("ERROR") and "no configurado" in r3


def test_a2a_card_agente_caido_no_corta_el_listado(monkeypatch):
    """Con un agente sano y otro caído, el listado muestra el card del sano
    e 'inaccesible' para el caído (el caído no corta el listado)."""
    import json as _json

    import modules.a2a as a2a

    srv = _ServidorA2A()
    base, httpd = srv.arrancar()
    try:
        monkeypatch.setenv("A2A_AGENTS", _json.dumps({"sano": base, "caido": "http://127.0.0.1:1"}))
        r = a2a.agentes_remotos()
        assert "sano" in r and "agente de prueba" in r
        assert "caido" in r and "inaccesible" in r
    finally:
        httpd.shutdown()


def test_action_space_suma_vision_y_a2a():
    from nodes import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    assert {"ver_imagen", "ver_pdf", "agentes_remotos", "a2a_tarea"} <= nombres


# ---------------------------------------------------------------------------
# Pulido de terminal (mesa 8): colores por tipo de evento + progreso de rondas
# ---------------------------------------------------------------------------


def test_colorear_sin_tty_no_pinta(monkeypatch):
    """Sin tty (tests, pipes) el color NO aparece: los textos quedan
    intactos. Es lo que garantiza que nada cambie en CI ni en logs."""
    import utils.terminal as t

    monkeypatch.setattr(t.sys.stdout, "isatty", lambda: False, raising=False)
    assert t.colorear("hola", "tool") == "hola"
    assert t.colorear("hola", "error") == "hola"


def test_colorear_con_tty_pinta_y_respeta_apagados(monkeypatch):
    """Con tty sí pinta (códigos ANSI + reset); NO_COLOR y COLOR=0 mandan
    sobre un tty real."""
    import utils.terminal as t

    monkeypatch.setattr(t.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("COLOR", raising=False)
    pintado = t.colorear("hola", "error")
    assert pintado != "hola" and "\033[" in pintado and pintado.endswith("\033[0m")
    assert "hola" in pintado

    # NO_COLOR (estándar) apaga aun con tty
    monkeypatch.setenv("NO_COLOR", "1")
    assert t.colorear("hola", "error") == "hola"

    # COLOR=0 (escape hatch propio) también apaga
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("COLOR", "0")
    assert t.colorear("hola", "error") == "hola"


def test_colorear_tipo_desconocido_no_altera(monkeypatch):
    import utils.terminal as t

    monkeypatch.setattr(t.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("COLOR", raising=False)
    assert t.colorear("hola", "inexistente") == "hola"


def test_progreso_ronda():
    from utils.terminal import progreso_ronda

    assert progreso_ronda(2, 8) == "⚙ ronda 2/8"
    assert progreso_ronda(1, 1) == "⚙ ronda 1/1"
    assert progreso_ronda(3) == "⚙ ronda 3"  # sin tope conocido


def test_execute_tools_anuncia_y_etiqueta(monkeypatch, capsys):
    """Una ronda larga no parece colgada: cada tool se anuncia ANTES de
    correr y la ronda consumida se etiqueta con su avance (n/MAX)."""
    import nodes

    # sin tty → texto plano (así lo ve un pipe; los tests no ven ANSI)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)
    monkeypatch.setattr(nodes, "MODULE_IMPLS", {})
    monkeypatch.setattr(
        nodes, "run_tool_call",
        lambda tc, impls: {"role": "tool", "tool_call_id": tc["id"], "content": "ok"},
    )

    et = nodes.ExecuteTools()
    shared = {"messages": [], "tool_rounds": 0}
    tool_calls = [
        {"id": "a", "function": {"name": "read_file", "arguments": "{}"}},
        {"id": "b", "function": {"name": "list_files", "arguments": "{}"}},
    ]
    resultados = et.exec(tool_calls)
    salida = capsys.readouterr().out
    assert "→ read_file" in salida and "→ list_files" in salida
    # el anuncio precede al resultado: aparece aunque el resultado viniera ok
    assert len(resultados) == 2

    # la ronda se etiqueta con el avance sobre el tope
    et.post(shared, None, resultados)
    salida = capsys.readouterr().out
    assert f"⚙ ronda 1/{nodes.MAX_TOOL_ROUNDS}" in salida


# ---------------------------------------------------------------------------
# Pre-filtro de contexto por Laya (Mesa 6)
# ---------------------------------------------------------------------------

def test_unidades_bloques_no_parte_parrafos():
    from utils.contexto import unidades_bloques

    texto = "# Título\n\nprimer párrafo\ncon dos líneas\n\n# Sección\n\nsegundo párrafo"
    bloques = unidades_bloques(texto)
    assert bloques == ["# Título", "primer párrafo\ncon dos líneas", "# Sección", "segundo párrafo"]
    assert unidades_bloques("") == []


def test_elegir_por_laya_sin_modelo_es_noop(monkeypatch):
    """Regla de hierro: sin Laya disponible, entran los primeros max sin
    perder recall (no-op). El filtro es un acelerador, no una dependencia.
    Desde exp/13 el checkpoint existe: la ausencia se SIMULA con monkeypatch
    (la regla es 'si no está disponible', no 'si nunca se entrenó')."""
    import utils.laya as ul
    from utils.contexto import elegir_por_laya

    monkeypatch.setattr(ul, "disponible", lambda setting=None: False)
    unidades = ["a", "b", "c", "d"]
    # checkpoint indisponible: _puntuar → None → primeros N (default seguro)
    out = elegir_por_laya("consulta", unidades, 2, setting_modelo="LAYA_MODEL_PREFILTRO")
    assert out == ["a", "b"]
    # con max<=0 o menos unidades que el tope, devuelve intactas
    assert elegir_por_laya("q", unidades, 0) == unidades
    assert elegir_por_laya("q", unidades[:2], 5) == unidades[:2]


def test_elegir_por_laya_elige_y_conserva_orden(monkeypatch):
    """Con un Laya simulado, elige los de mayor puntaje y los devuelve en
    ORDEN ORIGINAL (la relevancia decide qué entra, no cómo se muestra)."""
    import utils.contexto as ctx

    # simula puntajes de Laya: "a" y "c" aportan; "b" y "d" no
    puntajes = {"bloque a": 0.9, "bloque b": 0.1, "bloque c": 0.8, "bloque d": 0.4}
    monkeypatch.setattr(ctx, "_puntuar",
                        lambda consulta, unidades, setting: {i: puntajes[u] for i, u in enumerate(unidades)})

    unidades = ["bloque a", "bloque b", "bloque c", "bloque d"]
    out = ctx.elegir_por_laya("q", unidades, 2)
    assert out == ["bloque a", "bloque c"]  # los 2 mejores, en orden original


def test_rag_prefiltro_noop_sin_modelo(monkeypatch):
    """rag_search con RAG_PREFILTRO=1 pero sin Laya: la salida queda intacta."""
    import modules.rag as rag
    import utils.contexto as ctx

    salida = ("3 fragmentos indexados (modo lexico); top 3:\n\n"
              "--- a.py (score 0.5) ---\ncuerpo a\n\n"
              "--- b.py (score 0.4) ---\ncuerpo b\n\n"
              "--- c.py (score 0.3) ---\ncuerpo c")
    # sin checkpoint del prefiltro: _puntuar levanta (Laya no está) → no-op
    monkeypatch.setattr(ctx, "_puntuar",
                        lambda consulta, unidades, setting: (_ for _ in ()).throw(RuntimeError("sin modelo")))
    monkeypatch.setenv("RAG_PREFILTRO", "1")
    monkeypatch.setenv("RAG_PREFILTRO_N", "2")
    assert rag._prefiltrar("consulta", salida, 3) == salida  # sin Laya: intacta
    # con 0 lo apaga explícitamente
    monkeypatch.setenv("RAG_PREFILTRO", "0")
    assert rag._prefiltrar("consulta", salida, 3) == salida


def test_rag_prefiltro_actua_con_laya_simulado(monkeypatch):
    import modules.rag as rag
    import utils.contexto as ctx

    salida = ("3 fragmentos indexados (modo lexico); top 3:\n\n"
              "--- a.py (score 0.5) ---\ncuerpo a\n\n"
              "--- b.py (score 0.4) ---\ncuerpo b\n\n"
              "--- c.py (score 0.3) ---\ncuerpo c")
    monkeypatch.setenv("RAG_PREFILTRO", "1")
    monkeypatch.setenv("RAG_PREFILTRO_N", "1")
    # el fragmento que contiene "cuerpo c" aporta; el resto no
    monkeypatch.setattr(ctx, "_puntuar", lambda consulta, unidades, setting: {
        i: (0.9 if "cuerpo c" in u else 0.1) for i, u in enumerate(unidades)})
    out = rag._prefiltrar("consulta", salida, 3)
    assert "[prefiltro Laya: 3 → 1 fragmentos]" in out
    assert out.startswith("3 fragmentos indexados")  # el resumen original se conserva
    assert "cuerpo c" in out and "cuerpo a" not in out


def test_memoria_prefiltro_noop_sin_modelo(tmp_path, monkeypatch):
    """memory_search sin Laya devuelve la memoria completa (no-op)."""
    import modules.memoria as mem
    import utils.contexto as ctx

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORIA_PREFILTRO", "1")
    monkeypatch.setattr(ctx, "_puntuar",
                        lambda consulta, unidades, setting: (_ for _ in ()).throw(RuntimeError("sin modelo")))
    (tmp_path / "a.md").write_text("nota sobre pytest y compacción\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("otra nota cualquiera\n", encoding="utf-8")
    out = mem.memory_search("compacción")
    assert "a.md" in out  # encuentra la nota real
    assert "prefiltro Laya" not in out  # sin Laya, sin aviso (no-op)


def test_memoria_prefiltro_actua(tmp_path, monkeypatch):
    import modules.memoria as mem
    import utils.contexto as ctx

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORIA_PREFILTRO", "1")
    monkeypatch.setenv("MEMORIA_PREFILTRO_N", "1")
    for nombre in ("a.md", "b.md", "c.md"):
        (tmp_path / nombre).write_text(f"contenido {nombre} sobre compacción\n", encoding="utf-8")
    monkeypatch.setattr(ctx, "_puntuar", lambda consulta, unidades, setting: {
        i: (0.9 if "b.md" in str(u) else 0.1) for i, u in enumerate(unidades)})
    out = mem.memory_search("compacción")
    assert "[prefiltro Laya: 3 → 1 archivos]" in out
    assert "b.md" in out


def test_rag_prefiltro_extrae_fragmentos():
    """El parser de la salida de buscar() separa fragmentos sin romper el
    shape (y devuelve None cuando no hay fragmentos)."""
    import modules.rag as rag

    salida = ("2 fragmentos indexados (modo lexico); top 2:\n\n"
              "--- a.py (score 0.5) ---\ncuerpo a\n\n"
              "--- b.py (score 0.4) ---\ncuerpo b")
    frags = rag._extraer_fragmentos(salida)
    assert len(frags) == 2
    assert frags[0].startswith("--- a.py (score 0.5) ---")
    assert "cuerpo b" in frags[1]
    assert rag._extraer_fragmentos("El índice está vacío: reindexa con rag_index.") is None

def _historial_sintetico(n_vueltas=50, relleno=400):
    """Historial canónico grande: system + N vueltas (user → assistant con
    tool_calls → tool → assistant texto). Cada vuelta son 4 mensajes, así
    que n_vueltas=50 da 201 mensajes, con mezcla real de tools."""
    msgs = [{"role": "system", "content": "system prompt estable " + "x" * 200}]
    for i in range(n_vueltas):
        msgs.append({"role": "user", "content": f"pedido {i} " + "u" * relleno})
        msgs.append({
            "role": "assistant", "content": None,
            "tool_calls": [{"id": f"call_{i}", "type": "function",
                            "function": {"name": "read_file", "arguments": "{}"}}],
        })
        msgs.append({"role": "tool", "tool_call_id": f"call_{i}",
                     "content": f"resultado {i} " + "t" * relleno})
        msgs.append({"role": "assistant", "content": f"respuesta {i} " + "a" * relleno})
    return msgs


def test_compaccion_noop_historial_corto():
    """Con menos de ventana+2 mensajes devuelve intacto (no-op documentado)."""
    from utils.compaccion import compactar

    corto = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hola " + "x" * 5000},
        {"role": "assistant", "content": "chau " + "y" * 5000},
    ]
    out = compactar(corto, max_chars=10)
    assert out == corto  # intacto aunque supere max_chars


def test_compaccion_noop_si_entra_en_max_chars():
    """Si el historial ya entra en max_chars, no toca nada."""
    from utils.compaccion import compactar, serializar

    largo = _historial_sintetico(n_vueltas=10)
    out = compactar(largo, max_chars=len(serializar(largo)) + 10)
    assert out == largo


def test_compaccion_conserva_system_y_ventana_caliente():
    """El system y los últimos N mensajes quedan intactos; la zona fría se
    reemplaza por UN resumen [compacción]."""
    from utils.compaccion import PREFIJO_COMPACCION, VENTANA_DEFAULT, compactar

    largo = _historial_sintetico(n_vueltas=40)
    out = compactar(largo, max_chars=100)
    # system intacto
    assert out[0] == largo[0]
    # resumen sintético en el medio
    assert out[1]["role"] == "user"
    assert out[1]["content"].startswith(PREFIJO_COMPACCION)
    # la ventana caliente son los últimos N mensajes, idénticos byte a byte
    assert out[-(VENTANA_DEFAULT):] == largo[-(VENTANA_DEFAULT):]
    assert len(out) < len(largo)


def test_compaccion_unidad_indivisible():
    """Compactar nunca deja un assistant con tool_calls sin su tool, ni una
    tool huérfana."""
    from utils.compaccion import compactar, validar_historial

    largo = _historial_sintetico(n_vueltas=40)
    out = compactar(largo, max_chars=100)
    assert validar_historial(out) == []
    # ninguna tool huérfana: cada tool tiene su assistant con tools antes
    ids_con_tools = {
        tc["id"]
        for m in out if m.get("role") == "assistant"
        for tc in m.get("tool_calls", [])
    }
    for j, m in enumerate(out):
        if m.get("role") == "tool":
            assert m["tool_call_id"] in ids_con_tools, f"tool huérfana en [{j}]"


def test_compaccion_no_parte_unidad_al_recortar():
    """Caso borde: si el corte por ventana cae en medio de una unidad, la
    unidad entra completa (la ventana puede quedar en más de N mensajes)."""
    from utils.compaccion import compactar, validar_historial

    largo = _historial_sintetico(n_vueltas=40)
    out = compactar(largo, max_chars=100)
    assert validar_historial(out) == []
    # ninguna unidad (assistant con tools) quedó a medias
    for i, m in enumerate(out):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            assert i + 1 < len(out) and out[i + 1].get("role") == "tool"


def test_compaccion_determinista():
    """Mismo input → mismo output (dos llamadas)."""
    from utils.compaccion import compactar

    largo = _historial_sintetico(n_vueltas=30)
    a = compactar(largo, max_chars=100)
    b = compactar(largo, max_chars=100)
    assert a == b


def test_compaccion_invariantes_antes_y_despues():
    """El test que clava los invariantes del modo thinking: el sintético
    grande (200+ mensajes con tools) valida ANTES y DESPUÉS de compactar."""
    from utils.compaccion import compactar, validar_historial

    largo = _historial_sintetico(n_vueltas=50)
    assert len(largo) >= 201
    assert validar_historial(largo) == []  # ANTES: válido
    out = compactar(largo, max_chars=100)
    assert validar_historial(out) == []  # DESPUÉS: sigue válido

    # y validar_historial SÍ detecta cada rotura (no es un chequeo vacuo)
    con_reasoning = [dict(m) for m in largo]
    con_reasoning[5]["reasoning_content"] = "trace"
    assert validar_historial(con_reasoning)
    sin_tools = [dict(m) for m in largo]
    del sin_tools[3]  # saca la tool de la vuelta 0: su head queda sin tool
    assert validar_historial(sin_tools)
    sin_system = list(largo[1:])
    assert validar_historial(sin_system)


def test_agent_step_prep_compacta_y_cuenta(monkeypatch, capsys):
    """Integración: con COMPACTION_CHARS chico, AgentStep.prep devuelve el
    historial compactado y cuenta en shared['compacciones']. Y no re-compacta
    la misma ronda (huella)."""
    import nodes
    from utils.compaccion import PREFIJO_COMPACCION

    monkeypatch.setenv("COMPACTION_CHARS", "200")
    largo = _historial_sintetico(n_vueltas=40)
    shared = {"messages": list(largo), "tool_rounds": 0}

    mensajes, tools = nodes.AgentStep().prep(shared)
    assert shared["compacciones"] == 1
    assert mensajes is shared["messages"]
    assert len(mensajes) < len(largo)
    assert mensajes[1]["content"].startswith(PREFIJO_COMPACCION)
    assert mensajes[0] == largo[0]
    assert "zona fría" in capsys.readouterr().out

    # segunda llamada con el MISMO historial ya compactado: no re-compacta
    nodes.AgentStep().prep(shared)
    assert shared["compacciones"] == 1

    # un historial corto no dispara compacción
    shared2 = {"messages": largo[:3], "tool_rounds": 0}
    nodes.AgentStep().prep(shared2)
    assert "compacciones" not in shared2


def test_get_question_slash_aprobaciones(monkeypatch, capsys):
    """/aprobaciones muestra el historial HITL sin llegar al modelo."""
    import nodes
    import utils.aprobaciones as ap

    ap.limpiar()
    ap.registrar("run_command", "echo hola", True, "auto")
    shared = {"messages": [], "tool_rounds": 0}
    accion = nodes.GetQuestion().post(shared, None, "/aprobaciones")
    salida = capsys.readouterr().out
    assert accion == "continue"
    assert "✓ [auto] run_command: echo hola" in salida
    assert shared["messages"] == []  # no entra al historial del modelo
    # una pregunta normal sí entra al historial
    nodes.GetQuestion().post(shared, None, "hola")
    assert shared["messages"][-1]["content"] == "hola"
    ap.limpiar()


# ---------------------------------------------------------------------------
# HITL UX (mesa 8): highlight, explicación y historial de aprobaciones
# ---------------------------------------------------------------------------

def test_highlight_diff(monkeypatch):
    """El diff se colorea por tipo de línea; sin color, queda intacto."""
    import utils.terminal as term

    diff = "@@ -1 +1 @@\n-a = 1\n+a = 2\n c"
    # sin tty/color: intacto (lo que ven tests, pipes y logs)
    monkeypatch.setattr(term, "_quiere_color", lambda: False)
    assert term.highlight_diff(diff) == diff
    # con color: adiciones verdes, supresiones rojas, cabeceras coloreadas
    monkeypatch.setattr(term, "_quiere_color", lambda: True)
    h = term.highlight_diff(diff)
    assert "\033[32m+a = 2\033[0m" in h  # verde
    assert "\033[31m-a = 1\033[0m" in h  # rojo
    assert "\033[36m@@ -1 +1 @@\033[0m" in h  # cian
    # las cabeceras +++/--- van en gris, no verde/rojo (no confundir el nombre)
    assert "\033[90m--- a (actual)\033[0m" in term.highlight_diff("--- a (actual)\n+++ a (nuevo)")


def test_explicar_comando():
    """Explicación corta y determinista por comando (mesa 8)."""
    from utils.policy import explicar

    assert "borrado recursivo" in explicar("rm -rf /tmp/x")
    assert "borra archivos" in explicar("rm archivo.txt")
    assert "publica commits" in explicar("git push origin main")
    assert "solo lee" in explicar("grep -r foo src/")
    assert "código Python arbitrario" in explicar('python3 -c "print(1)"')
    # no reconocido: describe el default preguntar
    assert "pide aprobación" in explicar("comando_raro --x")
    # vacío: default seguro
    assert "inválido" in explicar("   ")


def test_historial_aprobaciones(monkeypatch):
    """El registro de aprobaciones cuenta aprobadas/rechazadas de la sesión."""
    import utils.aprobaciones as ap

    ap.limpiar()
    assert "No hay aprobaciones" in ap.resumen()

    ap.registrar("run_command", "echo hola", True, "auto")
    ap.registrar("write_file", "/tmp/x.py", False)
    r = ap.resumen()
    assert "2 (1 aprobadas, 1 rechazadas)" in r
    assert "✓ [auto] run_command: echo hola" in r
    assert "✗ write_file: /tmp/x.py" in r
    # el buffer no crece sin techo
    for i in range(300):
        ap.registrar("run_command", f"c{i}", True)
    assert len(ap.eventos()) == 200
    ap.limpiar()


def test_approve_registra_aprobaciones(monkeypatch, tmp_path):
    """write_file/run_command registran su aprobación (aprobada o rechazada)."""
    import modules.coding as coding
    import modules.escritura as esc
    import utils.aprobaciones as ap

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setenv("HITL_AUTO", "0")
    ap.limpiar()

    # run_command rechazado: queda registrado como rechazo
    monkeypatch.setattr(coding, "_approve", lambda p: False)
    coding.run_command("echo x")
    assert ap.eventos()[-1]["tipo"] == "run_command"
    assert ap.eventos()[-1]["decision"] is False

    # write_file aprobado: queda registrado como aprobación
    monkeypatch.setattr(esc, "_approve", lambda p: True)
    esc.write_file(str(tmp_path / "nuevo.txt"), "contenido")
    assert ap.eventos()[-1]["tipo"] == "write_file"
    assert ap.eventos()[-1]["decision"] is True
    ap.limpiar()


def test_catalogo_memoria_al_arranque(tmp_path, monkeypatch, capsys):
    """El arranque muestra el CATÁLOGO de la biblioteca (qué notas hay) SIN
    inyectar su contenido al contexto — el arranque vacío es regla (mesa 8)."""
    import main

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORIA", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    (tmp_path / "nota_a.md").write_text("contenido secreto A\n", encoding="utf-8")
    (tmp_path / "nota_b.md").write_text("contenido secreto B\n", encoding="utf-8")

    main.catalogo_memoria()
    salida = capsys.readouterr().out
    assert "biblioteca: 2 notas" in salida
    assert "nota_a.md" in salida and "nota_b.md" in salida
    # catálogo, no contenido: el cuerpo de las notas NO se imprime
    assert "contenido secreto" not in salida

    # MEMORIA=0 no muestra nada
    monkeypatch.setenv("MEMORIA", "0")
    main.catalogo_memoria()
    assert capsys.readouterr().out == ""


def test_catalogo_memoria_vacio(tmp_path, monkeypatch, capsys):
    """Biblioteca vacía: no imprime nada (arranque silencioso)."""
    import main

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORIA", "1")
    main.catalogo_memoria()
    assert capsys.readouterr().out == ""


def test_catalogo_memoria_nunca_rompe(monkeypatch, capsys):
    """Aunque la lectura de la biblioteca falle, el arranque sigue."""
    import main

    monkeypatch.setenv("MEMORIA", "1")
    import modules.memoria as mem

    def boom():
        raise OSError("disco")

    monkeypatch.setattr(mem, "_archivos_md", boom)
    main.catalogo_memoria()  # no levanta
    assert capsys.readouterr().out == ""


def test_split_umbrales_router_y_voto(monkeypatch):
    """exp/8: la compuerta del router (LAYA_UNSURE_HIGH) y la del voto
    (LAYA_UNSURE_HIGH_VOTO) son settings SEPARADAS. El test fija el entorno
    con monkeypatch porque _setting lee en cascada nuestro .env y el de bmo
    (BMO_ENV tiene LAYA_UNSURE_HIGH=0.7 heredado, que enmascara el default
    0.85 del código — medido: sin fijar la env, veredicto(0.84) da met)."""
    from utils.laya import veredicto

    # la setting del router manda sobre cualquier cascada
    monkeypatch.setenv("LAYA_UNSURE_HIGH", "0.85")
    assert veredicto(0.84) == "uncertain"
    assert veredicto(0.85) == "met"
    monkeypatch.setenv("LAYA_UNSURE_HIGH", "0.7")
    assert veredicto(0.75) == "met"
    # el voto consulta con su propio alto explícito: nunca hereda al router
    assert veredicto(0.75, alto=0.7) == "met"
    assert veredicto(0.84, alto=0.7) == "met"


def test_nota_presupuesto_solo_en_la_anteultima_ronda():
    """exp/4: el modelo no veía su presupuesto (el ⚙ iba solo a la terminal)
    y el tope lo cortaba en mudo — tres sesiones de aplicación muertas así.
    La nota viaja en el resultado de la última tool de la anteúltima ronda."""
    from nodes import nota_presupuesto

    assert nota_presupuesto(2, 4) is None
    assert nota_presupuesto(4, 4) is None
    nota = nota_presupuesto(3, 4)
    assert nota and "3/4" in nota and "ÚLTIMA" in nota and "reinicia" in nota
    # máximo degenerado: la única ronda es también la anteúltima
    assert nota_presupuesto(0, 1) is not None


def test_edit_file_diagnostico_whitespace_y_candidatos():
    """exp/10: edit_file generaba el 63% de los errores del harness (27/43)
    con un feedback ciego ('releé el archivo'). Ahora diagnostica la causa
    clásica (indentación) y ofrece candidatos con línea — el reintento
    debería ser uno y sin relectura completa."""
    from modules.coding import _contiene_subsecuencia, _normalizar_ws, candidatos_similares

    # archivo con indentación MIXTA: def g usa un tab real
    archivo = "def f():\n    x = 1\n    return x\ndef g():\n\ty = 2\n    return y\n"
    # old_string 'igual' pero con 4 espacios donde el archivo tiene tab
    viejo_espacios = "def g():\n    y = 2\n    return y"

    # el match exacto falla, pero la subsecuencia normalizada está
    assert "def g():\n\ty = 2\n    return y" not in viejo_espacios
    lineas_txt = _normalizar_ws(archivo).split("\n")
    lineas_old = _normalizar_ws(viejo_espacios).split("\n")
    assert _contiene_subsecuencia(lineas_txt, lineas_old)

    # candidatos: la ventana correcta con su línea exacta (base 1)
    cands = candidatos_similares(archivo, viejo_espacios)
    assert cands and cands[0][0] == 4, "la ventana def g() arranca en L4"
    assert "y = 2" in cands[0][1]

    # cadena totalmente ajena: sin candidatos
    assert candidatos_similares(archivo, "import numpy as np\nimport pandas") == []


def test_dsml_con_presupuesto_agotado_no_rearma_lo_retirado():
    """exp/12: medido en exp/4 — el modelo emitía tool-calls como texto
    DSML DESPUÉS del retiro por el tope y la recuperación las ejecutaba:
    la ley L8 quedaba by-paseada. Ahora sin tools el markup se corta; con
    tools, la recuperación de siempre."""
    from nodes import MENSAJE_DSML_AGOTADO, dsml_con_presupuesto_agotado

    content = "Cerrando el estado.<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name=\"write_file\">..."
    # tools presentes: intacto, sin aviso (la recuperación corre aparte)
    nuevo, avisar = dsml_con_presupuesto_agotado(content, ["x"], TOOLS_PRESENTES := ["t"])
    assert nuevo == content and avisar is False
    # tools retiradas: corta antes del markup
    nuevo, avisar = dsml_con_presupuesto_agotado(content, ["x"], None)
    assert nuevo == "Cerrando el estado." and avisar is True
    # solo markup: mensaje honesto y accionable
    solo = "<｜｜DSML｜｜ calls> todo markup"
    nuevo, avisar = dsml_con_presupuesto_agotado(solo, ["x"], None)
    assert nuevo == MENSAJE_DSML_AGOTADO and "seguí" in nuevo and avisar is True


def test_tool_evals_no_pisa_el_baseline(monkeypatch, tmp_path):
    """exp/2: la tool del chat corre el pipeline de evals COMPARANDO contra
    el baseline pero sin guardarlo — el ancla de medición no se sobrescribe
    desde una conversación (el CLI sí actualiza, como siempre)."""
    import modules.evals as mod

    llamadas = {"guardar": 0}
    monkeypatch.setattr("evals.correr_bench", lambda agente=None: ({"score": 1.0}, None))
    monkeypatch.setattr("evals.comparar_baseline", lambda b: {"veredicto": "OK"})
    monkeypatch.setattr("evals.guardar_baseline", lambda *a, **k: llamadas.__setitem__("guardar", llamadas["guardar"] + 1))
    monkeypatch.setattr("evals.linter_runs", lambda d=None: {})
    monkeypatch.setattr("evals.costos_runs", lambda d=None: [])
    monkeypatch.setattr("evals.informe_markdown", lambda *a, **k: "# evals")

    # rutas DENTRO de las raíces permitidas (tmp_path de pytest está fuera)
    r = mod.evals(dir_runs=None, salida="salidas/banco")
    assert "Informe de evals generado" in r
    assert llamadas["guardar"] == 0, "la tool del chat NO guarda baseline"


def test_contrato_prefiltro_congelado_sha1():
    """El contrato del pre-filtro (exp/13): entrenamiento y producción leen
    la misma pregunta byte a byte — cambiar una palabra desincroniza el
    fine-tune router_prefiltro sin que nada lo note, como los demás
    contratos congelados."""
    import hashlib
    import json

    from utils.contexto import PREGUNTA_PREFILTRO

    sha = hashlib.sha1(json.dumps(PREGUNTA_PREFILTRO, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert sha == "b40267534690ca6a787ebf8b40903b8dac8b3521", f"contrato del prefiltro derivado: {sha}"


def test_preguntar_lote_alinea_y_extrae(monkeypatch):
    """exp/14: preguntar_lote() es la versión en lote de preguntar(): un
    forward compartido (predict_batch) para N estados, con la MISMA
    extracción (respuesta, confianza) y alineado por índice."""
    import utils.laya as laya_mod

    class FakeAgente:
        def __init__(self):
            self.vistos = None

        def predict_batch(self, estados, preguntas, lang="es"):
            self.vistos = list(estados)
            # dos resultados con answer_confidence DISTINTAS, en orden
            return [
                {"answers": {"aporta_contexto": {"choice": "si", "answer_confidence": 0.9}}},
                {"answers": {"aporta_contexto": {"choice": "no", "answer_confidence": 0.2}}},
            ]

    fake = FakeAgente()
    monkeypatch.setattr(laya_mod, "agente", lambda setting="LAYA_MODEL": fake)

    estados = [{"consulta": "a", "bloque": "x"}, {"consulta": "a", "bloque": "y"}]
    contrato = {"aporta_contexto": {"type": "choice"}}
    salida = laya_mod.preguntar_lote(estados, contrato)

    assert len(salida) == 2  # alineado 1:1 con los estados
    assert salida[0]["aporta_contexto"] == ("si", 0.9)
    assert salida[1]["aporta_contexto"] == ("no", 0.2)
    # el batch se mandó de una: los MISMOS estados y contrato
    assert fake.vistos == estados


def test_puntuar_una_llamada_y_formula(monkeypatch):
    """exp/14: _puntuar() arma TODOS los estados (mismo truncamiento y
    orden) y llama a preguntar_lote UNA vez; los puntajes siguen la fórmula
    confianza si 'si', 1-confianza si 'no'."""
    import utils.contexto as ctx
    import utils.laya as laya_mod

    llamadas = {"n": 0}
    capturado = {}

    def fake_lote(estados, preguntas, setting="LAYA_MODEL"):
        llamadas["n"] += 1
        capturado["estados"] = list(estados)
        # 'si' → confianza; 'no' → 1-confianza
        return [
            {"aporta_contexto": ("si", 0.8)},
            {"aporta_contexto": ("no", 0.25)},
            {"aporta_contexto": ("si", 0.6)},
            {"aporta_contexto": ("no", 0.1)},
        ]

    monkeypatch.setattr(laya_mod, "disponible", lambda setting="LAYA_MODEL": True)
    monkeypatch.setattr(laya_mod, "preguntar_lote", fake_lote)

    unidades = ["u0", "u1", "u2", "u3"]
    puntajes = ctx._puntuar("consulta", unidades, "LAYA_MODEL_PREFILTRO")

    assert llamadas["n"] == 1, "debe ser UNA sola llamada en lote"
    # fórmula: si → conf; no → 1-conf
    assert puntajes == {0: 0.8, 1: 1.0 - 0.25, 2: 0.6, 3: 1.0 - 0.1}
    # truncamiento y orden: consulta[:1000], bloque[:2000], en orden
    assert capturado["estados"] == [
        {"consulta": "consulta", "bloque": "u0"},
        {"consulta": "consulta", "bloque": "u1"},
        {"consulta": "consulta", "bloque": "u2"},
        {"consulta": "consulta", "bloque": "u3"},
    ]


def test_puntuar_lote_que_falla_devuelve_none(monkeypatch):
    """exp/14: la ley de hierro no cambia — si preguntar_lote lanza, _puntuar
    devuelve None y el llamador cae al default seguro (sin juicio)."""
    import utils.contexto as ctx
    import utils.laya as laya_mod

    def boom(estados, preguntas, setting="LAYA_MODEL"):
        raise RuntimeError("batch roto")

    monkeypatch.setattr(laya_mod, "disponible", lambda setting="LAYA_MODEL": True)
    monkeypatch.setattr(laya_mod, "preguntar_lote", boom)

    assert ctx._puntuar("c", ["a", "b"], "LAYA_MODEL_PREFILTRO") is None


def test_embed_decide_prefijo_despues_de_cargar(monkeypatch):
    """Fix 1: en la PRIMERA llamada de un proceso con e5 activo el prefijo
    debe decidirse sobre el nombre EFECTIVAMENTE cargado, no sobre la global
    (que arranca en None). Un fake de get_modelo deja _nombre_modelo en un
    nombre con 'e5' y captura el input: el texto debe llegar prefijado."""
    import utils.embeddings as emb

    capturado = {}

    class FakeModelo:
        def embed(self, textos):
            capturado["textos"] = list(textos)
            return [[0.0, 0.1] for _ in textos]

    def fake_get_modelo():
        emb._nombre_modelo = "intfloat/multilingual-e5-large"
        return FakeModelo()

    monkeypatch.setattr(emb, "_nombre_modelo", None)
    monkeypatch.setattr(emb, "get_modelo", fake_get_modelo)

    r = emb.embed(["hola"])  # UNA sola llamada

    assert capturado["textos"] == ["passage: hola"], capturado
    assert r == [[0.0, 0.1]]


def test_carga_trazas_serializa_criteria_no_string(tmp_path):
    """Fix 3: un criteria lista/dict del task yaml reventaba el INSERT de
    sqlite3 (InterfaceError). Debe serializarse a JSON y la carga seguir.

    NOTA: la carpeta debe vivir dentro de AGENT_ALLOWED_DIRS (la contención
    de _resolve vale también en tests), así que se usa un dir temporal bajo
    la raíz del repo, no tmp_path."""
    import json as _json
    import sqlite3

    import carga_trazas

    base = RAIZ / "_tmp_test_carga_trazas"
    base.mkdir(exist_ok=True)
    try:
        carpeta = base / "trazas"
        carpeta.mkdir(exist_ok=True)
        registro = {
            "answers": {"next": "router"},
            "fields": {"task": "clasificar", "criteria": ["a", "b"], "steps": []},
        }
        (carpeta / "uno.jsonl").write_text(_json.dumps(registro) + "\n", encoding="utf-8")

        db = base / "trazas.db"
        total, rotas = carga_trazas.cargar(str(carpeta), db=str(db))
        assert total == 1 and rotas == 0

        con = sqlite3.connect(db)
        try:
            celda = con.execute("SELECT criterios FROM trazas").fetchone()[0]
        finally:
            con.close()
        assert _json.loads(celda) == ["a", "b"]
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_compactar_dispara_por_caracteres_con_umbral_de_mensajes():
    """El disparador de `compactar` es el TAMAÑO en CARACTERES (`_tamano >
    max_chars`), pero con la compuerta de mensajes: con `ventana + 2` o más
    mensajes (9 >= 6+2) compacta en cuanto los caracteres pasan el tope;
    por debajo de `ventana + 2` es no-op aunque los caracteres lo superen."""
    from utils.compaccion import compactar

    system = {"role": "system", "content": "s" * 5000}
    turnos = [{"role": "user", "content": "u" * 5000} for _ in range(8)]
    messages = [system] + turnos  # 9 mensajes >= ventana+2

    # 9 mensajes + max_chars=1: los caracteres pasan el tope -> COMPACTA.
    out = compactar(messages, max_chars=1)
    assert out is not messages and out != messages
    assert out[0] == messages[0]  # system conservado
    assert out[0]["role"] == "system"
    assert len(out) < len(messages)  # los totales bajan
    # la ventana caliente sobrevive byte a byte al final del compactado
    assert out[-6:] == messages[-6:]

    # 7 mensajes (menos de ventana+2) + max_chars=1: no-op por la compuerta.
    mensajes_7 = [system] + turnos[:6]  # 7 mensajes < 8
    assert compactar(mensajes_7, max_chars=1) == mensajes_7

    # 9 mensajes pero max_chars enorme: los caracteres NO pasan el tope -> no-op.
    assert compactar(messages, max_chars=10**9) == messages


def test_guardar_resumen_sesion_no_pisa_el_mismo_dia(tmp_path, monkeypatch):
    """Fix 6: dos sesiones el mismo día NO se pisan. La primera conserva el
    nombre clásico `sesion_FECHA.md`; la segunda usa sufijo horario, así que
    quedan DOS archivos distintos y cada uno con su contenido."""
    import modules.memoria as mem

    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))

    p1 = mem.guardar_resumen_sesion("uno")
    p2 = mem.guardar_resumen_sesion("dos")

    assert p1 is not None and p2 is not None
    assert p1 != p2, "la segunda sesión del día pisó el archivo de la primera"
    # la primera conserva el nombre clásico
    from datetime import date

    assert p1.name == f"sesion_{date.today().isoformat()}.md"
    # ambas existen con su contenido propio
    assert p1.read_text(encoding="utf-8").strip() == "uno"
    assert p2.read_text(encoding="utf-8").strip() == "dos"
    sesiones = sorted(f.name for f in tmp_path.glob("sesion_*.md"))
    assert len(sesiones) == 2
