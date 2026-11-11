"""X196: caracterización byte a byte de `debate` antes del template.

Un `call_llm` guionado (responde en orden y registra cada prompt) corre el
debate entero en dos escenarios (1 y 2 rondas) y guarda prompts y veredicto:
la migración al template de X194 tiene que dar los mismos bytes. Además fija
las DOS FASES del council (ítem 7 de X193b): en cada ronda la propuesta va
antes que su refutación y no ve la refutación de su propia ronda.

Correr con `--fotografiar` reescribe la foto.
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

import debate

FOTO = Path(__file__).resolve().parent / "caracterizacion_debate.json"
JUEZ = """```yaml
ganador: proponente
sintesis: |
  El proponente ancla la tesis en evidencia;
  el crítico muestra el supuesto que falta.
```"""

ESCENARIOS = {
    "una_ronda": ("la IA debe regularse", 1),
    "dos_rondas": ("los tests primero", 2),
}


def _guion(rondas):
    """call_llm falsa: propuesta, refutación, propuesta, … y el juez al final.

    Devuelve (llm, prompts): la respuesta es reconocible por su texto para que
    las aserciones de fase puedan buscarla en los prompts siguientes."""
    cola = []
    for n in range(rondas):
        cola.append(f"Propuesta {n + 1}: el costo está acotado y hay evidencia.")
        cola.append(f"Refutación {n + 1}: falta el dato que sostiene la tesis.")
    cola.append(JUEZ)
    prompts = []

    def llm(prompt):
        prompts.append(prompt)
        return cola[len(prompts) - 1]

    return llm, prompts


def _correr(nombre, monkeypatch):
    tema, rondas = ESCENARIOS[nombre]
    llm, prompts = _guion(rondas)
    monkeypatch.setattr(debate, "call_llm", llm)
    veredicto = debate.debatir(tema, rondas)
    foto = {"prompts": [hashlib.sha256(p.encode()).hexdigest() for p in prompts],
            "veredicto": veredicto}
    return foto, prompts


@pytest.mark.parametrize("nombre", sorted(ESCENARIOS))
def test_el_debate_da_los_mismos_bytes_que_la_foto(nombre, monkeypatch):
    foto = json.loads(FOTO.read_text(encoding="utf-8"))
    assert _correr(nombre, monkeypatch)[0] == foto[nombre]


def test_el_council_separa_la_propuesta_ciega_de_la_refutacion(monkeypatch):
    """Ítem 7 de X193b con k=1/1: por ronda, la propuesta del proponente sale
    ANTES que la refutación del crítico, y la propuesta no ve la refutación de
    su propia ronda (sólo la anterior, en el historial)."""
    _, prompts = _correr("dos_rondas", monkeypatch)
    orden = ["propuesta" if "Eres el PROPONENTE" in p else
             "refutacion" if "Eres el CRÍTICO" in p else "juez" for p in prompts]
    assert orden == ["propuesta", "refutacion", "propuesta", "refutacion", "juez"]
    # la propuesta de la ronda 2 ve la refutación 1 y NO la refutación 2
    assert "Refutación 1" in prompts[2] and "Refutación 2" not in prompts[2]
    # la refutación ve la propuesta de su ronda
    assert "Propuesta 1" in prompts[1] and "Propuesta 2" in prompts[3]


if __name__ == "__main__" and "--fotografiar" in sys.argv:
    fotos = {}
    for nombre in sorted(ESCENARIOS):
        with pytest.MonkeyPatch.context() as mp:
            fotos[nombre] = _correr(nombre, mp)[0]
    FOTO.write_text(json.dumps(fotos, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8")
    print(f"foto: {FOTO} ({len(fotos)} escenarios)")
