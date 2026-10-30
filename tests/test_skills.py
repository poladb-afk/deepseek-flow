"""exp/55 — skills declarativas (Mesa 7): loader, disparo y cableado.

Clavan el contrato mínimo: YAML válido → skill cargado; condición regex →
disparo determinístico; el nodo Skills (X106) lo activa a la entrada, inyecta el
prompt (prefijo `[skill]`) y el loop recorta la lista de tools al subset. Un
YAML roto se saltea; un skill nunca expande el action space.
"""

from modules import memoria
from utils.skills import (
    PREFIJO_SKILL,
    Skill,
    cargar_skills,
    filtrar_tools,
    mensaje,
    skill_para,
)


def test_skills_del_repo_cargan_y_disparan():
    habilidades = cargar_skills()
    ids = {habilidad.id for habilidad in habilidades}
    assert {"revision", "tdd"} <= ids
    revision = next(h for h in habilidades if h.id == "revision")
    assert revision.tools and "read_file" in revision.tools
    assert skill_para("Revisá el código de utils/formato.py.", habilidades) is revision
    assert skill_para("implementá esto con TDD", habilidades).id == "tdd"
    for control in ("escribime un haiku sobre el mar", "¿qué es un closure en Python?",
                    "corré la suite de tests"):
        assert skill_para(control, habilidades) is None


def test_skill_roto_se_saltea_sin_tumbar_el_resto(tmp_path):
    (tmp_path / "ok.yaml").write_text(
        "id: ok\ndescripcion: prueba\ncondicion: 'hola'\ninstrucciones: hacé algo\n",
        encoding="utf-8")
    (tmp_path / "sin_campos.yaml").write_text("id: roto\n", encoding="utf-8")
    (tmp_path / "regex_roto.yaml").write_text(
        "id: x\ndescripcion: d\ncondicion: '('\ninstrucciones: i\n", encoding="utf-8")
    habilidades = cargar_skills(tmp_path)
    assert [habilidad.id for habilidad in habilidades] == ["ok"]


def test_mensaje_lleva_prefijo_estable_y_descripcion():
    skill = Skill(id="x", descripcion="una skill", condicion=None, instrucciones="reglas")
    texto = mensaje(skill)
    assert texto.startswith(f"{PREFIJO_SKILL} x — una skill")
    assert texto.endswith("reglas")


def test_filtrar_tools_es_subset_y_nunca_expande():
    tools = [
        {"function": {"name": "read_file"}},
        {"function": {"name": "run_command"}},
        {"function": {"name": "web_search"}},
    ]
    skill = Skill(id="x", descripcion="d", condicion=None, instrucciones="i",
                  tools=("read_file", "no_existe"))
    elegidas = filtrar_tools(tools, skill)
    assert [tool["function"]["name"] for tool in elegidas] == ["read_file"]


def test_agent_step_anuncia_solo_el_subset_del_skill():
    import nodes
    from utils.skills import disponibles

    revision = next(h for h in disponibles() if h.id == "revision")
    shared = {"messages": [{"role": "user", "content": "revisá el código"}],
              "turno": {**nodes.nuevo_turno(), "skill": revision.id}}
    _, tools = nodes.AgentStep().prep(shared)
    assert {tool["function"]["name"] for tool in tools} == set(revision.tools)
    _, todos = nodes.AgentStep().prep({"messages": [{"role": "user", "content": "hola"}]})
    assert {tool["function"]["name"] for tool in todos} == {
        tool["function"]["name"] for tool in nodes.TOOLS}


def test_preguntas_reales_no_cuentan_el_mensaje_de_skill():

    mensajes = [
        {"role": "user", "content": "¿qué es un closure?"},
        {"role": "user", "content": f"{PREFIJO_SKILL} revision — reglas"},
        {"role": "assistant", "content": "…"},
    ]
    assert memoria.preguntas_reales(mensajes) == 1


def test_el_nodo_skills_activa_el_skill_una_vez(monkeypatch):
    """X106: el skill se activa a la entrada de la pregunta (antes, dentro del
    router y solo en enforce). La pregunta en curso sigue siendo la del usuario."""
    import nodes

    monkeypatch.setenv("SKILLS", "1")
    pregunta = "Revisá el código de utils/formato.py y decime si hay problemas."
    shared = {"messages": [{"role": "user", "content": pregunta}]}
    assert nodes.Skills()._run(shared) == "continue"
    assert shared["turno"]["skill"] == "revision"  # el ID: el shared es JSON (F4)
    assert shared["messages"][-1]["content"].startswith(PREFIJO_SKILL)
    assert nodes.pregunta_en_curso(shared["messages"]) == pregunta


def test_el_nodo_skills_apagado_o_sin_disparo_no_toca_nada(monkeypatch):
    import nodes

    for valor, pregunta in (("0", "Revisá el código de utils/formato.py y decime si hay problemas."),
                            ("1", "escribime un haiku sobre el mar.")):
        monkeypatch.setenv("SKILLS", valor)
        shared = {"messages": [{"role": "user", "content": pregunta}]}
        assert nodes.Skills()._run(shared) == "continue"
        assert shared.get("turno", {}).get("skill") is None and len(shared["messages"]) == 1
