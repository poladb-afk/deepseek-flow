"""Tests del juez de riesgo (exp/44) — escritos por el conductor.

La sesión de aplicación cableó el feature pero no escribió los tests que su
spec exigía (hallazgo de auditoría: el conteo de tests no creció). Acá están
los candados de la spec §5 más el del centinela de apagado explícito
(LAYA_MODEL_RIESGO="0"/"off" — la cadena vacía cae al .env por cascada y
las sesiones cargaban el checkpoint sin querer)."""
import hashlib
import json

import pytest

from utils import riesgo
from utils.riesgo import PREGUNTA_RIESGO, juzgar, registrar


def _ajustes(monkeypatch, **valores):
    """Parchea el _setting que riesgo USA: el módulo lo importa DIRECTO al
    tope (mismo binding que el contador del bench midió) — tocar
    utils.call_llm._setting no lo alcanza."""
    monkeypatch.setattr(
        riesgo, "_setting", lambda nombre, default=None: valores.get(nombre, default)
    )


# ---------------------------------------------------------------------------
# juzgar: degradación y centinela
# ---------------------------------------------------------------------------

def test_juzgar_sin_setting_es_none(monkeypatch):
    _ajustes(monkeypatch, LAYA_MODEL_RIESGO=None)
    assert juzgar("ls -la", "listame") is None


@pytest.mark.parametrize("valor", ["0", "off", "no", "OFF", " 0 "])
def test_juzgar_apagado_explicito_es_none(monkeypatch, valor):
    """El centinela apaga DE VERDAD: la cadena vacía no sirve (cae al .env
    por cascada) — medido cargando 2.86 GiB invisibles en las sesiones."""
    _ajustes(monkeypatch, LAYA_MODEL_RIESGO=valor)
    assert juzgar("ls -la", "listame") is None


def test_juzgar_con_fallo_degrade_a_none(monkeypatch):
    """Cualquier excepción de la inferencia → None (sin juicio no hay log)."""
    from utils import laya

    _ajustes(monkeypatch, LAYA_MODEL_RIESGO=".modelos/laya-multilingual")

    def explota(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(laya, "preguntar", explota)
    assert juzgar("ls -la", "listame") is None


def test_juzgar_pasa_el_estado_recortado(monkeypatch):
    from utils import laya

    visto = {}

    def falso_preguntar(estado, preguntas, setting="LAYA_MODEL"):
        visto.update(estado)
        visto["setting"] = setting
        return {"modifica_estado": ("si", 0.9)}

    monkeypatch.setattr(laya, "preguntar", falso_preguntar)
    _ajustes(monkeypatch, LAYA_MODEL_RIESGO=".modelos/x")
    r = juzgar("x" * 2000, "m" * 2000)
    assert r == {"modifica_estado": ("si", 0.9)}
    assert visto["setting"] == "LAYA_MODEL_RIESGO"
    assert len(visto["comando"]) == 1000 and len(visto["mensaje"]) == 1000


# ---------------------------------------------------------------------------
# registrar: la línea, el gate y el bookkeeping
# ---------------------------------------------------------------------------

def test_registrar_escribe_la_linea_completa(tmp_path, monkeypatch):
    _ajustes(monkeypatch, RIESGO_ARCHIVO=str(tmp_path / "r.jsonl"))
    registrar("mkdir -p x", "creá la carpeta",
              {"requiere_revision": ("si", 0.64)}, True)
    linea = json.loads((tmp_path / "r.jsonl").read_text(encoding="utf-8").strip())
    assert linea["comando"] == "mkdir -p x"
    assert linea["juicios"]["requiere_revision"] == ["si", 0.64]
    assert linea["aprobado"] is True


def test_registrar_gate_apagado_no_escribe(tmp_path, monkeypatch):
    _ajustes(monkeypatch, RIESGO_LOG="0", RIESGO_ARCHIVO=str(tmp_path / "r.jsonl"))
    registrar("ls", "hola", None, False)
    assert not (tmp_path / "r.jsonl").exists()


def test_registrar_ruta_rota_no_levanta(tmp_path, monkeypatch):
    _ajustes(monkeypatch, RIESGO_ARCHIVO=str(tmp_path / "no" / "existe" / "r.jsonl"))
    # el mkdir lo crea el propio registrar; para forzar el fallo usamos un path
    # cuyo PARENT es un ARCHIVO (mkdir falla) — bookkeeping lo traga
    archivo = tmp_path / "bloqueo"
    archivo.write_text("x", encoding="utf-8")
    registrar("ls", "hola", None, False, ruta=str(archivo / "sub" / "r.jsonl"))


# ---------------------------------------------------------------------------
# estado_sesion: el plumbing del último mensaje
# ---------------------------------------------------------------------------

def test_estado_sesion_recordar_y_leer():
    from utils import estado_sesion

    estado_sesion.recordar_usuario("  hola  " * 300)
    assert len(estado_sesion.ultimo_usuario()) == 1000
    estado_sesion.recordar_usuario(None)
    assert estado_sesion.ultimo_usuario() == ""


# ---------------------------------------------------------------------------
# el contrato: tres preguntas de UNA dimensión, congeladas por sha1
# ---------------------------------------------------------------------------

def test_el_contrato_tiene_las_tres_preguntas_de_una_dimension():
    assert set(PREGUNTA_RIESGO) == {"modifica_estado", "danio_irreversible",
                                    "requiere_revision"}
    for pregunta in PREGUNTA_RIESGO.values():
        assert pregunta["type"] == "choice"
        assert set(pregunta["criteria"]) == {"si", "no"}


def test_el_contrato_de_riesgo_queda_congelado_sha1():
    """Mismo patrón que los contratos de Laya: cambiar una palabra rompe el
    test — el checkpoint del fine-tune entrenará contra este texto EXACTO."""
    canonico = json.dumps(PREGUNTA_RIESGO, sort_keys=True, ensure_ascii=False)
    assert hashlib.sha1(canonico.encode()).hexdigest() == "afb44dd7752ac593f25da7c5f54d0d7dcf1c58d7"


def test_registrar_marca_el_origen_de_la_decision(tmp_path, monkeypatch):
    """exp/44: sin procedencia no se puede distinguir banco sintético de humano."""
    import json

    from utils.riesgo import registrar

    ruta = tmp_path / "riesgo.jsonl"
    monkeypatch.setenv("RIESGO_ARCHIVO", str(ruta))
    monkeypatch.delenv("BANCO", raising=False)
    monkeypatch.delenv("HITL_WEB", raising=False)
    registrar("ls", "pedido", {"modifica_estado": ["no", 0.9]}, True, ruta=ruta)
    monkeypatch.setenv("BANCO", "1")
    registrar("ls", "pedido", {"modifica_estado": ["no", 0.9]}, False, ruta=ruta)
    monkeypatch.setenv("BANCO", "0")
    monkeypatch.setenv("HITL_WEB", "1")
    registrar("ls", "pedido", {"modifica_estado": ["no", 0.9]}, True, ruta=ruta)
    origenes = [json.loads(linea)["origen"] for linea in ruta.read_text(encoding="utf-8").splitlines()]
    assert origenes == ["terminal", "banco", "web"]
