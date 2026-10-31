"""Skills por descripción (fase 5b, X111): el modelo los carga con `usar_skill`.

Hasta X110 una regex del YAML decidía y el loop recortaba las tools; con otro
idioma o redacción no se activaba (1 de 4 positivos, `test_fase5b.py`). Acá:
el catálogo carga, la tool devuelve las instrucciones y anuncia el marcador
del banco, un YAML roto se saltea, y el chat ya no tiene nodo ni recorte.
"""
import hashlib

from modules import skills as mod


def test_los_skills_del_repo_cargan_sin_condicion_ni_tools():
    ids = [s.id for s in mod.cargar()]
    assert ids == ["auditoria-seguridad", "metodo-fable", "revision", "tdd"]
    for ruta in sorted(mod.DIR_SKILLS.glob("*.yaml")):
        texto = ruta.read_text(encoding="utf-8")
        assert "condicion:" not in texto and "\ntools:" not in texto, ruta.name


def test_las_directivas_pasaron_a_skills_con_el_texto_intacto():
    """El texto de DIRECTIVA_AUDITORIA (exp/78) y DIRECTIVA_FABLE (exp/72) es
    el mismo byte a byte: el A/B compara el mecanismo, no una redacción nueva."""
    sha = {s.id: hashlib.sha1(s.instrucciones.encode()).hexdigest() for s in mod.cargar()}
    assert sha["auditoria-seguridad"] == "a6efc0a5410617537e4b97953950951fded8d759"
    assert sha["metodo-fable"] == "edaad0d1823609163ed0c672eaef328b3b9b0779"


def test_el_catalogo_va_en_la_descripcion_de_la_tool():
    funcion = mod.TOOLS[0]["function"]
    assert funcion["name"] == "usar_skill"
    for s in mod.cargar():
        assert f"- {s.id}: {s.descripcion}" in funcion["description"]
    assert funcion["parameters"]["properties"]["skill"]["enum"] == [s.id for s in mod.cargar()]


def test_usar_skill_devuelve_las_instrucciones_y_anuncia_el_marcador(capsys):
    import re

    from banco.banco import MARCADORES

    texto = mod.usar_skill("revision")
    assert texto == mod.SKILLS["revision"].instrucciones
    assert re.search(MARCADORES["skill"], capsys.readouterr().out)
    assert mod.usar_skill("no-existe").startswith("ERROR: no hay un skill 'no-existe'")


def test_un_yaml_roto_se_saltea_sin_tumbar_el_resto(tmp_path):
    (tmp_path / "a.yaml").write_text("id: ok\ndescripcion: prueba\ninstrucciones: hacé algo\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("id: roto\n", encoding="utf-8")
    (tmp_path / "c.yaml").write_text("- no es un mapa\n", encoding="utf-8")
    assert [s.id for s in mod.cargar(tmp_path)] == ["ok"]
    assert mod.esquema([])["function"]["parameters"]["properties"]["skill"]["enum"] == []


def test_el_chat_no_tiene_nodo_de_skills_ni_recorta_tools():
    import nodes
    from flow import create_agent_flow

    assert not hasattr(nodes, "Skills")
    assert type(create_agent_flow().start_node.successors["continue"].successors["continue"]).__name__ == "Contexto"
    _, tools = nodes.AgentStep().prep({"messages": [{"role": "user", "content": "revisá el código"}]})
    assert tools is nodes.TOOLS
    assert "usar_skill" in {t["function"]["name"] for t in nodes.TOOLS}
