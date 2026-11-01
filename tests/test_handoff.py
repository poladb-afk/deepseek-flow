"""El handoff y los principios no pueden mentir (X113).

`docs/handoff.md` es lo que lee una sesión nueva antes que el código, y
`docs/principios.md` es la constitución del harness. Si citan una ruta, un
test o una métrica que ya no existen, la sesión nueva arranca sobre un mapa
falso. Cada principio nombra su gate o dice "sin gate"; cada fuente tiene URL.
"""
import re

from conftest import RAIZ
from test_deriva_reglas import _RUTA, _TEST, _defs_de_tests, _existe_ruta, _tokens

import ratchet

HANDOFF = RAIZ / "docs" / "handoff.md"
PRINCIPIOS = RAIZ / "docs" / "principios.md"


def _texto(ruta):
    return ruta.read_text(encoding="utf-8")


def _filas(texto, prefijo):
    return [linea for linea in texto.splitlines() if re.match(rf"\|\s*{prefijo}\d+\s*\|", linea)]


def _vigente(token, defs):
    return (token in defs or token in ratchet.METRICAS
            or (_RUTA.fullmatch(token) is not None and _existe_ruta(token)))


def test_handoff_y_principios_citan_rutas_y_tests_que_existen():
    defs = _defs_de_tests()
    faltan = []
    for ruta in (HANDOFF, PRINCIPIOS):
        for token in _tokens(_texto(ruta)):
            if _RUTA.fullmatch(token) and _existe_ruta(token) is False or _TEST.fullmatch(token) and token not in defs:
                faltan.append(f"{ruta.name}: {token}")
    assert not faltan, f"citas a cosas que no existen: {faltan}"


def test_cada_principio_nombra_su_gate_o_dice_sin_gate():
    """Un principio sin gate se declara; uno con gate cita algo vigente."""
    defs = _defs_de_tests()
    texto = _texto(PRINCIPIOS)
    filas = _filas(texto, "S") + _filas(texto, "P") + _filas(texto, "N")
    assert len(filas) == 9, f"se esperaban S0, P1–P4 y N1–N4 (X118), hay {len(filas)} filas"
    sueltos = []
    for fila in filas:
        celdas = [celda.strip() for celda in fila.strip().strip("|").split("|")]
        verifica = celdas[-2]
        citados = re.findall(r"`([^`\n]+)`", verifica)
        if "sin gate" in verifica:
            continue
        if not any(_vigente(token, defs) for token in citados):
            sueltos.append(celdas[0])
    assert not sueltos, f"principios sin gate vigente ni 'sin gate' declarado: {sueltos}"


def test_cada_fuente_tiene_url_y_dice_donde_se_aplica():
    texto = _texto(PRINCIPIOS).split("## Fuentes", 1)[1]
    filas = [linea for linea in texto.splitlines() if linea.startswith("| ") and not linea.startswith("| Fuente")]
    assert len(filas) >= 20
    sin_url = [fila.split("|")[1].strip() for fila in filas
               if "http" not in fila and "privado" not in fila]
    assert not sin_url, f"fuentes sin URL: {sin_url}"
    assert all(fila.rstrip().rstrip("|").split("|")[-1].strip() for fila in filas)
