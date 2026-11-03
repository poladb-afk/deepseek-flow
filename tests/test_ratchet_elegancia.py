"""Ratchets de elegancia (fase 0 del refactor, `docs/elegancia.md`).

Las métricas que el refactor tiene que bajar y que hoy ningún gate miraba.
Estos tests fijan qué cuenta cada detector (y qué NO, para que el falso
positivo no empuje a "arreglar" lo que está bien).
"""
import re

import pytest

import ratchet


def _escribir(raiz, relativa, texto):
    ruta = raiz / relativa
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")


def test_core_que_importa_un_modulo_concreto_cuenta_y_el_registro_no(tmp_path):
    _escribir(tmp_path, "nodes.py",
              "from modules import discover\n\n"
              "def f():\n    from modules.memoria import guardar\n    return guardar\n")
    _escribir(tmp_path, "modules/coding.py", "from modules.memoria import x\n")
    assert ratchet.escanear_core_importa_modulos(tmp_path) == {"nodes.py:f": 1}


def test_producto_que_nombra_al_laboratorio_cuenta(tmp_path):
    _escribir(tmp_path, "utils/riesgo.py",
              "def origen(s):\n    return 'banco' if s('BANCO') == '1' else 'terminal'\n")
    _escribir(tmp_path, "delegar.py", "from banco.banco import Chat\n")
    _escribir(tmp_path, "nodes.py", "SALTEAR = 'GROUND-TRUTH.md'\n")
    assert ratchet.escanear_producto_conoce_lab(tmp_path) == {
        "delegar.py:<módulo>": 1, "nodes.py:SALTEAR": 1, "utils/riesgo.py:origen": 2}


def test_la_prosa_que_menciona_el_banco_no_cuenta(tmp_path):
    _escribir(tmp_path, "nodes.py",
              'def f():\n    """El banco mide esto; el producto no lo lee."""\n    return 1\n')
    assert ratchet.escanear_producto_conoce_lab(tmp_path) == {}


@pytest.mark.parametrize(("codigo", "cuenta"), [
    ("VERBOS = frozenset({'debatí', 'corré', 'leé', 'listá', 'mostrá'})\n", 1),
    ("import re\nR = re.compile(r'(?i)\\b(hoy|ahora|último|reciente|novedad)\\b')\n", 1),
    # sin tilde ni (?i): una tabla de tokens técnicos, no vocabulario del usuario
    ("ENVOLTORIOS = {'sudo', 'env', 'nice', 'nohup', 'time'}\n", 0),
    # pocas palabras: un sí/no no es una lista que decide por keywords
    ("SI = {'sí', 'si', 'y'}\n", 0),
    ("import re\nR = re.compile(r'[\\w./-]+\\.py')\n", 0),
])
def test_vocabulario_hardcodeado(tmp_path, codigo, cuenta):
    _escribir(tmp_path, "utils/x.py", codigo)
    assert sum(ratchet.escanear_vocabulario(tmp_path).values()) == cuenta


def test_la_condicion_regex_de_un_skill_cuenta_como_vocabulario(tmp_path):
    """X112: la regex del YAML decide por palabras igual que una del código."""
    _escribir(tmp_path, "skills/a.yaml", "id: a\ncondicion: '(?i)\\b(revisá|revisa|auditá|audita|mirá)\\b'\n")
    _escribir(tmp_path, "skills/b.yaml", "id: b\ncondicion: '(?i)\\b(tdd|test-first)\\b'\n")
    _escribir(tmp_path, "skills/roto.yaml", "id: [\n")
    assert ratchet.escanear_vocabulario(tmp_path) == {"skills/a.yaml:condicion": 1}


def test_imports_perezosos_cuentan_solo_dentro_de_funciones(tmp_path):
    _escribir(tmp_path, "nodes.py",
              "import json\n\nclass N:\n    def prep(self):\n        import re\n        return re\n\n"
              "def g():\n    from pathlib import Path\n    import os\n    return Path, os\n")
    assert ratchet.escanear_imports_perezosos(tmp_path) == {"nodes.py:N": 1, "nodes.py:g": 2}


def test_settings_leidos_por_nombre_con_sus_lectores(tmp_path):
    _escribir(tmp_path, "nodes.py", "a = _setting('CHAT_STREAM', '1')\nb = _entero(\"MAX_TOOL_ROUNDS\", 8)\n")
    _escribir(tmp_path, "utils/x.py", "c = os.environ.get('CHAT_STREAM')\n")
    assert ratchet.escanear_settings(tmp_path) == {
        "CHAT_STREAM": ["nodes.py", "utils/x.py"], "MAX_TOOL_ROUNDS": ["nodes.py"]}


def test_nodo_largo_es_una_clase_con_prep_exec_post(tmp_path):
    relleno = "".join(f"        x{i} = {i}\n" for i in range(45))
    _escribir(tmp_path, "nodes.py",
              f"class Largo:\n    def prep(self, s):\n{relleno}        return s\n\n"
              f"class Asincrono:\n    async def exec_async(self, s):\n{relleno}        return s\n\n"
              f"class Datos:\n    def otro(self):\n{relleno}        return 1\n")
    assert list(ratchet.escanear_nodos_largos(tmp_path)) == [
        "nodes.py:Asincrono", "nodes.py:Largo"]


CUERPOS_DE_TEXTO = (
    '    def exec(self, x):\n        # el texto no decide nada, pero ocupa líneas\n\n'
    '        return """\n{texto}        """\n',
    '    def prep(self, x):\n        return f"""\n{texto}        """\n',
)


@pytest.mark.parametrize("cuerpo", CUERPOS_DE_TEXTO, ids=["docstring", "fstring"])
def test_el_texto_de_un_nodo_no_cuenta_como_codigo(tmp_path, cuerpo):
    """X134: prompts y docstrings (multilínea; el f-string con interpolaciones
    incluida), comentarios y blancos son texto: no esconden control."""
    texto = "".join(f"        Ronda {{x}} — línea {i} del prompt.\n" for i in range(50))
    _escribir(tmp_path, "nodes.py", f"class Prompt:\n{cuerpo.format(texto=texto)}")
    assert ratchet.escanear_nodos_largos(tmp_path) == {}


def test_una_linea_con_strings_y_logica_cuenta_como_codigo(tmp_path):
    """La corrección no puede comerse líneas de lógica que mencionan strings:
    `if d.get("k") != "v":` es código, no texto (la trampa que marcó el
    dictamen de Auditor)."""
    cuerpo = "".join(
        f'        if d.get("k{i}") != "v":\n            d["k{i}"] = "v"\n' for i in range(22))
    _escribir(tmp_path, "nodes.py",
              f"class Largo:\n    def post(self, d):\n{cuerpo}        return d\n")
    assert list(ratchet.escanear_nodos_largos(tmp_path)) == ["nodes.py:Largo"]


def test_el_conteo_fisico_queda_como_diagnostico_no_gateado(tmp_path):
    """X134: el número viejo (líneas físicas) se conserva para comparar, pero
    no decide el semáforo."""
    relleno = "".join(f"        Línea {i} del prompt.\n" for i in range(50))
    _escribir(tmp_path, "nodes.py",
              f'class Prompt:\n    def exec(self, x):\n        return """\n{relleno}        """\n')
    assert ratchet.escanear_nodos_largos(tmp_path) == {}
    assert list(ratchet.escanear_nodos_fisicos(tmp_path)) == ["nodes.py:Prompt"]


def test_texto_de_prompt_mide_lo_literal_y_no_lo_interpolado(tmp_path):
    _escribir(tmp_path, "main.py",
              'DIRECTIVA_X = "abcde"\n\n'
              'def system_prompt():\n    cwd = "/una/ruta/larguisima"\n    return f"Hola {cwd} chau"\n')
    assert ratchet.escanear_texto_de_prompt(tmp_path) == {"DIRECTIVA_X": 5, "system_prompt": 10}


def test_bytes_primer_request_suma_prompt_y_esquemas_sin_lo_interpolado(tmp_path):
    """P1 (X124): lo fijo de cada request es el prompt MÁS los esquemas de
    tools. Un esquema del CORE y uno de un módulo cuentan; lo interpolado no."""
    _escribir(tmp_path, "main.py", 'def system_prompt():\n    return f"Hola {x}"\n')
    _escribir(tmp_path, "utils/fs_tools.py", 'TOOLS = [{"name": "leer"}]\n')
    _escribir(tmp_path, "modules/m.py", 'D = "/r"\nTOOLS = [{"description": f"ñ {D}"}]\nOTRA = ["no cuenta"]\n')
    assert ratchet.escanear_bytes_primer_request(tmp_path) == {
        "main.py:system_prompt": 5, "modules/m.py:TOOLS": len("description") + len("ñ ".encode()),
        "utils/fs_tools.py:TOOLS": len("name") + len("leer")}


def test_lineas_del_loop_cuenta_codigo_y_docstrings_no_comentarios(tmp_path):
    _escribir(tmp_path, "utils/kernel.py", '"""doc"""\n# comentario\n\nx = 1\n')
    _escribir(tmp_path, "flow.py", "y = 2\n")
    assert ratchet.escanear_lineas_del_loop(tmp_path) == {"utils/kernel.py": 2, "flow.py": 1}


def test_un_setting_nuevo_pone_rojo_aunque_otro_se_borre(tmp_path):
    """Las métricas de conjunto comparan identidad: cambiar un setting por
    otro no es mejora, es la misma deuda con otro nombre."""
    (tmp_path / "ratchets").mkdir()
    baseline = tmp_path / "ratchets" / "baseline.json"
    _escribir(tmp_path, "nodes.py", "a = _setting('VIEJO', '1')\n")
    assert ratchet.correr(raiz=tmp_path, ruta_baseline=baseline, guardia=False, salida=lambda _: None) == 0
    _escribir(tmp_path, "nodes.py", "a = _setting('NUEVO', '1')\n")
    lineas = []
    assert ratchet.correr(raiz=tmp_path, ruta_baseline=baseline, guardia=False, salida=lineas.append) == 1
    assert any("settings_leidos" in linea and "EMPEORÓ" in linea for linea in lineas)
    assert any("NUEVO" in linea for linea in lineas)


def test_las_metricas_de_elegancia_estan_en_el_baseline_versionado():
    """Sembradas en la fase 0: sin baseline, el ratchet las siembra en
    silencio y una regresión del mismo commit pasaría."""
    datos = ratchet.cargar_baseline(ratchet.BASELINE)
    faltan = [m for m in ratchet.ELEGANCIA if m not in (datos or {}).get("ratchets", {})]
    assert not faltan, f"métricas de elegancia sin baseline: {faltan}"


def test_todo_setting_tiene_veredicto_en_el_inventario():
    """El inventario de `docs/elegancia.md` decide qué setting se queda: uno
    nuevo sin fila sería configuración que nadie decidió."""
    from conftest import RAIZ

    doc = (RAIZ / "docs" / "elegancia.md").read_text(encoding="utf-8")
    con_fila = set(re.findall(r"^\| `([A-Z][A-Z0-9_]+)` \| (?:contrato|revisar|borrar) \|", doc, re.M))
    faltan = sorted(set(ratchet.escanear_settings(RAIZ)) - con_fila)
    assert not faltan, f"settings sin veredicto en docs/elegancia.md: {faltan}"


def test_la_columna_lo_lee_del_inventario_es_la_del_codigo():
    """X112: la columna "Lo lee" se desactualizaba en silencio (HITL_SCOPE y
    MEMORIA nombraban archivos que ya no eran sus lectores). Cada fila tiene
    que nombrar exactamente los archivos que el escaneo encuentra."""
    from conftest import RAIZ

    doc = (RAIZ / "docs" / "elegancia.md").read_text(encoding="utf-8")
    filas = re.findall(r"^\| `([A-Z][A-Z0-9_]+)` \| (?:contrato|revisar|borrar) \|.*\| ([^|]*) \|$", doc, re.M)
    reales = ratchet.escanear_settings(RAIZ)
    distintos = {}
    for nombre, lee in filas:
        citados = sorted(re.findall(r"`([^`]+)`", lee))
        if citados != reales.get(nombre):
            distintos[nombre] = (citados, reales.get(nombre))
    assert filas and not distintos, f"columna 'Lo lee' desactualizada (doc, código): {distintos}"
