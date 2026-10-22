"""Tests del loader de dominios de fable (F3): los adapters son DATOS
versionados con un schema (las secciones vinculantes del TEMPLATE upstream);
un .md que no lo cumple se saltea con aviso, no rompe nada."""
from pathlib import Path

from utils import fable_dominios
from utils.fable_dominios import adaptador, disponibles

OCHO = {"business-ops", "data-analysis", "design-ux", "devops",
        "finance", "legal-compliance", "marketing", "research"}


def test_los_ocho_adapters_cargan_con_sus_secciones():
    cargados = disponibles()

    assert set(cargados) >= OCHO
    assert "TEMPLATE" not in cargados  # el schema no es un adapter
    for id_, dom in cargados.items():
        assert dom["fraudes"].strip(), f"{id_} sin fraud table"
        assert dom["evidencia"].strip(), f"{id_} sin minimum evidence set"


def test_adaptador_resuelve_por_id_y_rechaza_typos():
    assert adaptador("marketing")["nombre"] == "marketing and content"
    assert adaptador("Marketing") is not None  # case-insensitive
    assert adaptador("marketin") is None
    assert adaptador("") is None
    assert adaptador(None) is None


def test_adapter_sin_secciones_vinculantes_se_saltea_con_aviso(tmp_path, monkeypatch, capsys):
    (tmp_path / "roto.md").write_text(
        "# Domain adapter: roto\n\nApplies when falta todo lo vinculante.\n",
        encoding="utf-8")
    monkeypatch.setattr(fable_dominios, "DOMINIOS_DIR", tmp_path)
    monkeypatch.setattr(fable_dominios, "_cache", None)

    assert disponibles() == {}
    assert "roto.md no tiene las secciones obligatorias" in capsys.readouterr().err


def test_adapter_valido_en_directorio_propio_carga(tmp_path, monkeypatch):
    (tmp_path / "marketing.md").write_text(
        "# Domain adapter: marketing and content\n\nApplies when copy.\n\n"
        "## Minimum evidence set (binding)\n\n1. brand.md\n\n"
        "## Evidence and primary sources\n\nlos docs del producto.\n\n"
        "## Authority order\n\nusuario > brand.md.\n\n"
        "## Fraud table (for fable-judge)\n\n| Fraud | Symptom |\n|---|---|\n"
        "| Fabricated statistics | sin fuente |\n",
        encoding="utf-8")
    monkeypatch.setattr(fable_dominios, "DOMINIOS_DIR", tmp_path)
    monkeypatch.setattr(fable_dominios, "_cache", None)

    dom = adaptador("marketing")

    assert dom["aplica"] == "copy."
    assert "Fabricated statistics" in dom["fraudes"]
    assert "usuario > brand.md" in dom["autoridad"]


def test_directorio_inexistente_degrada_a_vacio(tmp_path, monkeypatch):
    monkeypatch.setattr(fable_dominios, "DOMINIOS_DIR", tmp_path / "no_existe")
    monkeypatch.setattr(fable_dominios, "_cache", None)

    assert disponibles() == {}


RAIZ = Path(__file__).resolve().parent.parent
S8 = RAIZ / "banco" / "fable" / "escenarios" / "s8-fraudulent-copy"


def test_el_fixture_s8_trae_las_fuentes_que_el_juez_debe_descubrir():
    """El contrato del fixture (upstream): las fuentes viven en docs/ y NO se
    nombran en el landing — el juez las tiene que encontrar solo."""
    for rel in ("landing.md", "docs/brand.md", "docs/product-facts.md", "GROUND-TRUTH.md"):
        assert (S8 / rel).is_file(), f"falta {rel} en s8"
    landing = (S8 / "landing.md").read_text(encoding="utf-8")
    assert "brand.md" not in landing and "product-facts" not in landing
