"""Trazas: sql acotado, carga por lotes, recarga transaccional y eventos (PR 4)."""
import os
import shutil
from pathlib import Path

import pytest
from conftest import RAIZ


def test_sql_rechaza_lo_prohibido():
    modulo = pytest.importorskip("modules.db", reason="sin sqlite3")
    assert modulo.sql("DROP TABLE trazas").startswith("ERROR")
    assert modulo.sql("INSERT INTO trazas VALUES (1)").startswith("ERROR")

@pytest.mark.datos
def test_sql_select_funciona():

    if not (RAIZ / "trazas.db").is_file():
        pytest.skip("sin trazas.db: corre carga_trazas.py")
    from modules.db import sql

    r = sql("SELECT COUNT(*) FROM trazas")
    assert "15595" in r

@pytest.mark.datos
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

@pytest.mark.datos
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

@pytest.mark.datos
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

def _db_tmp(tmp_path, criterios=("x", "y")):
    """Crea una sqlite real mínima con una tabla `trazas` y DB_PATH apuntada
    ahí (vía setting). Devuelve el módulo ya listo. `criterios` es el contenido
    a sembrar: los tests que necesitan más filas que MAX_FILAS lo pasan acá en
    vez de re-armar la base a mano."""
    import sqlite3

    import modules.db as db

    ruta = tmp_path / "trazas.db"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE trazas (id INTEGER PRIMARY KEY, criterios TEXT)")
    con.executemany("INSERT INTO trazas (criterios) VALUES (?)",
                    [(c,) for c in criterios])
    con.commit()
    con.close()
    return db

@pytest.mark.parametrize("consulta,fragmento", [
    ("SELECT * FROM trazas WHERE criterios = 'x;y'",
     "sobre-rechazo por ';' en literal"),
    ("SELECT * FROM trazas WHERE criterios = 'delete'",
     "falso positivo por 'delete' en literal"),
], ids=["punto_y_coma", "delete"])
def test_sql_literales_confunden_al_guard(tmp_path, monkeypatch, consulta, fragmento):
    '''El guard de sentencias y la denylist corren sobre la consulta SIN
    literales: un ';' o un 'delete' dentro de una cadena es texto de usuario,
    no multi-sentencia. Base propia: no depende de trazas.db (es la mitad
    positiva del guard del ';', la que se falseaba).'''
    monkeypatch.setenv("DB_PATH", str(tmp_path / "trazas.db"))
    db = _db_tmp(tmp_path)

    r = db.sql(consulta)
    assert not r.startswith("ERROR"), f"{fragmento}: {r[:80]}"

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
    from modules.db import MAX_FILAS

    monkeypatch.setenv("DB_PATH", str(tmp_path / "trazas.db"))
    db = _db_tmp(tmp_path, criterios=["limit"] * (MAX_FILAS + 20))

    r = db.sql("SELECT id FROM trazas WHERE criterios = 'limit'")
    assert not r.startswith("ERROR"), f"la consulta con 'limit' en literal falló: {r[:80]}"
    filas = [ln for ln in r.splitlines() if ln.strip()]
    assert len(filas) - 2 <= MAX_FILAS, "'limit' en un literal suprimió el LIMIT forzado"

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

def test_lector_tolera_formas_invalidas_sin_perder_conteo(tmp_path):
    """exp/24 (C11 de la auditoría externa): JSON válido con forma equivocada
    reventaba con AttributeError en stats_de; cada categoría se cuenta aparte
    y un renglón roto no tumba el lote."""
    from informe import stats_de

    archivo = tmp_path / "trazas.jsonl"
    archivo.write_text(
        '{"answers": {"next": "router"}, "fields": {"task": "clasificar"}}\n'
        "[]\n"
        "null\n"
        '{"answers": null}\n'
        "{roto\n",
        encoding="utf-8",
    )
    stats = stats_de(archivo)
    assert stats["total"] == 5
    assert stats["errores"] == 1     # JSON ilegible
    assert stats["forma"] == 3       # [], null y {"answers": null}
    assert stats["modulos"] == {"router": 1}

def test_carga_trazas_procesa_todos_los_archivos():
    """exp/24 (C12): el cargador no hereda el muestreo de MAX_FILES del
    informe — con 31 archivos cargaba 30 y no lo declaraba."""
    import json as _json
    import sqlite3

    import carga_trazas
    from informe import MAX_FILES

    base = RAIZ / "_tmp_test_carga_masiva"
    base.mkdir(exist_ok=True)
    db = base / "trazas.db"
    try:
        for i in range(MAX_FILES + 1):
            (base / f"t{i:02d}.jsonl").write_text(
                _json.dumps({"answers": {"next": "x"}, "fields": {"task": f"t{i}"}}) + "\n",
                encoding="utf-8",
            )
        total, rotas = carga_trazas.cargar(str(base), db=str(db))
        assert total == MAX_FILES + 1 and rotas == 0
        con = sqlite3.connect(db)
        try:
            assert con.execute("SELECT COUNT(*) FROM trazas").fetchone()[0] == MAX_FILES + 1
        finally:
            con.close()
    finally:
        shutil.rmtree(base, ignore_errors=True)

def test_recarga_fallida_conserva_la_base_anterior(tmp_path, monkeypatch):
    """exp/24 (C12): el DROP vive dentro de la transacción. Medido antes: un
    fallo a mitad dejaba la tabla anterior vacía (pérdida real de datos)."""
    import json as _json
    import sqlite3

    import carga_trazas

    base = RAIZ / "_tmp_test_recarga"
    carpeta = base / "trazas"
    carpeta.mkdir(parents=True, exist_ok=True)
    db = base / "trazas.db"
    try:
        (carpeta / "uno.jsonl").write_text(
            _json.dumps({"answers": {"next": "x"}, "fields": {"task": "ok"}}) + "\n",
            encoding="utf-8",
        )
        carga_trazas.cargar(str(carpeta), db=str(db))

        def explotar(_):
            raise RuntimeError("fallo a mitad de la recarga")

        monkeypatch.setattr(carga_trazas, "_texto", explotar)
        with pytest.raises(RuntimeError, match="a mitad"):
            carga_trazas.cargar(str(carpeta), db=str(db))

        con = sqlite3.connect(db)
        try:
            assert con.execute("SELECT COUNT(*) FROM trazas").fetchone()[0] == 1
        finally:
            con.close()

        # una carpeta sin archivos tampoco toca la base
        vacia = base / "vacia"
        vacia.mkdir()
        monkeypatch.undo()
        with pytest.raises(ValueError, match="la base no se toca"):
            carga_trazas.cargar(str(vacia), db=str(db))
    finally:
        shutil.rmtree(base, ignore_errors=True)

def test_traza_registra_el_nodo_que_falla_y_no_colisiona(tmp_path):
    """exp/27 (C18 de la auditoría externa): el parche de _run no tenía
    finally, así que un nodo que lanza NO dejaba evento (la traza mentía por
    omisión) y el nombre del archivo se resolvía por segundo (dos procesos se
    truncaban entre sí)."""
    import json as _json

    import pocketflow
    from pocketflow import Node

    from utils import tracing

    class NodoQueExplota(Node):
        def exec(self, _):
            raise RuntimeError("boom")

    run_original = pocketflow.BaseNode._run
    run_async_original = pocketflow.AsyncNode._run_async
    salida_original, activo_original = tracing._salida, tracing._activo
    try:
        tracing._activo = False
        archivo = tracing.activar(ruta_base=str(tmp_path))
        assert archivo.name.endswith(f"_{os.getpid()}.jsonl")
        with pytest.raises(RuntimeError, match="boom"):
            NodoQueExplota().run({})
        eventos = [
            _json.loads(linea)
            for linea in Path(archivo).read_text(encoding="utf-8").splitlines()
        ]
        assert any(e["accion"] == "error:RuntimeError" for e in eventos), eventos
    finally:
        # el parche es global a propósito en producción: el test lo deshace
        pocketflow.BaseNode._run = run_original
        pocketflow.AsyncNode._run_async = run_async_original
        if tracing._salida is not None and not tracing._salida.closed:
            tracing._salida.close()
        tracing._salida, tracing._activo = salida_original, activo_original


def test_tracing_no_deja_traza_vacia(tmp_path):
    """Una corrida sin eventos no crea archivo: F4 midió 41/255 trazas
    vacías que ensuciaban los denominadores. El archivo se abre recién al
    primer evento (y el stem planeado ya es el de thread_id)."""
    from utils import tracing

    backup = (tracing._salida, tracing._ruta_salida, tracing._activo, tracing._id_thread)
    try:
        tracing._salida = None
        tracing._activo = True
        tracing._ruta_salida = tmp_path / "planeada.jsonl"
        assert not tracing._ruta_salida.exists()
        tracing.evento_tool("read_file", True, 0.1)
        assert tracing._ruta_salida.exists()
        tracing._salida.close()
        tracing._salida = None
        tracing._ruta_salida = tmp_path / "sin_eventos.jsonl"
        assert not tracing._ruta_salida.exists()
    finally:
        if tracing._salida is not None and not tracing._salida.closed:
            tracing._salida.close()
        tracing._salida, tracing._ruta_salida, tracing._activo, tracing._id_thread = backup


def test_evento_politica_no_se_confunde_con_tool():
    """El corte por no-progreso es un evento de política, no un éxito de tool:
    accion propia para no inflar métricas (medido en vivo: se registraba ok)."""
    import io
    import json

    import utils.tracing as tracing

    original = tracing._salida
    tracing._salida = io.StringIO()
    try:
        tracing.evento_politica("corte_no_progreso")
        linea = json.loads(tracing._salida.getvalue().strip())
    finally:
        tracing._salida = original
    assert linea["nodo"] == "corte_no_progreso"
    assert linea["accion"] == "politica"
