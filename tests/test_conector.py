"""El template del módulo (X194): el contrato del conector y los 5 tipos.

No prueba la conducta de ningún módulo (X194 no migra ninguno): prueba el
contrato. Una composición válida arma y corre; una que no encaja no arranca
ni gasta una llamada; el conector no acepta política, validador ni allowlist;
hay una sola arista (tool o hijo por el flag `agente`) y una sola descripción,
la del esquema de la tool que lee el módulo de arriba.
"""
import json
from dataclasses import fields
from types import SimpleNamespace as NS

import pytest

from utils.conector import TIPOS, Artefacto, Conector, componer
from utils.kernel import Ctx, Ledger, Tool, agente, correr

CITA = "utils/kernel.py:1"  # existe: el verificador mira la línea, no el texto


def tool(nombre, descripcion="hace algo"):
    esquema = {"type": "function", "function": {
        "name": nombre, "description": descripcion, "parameters": {"type": "object"}}}
    return Tool(nombre, esquema, lambda llamada, ctx: "ok", "lectura")


def test_una_composicion_valida_arranca():
    plan = Conector(tool("planificador"), "plan", ("pregunta",))
    buscar = Conector(tool("investigador"), "hallazgos", ("plan",))
    juzgar = Conector(tool("juez"), "veredicto", ("hallazgos",))
    tools = componer(plan, buscar, juzgar)
    assert tools == (plan.tool, buscar.tool, juzgar.tool)

    llamadas = []

    def llm(mensajes, disponibles=None):
        llamadas.append(disponibles)
        return NS(content="listo", tool_calls=None)

    respuesta, _ = correr("sistema", "pedido", list(tools), Ctx(llm, Ledger(2)), wait=0)
    assert respuesta == "listo"
    assert len(llamadas) == 1


def test_una_composicion_que_no_encaja_no_arranca():
    """El `ValueError` es estructural: sale de `componer()`, antes de armar el
    loop y sin un LLM en el camino."""
    plan = Conector(tool("planificador"), "plan", ("pregunta",))
    juzgar = Conector(tool("juez"), "veredicto", ("hallazgos",))
    with pytest.raises(ValueError, match="no encaja"):
        componer(plan, juzgar)


def test_la_composicion_arranca_en_pregunta():
    with pytest.raises(ValueError, match="composición vacía"):
        componer()
    with pytest.raises(ValueError, match="arranca"):
        componer(Conector(tool("planificador"), "plan"))


def test_el_conector_no_acepta_politica_validador_ni_allowlist():
    assert {campo.name for campo in fields(Conector)} == {"tool", "produce", "consume"}
    for freno in ("politica", "validador", "allowlist"):
        with pytest.raises(TypeError):
            Conector(tool("x"), "plan", ("pregunta",), **{freno: object()})


def test_una_sola_arista_tool_o_hijo_por_el_flag_agente():
    sub = agente("sub", "hace algo", "sistema", [])
    simple = Conector(tool("leer"), "hallazgos", ("pregunta",))
    copia = Conector(sub, "veredicto", ("hallazgos",))
    assert (simple.tool.agente, copia.tool.agente) == (False, True)
    assert type(simple) is type(copia) is Conector  # una sola forma de conectar
    assert [t.agente for t in componer(simple, copia)] == [False, True]


def test_una_sola_descripcion_la_lee_el_de_arriba():
    conector = Conector(tool("planificar", "parte el pedido en pasos"), "plan", ("pregunta",))
    assert conector.tool.esquema["function"]["description"] == "parte el pedido en pasos"
    assert "descripcion" not in {campo.name for campo in fields(conector)}
    with pytest.raises(ValueError, match="sin descripción"):
        Conector(tool("mudo", "  "), "plan", ("pregunta",))


def test_el_artefacto_lleva_la_procedencia_y_las_citas():
    investigador = Conector(tool("investigador"), "hallazgos", ("pregunta",))
    juez = Conector(tool("juez"), "veredicto", ("hallazgos",))
    artefacto = investigador.producir("encontré X", (CITA,))
    assert (artefacto.procedencia, artefacto.citas) == ("investigador", (CITA,))
    assert juez.consumir(artefacto) == "encontré X"
    with pytest.raises(ValueError, match="no consume"):
        juez.consumir(Artefacto("plan", "un plan", "planificador"))


def test_hallazgos_sin_citas_no_se_arman():
    with pytest.raises(ValueError, match="sin citas"):
        Artefacto("hallazgos", "dato", "research")
    with pytest.raises(ValueError, match="no verifican"):
        Artefacto("hallazgos", "dato", "research", ("utils/kernel.py:999999",))
    with pytest.raises(ValueError, match="no verifican"):
        Artefacto("hallazgos", "dato", "research", ("sin_formato",))


def test_un_tipo_fuera_de_los_cinco_no_existe():
    assert TIPOS == ("pregunta", "plan", "hallazgos", "veredicto", "borrador")
    with pytest.raises(ValueError, match="desconocido"):
        Artefacto("hecho", "dato", "research")
    with pytest.raises(ValueError, match="desconocido"):
        Conector(tool("x"), "hecho", ("pregunta",))
    with pytest.raises(ValueError, match="no existen"):
        Conector(tool("x"), "plan", ("hecho",))


def test_un_artefacto_sin_procedencia_no_se_puede_auditar():
    with pytest.raises(ValueError, match="procedencia"):
        Artefacto("plan", "un plan", "  ")


def test_el_registro_valida_los_conectores_al_armar(monkeypatch, capsys):
    """El template se aplica al armar: un módulo con `CONECTORES` válidos carga;
    uno que declara otra cosa se saltea entero, como un módulo que no importa."""
    import modules

    valido = NS(name="valido", TOOLS=[tool("leido").esquema],
                IMPL={"leido": lambda **_: "ok"},
                CONECTORES=(Conector(tool("leido"), "hallazgos", ("pregunta",)),))
    roto = NS(name="roto", TOOLS=[tool("roto").esquema], IMPL={"roto": lambda **_: "ok"},
              CONECTORES=("no soy un conector",))
    ajena = NS(name="ajena", TOOLS=[tool("otra").esquema], IMPL={"otra": lambda **_: "ok"},
               CONECTORES=(Conector(tool("no_esta"), "veredicto", ("pregunta",)),))
    monkeypatch.setattr(modules, "pkgutil", NS(iter_modules=lambda _: [roto, ajena, valido]))
    monkeypatch.setattr(modules, "importlib", NS(
        import_module=lambda nombre: {"roto": roto, "ajena": ajena}.get(nombre.rsplit(".", 1)[-1], valido)))

    tools, impls = modules.discover()
    assert set(impls) == {"leido"}
    assert [t["function"]["name"] for t in tools] == ["leido"]
    err = capsys.readouterr().err
    assert "roto declara conectores" in err
    assert "ajena declara un conector de una tool ajena" in err


def test_el_conector_de_fable_produce_veredicto(monkeypatch):
    """X195: fable declara su arista; la tool del conector es la del módulo y
    corre por el despacho único (`run_tool_call`)."""
    from modules import fable

    conector, = fable.CONECTORES
    assert (conector.tool.nombre, conector.produce, conector.consume) == (
        "verificar_trabajo", "veredicto", ("pregunta",))
    monkeypatch.setattr(fable, "IMPL", {"verificar_trabajo": lambda **_: "juicio"})
    llamada = {"function": {"name": "verificar_trabajo",
                            "arguments": json.dumps({"trabajo": "t", "reporte": "r"})}}
    assert conector.tool.correr(llamada, None) == "juicio"
