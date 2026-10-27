"""Ratchet de métricas estructurales (mecanismo de git-agent-ratchet, adaptado).

Lo que estos tests clavan:

- el escaneo AST de las seis métricas (helpers bifurcados; tests definidos;
  excepts amplios; código muerto; cuerpos duplicados; tests copiados);
- la invariante de cada dirección: la deuda baja, la cobertura sube;
- la siembra, la auto-mejora del baseline (solo hacia la mejora) y el rojo
  que NO pisa el baseline cuando empeora;
- el determinismo de los bytes del baseline (es un dato versionado);
- la guardia anti-bypass: el baseline no puede empeorar sin clave humana.
"""
import json
import subprocess

import pytest
from conftest import requiere_git

import ratchet

# helpers

def _arbol(tmp_path):
    for sub in ("modules", "utils", "tests"):
        (tmp_path / sub).mkdir()
    return tmp_path


def _escribir(raiz, relativa, texto):
    ruta = raiz / relativa
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def _baseline(raiz):
    return raiz / "ratchets" / "baseline.json"


def _metricas(raiz):
    """Las dos métricas de un árbol de prueba, ya calculadas."""
    return {
        "helpers_duplicados": ratchet._metrica_helpers(raiz)[0],
        "tests_definidos": ratchet._metrica_tests(raiz)[0],
    }


# escaneo

def test_escanear_helpers_detecta_la_bifurcacion(tmp_path):
    """Un `_foo` en 2+ archivos del harness es deuda: el detalle nombra cuáles."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py", "def _repetido():\n    return 1\n")
    _escribir(raiz, "utils/b.py", "def _repetido():\n    return 2\n")
    _escribir(raiz, "main.py", "def _propia():\n    return 0\n")
    detalle = ratchet.escanear_helpers(raiz)
    assert detalle == {"_repetido": ["modules/a.py", "utils/b.py"]}
    assert ratchet._metrica_helpers(raiz) == (2, detalle)


def test_escanear_helpers_ignora_publicas_dunders_y_no_repetidas(tmp_path):
    """Solo funciones privadas de nivel superior, no dunders ni nombres públicos."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py",
              "def publica():\n    pass\n\n"
              "def __post_init__():\n    pass\n\n"
              "def _sola_aca():\n    pass\n")
    assert ratchet.escanear_helpers(raiz) == {}


def test_escanear_helpers_no_mira_tests_ni_banco(tmp_path):
    """El alcance es el harness: duplicados en tests/ o banco/ no son deuda."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py", "def _copiada():\n    pass\n")
    _escribir(raiz, "tests/test_x.py", "def _copiada():\n    pass\n")
    _escribir(raiz, "banco/b.py", "def _copiada():\n    pass\n")
    assert ratchet.escanear_helpers(raiz) == {}


@pytest.mark.parametrize("contenido,esperado", [
    ("import pytest\n\n"
     "@pytest.mark.parametrize('x', [1, 2, 3])\n"
     "def test_param(x):\n    assert x\n\n"
     "@pytest.mark.parametrize('a', [1, 2])\n"
     "@pytest.mark.parametrize('b', [1, 2])\n"
     "def test_doble(a, b):\n    assert a and b\n\n"
     "def test_uno():\n    assert True\n", 8),
    ("import pytest\n\nCASOS = [1, 2, 3]\n\n"
     "@pytest.mark.parametrize('x', CASOS)\n"
     "def test_param(x):\n    assert x\n", 1),
], ids=["parametrize_literal", "argvalues_variable"])
def test_escanear_tests_cuenta_casos(tmp_path, contenido, esperado):
    """La cobertura se mide en CASOS: parametrizar no baja el número; una
    variable como argvalues no se puede contar y vale 1 (límite declarado)."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "tests/test_a.py", contenido)
    assert ratchet.escanear_tests(raiz) == {"tests/test_a.py": esperado}


def test_escanear_tests_cuenta_defs_por_archivo(tmp_path):
    """La métrica de cobertura cuenta `def test_*` (incluso métodos de clase)."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "tests/test_a.py", "def test_uno():\n    pass\n\ndef test_dos():\n    pass\n")
    _escribir(raiz, "tests/test_b.py", "class T:\n    def test_tres(self):\n        pass\n")
    assert ratchet.escanear_tests(raiz) == {"tests/test_a.py": 2, "tests/test_b.py": 1}
    assert ratchet._metrica_tests(raiz) == (3, {"tests/test_a.py": 2, "tests/test_b.py": 1})


def test_escanear_excepts_cuenta_solo_los_amplios(tmp_path):
    """Amplio = `except:`, `except Exception`, `except BaseException`. Un
    `except (OSError, ValueError)` nombra lo que maneja y no cuenta."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py",
              "def f():\n    try:\n        pass\n    except Exception:\n        pass\n\n"
              "def g():\n    try:\n        pass\n    except (OSError, ValueError):\n        pass\n\n"
              "def h():\n    try:\n        pass\n    except:\n        pass\n")
    assert ratchet.escanear_excepts(raiz) == {"modules/a.py": [4, 16]}
    assert ratchet._metrica_excepts(raiz) == (2, {"modules/a.py": [4, 16]})


def test_escanear_muertas_detecta_privadas_sin_referencia(tmp_path):
    """El código por si acaso: una privada que ningún camino llama."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py", "def _muerta():\n    pass\n\ndef _viva():\n    pass\n")
    _escribir(raiz, "modules/b.py", "from modules.a import _viva\n\n\n_viva()\n")
    assert ratchet.escanear_muertas(raiz) == ["modules/a.py:1:_muerta"]


def test_escanear_muertas_no_cuenta_la_recursion_propia(tmp_path):
    """Una función que solo se llama a sí misma sigue muerta."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py", "def _rec():\n    return _rec()\n")
    assert ratchet.escanear_muertas(raiz) == ["modules/a.py:1:_rec"]


def test_escanear_muertas_ignora_publicas(tmp_path):
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py", "def publica():\n    pass\n")
    assert ratchet.escanear_muertas(raiz) == []


def test_escanear_cuerpos_detecta_copia_con_variables_renombradas(tmp_path):
    """El signature tell: misma lógica copiada con otros nombres locales."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py",
              "def a(x):\n    y = x + 1\n    z = y * 2\n    return z\n")
    _escribir(raiz, "utils/b.py",
              "def b(n):\n    m = n + 1\n    k = m * 2\n    return k\n")
    grupos = ratchet.escanear_cuerpos(raiz)
    assert len(grupos) == 1
    assert sum(len(v) for v in grupos.values()) == 2


def test_escanear_cuerpos_no_confunde_operaciones_distintas(tmp_path):
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py", "import json\n\ndef a(s):\n    return json.loads(s)\n")
    _escribir(raiz, "utils/b.py", "import json\n\ndef b(s):\n    return json.dumps(s)\n")
    _escribir(raiz, "utils/c.py", "import yaml\n\ndef c(s):\n    return yaml.safe_load(s)\n")
    assert ratchet.escanear_cuerpos(raiz) == {}


# invariante

def test_comparar_respeta_la_direccion_de_cada_ratchet():
    """Deuda: bajar es mejora. Cobertura: subir es mejora. Nunca al revés."""
    assert ratchet.comparar(3, 5, "menor_mejor") == "MEJORÓ"
    assert ratchet.comparar(5, 3, "menor_mejor") == "EMPEORÓ"
    assert ratchet.comparar(5, 5, "menor_mejor") == "IGUAL"
    assert ratchet.comparar(5, 3, "mayor_mejor") == "MEJORÓ"
    assert ratchet.comparar(3, 5, "mayor_mejor") == "EMPEORÓ"
    assert ratchet.comparar(5, 5, "mayor_mejor") == "IGUAL"


# baseline / gate

def test_sin_baseline_siembra_y_sale_verde(tmp_path):
    """Primera corrida: escribe el baseline con las métricas actuales."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py", "def _x():\n    pass\n")
    _escribir(raiz, "utils/b.py", "def _x():\n    pass\n")
    _escribir(raiz, "tests/test_a.py", "def test_uno():\n    pass\n")
    mensajes = []
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False, salida=mensajes.append) == 0
    datos = json.loads(_baseline(raiz).read_text(encoding="utf-8"))
    assert datos["ratchets"]["helpers_duplicados"]["metrica"] == 2
    assert datos["ratchets"]["tests_definidos"]["metrica"] == 1
    assert any("SIN BASELINE" in m for m in mensajes)


def test_igual_no_reescribe_el_baseline(tmp_path):
    """Igualdad: verde y el archivo queda idéntico (no hay churn)."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py", "def _x():\n    pass\n")
    _escribir(raiz, "utils/b.py", "def _x():\n    pass\n")
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False) == 0
    antes = _baseline(raiz).read_bytes()
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False) == 0
    assert _baseline(raiz).read_bytes() == antes


def test_empeora_falla_y_no_pisa_el_baseline(tmp_path):
    """Empeorar (otra copia del helper) = rojo, con el detalle del culpable, y
    el baseline versionado queda intacto: no se acepta deuda por accidente."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py", "def _x():\n    pass\n")
    _escribir(raiz, "utils/b.py", "def _x():\n    pass\n")
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False) == 0
    antes = _baseline(raiz).read_text(encoding="utf-8")
    _escribir(raiz, "main.py", "def _x():\n    pass\n")
    mensajes = []
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False, salida=mensajes.append) == 1
    assert _baseline(raiz).read_text(encoding="utf-8") == antes
    assert any("EMPEORÓ" in m for m in mensajes)
    assert any("_x:" in m for m in mensajes)


def test_mejora_baja_el_baseline_y_lo_deja_igual(tmp_path):
    """Mejorar (unificar el helper) reescribe el baseline; la corrida siguiente
    da IGUAL. El baseline es el trinquete: nunca vuelve a subir solo."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py", "def _x():\n    pass\n")
    _escribir(raiz, "utils/b.py", "def _x():\n    pass\n")
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False) == 0
    (raiz / "utils" / "b.py").unlink()  # se unificó: una sola definición
    mensajes = []
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False, salida=mensajes.append) == 0
    datos = json.loads(_baseline(raiz).read_text(encoding="utf-8"))
    assert datos["ratchets"]["helpers_duplicados"]["metrica"] == 0
    assert any("MEJORÓ" in m for m in mensajes)
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False) == 0


@pytest.mark.parametrize("archivo,contenido,extra_archivo,extra_contenido,metrica,fragmento", [
    ("modules/a.py",
     "def f():\n    try:\n        pass\n    except Exception:\n        pass\n",
     "utils/b.py", "def g():\n    try:\n        pass\n    except:\n        pass\n",
     "excepts_amplios", "utils/b.py: 0 → 1"),
    ("tests/test_a.py", "def test_uno():\n    pass\n\ndef test_dos():\n    pass\n",
     "tests/test_a.py", "def test_uno():\n    pass\n",
     "tests_definidos", "tests/test_a.py: 2 → 1 tests"),
], ids=["except_amplio", "test_borrado"])
def test_ratchet_empeora_y_frena(tmp_path, archivo, contenido, extra_archivo,
                                 extra_contenido, metrica, fragmento):
    """El ruido no crece y la cobertura no baja en silencio: la métrica que
    empeora frena el gate y el diagnóstico nombra el culpable (smell #1 del
    código de IA; el hueco del inventario del PR 4 para tests nuevos)."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, archivo, contenido)
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False) == 0
    _escribir(raiz, extra_archivo, extra_contenido)
    mensajes = []
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False,
                          salida=mensajes.append) == 1
    assert any(metrica in m and "EMPEORÓ" in m for m in mensajes)
    assert any(fragmento in m for m in mensajes)


@pytest.mark.git
@requiere_git
def test_actualizar_acepta_el_empeoramiento(tmp_path, monkeypatch):
    """--actualizar con la clave del operador acepta la baja y deja el baseline nuevo."""
    raiz = _arbol(tmp_path)
    _repo_con_baseline(raiz, 0, clave="la-clave-del-operador")
    monkeypatch.setenv(ratchet.CLAVE_BYPASS, "la-clave-del-operador")
    _escribir(raiz, "tests/test_a.py", "def test_uno():\n    pass\n\ndef test_dos():\n    pass\n")
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False) == 0
    _escribir(raiz, "tests/test_a.py", "def test_uno():\n    pass\n")
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False, actualizar=True) == 0
    datos = json.loads(_baseline(raiz).read_text(encoding="utf-8"))
    assert datos["ratchets"]["tests_definidos"]["metrica"] == 1


def test_no_escribir_no_toca_el_baseline(tmp_path):
    """`--no-escribir` es diagnóstico: informa la mejora pero no la versiona."""
    raiz = _arbol(tmp_path)
    _escribir(raiz, "modules/a.py", "def _x():\n    pass\n")
    _escribir(raiz, "utils/b.py", "def _x():\n    pass\n")
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False) == 0
    antes = _baseline(raiz).read_text(encoding="utf-8")
    (raiz / "utils" / "b.py").unlink()
    mensajes = []
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False,
                          escribir=False, salida=mensajes.append) == 0
    assert _baseline(raiz).read_text(encoding="utf-8") == antes
    assert any("--no-escribir" in m for m in mensajes)


def test_baseline_es_deterministico(tmp_path):
    """Mismos datos ⇒ mismos bytes (claves ordenadas): el baseline se versiona."""
    datos = {"version": 1, "ratchets": {"b": {"metrica": 2}, "a": {"metrica": 1}}}
    rutas = []
    for nombre in ("uno.json", "dos.json"):
        ruta = tmp_path / nombre
        ratchet.guardar_baseline(datos, ruta)
        rutas.append(ruta.read_text(encoding="utf-8"))
        ruta.unlink()
    assert rutas[0] == rutas[1]
    assert rutas[0].index('"a"') < rutas[0].index('"b"')


# guardia bypass

def test_hallazgos_bypass_detecta_el_baseline_que_empeora():
    """La dirección que empeora es bypass: deuda que sube y cobertura que baja."""
    en_head = {"ratchets": {"helpers_duplicados": {"metrica": 20}, "tests_definidos": {"metrica": 491}}}
    en_disco = {"ratchets": {"helpers_duplicados": {"metrica": 22}, "tests_definidos": {"metrica": 491}}}
    hallazgos = ratchet.hallazgos_bypass(en_disco, en_head, None)
    assert len(hallazgos) == 1 and "helpers_duplicados" in hallazgos[0]
    en_disco_bajo = {"ratchets": {"helpers_duplicados": {"metrica": 20}, "tests_definidos": {"metrica": 480}}}
    assert any("tests_definidos" in h for h in ratchet.hallazgos_bypass(en_disco_bajo, en_head, None))


def test_hallazgos_bypass_detecta_el_bypass_ya_commiteado():
    """HEAD peor que HEAD~1 también es bypass: nadie lo audita después."""
    en_anterior = {"ratchets": {"helpers_duplicados": {"metrica": 20}, "tests_definidos": {"metrica": 491}}}
    en_head = {"ratchets": {"helpers_duplicados": {"metrica": 21}, "tests_definidos": {"metrica": 491}}}
    hallazgos = ratchet.hallazgos_bypass(en_head, en_head, en_anterior)
    assert len(hallazgos) == 1 and "HEAD~1" in hallazgos[0]


def test_mejora_del_baseline_no_es_bypass():
    """Bajar la deuda o subir la cobertura es la dirección permitida."""
    en_head = {"ratchets": {"helpers_duplicados": {"metrica": 20}, "tests_definidos": {"metrica": 491}}}
    en_disco = {"ratchets": {"helpers_duplicados": {"metrica": 17}, "tests_definidos": {"metrica": 500}}}
    assert ratchet.hallazgos_bypass(en_disco, en_head, None) == []


def _repo_con_baseline(tmp_path, metrica, clave=None):
    """Un repo git mínimo con el baseline commiteado: la guardia lee HEAD.
    Con `clave`, también el hash del operador (`ratchets/clave_operador.sha256`)."""
    baseline = tmp_path / "ratchets" / "baseline.json"
    ratchet.guardar_baseline({"version": 1, "ratchets": {
        "helpers_duplicados": {"metrica": metrica},
        "tests_definidos": {"metrica": 1},
    }}, baseline)
    if clave:
        (tmp_path / "ratchets" / "clave_operador.sha256").write_text(ratchet.sha256(clave) + "\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "ratchets/"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "baseline"], check=True)
    return baseline


@pytest.mark.git
@requiere_git
def test_guardia_bypass_bloquea_el_baseline_editado_a_mano(tmp_path, monkeypatch):
    """El caso real: un agente sube el número del baseline para pasar. Rojo."""
    monkeypatch.delenv(ratchet.CLAVE_BYPASS, raising=False)
    baseline = _repo_con_baseline(tmp_path, 2)
    ratchet.guardar_baseline({"version": 1, "ratchets": {
        "helpers_duplicados": {"metrica": 5},
        "tests_definidos": {"metrica": 1},
    }}, baseline)
    mensajes = []
    assert ratchet.guardia_bypass(tmp_path, baseline, salida=mensajes.append) is True
    assert any("BYPASS" in m for m in mensajes)
    assert any("HUMAN_RATCHET_BYPASS_KEY" in m for m in mensajes)


@pytest.mark.git
@requiere_git
def test_guardia_bypass_cede_ante_la_clave_humana(tmp_path, monkeypatch):
    """El operador humano puede declarar el bypass con SU clave (la que
    coincide con el hash commiteado); queda impreso en el gate y la clave no."""
    clave = "operador-2026-10-19"
    baseline = _repo_con_baseline(tmp_path, 2, clave=clave)
    monkeypatch.setenv(ratchet.CLAVE_BYPASS, clave)
    ratchet.guardar_baseline({"version": 1, "ratchets": {
        "helpers_duplicados": {"metrica": 5},
        "tests_definidos": {"metrica": 1},
    }}, baseline)
    mensajes = []
    assert ratchet.guardia_bypass(tmp_path, baseline, salida=mensajes.append) is False
    assert any("clave verificada" in m for m in mensajes)
    assert not any(clave in m for m in mensajes), "la clave NO se imprime"


@pytest.mark.git
@requiere_git
@pytest.mark.parametrize("valor", ["1", "operador", "x" * 40])
def test_una_bandera_cualquiera_no_es_la_clave(tmp_path, monkeypatch, valor):
    """Medido (2026-10-26): con la guardia vieja, `HUMAN_RATCHET_BYPASS_KEY=1`
    alcanzaba y un agente la exportó. Ahora el valor tiene que ser la clave."""
    baseline = _repo_con_baseline(tmp_path, 2, clave="la-clave-real-del-operador")
    monkeypatch.setenv(ratchet.CLAVE_BYPASS, valor)
    ratchet.guardar_baseline({"version": 1, "ratchets": {
        "helpers_duplicados": {"metrica": 5}, "tests_definidos": {"metrica": 1}}}, baseline)
    mensajes = []
    assert ratchet.guardia_bypass(tmp_path, baseline, salida=mensajes.append) is True
    assert any("no coincide" in m for m in mensajes)


@pytest.mark.git
@requiere_git
def test_sin_hash_commiteado_no_hay_bypass_posible(tmp_path, monkeypatch):
    """Falla cerrado: si el operador nunca sembró la clave, nadie la tiene."""
    baseline = _repo_con_baseline(tmp_path, 2)
    monkeypatch.setenv(ratchet.CLAVE_BYPASS, "cualquier-cosa-larga")
    ratchet.guardar_baseline({"version": 1, "ratchets": {
        "helpers_duplicados": {"metrica": 5}, "tests_definidos": {"metrica": 1}}}, baseline)
    mensajes = []
    assert ratchet.guardia_bypass(tmp_path, baseline, salida=mensajes.append) is True
    assert any("--sembrar-clave" in m for m in mensajes)


@pytest.mark.git
@requiere_git
def test_el_hash_del_disco_no_vale_solo_el_commiteado(tmp_path, monkeypatch):
    """Un agente que reescribe el hash en el working tree con SU clave no pasa:
    la guardia lee el hash de la historia."""
    baseline = _repo_con_baseline(tmp_path, 2, clave="la-clave-real-del-operador")
    (tmp_path / "ratchets" / "clave_operador.sha256").write_text(ratchet.sha256("la-del-agente"))
    monkeypatch.setenv(ratchet.CLAVE_BYPASS, "la-del-agente")
    ratchet.guardar_baseline({"version": 1, "ratchets": {
        "helpers_duplicados": {"metrica": 5}, "tests_definidos": {"metrica": 1}}}, baseline)
    assert ratchet.guardia_bypass(tmp_path, baseline, salida=lambda m: None) is True


@pytest.mark.git
@requiere_git
def test_cambiar_el_hash_junto_con_el_empeoramiento_exige_la_clave_vieja(tmp_path, monkeypatch):
    """El hash nuevo commiteado en HEAD no alcanza: HEAD~1 tiene el anterior y
    la clave tiene que coincidir con los dos."""
    baseline = _repo_con_baseline(tmp_path, 2, clave="la-clave-real-del-operador")
    hash_ruta = tmp_path / "ratchets" / "clave_operador.sha256"
    hash_ruta.write_text(ratchet.sha256("la-del-agente"))
    ratchet.guardar_baseline({"version": 1, "ratchets": {
        "helpers_duplicados": {"metrica": 5}, "tests_definidos": {"metrica": 1}}}, baseline)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qam", "nueva clave + baseline"], check=True)
    monkeypatch.setenv(ratchet.CLAVE_BYPASS, "la-del-agente")
    assert ratchet.guardia_bypass(tmp_path, baseline, salida=lambda m: None) is True
    monkeypatch.setenv(ratchet.CLAVE_BYPASS, "la-clave-real-del-operador")
    assert ratchet.clave_valida(tmp_path, "la-clave-real-del-operador")[0] is False  # tampoco: no coincide con HEAD


def test_actualizar_sin_clave_no_acepta_el_empeoramiento(tmp_path, monkeypatch):
    """--actualizar solo ya no alcanza: el empeoramiento pide la clave."""
    raiz = _arbol(tmp_path)
    monkeypatch.setenv(ratchet.CLAVE_BYPASS, "1")  # una bandera, no la clave
    _escribir(raiz, "tests/test_a.py", "def test_uno():\n    pass\n\ndef test_dos():\n    pass\n")
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False) == 0
    _escribir(raiz, "tests/test_a.py", "def test_uno():\n    pass\n")  # menos tests: empeora
    mensajes = []
    assert ratchet.correr(raiz=raiz, ruta_baseline=_baseline(raiz), guardia=False,
                          actualizar=True, salida=mensajes.append) == 1
    assert any("clave del operador" in m for m in mensajes)


def test_sembrar_clave_escribe_solo_el_hash(tmp_path):
    ruta = tmp_path / "clave.sha256"
    respuestas = iter(["una-clave-de-operador", "una-clave-de-operador"])
    assert ratchet.sembrar_clave(ruta, salida=lambda m: None, leer=lambda _p: next(respuestas)) == 0
    assert ruta.read_text().strip() == ratchet.sha256("una-clave-de-operador")
    assert "una-clave" not in ruta.read_text()
    corta = iter(["corta", "corta"])
    assert ratchet.sembrar_clave(ruta, salida=lambda m: None, leer=lambda _p: next(corta)) == 1
