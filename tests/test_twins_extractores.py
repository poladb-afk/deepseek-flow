"""Tests del candado TWINS de exp/85: el inventario AST no se engaña con
docstrings y un sitio LLM nuevo sin clasificar se detecta (sin red ni LLM)."""
import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "twins_extractores", RAIZ / "banco" / "probes" / "twins_extractores.py")
twins = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(twins)


def test_el_arbol_real_no_tiene_gemelos():
    """El registro congelado de exp/85 cubre todos los sitios LLM del producto."""
    assert twins.gemelos(twins.sitios_llm()) == []


@pytest.mark.parametrize("nombre, contenido, inventario_esperado", [
    ("pieza.py",
     '"""docstring que menciona call_llm(prompt) de pasada."""\n'
     "# comentario con call_llm(\n"
     "from utils.call_llm import call_llm\n\n"
     "def f(p):\n    return call_llm(p)\n",
     {"pieza.py": 1}),
    ("modulo_vision.py",
     # vision.py no usa el cliente compartido: el endpoint literal en un
     # Constant también es un sitio (el candado no tiene esa punta abierta)
     'import requests\n\n'
     'def ver(u):\n'
     '    return requests.post(f"{u}/chat/completions", json={})\n',
     {"modulo_vision.py": 1}),
], ids=["sin_docstrings_ni_comentarios", "api_directa_cuenta"])
def test_el_escaneo_cuenta_solo_las_llamadas(tmp_path, nombre, contenido,
                                             inventario_esperado):
    (tmp_path / nombre).write_text(contenido, encoding="utf-8")

    assert twins.sitios_llm(raiz=tmp_path) == inventario_esperado


@pytest.mark.parametrize("nombre, contenido, fragmento", [
    ("extractor_nuevo.py",
     "from utils.call_llm import call_llm\n\n"
     "def clasificar(reporte):\n    return call_llm(reporte)\n",
     "SIN CLASIFICAR"),
    ("juez.py",
     "from utils.call_llm import call_llm\n\n"
     "def a(p):\n    return call_llm(p)\n\n"
     "def b(p):\n    return call_llm(p)\n",
     "congela 3"),
], ids=["archivo_nuevo", "sitio_de_mas_en_registrado"])
def test_lo_sin_clasificar_se_detecta(tmp_path, nombre, contenido, fragmento):
    (tmp_path / nombre).write_text(contenido, encoding="utf-8")

    problemas = twins.gemelos(twins.sitios_llm(raiz=tmp_path))

    assert any(nombre in p and fragmento in p for p in problemas)
