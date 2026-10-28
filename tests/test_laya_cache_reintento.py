"""Tests del fix del caché de errores de Laya (spec laya_cache_reintento).

Un OOM transitorio cacheaba el fallo de `laya.load` PARA SIEMPRE dentro del
proceso: el resto de la sesión salía "sin detalle de Laya" sin un solo
reintento. El error ahora VENCE tras LAYA_ERROR_COOLDOWN y se reintenta la
carga en la misma llamada. Sin modelo real: se inyecta un módulo `laya` falso
y se siembra el estado a mano (el test escribe un ts viejo directo).
"""
import sys
import time
from types import SimpleNamespace

import pytest

from utils import laya

CLAVE = "modelo-falso"


@pytest.fixture(autouse=True)
def _estado_limpio(monkeypatch):
    """Cada test arranca con las cachés vacías: los tests siembran su estado."""
    monkeypatch.setattr(laya, "_agentes", {})
    monkeypatch.setattr(laya, "_errores", {})
    monkeypatch.setattr(laya, "_uso", {})
    # la clave es literal (no un path real del entorno) para poder sembrar el estado
    monkeypatch.setattr(laya, "_setting", lambda nombre, default=None: CLAVE)


def _fake(monkeypatch, load):
    monkeypatch.setitem(sys.modules, "laya", SimpleNamespace(load=load))


def test_fallo_transitorio_se_recupera(monkeypatch):
    """load falla 1ª vez → RuntimeError; con el ts vencido, la 2ª llamada
    reintenta y ahora sí carga, y el error queda limpio."""
    intentos = {"n": 0}

    def load(clave):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise MemoryError("OOM")
        return "agente-vivo"

    _fake(monkeypatch, load)

    with pytest.raises(RuntimeError):
        laya.agente()
    assert intentos["n"] == 1
    assert CLAVE in laya._errores

    # el test siembra el vencimiento: un error de hace mucho más que el cooldown
    _ts, msg = laya._errores[CLAVE]
    laya._errores[CLAVE] = (time.monotonic() - laya.LAYA_ERROR_COOLDOWN - 1, msg)

    assert laya.agente() == "agente-vivo"
    assert intentos["n"] == 2
    assert CLAVE not in laya._errores


def test_dentro_del_cooldown_no_reintenta(monkeypatch):
    """Dentro del cooldown, la llamada inmediata relanza el RuntimeError
    cacheado SIN volver a llamar a load (lo clava el contador del fake)."""
    intentos = {"n": 0}

    def load(clave):
        intentos["n"] += 1
        raise MemoryError("OOM")

    _fake(monkeypatch, load)

    with pytest.raises(RuntimeError):
        laya.agente()
    with pytest.raises(RuntimeError):
        laya.agente()

    assert intentos["n"] == 1  # el segundo intento no tocó load


def test_el_exito_limpia_el_error_residual(monkeypatch):
    """Clave con error vencido + agente cargado → sin RuntimeError, y el
    error residual se limpia."""
    _fake(monkeypatch, lambda clave: "recargado")

    laya._agentes[CLAVE] = "ya-cargado"
    laya._errores[CLAVE] = (time.monotonic() - 3600, "MemoryError: OOM")

    assert laya.agente() == "ya-cargado"
    assert CLAVE not in laya._errores


def test_el_raise_reporta_la_edad(monkeypatch):
    """El raise conserva el mensaje e incluye la edad del error (debug)."""
    _fake(monkeypatch, lambda clave: (_ for _ in ()).throw(MemoryError("OOM")))

    with pytest.raises(RuntimeError) as exc:
        laya.agente()
    assert "MemoryError: OOM" in str(exc.value)
    assert "hace" in str(exc.value)


def test_cooldown_con_basura_usa_60(monkeypatch):
    """El cooldown es una constante desde X101: un .env con
    LAYA_ERROR_COOLDOWN=sesenta (el caso que este test cubría vía `_entero`)
    ya no tiene lectura que pueda fallar. Queda fijado el valor."""
    from utils import laya

    monkeypatch.setenv("LAYA_ERROR_COOLDOWN", "sesenta")
    assert laya.LAYA_ERROR_COOLDOWN == 60
