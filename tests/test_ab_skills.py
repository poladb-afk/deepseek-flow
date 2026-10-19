"""exp/56 — sonda del A/B de la skill `revision`: funciones deterministas.

Clavan la extracción de la respuesta final del transcript, la detección por
keywords de los issues plantados, la verificación de citas (inyectable) y el
veredicto pre-registrado. No corren el banco.
"""
import sys

from conftest import RAIZ

sys.path.insert(0, str(RAIZ / "banco" / "probes"))

import ab_skills as sonda  # noqa: E402


def test_extraer_respuesta_final_toma_el_ultimo_bloque():
    log = (
        "Agente…\n\n"
        "Tú: [trace] .runs/x.jsonl\n"
        "  [skill] revision activo\n"
        "\n"
        "DeepSeek: voy a leer → read_file\n"
        "  ⚙ ronda 1/8\n"
        "\n"
        "DeepSeek: Hallazgo uno en linea.py:1\n"
        "y hallazgo dos.\n"
        "\n"
        "Tú: \n"
        "¡Chao! 👋\n"
    )
    assert sonda.extraer_respuesta_final(log) == "Hallazgo uno en linea.py:1\ny hallazgo dos."


def test_extraer_respuesta_final_sin_respuesta_devuelve_vacio():
    assert sonda.extraer_respuesta_final("Tú: hola\n  [skill] x\n") == ""


def test_detectar_issues_por_keywords():
    completo = ("El docstring miente: dice 0-100 y devuelve fracción. "
                "El except es amplio y enmascara el error. El cache está sin usar.")
    assert sonda.detectar_issues(completo) == {
        "global_muerta_param_sin_usar": True,
        "except_amplio_mudo": True,
        "docstring_miente_unidad": True,
    }
    assert not any(sonda.detectar_issues("Está todo bien.").values())


def test_medir_respuesta_usa_verificar_inyectable():
    fake = lambda _texto: {"total": 2, "ok": 1, "mal": [{"estado": "no_existe"}]}  # noqa: E731
    fila = sonda.medir_respuesta(
        "El except amplio enmascara; ver utils/formato.py:10 y nada.py:3",
        verificar=fake)
    assert fila["issues_detectados"] == 1
    assert fila["citas_total"] == 2 and fila["citas_ok"] == 1
    assert fila["citas_invalidas"] == 1
    assert fila["palabras"] == 8


def _resumen(off, on):
    base_off = {"filas": 3, "issues_media": 1.0, "citas_ok_ratio": 0.5,
                "citas_invalidas": 2, "palabras_media": 200.0, "seg_media": 30.0,
                "rondas_media": 3.0}
    base_on = {"filas": 3, "issues_media": 2.5, "citas_ok_ratio": 0.9,
               "citas_invalidas": 0, "palabras_media": 220.0, "seg_media": 25.0,
               "rondas_media": 3.0}
    base_off.update(off)
    base_on.update(on)
    return {"off": base_off, "on": base_on}


def test_veredicto_cumple_con_el_criterio():
    cumple, fallas = sonda.veredicto(_resumen({}, {}))
    assert cumple and fallas == []


def test_veredicto_falla_cada_punto():
    cumple, fallas = sonda.veredicto(_resumen({}, {"issues_media": 1.5}))
    assert not cumple and any("(1)" in falla for falla in fallas)
    _, fallas = sonda.veredicto(_resumen({}, {"citas_ok_ratio": 0.4}))
    assert any("(2)" in falla for falla in fallas)
    _, fallas = sonda.veredicto(_resumen({}, {"citas_invalidas": 1}))
    assert any("(3)" in falla for falla in fallas)
    _, fallas = sonda.veredicto(_resumen({}, {"palabras_media": 400.0}))
    assert any("(4)" in falla for falla in fallas)


def test_veredicto_sin_filas_validas():
    cumple, fallas = sonda.veredicto({"off": {"filas": 0}, "on": {"filas": 0}})
    assert not cumple and "sin filas" in fallas[0]
