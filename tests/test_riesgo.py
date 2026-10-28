"""Tests del juez de riesgo (exp/44) — escritos por el conductor.

La sesión de aplicación cableó el feature pero no escribió los tests que su
spec exigía (hallazgo de auditoría: el conteo de tests no creció). Acá están
los candados de la spec §5 más el del centinela de apagado explícito
(LAYA_MODEL_RIESGO="0"/"off" — la cadena vacía cae al .env por cascada y
las sesiones cargaban el checkpoint sin querer)."""
import hashlib
import json
from pathlib import Path

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


# juzgar: degradación y centinela

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


# registrar: la línea, el gate y el bookkeeping

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
    # observable: el fallo se traga Y no deja un archivo a medias
    assert not (archivo / "sub").exists()


# estado_sesion: el plumbing del último mensaje

def test_estado_sesion_recordar_y_leer():
    from utils import estado_sesion

    estado_sesion.recordar_usuario("  hola  " * 300)
    assert len(estado_sesion.ultimo_usuario()) == 1000
    estado_sesion.recordar_usuario(None)
    assert estado_sesion.ultimo_usuario() == ""


# el contrato: tres preguntas de UNA dimensión, congeladas por sha1

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
    """exp/44: la procedencia del canal humano (terminal / web). Lo sintético
    no se marca acá: el banco escribe sus logs aparte (X93)."""
    import json

    from utils.riesgo import registrar

    ruta = tmp_path / "riesgo.jsonl"
    monkeypatch.setenv("RIESGO_ARCHIVO", str(ruta))
    monkeypatch.delenv("HITL_WEB", raising=False)
    registrar("ls", "pedido", {"modifica_estado": ["no", 0.9]}, True, ruta=ruta)
    monkeypatch.setenv("HITL_WEB", "1")
    registrar("ls", "pedido", {"modifica_estado": ["no", 0.9]}, True, ruta=ruta)
    origenes = [json.loads(linea)["origen"] for linea in ruta.read_text(encoding="utf-8").splitlines()]
    assert origenes == ["terminal", "web"]


# exp/101 — la etiqueta que decide un scope no es juicio humano

def test_la_etiqueta_delegada_no_cuenta_como_humana(tmp_path, monkeypatch):
    """Con HITL_SCOPE el s/n lo decide el archivo de scope (conductor o
    banco): la ETIQUETA de riesgo es `scope` (excluida del fine-tune), por el
    MECANISMO que decidió y no por una bandera de quién corre. El `origen()`
    del PAR de routing sigue `terminal` — la flywheel no pierde las delegadas
    (contrato de exp/99)."""
    import json

    from utils.riesgo import origen, origen_etiqueta, registrar

    ruta = tmp_path / "riesgo.jsonl"
    monkeypatch.delenv("HITL_WEB", raising=False)
    monkeypatch.setenv("HITL_SCOPE", str(tmp_path / "scope.json"))
    assert origen_etiqueta() == "scope"
    assert origen() == "terminal"  # el par de routing NO cambia
    registrar("du -sh salidas", "pedido", {"modifica_estado": ["no", 0.9]}, True, ruta=ruta)
    monkeypatch.delenv("HITL_SCOPE")
    assert origen_etiqueta() == "terminal"
    registrar("du -sh salidas", "pedido", {"modifica_estado": ["no", 0.9]}, True, ruta=ruta)
    origenes = [json.loads(linea)["origen"] for linea
                in ruta.read_text(encoding="utf-8").splitlines()]
    assert origenes == ["scope", "terminal"]


def test_estado_riesgo_cuenta_las_delegadas_aparte():
    """El probe de readiness: lo aprobado por scope queda fuera de las
    orgánicas con su propia fila, en los DOS vocabularios (`delegado` de los
    logs de exp/101, `scope` desde X93)."""
    from banco.probes.estado_riesgo import estado

    filas = [
        {"origen": "terminal", "aprobado": True},
        {"origen": "delegado", "aprobado": True},
        {"origen": "scope", "aprobado": False},
        {"origen": "banco", "aprobado": True},
    ]
    e = estado(filas)
    assert e["organicas"] == 1
    assert e["rechazos"] == 0  # el rechazo por scope no es rechazo humano
    assert e["scope"] == 2
    assert e["banco"] == 1


# exp/71 — la suite no ensucia los logs ni carga el checkpoint real

def test_observar_riesgo_solo_juzga_bandas_humanas(monkeypatch):
    """La observación (exp/44) es no-op en 'auto' y denylist: solo el humano
    gatea esas bandas. Con conftest apagando el checkpoint, este fake es el
    que mantiene cubierta la integración."""
    import modules.coding as coding

    llamados = []

    def falso(comando, mensaje):
        llamados.append((comando, mensaje))
        return {"modifica_estado": ("no", 0.9)}

    monkeypatch.setattr(coding, "juzgar", falso)
    monkeypatch.setattr(coding, "ultimo_usuario", lambda: "pedido")
    assert coding._observar_riesgo("ls", "auto") is None
    assert llamados == []
    assert coding._observar_riesgo("ls", "preguntar") == {"modifica_estado": ("no", 0.9)}
    assert llamados == [("ls", "pedido")]


def test_la_suite_no_escribe_los_logs_ni_la_memoria_de_produccion(monkeypatch):
    """exp/71: la suite dejaba 541 filas `terminal` en `salidas/riesgo.jsonl`
    (24,4 s y 2,98 GiB de RSS por cargar el checkpoint) y 157 respaldos de
    fixture en `memoria/`. El conftest manda los logs, MEMORIA_DIR y el trace
    de resume (`THREADS_DIR`, review de exp/71) a tmp; los tests que prueban estos
    caminos fijan su propia ruta y ganan después."""
    from utils.call_llm import _setting

    raiz = Path(__file__).resolve().parent.parent
    riesgo = Path(_setting("RIESGO_ARCHIVO")).resolve()
    memoria = Path(_setting("MEMORIA_DIR")).resolve()
    threads = Path(_setting("THREADS_DIR", "salidas/threads")).resolve()
    assert riesgo != (raiz / "salidas" / "riesgo.jsonl")
    assert memoria != (raiz / "memoria")
    assert threads != (raiz / "salidas" / "threads")
    assert _setting("LAYA_MODEL_RIESGO") == "0"  # sin checkpoint del juez en tests
    assert riesgo.parent == memoria.parent == threads.parent  # todo en el basetemp
