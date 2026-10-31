"""Fase 5b, pre-registro: la sonda que dice qué skill se cargó por turno (sin red)."""
from banco.probes import fase5b


def _fin(turno, skills):
    return {"tipo": "turno-fin", "detalle": {"id": turno, "marcadores": {"skill": skills} if skills else {}}}


def test_reparte_las_marcas_del_transcript_por_turno():
    eventos = [{"tipo": "inicio"}, _fin("a", 1), _fin("b", 0), _fin("c", 2)]
    log = "  [skill] revision activo — x\n...\n  [skill] tdd activo\n  [skill] revision activo\n"
    assert fase5b.skills_por_turno(eventos, log) == {"a": ["revision"], "b": [], "c": ["tdd", "revision"]}


def test_el_disparo_pide_tres_de_cuatro_en_cada_corrida_y_cero_en_negativos():
    buena = {t: ([s] if s else []) for t, s in fase5b.ESPERADO.items()}
    una_menos = dict(buena, **{"pos-revision-en": []})
    dos_menos = dict(una_menos, **{"pos-auditoria": ["revision"]})  # skill equivocado = fallo
    assert fase5b.veredicto_disparo([buena, una_menos])["cumple"] is True
    assert fase5b.veredicto_disparo([buena, dos_menos])["aciertos_por_corrida"] == [4, 2]
    assert fase5b.veredicto_disparo([buena, dos_menos])["cumple"] is False
    con_negativo = dict(buena, **{"neg-haiku": ["revision"]})
    assert fase5b.veredicto_disparo([con_negativo])["cargas_en_negativos"] == 1
    assert fase5b.veredicto_disparo([con_negativo])["cumple"] is False
    assert fase5b.veredicto_disparo([])["cumple"] is False


def test_cada_skill_esperado_esta_en_el_catalogo():
    """X110 midió que la regex de la base disparaba en 1 de 4 positivos (con la
    regex ya borrada, el número queda en la bitácora y en el pre-registro).
    Lo que sigue verificable sin LLM: cada skill que el escenario espera es una
    opción de `usar_skill`, y los negativos no tienen ninguno."""
    from modules import skills

    enum = skills.TOOLS[0]["function"]["parameters"]["properties"]["skill"]["enum"]
    assert {s for s in fase5b.ESPERADO.values() if s} <= set(enum)
