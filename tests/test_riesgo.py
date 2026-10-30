"""El log de decisiones HITL de comando: la etiqueta humana del juez futuro.

El juez de Laya que solo observaba (exp/44) se borró en X109; la etiqueta ya
no depende de que haya un checkpoint cargado."""
import json
from pathlib import Path

from utils import riesgo
from utils.riesgo import registrar


def _ajustes(monkeypatch, **valores):
    """Parchea el _setting que riesgo USA: el módulo lo importa directo al tope."""
    monkeypatch.setattr(riesgo, "_setting", lambda nombre, default=None: valores.get(nombre, default))


def test_registrar_escribe_la_linea_completa(tmp_path, monkeypatch):
    _ajustes(monkeypatch, RIESGO_ARCHIVO=str(tmp_path / "r.jsonl"))
    registrar("mkdir -p x", "creá la carpeta", True)
    linea = json.loads((tmp_path / "r.jsonl").read_text(encoding="utf-8").strip())
    assert (linea["comando"], linea["mensaje"], linea["aprobado"]) == ("mkdir -p x", "creá la carpeta", True)
    assert "juicios" not in linea


def test_registrar_gate_apagado_no_escribe(tmp_path, monkeypatch):
    _ajustes(monkeypatch, RIESGO_LOG="0", RIESGO_ARCHIVO=str(tmp_path / "r.jsonl"))
    registrar("ls", "hola", False)
    assert not (tmp_path / "r.jsonl").exists()


def test_registrar_ruta_rota_no_levanta(tmp_path, monkeypatch):
    # el PARENT de la ruta es un ARCHIVO: el mkdir falla y el bookkeeping lo traga
    archivo = tmp_path / "bloqueo"
    archivo.write_text("x", encoding="utf-8")
    registrar("ls", "hola", False, ruta=str(archivo / "sub" / "r.jsonl"))
    assert not (archivo / "sub").exists()


def test_estado_sesion_recordar_y_leer():
    from utils import estado_sesion

    estado_sesion.recordar_usuario("  hola  " * 300)
    assert len(estado_sesion.ultimo_usuario()) == 1000
    estado_sesion.recordar_usuario(None)
    assert estado_sesion.ultimo_usuario() == ""


def test_registrar_marca_el_origen_de_la_decision(tmp_path, monkeypatch):
    """La procedencia del canal humano (terminal / web)."""
    ruta = tmp_path / "riesgo.jsonl"
    monkeypatch.delenv("HITL_WEB", raising=False)
    registrar("ls", "pedido", True, ruta=ruta)
    monkeypatch.setenv("HITL_WEB", "1")
    registrar("ls", "pedido", True, ruta=ruta)
    origenes = [json.loads(linea)["origen"] for linea in ruta.read_text(encoding="utf-8").splitlines()]
    assert origenes == ["terminal", "web"]


def test_la_etiqueta_delegada_no_cuenta_como_humana(tmp_path, monkeypatch):
    """Con HITL_SCOPE el s/n lo decide el archivo de scope (conductor o
    banco): la ETIQUETA es `scope` (excluida del fine-tune). El `origen()` del
    tráfico sigue `terminal`."""
    from utils.riesgo import origen, origen_etiqueta

    ruta = tmp_path / "riesgo.jsonl"
    monkeypatch.delenv("HITL_WEB", raising=False)
    monkeypatch.setenv("HITL_SCOPE", str(tmp_path / "scope.json"))
    assert origen_etiqueta() == "scope"
    assert origen() == "terminal"
    registrar("du -sh salidas", "pedido", True, ruta=ruta)
    monkeypatch.delenv("HITL_SCOPE")
    registrar("du -sh salidas", "pedido", True, ruta=ruta)
    origenes = [json.loads(linea)["origen"] for linea in ruta.read_text(encoding="utf-8").splitlines()]
    assert origenes == ["scope", "terminal"]


def test_estado_riesgo_cuenta_las_delegadas_aparte():
    """La sonda de readiness: lo aprobado por scope queda fuera de las
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


def test_run_command_registra_cada_decision_humana_y_nada_en_auto(tmp_path, monkeypatch):
    """Cada s/n humano deja su fila (aprobada o rechazada) con la intención
    del usuario; el `auto` no pregunta y no deja ninguna."""
    import modules.coding as coding

    ruta = tmp_path / "riesgo.jsonl"
    monkeypatch.setenv("RIESGO_ARCHIVO", str(ruta))
    monkeypatch.setattr(coding, "ultimo_usuario", lambda: "creá las carpetas")
    monkeypatch.setattr(coding, "registrar_aprobacion", lambda *a, **k: None)
    respuestas = iter([True, False])
    monkeypatch.setattr(coding, "_approve", lambda _p: next(respuestas))
    assert coding._aprobar("mkdir x", "preguntar") == (True, "")
    assert coding._aprobar("mkdir y", "preguntar")[0] is False

    def no_preguntar(_p):
        raise AssertionError("auto no pide aprobación")

    monkeypatch.setattr(coding, "_approve", no_preguntar)
    assert coding._aprobar("ls", "auto") == (True, "")
    filas = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]
    assert [(f["comando"], f["aprobado"], f["mensaje"]) for f in filas] == [
        ("mkdir x", True, "creá las carpetas"), ("mkdir y", False, "creá las carpetas")]


def test_la_suite_no_escribe_los_logs_ni_la_memoria_de_produccion(monkeypatch):
    """exp/71: la suite dejaba 541 filas `terminal` en `salidas/riesgo.jsonl`
    y 157 respaldos de fixture en `memoria/`. El conftest manda los logs,
    MEMORIA_DIR y el trace de resume (`THREADS_DIR`) a tmp; los tests que
    prueban estos caminos fijan su propia ruta y ganan después."""
    from utils.call_llm import _setting

    raiz = Path(__file__).resolve().parent.parent
    destino = Path(_setting("RIESGO_ARCHIVO")).resolve()
    memoria = Path(_setting("MEMORIA_DIR")).resolve()
    threads = Path(_setting("THREADS_DIR", "salidas/threads")).resolve()
    assert destino != (raiz / "salidas" / "riesgo.jsonl")
    assert memoria != (raiz / "memoria")
    assert threads != (raiz / "salidas" / "threads")
    assert destino.parent == memoria.parent == threads.parent  # todo en el basetemp
