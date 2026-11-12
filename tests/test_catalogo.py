"""X198: el catálogo — el primer request lleva cinco tools y `usar` despacha.

El chat manda el CORE + `catalogo` + `usar`; las capacidades de los módulos ya
no viajan en el prompt y se alcanzan por el catálogo. `usar` corre por
`run_tool_call`, así que la política y los hooks PRE frenan una capacidad
igual que en el chat (la lección X197b).
"""
import json

from utils.catalogo import catalogo_de
from utils.fs_tools import HOOKS_PRE, run_tool_call


def _llamada(tool, **argumentos):
    return {"function": {"name": tool, "arguments": json.dumps(argumentos)}}


def _capacidad(nombre, descripcion="hace algo", requerido="texto"):
    return {"type": "function", "function": {
        "name": nombre, "description": descripcion,
        "parameters": {"type": "object", "required": [requerido],
                       "properties": {requerido: {"type": "string"}}}}}


def test_las_tools_del_chat_son_cinco_el_core_mas_el_catalogo():
    import nodes

    nombres = [t.nombre for t in nodes.herramientas_de({"turno": {}})]
    assert nombres == ["list_files", "read_file", "search_files", "catalogo", "usar"]
    assert not set(nombres) & {t["function"]["name"] for t in nodes.MODULE_TOOLS}
    assert nodes.TOOLS == nodes.CORE_TOOLS + nodes.MODULE_TOOLS  # inventario completo


def test_el_catalogo_lista_las_capacidades_con_sus_parametros():
    tools = [_capacidad("eco"), _capacidad("sumar", "suma dos números", "a")]
    _, impls = catalogo_de(tools, {"eco": lambda texto: texto, "sumar": lambda a: a})
    manifiesto = json.loads(run_tool_call(_llamada("catalogo"), impls)["content"])
    assert [c["nombre"] for c in manifiesto["capacidades"]] == ["eco", "sumar"]
    assert manifiesto["capacidades"][1]["parametros"]["required"] == ["a"]
    assert "suma dos números" in manifiesto["capacidades"][1]["descripcion"]


def test_usar_despacha_por_run_tool_call_y_un_veto_pre_lo_corta(monkeypatch):
    corridas = []
    _, impls = catalogo_de([_capacidad("eco")],
                           {"eco": lambda texto: corridas.append(texto) or texto})
    assert run_tool_call(_llamada("usar", nombre="eco", argumentos={"texto": "hola"}),
                         impls)["content"] == "hola"
    assert corridas == ["hola"]
    # X197b: el veto PRE de la capacidad frena el `usar` (el despacho único).
    monkeypatch.setitem(HOOKS_PRE, "eco", [lambda _tc: "ERROR: vetado por la política"])
    assert "vetado" in run_tool_call(_llamada("usar", nombre="eco",
                                              argumentos={"texto": "otra"}), impls)["content"]
    assert corridas == ["hola"]  # la segunda no se ejecutó


def test_usar_una_capacidad_que_no_esta_falla_cerrada():
    _, impls = catalogo_de([], {})
    assert run_tool_call(_llamada("usar", nombre="read_file", argumentos={}),
                         impls)["content"].startswith("ERROR")
    assert "desconocida" in run_tool_call(_llamada("usar", nombre="deep_research",
                                                   argumentos={}), impls)["content"]


def test_usar_acepta_los_argumentos_como_json():
    _, impls = catalogo_de([_capacidad("eco")], {"eco": lambda texto: texto})
    assert run_tool_call(_llamada("usar", nombre="eco",
                                  argumentos='{"texto": "hola"}'), impls)["content"] == "hola"


def test_usar_con_argumentos_que_no_son_json_falla_cerrada():
    _, impls = catalogo_de([_capacidad("eco")], {"eco": lambda texto: texto})
    assert "no son JSON" in run_tool_call(_llamada("usar", nombre="eco",
                                                   argumentos="{no json"), impls)["content"]


def test_despachar_mezcla_el_catalogo_con_las_capacidades():
    from utils import catalogo

    tools, impls = [_capacidad("eco")], {"eco": lambda texto: texto}
    assert catalogo.despachar(_llamada("usar", nombre="eco",
                                       argumentos={"texto": "hola"}), tools, impls)["content"] == "hola"
    assert "capacidades" in catalogo.despachar(_llamada("catalogo"), tools, impls)["content"]
