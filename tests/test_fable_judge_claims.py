"""Tests del lado CLAIMS del juez de fable: cómo se extraen, validan y
priorizan (exp/84 candidatas en prosa, exp/87 F7 presupuesto declarado,
exp/92 prioridad de lo re-ejecutable). Puro, sin LLM ni red."""
import pytest

import fable_judge
from fable_judge import validar_claims, validar_juicio

# ── contratos de structured output ──────────────────────────────────────


def _claims_yaml(n=1, tipo="hecho", desde=0):
    filas = "\n".join(
        f"  - texto: hecho {i}\n    tipo: {tipo}" for i in range(desde, desde + n))
    return f"```yaml\nclaims:\n{filas}\n```"


def _claims_mixtos_yaml(n_hechos, n_verif):
    hechos = "".join(f"  - texto: hecho {i}\n    tipo: hecho\n" for i in range(n_hechos))
    verif = "".join(f"  - texto: verificacion {i}\n    tipo: verificacion\n"
                    for i in range(n_verif))
    return f"```yaml\nclaims:\n{hechos}{verif}\n```"


@pytest.mark.parametrize("crudo, motivo", [
    ("esto no es yaml de claims", "no parseó"),
    ("```yaml\nclaims: []\n```", "vacía"),
    ("```yaml\nclaims:\n  - tipo: hecho\n```", "texto no vacío"),
    ("```yaml\nclaims:\n  - texto: x\n    tipo: opinion\n```", "tipo de claim inválido"),
], ids=["no_yaml", "vacio", "sin_texto", "tipo_inventado"])
def test_validar_claims_rechaza_lo_invalido(crudo, motivo):
    claims, motivo_err = fable_judge.yaml_valido(crudo, validar_claims)
    assert claims is None and motivo in motivo_err


def test_validar_claims_trunca_al_presupuesto_y_canonicaliza():
    claims, motivo = fable_judge.yaml_valido(_claims_yaml(20), validar_claims)

    # el presupuesto se DECLARA (dogfood exp/87): MAX_CLAIMS + el aviso sintético
    assert motivo == "" and len(claims) == fable_judge.MAX_CLAIMS + 1
    assert claims[0]["tipo"] == "hecho"
    assert "no fue juzgado" in claims[-1]["texto"]


def test_validar_claims_prioriza_verificaciones_que_van_al_final():
    """exp/92 fix 1: el reporte outcome-first verifica al final; el corte viejo
    se quedaba con las descripciones y el juicio salía sin nada que re-ejecutar."""
    crudo = _claims_mixtos_yaml(n_hechos=20, n_verif=3)

    claims, motivo = fable_judge.yaml_valido(crudo, validar_claims)

    assert motivo == ""
    cuerpos, presupuesto = claims[:-1], claims[-1]
    assert len(cuerpos) == fable_judge.MAX_CLAIMS
    assert [c["texto"] for c in cuerpos[:3]] == [
        "verificacion 0", "verificacion 1", "verificacion 2"]
    assert all(c["tipo"] == "hecho" for c in cuerpos[3:])
    # el texto de presupuesto dice la verdad nueva, no la del corte ciego
    assert presupuesto["tipo"] == "hecho"
    assert "priorizando los 3 de tipo verificacion" in presupuesto["texto"]


@pytest.mark.parametrize("n", [1, 12], ids=["uno", "justo_el_tope"])
def test_validar_claims_con_tope_o_menos_no_cambia_nada(n):
    claims, motivo = fable_judge.yaml_valido(_claims_yaml(n), validar_claims)

    assert motivo == ""
    assert len(claims) == n
    assert [c["texto"] for c in claims] == [f"hecho {i}" for i in range(n)]


def test_validar_claims_en_el_tope_conserva_el_orden_original():
    """≤12 no se reordena: la prioridad es solo post-procesamiento del corte."""
    crudo = _claims_mixtos_yaml(n_hechos=9, n_verif=3)

    claims, motivo = fable_judge.yaml_valido(crudo, validar_claims)

    assert motivo == "" and len(claims) == 12
    assert [c["tipo"] for c in claims] == ["hecho"] * 9 + ["verificacion"] * 3


def test_validar_claims_capea_verificaciones_solas():
    claims, motivo = fable_judge.yaml_valido(
        _claims_yaml(15, "verificacion"), validar_claims)

    assert motivo == ""
    assert len(claims) == fable_judge.MAX_CLAIMS + 1
    assert all(c["tipo"] == "verificacion" for c in claims[:-1])
    # el texto del presupuesto dice las CUENTAS (caveat del re-juicio de
    # exp/92): cuántos había y cuántos verificacion entraron
    assert "de 15 claims se evalúan 12, priorizando los 12" in claims[-1]["texto"]
    assert "no fue juzgado" in claims[-1]["texto"]


@pytest.mark.parametrize("crudo, motivo", [
    ("```yaml\nclaims:\n" + "".join(
        f"  - texto: hecho {i}\n    tipo: hecho\n" for i in range(13))
     + "  - tipo: hecho\n```", "texto no vacío"),
    ("```yaml\nclaims:\n" + "".join(
        f"  - texto: hecho {i}\n    tipo: hecho\n" for i in range(13))
     + "  - texto: x\n    tipo: opinion\n```", "tipo de claim inválido"),
], ids=["tras_el_tope_sin_texto", "tras_el_tope_tipo_inventado"])
def test_validar_claims_invalido_tras_el_tope_igual_falla(crudo, motivo):
    """Comportamiento nuevo (exp/92): no hay zona muerta — todo claim se valida."""
    claims, motivo_err = fable_judge.yaml_valido(crudo, validar_claims)

    assert claims is None and motivo in motivo_err


@pytest.mark.parametrize("veredicto, canon", [
    ("REFUTED", "refuted"),
    ("verified ", "verified"),
    ("Verified_With_Caveats", "verified_with_caveats"),
])
def test_validar_juicio_canonicaliza(veredicto, canon):
    juicio, motivo = validar_juicio({"veredicto": veredicto, "fraudes": []})

    assert motivo == "" and juicio["veredicto"] == canon


@pytest.mark.parametrize("datos, motivo", [
    ({"veredicto": "ok"}, "veredicto inválido"),
    ({"veredicto": "refuted", "fraudes": "no lista"}, "no es lista"),
    ({"veredicto": "refuted",
      "fraudes": [{"tipo": "hack", "detalle": "x"}]}, "tipo debe ser"),
    ("no dict", "no es un diccionario"),
], ids=["veredicto_inventado", "fraudes_str", "fraude_inventado", "no_dict"])
def test_validar_juicio_rechaza_lo_invalido(datos, motivo):
    juicio, motivo_err = validar_juicio(datos)
    assert juicio is None and motivo in motivo_err



# ── candidatas a verificación: el código reúne, el LLM clasifica ────────


def test_candidatas_encuentra_las_verificaciones_en_prosa():
    reporte = (
        "Listo el fix de convert(). Verificaciones: pytest tests/ da 63 passed "
        "y ruff check . está limpio. También corrí exit 0 del gate de calidad."
    )

    candidatas = fable_judge.candidatas_verificacion(reporte)

    assert any("pytest" in c and "63 passed" in c for c in candidatas)
    assert any("ruff" in c for c in candidatas)
    assert any("gate" in c for c in candidatas)


@pytest.mark.parametrize("prosa", [
    "Toqué convert.py y leí el README.",
    "El diseño quedó más limpio y prolijo.",
    "Agregué una función nueva con tests pensados.",
])
def test_candidatas_no_matchea_prosa_neutra(prosa):
    assert fable_judge.candidatas_verificacion(prosa) == []


def test_candidatas_esta_acotada():
    reporte = "\n".join(f"pytest corrida {i} da 1 passed" for i in range(30))

    candidatas = fable_judge.candidatas_verificacion(reporte)

    assert len(candidatas) == fable_judge.MAX_CANDIDATAS


