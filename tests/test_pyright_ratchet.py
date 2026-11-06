"""X184: la etapa 6/6 — errores de tipo del producto con Pyright y su ratchet.

La etapa corre Pyright en `calidad.sh` y le deja el JSON a `ratchet.py
--pyright`; acá se fija el ratchet con datos falsos (no corre Pyright ni lo
necesita) y los candados de configuración del gate."""
import json
import re
import subprocess
import tomllib

from conftest import RAIZ, requiere_git

import ratchet

VERSION = "1.1.409"


def _proyecto(tmp_path, python="3.12"):
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.pyright]\ntypeCheckingMode = "basic"\npythonVersion = "{python}"\n'
        'reportMissingImports = "none"\n', encoding="utf-8")
    return tmp_path


def _datos(tmp_path, *diagnosticos, version=VERSION):
    """Un `.pyright/datos.json` con la forma de `pyright --outputjson`."""
    ruta = tmp_path / "datos.json"
    ruta.write_text(json.dumps({"version": version, "generalDiagnostics": list(diagnosticos)}),
                    encoding="utf-8")
    return ruta


def _err(archivo, regla="reportArgumentType", severity="error"):
    return {"file": str(archivo), "severity": severity, "rule": regla,
            "range": {"start": {"line": 0, "character": 0}}}


def _gate(tmp_path, datos, **k):
    salida = []
    codigo = ratchet.correr_pyright(raiz=tmp_path, ruta_baseline=tmp_path / "py.json",
                                    datos=datos, salida=salida.append, **k)
    return codigo, " ".join(salida)


def _sembrar(tmp_path, datos):
    codigo, salida = _gate(tmp_path, datos, sembrar=True)
    assert codigo == 0 and "sembrado" in salida
    return salida


def _base(tmp_path):
    return json.loads((tmp_path / "py.json").read_text(encoding="utf-8"))


def _detalle(tmp_path):
    return _base(tmp_path)["ratchets"]["pyright"]["detalle"]


def _escribir_base(tmp_path, n):
    ratchet.guardar_baseline({"version": 1, "pyright": VERSION, "pythonVersion": "3.12",
                              "ratchets": {"pyright": {"metrica": n,
                                                       "detalle": {"main.py:reportArgumentType": n}}}},
                             tmp_path / "py.json")


def test_sin_baseline_es_rojo_y_sembrar_pyright_lo_crea(tmp_path):
    """Primera corrida: la foto de la deuda es explícita, no un verde por omisión."""
    _proyecto(tmp_path)
    archivo = tmp_path / "main.py"
    datos = _datos(tmp_path, _err(archivo))
    codigo, salida = _gate(tmp_path, datos)
    assert codigo == 1 and "no hay baseline" in salida
    _sembrar(tmp_path, datos)
    base = _base(tmp_path)
    assert base["pyright"] == VERSION and base["pythonVersion"] == "3.12"
    assert _detalle(tmp_path) == {"main.py:reportArgumentType": 1}
    antes = (tmp_path / "py.json").read_bytes()
    assert _gate(tmp_path, datos)[0] == 0
    assert (tmp_path / "py.json").read_bytes() == antes
    # ya sembrado, --sembrar-pyright no es una puerta para aceptar un empeoramiento
    codigo, salida = _gate(tmp_path, datos, sembrar=True)
    assert codigo == 1 and "ya existe" in salida


def test_un_error_de_menos_baja_el_baseline_solo(tmp_path):
    _proyecto(tmp_path)
    archivo = tmp_path / "main.py"
    _sembrar(tmp_path, _datos(tmp_path, _err(archivo), _err(archivo)))
    assert _detalle(tmp_path) == {"main.py:reportArgumentType": 2}
    codigo, salida = _gate(tmp_path, _datos(tmp_path, _err(archivo)))
    assert codigo == 0 and "VERDE" in salida
    assert _detalle(tmp_path) == {"main.py:reportArgumentType": 1}


def test_un_error_nuevo_es_rojo_y_no_pisa_el_baseline(tmp_path):
    _proyecto(tmp_path)
    archivo = tmp_path / "main.py"
    _sembrar(tmp_path, _datos(tmp_path, _err(archivo)))
    antes = (tmp_path / "py.json").read_bytes()
    codigo, salida = _gate(tmp_path, _datos(tmp_path, _err(archivo), _err(archivo)))
    assert codigo == 1 and "main.py:reportArgumentType: 1 → 2 errores" in salida
    assert (tmp_path / "py.json").read_bytes() == antes
    codigo, _ = _gate(tmp_path, _datos(tmp_path, _err(archivo), _err(archivo)), actualizar=True)
    assert codigo == 1, "--actualizar sin la clave del operador no acepta"


def test_un_archivo_nuevo_con_error_es_rojo(tmp_path):
    _proyecto(tmp_path)
    _sembrar(tmp_path, _datos(tmp_path))
    codigo, salida = _gate(tmp_path, _datos(tmp_path, _err(tmp_path / "utils" / "nuevo.py")))
    assert codigo == 1 and "utils/nuevo.py:reportArgumentType: 0 → 1 errores" in salida


def test_los_warnings_no_gatean(tmp_path):
    """El DSL de PocketFlow usa `>>` por efecto: `reportUnusedExpression` es
    diagnóstico, no deuda de tipos (decisión del operador, X184)."""
    _proyecto(tmp_path)
    _sembrar(tmp_path, _datos(tmp_path))
    archivo = tmp_path / "main.py"
    codigo, salida = _gate(tmp_path, _datos(tmp_path, _err(archivo, "reportUnusedExpression", "warning")))
    assert codigo == 0 and "VERDE" in salida
    assert _detalle(tmp_path) == {}


def test_el_baseline_no_se_mueve_por_la_herramienta(tmp_path):
    """La versión de Pyright y el target de Python son parte del baseline: si la
    corrida mide con otra herramienta, no se compara contra la foto vieja."""
    _proyecto(tmp_path)
    archivo = tmp_path / "main.py"
    _sembrar(tmp_path, _datos(tmp_path, _err(archivo)))
    codigo, salida = _gate(tmp_path, _datos(tmp_path, _err(archivo), version="1.1.414"))
    assert codigo == 1 and "pyright 1.1.409" in salida
    _proyecto(tmp_path, "3.10")
    codigo, salida = _gate(tmp_path, _datos(tmp_path, _err(archivo)))
    assert codigo == 1 and "Python 3.12" in salida


def test_sin_datos_validos_es_rojo(tmp_path):
    _proyecto(tmp_path)
    codigo, salida = _gate(tmp_path, tmp_path / "no_hay.json")
    assert codigo == 1 and "no hay datos válidos" in salida
    roto = tmp_path / "roto.json"
    roto.write_text("{no es json", encoding="utf-8")
    codigo, salida = _gate(tmp_path, roto)
    assert codigo == 1 and "no hay datos válidos" in salida


def test_hallazgos_pyright_mira_cada_archivo_y_regla():
    """Bajar 2 en un (archivo, regla) no compra subir 1 en otro."""
    assert ratchet.hallazgos_pyright({"a.py:r": 1, "b.py:r": 3},
                                     {"a.py:r": 5, "b.py:r": 2}) == ["b.py:r: 2 → 3 errores"]
    assert ratchet.hallazgos_pyright({"a.py:r": 1}, {"a.py:r": 1}) == []


def test_la_medicion_de_tipos_es_determinista(tmp_path):
    _proyecto(tmp_path)
    archivo = tmp_path / "main.py"
    datos = _datos(tmp_path, _err(archivo))
    _sembrar(tmp_path, datos)
    antes = (tmp_path / "py.json").read_bytes()
    assert ratchet.escanear_pyright(tmp_path, datos) == {"main.py:reportArgumentType": 1}
    assert ratchet.escanear_pyright(tmp_path, datos) == {"main.py:reportArgumentType": 1}
    assert _gate(tmp_path, datos)[0] == 0
    assert (tmp_path / "py.json").read_bytes() == antes


@requiere_git
def test_pyright_bypass_commiteado_es_rojo(tmp_path):
    """Un baseline de tipos empeorado y commiteado (HEAD peor que HEAD~1) sin la
    clave es ROJO aunque el árbol coincida con HEAD."""
    _proyecto(tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)

    def commitear(n):
        _escribir_base(tmp_path, n)
        subprocess.run(["git", "-C", str(tmp_path), "add", "py.json"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", f"py {n}"], check=True)

    commitear(0)
    commitear(1)
    codigo, salida = _gate(tmp_path, _datos(tmp_path, _err(tmp_path / "main.py")))
    assert codigo == 1 and "BYPASS: main.py:reportArgumentType: 0 → 1 errores" in salida


def test_el_gate_pinea_pyright_y_fija_el_target():
    """Sin pin ni target fijo el baseline dependería de la máquina y de la
    versión: es la config, no una costumbre."""
    requisitos = (RAIZ / "requirements-dev.txt").read_text(encoding="utf-8")
    assert re.search(r"^pyright==\d+\.\d+\.\d+$", requisitos, re.M)
    config = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pyright"]
    assert config["typeCheckingMode"] == "basic"
    assert config["pythonVersion"] == "3.12"
    assert config["reportMissingImports"] == "none"
    assert {"utils", "modules"} <= set(config["include"])
    assert (RAIZ / "calidad.sh").read_text(encoding="utf-8").count("6/6 tipos") == 1
