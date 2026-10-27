"""El generador del dataset: las cercas de X88, sin LLM."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "banco" / "probes"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import voto_dataset_gen as gen  # noqa: E402


def test_el_veredicto_del_juez_se_parsea():
    assert gen.RE_VEREDICTO.search("```yaml\nveredicto: Herramientas\n```").group(1).lower() == "herramientas"
    assert gen.RE_VEREDICTO.search("veredicto:directo") is not None
    assert gen.RE_VEREDICTO.search("sin veredicto acá") is None


def test_el_dedup_es_por_parecido_no_por_identidad():
    """Reusa palabras/jaccard del antifuga: tildes y mayúsculas no salvan a
    un duplicado (la MISMA normalización que la cerca final)."""
    a = gen.palabras("¿Quién ganó la última Copa del Rey?")
    b = gen.palabras("¿quien gano la ultima copa del rey?")
    c = gen.palabras("¿Quién escribió el Martín Fierro?")
    assert gen.jaccard(a, b) == 1.0
    assert gen.jaccard(a, c) < 0.2


def test_el_pedido_del_generador_no_contiene_ningun_caso_del_control():
    """La cerca: el prompt que ve el generador describe SOLO familias. Si un
    caso del control (o del bench) viajara adentro, la puerta de entrada del
    dataset estaría contaminada."""
    capturado = {}

    def llm_falso(pedido):
        capturado["pedido"] = pedido
        return "1. pregunta suficientemente larga de prueba"

    original = gen.call_llm
    gen.call_llm = llm_falso
    try:
        gen.generar_lote("ganador", 1)
    finally:
        gen.call_llm = original
    raiz = Path(__file__).resolve().parents[1]
    for ruta in ("banco/voto_control.jsonl", "banco/voto_casos.jsonl"):
        for linea in (raiz / ruta).read_text(encoding="utf-8").splitlines():
            pregunta = json.loads(linea)["pregunta"]
            por_palabra = [p for p in pregunta.split() if len(p) > 4]
            overlap = sum(1 for p in por_palabra if p.lower().strip(".,;:¿?¡!«»") in capturado["pedido"].lower())
            assert overlap < len(por_palabra) * 0.6, f"{ruta}: {pregunta!r} parece estar en el pedido"


def test_el_juez_es_ciego_no_ve_familia_ni_intencion():
    capturado = {}

    def llm_falso(pregunta):
        capturado["prompt"] = pregunta
        return "```yaml\nveredicto: directo\n```"

    original = gen.call_llm
    gen.call_llm = llm_falso
    try:
        veredicto, err = gen.juzgar("¿pregunta de prueba suficientemente larga?")
    finally:
        gen.call_llm = original
    assert veredicto == "directo" and err is None
    assert "familia" not in capturado["prompt"].lower()
    assert "intencion" not in capturado["prompt"].lower()
