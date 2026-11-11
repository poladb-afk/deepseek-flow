"""X197: la composición research + council, declarada y validada al armar.

La cadena es `pregunta → research (borrador) → puente (pregunta) → council
(veredicto)`. El puente es el adaptador entre tipos: la arista de `debate`
que fijó X196 (`consume=("pregunta",)`) no se mueve y `componer(research,
debate)` no arma. El runner corre la composición con el cliente del LLM
falseado (sin red) y cobra todas las llamadas al mismo `Ledger`.
"""
import json

import pytest
from test_gate_fractal import _cliente_falso

from utils.composicion import cadena_de, correr_composicion
from utils.conector import componer


def test_la_composicion_valida_al_armar_y_la_arista_de_debate_no_se_mueve():
    cadena = cadena_de("research_council")
    assert [c.tool.nombre for c in cadena] == [
        "deep_research", "puente_research_council", "debate"]
    assert [(c.produce, c.consume) for c in cadena] == [
        ("borrador", ("pregunta",)), ("pregunta", ("borrador",)), ("veredicto", ("pregunta",))]
    assert componer(*cadena) == tuple(c.tool for c in cadena)
    with pytest.raises(ValueError, match="no encaja"):
        componer(cadena[0], cadena[2])  # research + debate SIN el puente: no arma
    with pytest.raises(ValueError, match="arranca"):
        componer(cadena[1], cadena[0])  # el puente no arranca una composición
    with pytest.raises(ValueError, match="desconocida"):
        cadena_de("no_existe")


def test_el_conector_de_research_devuelve_el_informe_y_el_chat_la_ruta(monkeypatch, tmp_path):
    """D6=A: el artefacto de la composición es el INFORME; el `IMPL` del chat
    sigue devolviendo la ruta (no inunda su contexto)."""
    from modules import research as modulo

    informe = tmp_path / "informe.md"
    informe.write_text("# informe\ncon fuentes\n", encoding="utf-8")
    monkeypatch.setattr(modulo, "investigar", lambda tema, salida=None: str(informe))

    conector, = modulo.CONECTORES
    llamada = {"function": {"name": "deep_research", "arguments": json.dumps({"tema": "t"})}}
    assert conector.tool.correr(llamada, None) == "# informe\ncon fuentes\n"
    assert modulo.deep_research("t").startswith("Informe de investigación escrito: ")


def _respuesta(kwargs):
    from types import SimpleNamespace as NS

    prompt = kwargs["messages"][-1]["content"]
    if "consultas de búsqueda" in prompt:
        texto = "queries: [a, b, c]\ncontent: ''\n"
    elif prompt.startswith("Extrae"):
        texto = "- un hecho (https://ejemplo.org)"
    elif "¿El material alcanza" in prompt:
        texto = "action: finalize\ncontent: '# Informe sobre el tema\ncon fuentes'\n"
    elif "Eres el PROPONENTE" in prompt:
        texto = "El proponente sostiene la tesis con evidencia."
    elif "Eres el CRÍTICO" in prompt:
        texto = "El crítico señala el supuesto que falta."
    else:
        texto = "```yaml\nganador: proponente\nsintesis: |\n  Gana por evidencia.\n```"
    return NS(content=texto, tool_calls=None)


def test_la_composicion_corre_y_cobra_un_solo_saldo(monkeypatch, tmp_path):
    import research

    monkeypatch.setattr(research, "search_web", lambda q, k=4: f"- {q}: https://ejemplo.org")

    def escribir(_ruta, contenido):
        destino = tmp_path / "informe.md"
        destino.write_text(contenido, encoding="utf-8")
        return destino, None

    monkeypatch.setattr(research, "escribir_salida", escribir)
    creados = _cliente_falso(monkeypatch, _respuesta)
    artefacto, llamadas = correr_composicion("research_council", "¿la IA debe regularse?")

    assert artefacto.tipo == "veredicto"
    assert "Gana por evidencia" in artefacto.contenido
    # 5 de research (plan + 3 extracciones + síntesis) + 5 del council (2 rondas + juez)
    assert llamadas == 10 == len(creados)
    # Criterio 2 / D8=A: el council arranca con la moción del puente (el
    # informe), no con el tema del usuario; sin esta aserción, pasarle el tema
    # al council pasaría el test igual (los dos artefactos son `pregunta`).
    proponentes = [c["messages"][-1]["content"] for c in creados
                   if "Eres el PROPONENTE" in c["messages"][-1]["content"]]
    assert proponentes
    for prompt in proponentes:
        assert "Debatí si la evidencia" in prompt
        assert "# Informe sobre el tema" in prompt
        assert "¿la IA debe regularse?" not in prompt


def test_la_cli_imprime_el_veredicto_y_las_llamadas(capsys, monkeypatch):
    from utils import composicion

    monkeypatch.setattr(composicion, "correr_composicion",
                        lambda nombre, tema: (composicion.Artefacto("veredicto", "listo", nombre), 3))
    composicion.main(["research_council", "tema"])
    salida = capsys.readouterr().out
    assert "listo" in salida and "3 llamadas del árbol" in salida

    def falla(_nombre, _tema):
        raise ValueError("sin conectores")

    monkeypatch.setattr(composicion, "correr_composicion", falla)
    with pytest.raises(SystemExit, match="ERROR: sin conectores"):
        composicion.main(["research_council", "tema"])


def test_una_composicion_con_un_conector_que_falta_no_arranca(monkeypatch):
    from utils import composicion

    monkeypatch.setitem(composicion.COMPOSICIONES, "falta", ("no_existe",))
    with pytest.raises(ValueError, match="no está"):
        composicion.cadena_de("falta")


def test_un_error_de_una_pieza_corta_la_composicion(monkeypatch):
    """Una tool que falla no fabrica un artefacto: el runner corta con ERROR."""
    from modules import research as modulo

    def sin_red(*_args, **_kwargs):
        raise RuntimeError("sin red")

    monkeypatch.setattr(modulo, "investigar", sin_red)
    with pytest.raises(ValueError, match="ERROR: RuntimeError: sin red"):
        correr_composicion("research_council", "tema")
