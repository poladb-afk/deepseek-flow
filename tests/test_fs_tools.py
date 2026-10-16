"""Candados de utils/fs_tools: búsqueda, raíces permitidas y enlaces simbólicos (PR 4)."""
import shutil
from pathlib import Path

import pytest


def test_contencion_de_rutas():
    from utils.fs_tools import _resolve

    _, err = _resolve("/etc/passwd")
    assert err and "fuera" in err
    raiz = Path(__file__).resolve().parent.parent
    resolved, err = _resolve(str(raiz / "docs" / "design.md"))
    assert err is None and resolved.is_file()

def test_search_files_por_nombre():
    from utils.fs_tools import search_files

    raiz = Path(__file__).resolve().parent.parent
    r = search_files(glob="requirements.txt", path=str(raiz))
    assert "requirements.txt" in r

def test_search_files_conteo_exacto_al_truncar(tmp_path):
    """El tope SEARCH_MAX_FILES es de MUESTRA, no del conteo: con 55 archivos
    el resultado debe decir el total exacto (55) y cuántos se muestran (50),
    más la sugerencia de find. El conteo se calcula ANTES de truncar."""
    from utils.fs_tools import SEARCH_MAX_FILES, search_files

    # El fixture vive en el tmp de pytest, que la fixture autouse ya suma a
    # AGENT_ALLOWED_DIRS: queda dentro del alcance de la tool y no escribe
    # fuera del repo (antes creaba una carpeta en el directorio padre).
    base = tmp_path / "_tmp_search_files"
    base.mkdir()
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

    base = tmp_path / "_tmp_search_files_bajo"
    base.mkdir()
    try:
        for i in range(10):
            (base / f"archivo_{i:02d}.txt").write_text("")

        r = search_files(glob="*.txt", path=str(base))
        assert "10 archivos coinciden" in r
        assert "run_command" not in r
        assert "más" not in r
    finally:
        shutil.rmtree(base, ignore_errors=True)

def test_search_files_con_path_a_archivo():
    """Falso negativo medido en la auditoría: os.walk sobre un archivo no
    visita nada y la tool decía 'Ningún archivo contiene' sobre un
    archivo que sí lo contiene."""
    from utils.fs_tools import search_files

    r = search_files(query="PREGUNTA_ROUTER", path="nodes.py")
    assert "nodes.py" in r and "Ningún archivo" not in r

    r = search_files(query="PREGUNTA", path="sonda_router.py")
    assert "sonda_router.py" in r and "Ningún archivo" not in r

def test_recorrido_no_sigue_enlaces_simbolicos(tmp_path, monkeypatch):
    """exp/22 (C02 de la auditoría externa): comprobar la RAÍZ no comprueba
    cada archivo — medido: read_file rechazaba un enlace externo y
    search_files devolvía su contenido. La política es una sola: ningún
    recorrido del agente sigue enlaces."""
    from informe import collect_files
    from utils.fs_tools import read_file, search_files

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    fuera = tmp_path / "fuera.txt"
    fuera.write_text("EXTERNAL_MARKER_123\n", encoding="utf-8")
    (allowed / "propio.txt").write_text("contenido propio\n", encoding="utf-8")
    enlace = allowed / "enlace.txt"
    try:
        enlace.symlink_to(fuera)
    except (OSError, NotImplementedError):
        pytest.skip("el entorno no permite enlaces simbólicos")

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(allowed))
    # read_file ya lo rechazaba; search_files filtraba de menos
    assert "ERROR" in read_file(str(enlace))
    assert "L1: EXTERNAL_MARKER_123" not in search_files(
        query="EXTERNAL_MARKER_123", path=str(allowed)
    )
    # el recorrido legítimo no se rompe
    assert "propio.txt" in search_files(query="contenido propio", path=str(allowed))
    # el informe comparte la MISMA política (helper único)
    assert enlace not in collect_files(str(allowed), "*.txt")
