"""Tests de la política del router (exp/35) — puros, sin modelo ni red.

La clasificación (Laya) y la decisión (Python) están separadas justamente
para poder clavar la segunda acá: respuestas inválidas, límites del umbral,
conjunto conformal y los tres modos.
"""
import json

import pytest

from utils.laya_routing import (
    RouterConfig,
    config_router,
    decide,
    probabilidades,
    registrar_decision,
    ruta_aplicada,
)


def detalle(p_directo, eleccion="directo"):
    return {"choice": eleccion,
            "probabilities": {"directo": p_directo, "herramientas": 1.0 - p_directo}}


@pytest.mark.parametrize("respuesta", [
    None,
    {},
    {"choice": "directo"},
    {"choice": "directo", "probabilities": {}},
    {"choice": "directo", "probabilities": {"directo": 0.9}},          # falta una
    {"choice": "directo", "probabilities": {"directo": 0.9, "herramientas": 0.5}},  # no suman 1
    {"choice": "directo", "probabilities": {"directo": float("nan"), "herramientas": 0.1}},
    {"choice": "directo", "probabilities": {"directo": float("inf"), "herramientas": 0.0}},
    {"choice": "directo", "probabilities": {"directo": True, "herramientas": 0.0}},
    {"choice": "directo", "probabilities": {"directo": "0.9", "herramientas": 0.1}},
    {"choice": "directo", "probabilities": {"directo": 1.2, "herramientas": -0.2}},
])
def test_respuesta_invalida_abstiene_nunca_directo(respuesta):
    """La regla dura: sin probabilidades usables no hay ruta directa. Un fallo
    del clasificador no puede habilitar la ruta que ahorra la llamada."""
    propuesta, causa, p_directo = decide(respuesta, RouterConfig())
    assert propuesta == "herramientas"
    assert "inválida" in causa or "contrato" in causa
    assert p_directo is None or isinstance(p_directo, float)


def test_etiqueta_fuera_de_contrato_abstiene():
    respuesta = {"choice": "quizas",
                 "probabilities": {"directo": 0.9, "herramientas": 0.1}}
    propuesta, causa, _ = decide(respuesta, RouterConfig())
    assert propuesta == "herramientas"
    assert "fuera de contrato" in causa


def test_umbral_fijo_incluye_el_limite():
    """p(directo) >= umbral decide directo; un pelo abajo, no."""
    config = RouterConfig(umbral=0.85)
    assert decide(detalle(0.85), config)[0] == "directo"
    assert decide(detalle(0.8499), config)[0] == "herramientas"
    assert "umbral" in decide(detalle(0.5), config)[1]


def test_conjunto_conformal_decide_por_colapso():
    """Con q calibrado, la ruta directa exige que el conjunto de etiquetas
    plausibles colapse en directo (piso = 1 - q)."""
    config = RouterConfig(q=0.60)          # piso 0.40
    assert decide(detalle(0.70), config)[0] == "directo"
    assert decide(detalle(0.55), config)[0] == "herramientas"   # ambas >= 0.40
    assert decide(detalle(0.30), config)[0] == "herramientas"   # conjunto vacío


def test_modos_off_shadow_enforce():
    """off no ejecuta Laya; shadow registra pero conserva herramientas;
    enforce aplica la propuesta."""
    respuesta = detalle(0.99)
    assert decide(respuesta, RouterConfig(modo="off"))[0] == "herramientas"
    assert decide(respuesta, RouterConfig(modo="shadow"))[0] == "directo"
    assert ruta_aplicada("directo", RouterConfig(modo="shadow")) == "herramientas"
    assert ruta_aplicada("directo", RouterConfig(modo="enforce")) == "directo"
    assert ruta_aplicada("herramientas", RouterConfig(modo="enforce")) == "herramientas"


def test_probabilidades_rechaza_bool_y_texto():
    assert probabilidades({"probabilities": {"directo": True, "herramientas": 0}}) is None
    assert probabilidades({"probabilities": {"directo": "0.9", "herramientas": 0.1}}) is None
    assert probabilidades(detalle(0.9)) == (0.9, pytest.approx(0.1))


def test_config_router_modo_desconocido_cae_a_enforce(monkeypatch):
    from utils import call_llm

    monkeypatch.setattr(call_llm, "_setting",
                        lambda nombre, default=None: "vaya_uno_a_saber" if nombre == "LAYA_MODO" else default)
    assert config_router().modo == "enforce"


def test_registrar_decision_escribe_y_no_rompe(tmp_path, monkeypatch):
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    monkeypatch.setattr(call_llm, "_setting", lambda nombre, default=None: default)
    registrar_decision({"modo": "shadow", "propuesta": "directo"}, ruta=archivo)
    linea = json.loads(archivo.read_text(encoding="utf-8").strip())
    assert linea["propuesta"] == "directo" and linea["modo"] == "shadow"
    assert "ts" in linea

    # apagado por setting: no escribe
    monkeypatch.setattr(call_llm, "_setting",
                        lambda nombre, default=None: "0" if nombre == "LAYA_LOG_DECISIONES" else default)
    registrar_decision({"modo": "off"}, ruta=archivo)
    assert len(archivo.read_text(encoding="utf-8").strip().splitlines()) == 1

    # destino imposible (un directorio): se traga, no rompe el chat
    monkeypatch.setattr(call_llm, "_setting", lambda nombre, default=None: default)
    registrar_decision({"modo": "off"}, ruta=tmp_path)


def test_registrar_decision_no_guarda_texto_por_default(tmp_path, monkeypatch):
    """Privacidad: sin LAYA_LOG_PREGUNTA=1 el evento no lleva la pregunta."""
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    monkeypatch.setattr(call_llm, "_setting", lambda nombre, default=None: default)
    registrar_decision(
        {"modo": "shadow"}, pregunta="¿quién ganó el último mundial?", ruta=archivo
    )
    assert "pregunta" not in json.loads(archivo.read_text(encoding="utf-8").strip())


def test_registrar_decision_con_pregunta_opt_in(tmp_path, monkeypatch):
    """Con LAYA_LOG_PREGUNTA=1 el evento lleva la pregunta normalizada y
    recortada a 200: es lo que une el registro con el etiquetador."""
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    monkeypatch.setattr(
        call_llm, "_setting",
        lambda nombre, default=None: "1" if nombre == "LAYA_LOG_PREGUNTA" else default,
    )
    registrar_decision({"modo": "shadow"}, pregunta="  hola\n  mundo  ", ruta=archivo)
    assert json.loads(archivo.read_text(encoding="utf-8").strip())["pregunta"] == "hola mundo"

    registrar_decision({"modo": "shadow"}, pregunta="x" * 500, ruta=archivo)
    ultima = json.loads(archivo.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert len(ultima["pregunta"]) == 200


def test_el_nodo_pasa_la_pregunta_al_registro(tmp_path, monkeypatch):
    """exp/35: en modo sombra, con la pregunta habilitada, el evento sale del
    nodo completo (pregunta + propuesta + confianza + ruta aplicada): el set
    que después etiqueta banco/probes/etiquetar_router.py."""
    import nodes
    from utils import call_llm, laya

    archivo = tmp_path / "routing.jsonl"
    ajustes = {
        "LAYA_MODO": "shadow",
        "LAYA_LOG_ARCHIVO": str(archivo),
        "LAYA_LOG_PREGUNTA": "1",
    }
    monkeypatch.setattr(
        call_llm, "_setting", lambda nombre, default=None: ajustes.get(nombre, default)
    )
    monkeypatch.setattr(laya, "disponible", lambda *a, **k: True)
    router = nodes.LayaRouter()
    respuesta = {
        "choice": "directo",
        "probabilities": {"directo": 0.99, "herramientas": 0.01},
    }
    assert router.post({}, {"pregunta": "leé el archivo X"}, respuesta) == "herramientas"
    linea = json.loads(archivo.read_text(encoding="utf-8").strip())
    assert linea["pregunta"] == "leé el archivo X"
    assert linea["propuesta"] == "directo" and linea["aplicada"] == "herramientas"
    assert linea["p_directo"] == 0.99 and linea["modo"] == "shadow"


# exp/43 — la etiqueta ambiental (decisión ──id──> resultado)


def test_registrar_resultado_escribe_la_linea_completa(tmp_path, monkeypatch):
    """La línea "resultado" lleva ts, evento, id, uso_tools y rondas; es la
    mitad derecha del join con la decisión."""
    from utils import call_llm
    from utils.laya_routing import registrar_resultado

    archivo = tmp_path / "routing.jsonl"
    monkeypatch.setattr(call_llm, "_setting", lambda nombre, default=None: default)
    registrar_resultado("abcd1234", 3, ruta=archivo)
    linea = json.loads(archivo.read_text(encoding="utf-8").strip())
    assert linea["evento"] == "resultado" and linea["id"] == "abcd1234"
    assert linea["uso_tools"] is True and linea["rondas"] == 3
    assert "ts" in linea

    registrar_resultado("ef", 0, ruta=archivo)
    ult = json.loads(archivo.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert ult["uso_tools"] is False and ult["rondas"] == 0


def test_registrar_resultado_gate_y_ruta_rota(tmp_path, monkeypatch):
    """Apagado por setting no escribe; sin id no escribe; destino imposible se
    traga (bookkeeping: nunca corta el chat)."""
    from utils import call_llm
    from utils.laya_routing import registrar_resultado

    archivo = tmp_path / "routing.jsonl"
    monkeypatch.setattr(
        call_llm, "_setting",
        lambda nombre, default=None: "0" if nombre == "LAYA_LOG_DECISIONES" else default,
    )
    registrar_resultado("abcd", 1, ruta=archivo)
    assert not archivo.exists()

    # gate abierto pero sin id: no hay a qué unir el resultado
    monkeypatch.setattr(call_llm, "_setting", lambda nombre, default=None: default)
    registrar_resultado(None, 1, ruta=archivo)
    registrar_resultado("", 1, ruta=archivo)
    assert not archivo.exists()

    # ruta rota (un directorio): se traga
    registrar_resultado("abcd", 1, ruta=tmp_path)


def test_shadow_con_probabilidades_deja_el_pendiente_igual_al_id(tmp_path, monkeypatch):
    """El pendiente es EXACTAMENTE el id de la línea de decisión escrita: el
    join 1:1 decisión┄resultado es el contrato."""
    import nodes
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    ajustes = {"LAYA_MODO": "shadow", "LAYA_LOG_ARCHIVO": str(archivo)}
    monkeypatch.setattr(
        call_llm, "_setting", lambda nombre, default=None: ajustes.get(nombre, default)
    )
    shared = {}
    router = nodes.LayaRouter()
    respuesta = {"choice": "directo",
                 "probabilities": {"directo": 0.9, "herramientas": 0.1}}
    assert router.post(shared, {"pregunta": "q"}, respuesta) == "herramientas"
    linea = json.loads(archivo.read_text(encoding="utf-8").strip())
    assert shared["_router_pendiente"] == linea["id"]


def test_shadow_con_log_apagado_no_deja_pendiente_ni_escribe(tmp_path, monkeypatch):
    """Con el gate apagado no hay línea de decisión: sin línea no hay
    pendiente ni resultado (el marcador mide líneas escritas, no el print)."""
    import nodes
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    ajustes = {"LAYA_MODO": "shadow", "LAYA_LOG_DECISIONES": "0",
               "LAYA_LOG_ARCHIVO": str(archivo)}
    monkeypatch.setattr(
        call_llm, "_setting", lambda nombre, default=None: ajustes.get(nombre, default)
    )
    # nodes.py importó _setting a nivel de módulo: el gate del pendiente lee
    # ESA referencia, así que el apagado se monkeypatchea también ahí.
    monkeypatch.setattr(
        nodes, "_setting", lambda nombre, default=None: ajustes.get(nombre, default)
    )
    shared = {}
    router = nodes.LayaRouter()
    respuesta = {"choice": "directo",
                 "probabilities": {"directo": 0.9, "herramientas": 0.1}}
    assert router.post(shared, {"pregunta": "q"}, respuesta) == "herramientas"
    assert "_router_pendiente" not in shared
    assert not archivo.exists()


def test_enforce_y_shadow_sin_probabilidades_no_dejan_pendiente(tmp_path, monkeypatch):
    """Enforce no etiqueta (mediría la política); sin p_directo no hay par
    (p, etiqueta) calibrable. El archivo va a tmp: este test posteaba la
    decisión en el routing log REAL (exp/71)."""
    import nodes
    from utils import call_llm

    ajustes = {
        "LAYA_MODO": "enforce",
        "LAYA_LOG_ARCHIVO": str(tmp_path / "routing.jsonl"),
    }
    monkeypatch.setattr(
        call_llm, "_setting", lambda nombre, default=None: ajustes.get(nombre, default)
    )
    shared = {}
    router = nodes.LayaRouter()
    router.post(shared, {"pregunta": "q"}, {"choice": "directo",
                                            "probabilities": {"directo": 0.9,
                                                              "herramientas": 0.1}})
    assert "_router_pendiente" not in shared

    # shadow pero respuesta inválida (p_directo None)
    ajustes["LAYA_MODO"] = "shadow"
    shared = {}
    assert router.post(shared, {"pregunta": "q"}, {}) == "herramientas"
    assert "_router_pendiente" not in shared


def test_agentstep_answer_consume_el_pendiente(tmp_path, monkeypatch):
    """Al responder se registra el resultado con las rondas de la pregunta:
    0 → directo; N → herramientas. El pop limpia el pendiente."""
    from types import SimpleNamespace

    import nodes
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    monkeypatch.setattr(
        call_llm, "_setting",
        lambda nombre, default=None: str(archivo) if nombre == "LAYA_LOG_ARCHIVO" else default,
    )
    paso = nodes.AgentStep()
    respuesta = SimpleNamespace(content="listo", tool_calls=None)

    shared = {"messages": [], "tool_rounds": 0, "_router_pendiente": "id0"}
    assert paso.post(shared, None, respuesta) == "answer"
    linea = json.loads(archivo.read_text(encoding="utf-8").strip())
    assert linea["id"] == "id0" and linea["uso_tools"] is False
    assert "_router_pendiente" not in shared

    shared = {"messages": [], "tool_rounds": 3, "_router_pendiente": "id3"}
    paso.post(shared, None, respuesta)
    ult = json.loads(archivo.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert ult["id"] == "id3" and ult["uso_tools"] is True and ult["rondas"] == 3


def test_agentstep_con_tool_calls_no_consume_el_pendiente(tmp_path, monkeypatch):
    """Con tool_calls (acción "tool") el pendiente SOBREVIVE y no hay línea:
    la etiqueta espera a que el ciclo de la pregunta cierre."""
    from types import SimpleNamespace

    import nodes
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    monkeypatch.setattr(
        call_llm, "_setting",
        lambda nombre, default=None: str(archivo) if nombre == "LAYA_LOG_ARCHIVO" else default,
    )
    paso = nodes.AgentStep()
    respuesta = SimpleNamespace(
        content=None,
        tool_calls=[SimpleNamespace(id="x", function=SimpleNamespace(name="read_file", arguments="{}"))],
    )
    shared = {"messages": [], "tool_rounds": 1, "_router_pendiente": "idX"}
    assert paso.post(shared, None, respuesta) == "tool"
    assert shared["_router_pendiente"] == "idX"
    assert not archivo.exists()


def test_getquestion_limpia_un_pendiente_huerfano(monkeypatch):
    """Una pregunta nueva empieza limpia: un ciclo abortado no etiqueta la
    siguiente."""
    import nodes

    monkeypatch.setattr(nodes, "registrar_pregunta", lambda *a, **k: None)
    shared = {"messages": [], "tool_rounds": 5, "_router_pendiente": "viejo"}
    nodes.GetQuestion().post(shared, None, "otra pregunta")
    assert "_router_pendiente" not in shared
    assert shared["tool_rounds"] == 0


def _decision(id_, propuesta, p_directo, ts=1.0, pregunta=None):
    linea = {"ts": ts, "id": id_, "propuesta": propuesta, "p_directo": p_directo}
    if pregunta is not None:
        linea["pregunta"] = pregunta
    return linea


def _resultado(id_, uso_tools):
    return {"ts": 2.0, "evento": "resultado", "id": id_,
            "uso_tools": uso_tools, "rondas": 1 if uso_tools else 0}


def test_unir_tabla_de_verdad():
    """Los cuatro casos propuesta × uso_tools: conf es de la opción ELEGIDA y
    `correcto` = propuesta == etiqueta."""
    from banco.probes.etiquetar_ambiental import unir

    lineas = [
        _decision("a", "directo", 0.9),
        _resultado("a", False),                 # directo/directo → correcto
        _decision("b", "directo", 0.9),
        _resultado("b", True),                  # directo/herramientas → falla
        _decision("c", "herramientas", 0.2),
        _resultado("c", False),                 # herramientas/directo → falla
        _decision("d", "herramientas", 0.2),
        _resultado("d", True),                  # herramientas/herramientas → correcto
    ]
    filas = unir(lineas)
    assert [f["laya"] for f in filas] == ["directo", "directo", "herramientas", "herramientas"]
    assert [f["etiqueta"] for f in filas] == ["directo", "herramientas", "directo", "herramientas"]
    assert [f["correcto"] for f in filas] == [True, False, False, True]
    # conf = confianza de la opción elegida
    assert filas[0]["conf"] == pytest.approx(0.9)     # p_directo
    assert filas[2]["conf"] == pytest.approx(0.8)     # 1 - p_directo

    # la pregunta solo viaja si estaba logueada
    with_preg = unir([_decision("a", "directo", 0.9, pregunta="¿hola?"), _resultado("a", False)])
    assert with_preg[0]["pregunta"] == "¿hola?"
    assert "pregunta" not in filas[0]


def test_unir_salteos_y_huerfanos():
    """Sin resultado (ciclo abortado) o sin p_directo (respuesta inválida) se
    saltan; un resultado huérfano se ignora; el orden sigue el de las
    decisiones."""
    from banco.probes.etiquetar_ambiental import unir

    lineas = [
        _decision("abierta", "directo", 0.9),            # sin resultado → salta
        _decision("sinp", "directo", None),
        _resultado("sinp", False),                       # su resultado queda huérfano
        _resultado("fantasma", True),                    # huérfano: sin decisión
        _decision("ok", "herramientas", 0.1),
        _resultado("ok", True),
    ]
    filas = unir(lineas)
    assert len(filas) == 1
    assert filas[0]["laya"] == "herramientas" and filas[0]["correcto"] is True
    assert filas[0]["fuente"] == "etiqueta ambiental exp/43"


# exp/46 — la regla temporal (recencia no la juzga Laya: regla dura antes
# del modelo; en shadow Laya corre igual para no cegar la flywheel)

def test_regla_temporal_pura():
    from utils.laya_routing import regla_temporal

    assert regla_temporal("¿Quién ganó el último mundial?")
    assert regla_temporal("cual es el ultimo partido")  # sin tilde
    assert regla_temporal("¿Qué versión de pytest hay en 2026?")
    assert regla_temporal("noticias de hoy")
    assert regla_temporal("the latest release?")
    assert not regla_temporal("¿Por qué el cielo es azul?")
    assert not regla_temporal("¿Cuál es la capital de Francia?")
    assert not regla_temporal("")
    assert not regla_temporal(None)


@pytest.fixture
def _laya_que_diria_directo(monkeypatch):
    """Un falso de utils.laya que SIEMPRE propondría directo 0.99 y cuenta
    cuántas veces se lo consultó (el contador clava la regla dura)."""
    import nodes
    from utils import laya

    llamadas = {"n": 0}

    def falso_detalle(estado, preguntas, setting="LAYA_MODEL"):
        llamadas["n"] += 1
        return {"necesita_herramientas": {
            "choice": "directo",
            "probabilities": {"directo": 0.99, "herramientas": 0.01},
        }}

    monkeypatch.setattr(laya, "disponible", lambda *a, **k: True)
    monkeypatch.setattr(laya, "preguntar_detalle", falso_detalle)
    monkeypatch.setattr(nodes, "voto_confirmacion_router", lambda p: "directo")
    return llamadas


def test_enforce_regla_temporal_no_consulta_a_laya(tmp_path, monkeypatch, _laya_que_diria_directo):
    """El caso mundial: Laya diría directo 0.99 (su punto ciego histórico) y
    la regla dura lo manda a herramientas SIN llamarla — la decisión queda
    registrada con la causa de la regla."""
    import json

    import nodes
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    ajustes = {"LAYA_MODO": "enforce", "LAYA_LOG_ARCHIVO": str(archivo)}
    monkeypatch.setattr(
        call_llm, "_setting", lambda nombre, default=None: ajustes.get(nombre, default)
    )
    router = nodes.LayaRouter()
    estado = {"pregunta": "¿Quién ganó el último mundial?"}
    res = router.exec(estado)
    assert res == "regla:temporal"
    assert _laya_que_diria_directo["n"] == 0
    shared = {}
    assert router.post(shared, estado, res) == "herramientas"
    linea = json.loads(archivo.read_text(encoding="utf-8").strip())
    assert "regla temporal" in linea["causa"]
    assert linea["propuesta"] == "herramientas" and linea["p_directo"] is None


def test_shadow_regla_temporal_sigue_consultando(tmp_path, monkeypatch, _laya_que_diria_directo):
    """En shadow la regla NO ciega la flywheel: Laya corre igual (el par
    (p, etiqueta) de esta clase es justamente el que valida la regla)."""
    import json

    import nodes
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    ajustes = {"LAYA_MODO": "shadow", "LAYA_LOG_ARCHIVO": str(archivo)}
    monkeypatch.setattr(
        call_llm, "_setting", lambda nombre, default=None: ajustes.get(nombre, default)
    )
    router = nodes.LayaRouter()
    estado = {"pregunta": "¿Quién ganó el último mundial?"}
    res = router.exec(estado)
    assert res != "regla:temporal" and _laya_que_diria_directo["n"] == 1
    shared = {}
    assert router.post(shared, estado, res) == "herramientas"  # shadow conserva
    linea = json.loads(archivo.read_text(encoding="utf-8").strip())
    assert linea["propuesta"] == "directo" and linea["p_directo"] == 0.99


def test_sin_recencia_flujo_de_siempre(tmp_path, monkeypatch, _laya_que_diria_directo):
    """Una pregunta de conocimiento estable en enforce: la regla no dispara y
    decide() aplica (con 0.99 y umbral default 0.85, la propuesta directo
    pasa la compuerta y el voto falso la confirma → ruta directo)."""
    import nodes
    from utils import call_llm

    ajustes = {"LAYA_MODO": "enforce", "LAYA_LOG_ARCHIVO": str(tmp_path / "r.jsonl")}
    monkeypatch.setattr(
        call_llm, "_setting", lambda nombre, default=None: ajustes.get(nombre, default)
    )
    router = nodes.LayaRouter()
    estado = {"pregunta": "¿Por qué el cielo es azul?"}
    res = router.exec(estado)
    assert res != "regla:temporal" and _laya_que_diria_directo["n"] == 1
    assert router.post({}, estado, res) == "directo"


def test_regla_imperativo_capacidad_pura():
    """exp/54: órdenes de capacidad → herramientas; creativos y conocimiento
    quedan directo (no romper la trampa inversa del router)."""
    from utils.laya_routing import regla_imperativo_capacidad

    for pregunta in (
        "debatí en 2 rondas sobre si conviene migrar el chat a web.",
        "investigá en la web cuál es la capital de Australia.",
        "buscá en el repo dónde se define MAX_TOOL_ROUNDS.",
        "leé README.md y decime cuántas secciones tiene.",
        "corré la suite de tests y decime cuántos pasan.",
        "editá utils/formato.py para que pct devuelva dos decimales.",
        "usá el servidor MCP matemática y sumá 2+2.",
        "mostrame el contenido de docs/roadmap.md.",
        "generá un informe breve de las métricas del repo.",
    ):
        assert regla_imperativo_capacidad(pregunta), pregunta
    for pregunta in (
        "escribime un haiku sobre el mar.",
        "generá un poema épico sobre el invierno.",
        "¿qué es un closure en Python?",
        "explicá brevemente la diferencia entre lista y tupla.",
        "resumí en una frase qué es un LLM.",
        "contame un cuento.",
        "¿qué significa REST en el contexto de APIs?",
    ):
        assert not regla_imperativo_capacidad(pregunta), pregunta


def test_enforce_regla_imperativo_no_consulta_a_laya(tmp_path, monkeypatch, _laya_que_diria_directo):
    """El hueco del bench del voto (c01): Laya diría directo, la regla dura de
    capacidad manda a herramientas SIN llamarla y lo deja registrado."""
    import json

    import nodes
    from utils import call_llm

    archivo = tmp_path / "routing.jsonl"
    ajustes = {"LAYA_MODO": "enforce", "LAYA_LOG_ARCHIVO": str(archivo)}
    monkeypatch.setattr(
        call_llm, "_setting", lambda nombre, default=None: ajustes.get(nombre, default)
    )
    router = nodes.LayaRouter()
    estado = {"pregunta": "debatí en 2 rondas sobre si migrar el chat a web"}
    res = router.exec(estado)
    assert res == "regla:imperativo"
    assert _laya_que_diria_directo["n"] == 0
    assert router.post({}, estado, res) == "herramientas"
    linea = json.loads(archivo.read_text(encoding="utf-8").strip())
    assert "regla imperativo" in linea["causa"]
    assert linea["propuesta"] == "herramientas" and linea["p_directo"] is None
