"""Cliente Laya: lotes, puntajes, checkpoints en proceso y log de preguntas (PR 4)."""
from conftest import RAIZ


def test_preguntar_lote_alinea_y_extrae(monkeypatch):
    """exp/14: preguntar_lote() es la versión en lote de preguntar(): un
    forward compartido (predict_batch) para N estados, con la MISMA
    extracción (respuesta, confianza) y alineado por índice."""
    import utils.laya as laya_mod

    class FakeAgente:
        def __init__(self):
            self.vistos = None

        def predict_batch(self, estados, preguntas, lang="es"):
            self.vistos = list(estados)
            # dos resultados con answer_confidence DISTINTAS, en orden
            return [
                {"answers": {"aporta_contexto": {"choice": "si", "answer_confidence": 0.9}}},
                {"answers": {"aporta_contexto": {"choice": "no", "answer_confidence": 0.2}}},
            ]

    fake = FakeAgente()
    monkeypatch.setattr(laya_mod, "agente", lambda setting="LAYA_MODEL": fake)

    estados = [{"consulta": "a", "bloque": "x"}, {"consulta": "a", "bloque": "y"}]
    contrato = {"aporta_contexto": {"type": "choice"}}
    salida = laya_mod.preguntar_lote(estados, contrato)

    assert len(salida) == 2  # alineado 1:1 con los estados
    assert salida[0]["aporta_contexto"] == ("si", 0.9)
    assert salida[1]["aporta_contexto"] == ("no", 0.2)
    # el batch se mandó de una: los MISMOS estados y contrato
    assert fake.vistos == estados

def test_puntuar_una_llamada_y_formula(monkeypatch):
    """exp/14: _puntuar() arma TODOS los estados (mismo truncamiento y
    orden) y llama a preguntar_lote UNA vez; los puntajes siguen la fórmula
    confianza si 'si', 1-confianza si 'no'."""
    import utils.contexto as ctx
    import utils.laya as laya_mod

    llamadas = {"n": 0}
    capturado = {}

    def fake_lote(estados, preguntas, setting="LAYA_MODEL"):
        llamadas["n"] += 1
        capturado["estados"] = list(estados)
        # 'si' → confianza; 'no' → 1-confianza
        return [
            {"aporta_contexto": ("si", 0.8)},
            {"aporta_contexto": ("no", 0.25)},
            {"aporta_contexto": ("si", 0.6)},
            {"aporta_contexto": ("no", 0.1)},
        ]

    monkeypatch.setattr(laya_mod, "disponible", lambda setting="LAYA_MODEL": True)
    monkeypatch.setattr(laya_mod, "preguntar_lote", fake_lote)

    unidades = ["u0", "u1", "u2", "u3"]
    puntajes = ctx._puntuar("consulta", unidades, "LAYA_MODEL_PREFILTRO")

    assert llamadas["n"] == 1, "debe ser UNA sola llamada en lote"
    # fórmula: si → conf; no → 1-conf
    assert puntajes == {0: 0.8, 1: 1.0 - 0.25, 2: 0.6, 3: 1.0 - 0.1}
    # truncamiento y orden: consulta[:1000], bloque[:2000], en orden
    assert capturado["estados"] == [
        {"consulta": "consulta", "bloque": "u0"},
        {"consulta": "consulta", "bloque": "u1"},
        {"consulta": "consulta", "bloque": "u2"},
        {"consulta": "consulta", "bloque": "u3"},
    ]

def test_puntuar_lote_que_falla_devuelve_none(monkeypatch):
    """exp/14: la ley de hierro no cambia — si preguntar_lote lanza, _puntuar
    devuelve None y el llamador cae al default seguro (sin juicio)."""
    import utils.contexto as ctx
    import utils.laya as laya_mod

    def boom(estados, preguntas, setting="LAYA_MODEL"):
        raise RuntimeError("batch roto")

    monkeypatch.setattr(laya_mod, "disponible", lambda setting="LAYA_MODEL": True)
    monkeypatch.setattr(laya_mod, "preguntar_lote", boom)

    assert ctx._puntuar("c", ["a", "b"], "LAYA_MODEL_PREFILTRO") is None

def test_laya_tope_de_checkpoints_en_proceso(monkeypatch):
    """exp/32: la ley medida es un checkpoint por proceso (2,86 GiB de RSS);
    el tope descarga el MENOS usado en vez de acumular hasta los cuatro
    alcanzables en un chat (router + voto + prefiltro + supervisor)."""
    import sys
    from types import SimpleNamespace

    from utils import laya

    class AgenteFalso:
        def __init__(self, clave):
            self.clave = clave

    monkeypatch.setattr(laya, "_agentes", {})
    monkeypatch.setattr(laya, "_errores", {})
    monkeypatch.setattr(laya, "_uso", {})
    monkeypatch.setattr(laya, "MAX_EN_PROCESO", 2)
    monkeypatch.setattr(
        laya, "_setting",
        lambda nombre, default=None: {"LAYA_A": "a", "LAYA_B": "b", "LAYA_C": "c"}.get(nombre, default),
    )
    monkeypatch.setitem(sys.modules, "laya", SimpleNamespace(load=lambda clave: AgenteFalso(clave)))

    assert laya.agente("LAYA_A").clave == "a"
    assert laya.agente("LAYA_B").clave == "b"
    assert set(laya._agentes) == {"a", "b"}
    # A se usa de nuevo (pasa a ser el más usado) y entra C: sale B
    laya.agente("LAYA_A")
    laya.agente("LAYA_C")
    assert set(laya._agentes) == {"a", "c"}
    # el recién cargado nunca se desaloja solo
    assert laya.agente("LAYA_C").clave == "c"

def test_registrar_pregunta_es_bookkeeping_que_no_rompe(tmp_path, monkeypatch):
    """exp/34: la pregunta del usuario queda en un JSONL local (el trace no
    guarda texto y los logs del banco van con echo off, así que sin esto no
    hay muestra natural para calibrar). Cualquier fallo se traga."""
    import json as _json

    import nodes

    archivo = tmp_path / "preguntas.jsonl"
    monkeypatch.setattr(
        nodes, "_setting",
        lambda nombre, default=None: {"PREGUNTAS_ARCHIVO": str(archivo)}.get(nombre, default),
    )
    nodo = nodes.GetQuestion()
    nodo.post({"messages": []}, None, "¿cuánto es 2+2?")
    nodo.post({"messages": []}, None, "otra pregunta")
    lineas = [
        _json.loads(linea)
        for linea in archivo.read_text(encoding="utf-8").splitlines()
    ]
    assert [linea["pregunta"] for linea in lineas] == ["¿cuánto es 2+2?", "otra pregunta"]
    assert all("ts" in linea for linea in lineas)
    # procedencia (exp/71b): el tráfico del banco no se confunde con el humano
    assert all(linea["origen"] in ("web", "terminal", "banco") for linea in lineas)

    # PREGUNTAS_LOG=0 lo apaga
    archivo.unlink()
    monkeypatch.setattr(
        nodes, "_setting",
        lambda nombre, default=None: "0" if nombre == "PREGUNTAS_LOG" else default,
    )
    nodo.post({"messages": []}, None, "no se guarda")
    assert not archivo.exists()

    # un destino imposible (un directorio) no corta el chat
    monkeypatch.setattr(
        nodes, "_setting",
        lambda nombre, default=None: (
            str(tmp_path) if nombre == "PREGUNTAS_ARCHIVO" else default
        ),
    )
    nodo.post({"messages": []}, None, "tampoco explota")

def test_etiquetador_acepta_el_log_de_preguntas_del_chat(tmp_path):
    """exp/34: el --extra del etiquetador lee el JSONL del log del chat, así el
    tráfico real entra a la calibración sin conversiones."""
    import json as _json
    import sys

    sys.path.insert(0, str(RAIZ / "banco" / "probes"))
    from etiquetar_router import preguntas_de_archivo

    archivo = tmp_path / "preguntas.jsonl"
    archivo.write_text(
        _json.dumps({"ts": 1.0, "pregunta": "¿quién ganó el último mundial?"}) + "\n"
        + "una pregunta suelta sin json\n"
        + _json.dumps({"ts": 2.0, "pregunta": "corta"}) + "\n",
        encoding="utf-8",
    )
    assert preguntas_de_archivo(archivo) == [
        "¿quién ganó el último mundial?",
        "una pregunta suelta sin json",
    ]
