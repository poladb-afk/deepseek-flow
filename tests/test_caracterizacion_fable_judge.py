"""X179: caracterización byte a byte de `fable_judge` antes de recomponerlo.

Un juez guionado (call_llm falsa que devuelve YAML fijo y registra cada prompt)
corre el flujo entero en seis escenarios: código con refutación, verificación
re-ejecutada que falla, veredicto ilegible dos veces, claims ilegibles, modo
dominio con fuentes grandes y la degradación por caída de la API. Se guarda
cada prompt enviado y la salida final; la recomposición tiene que dar los
mismos bytes. Correr con `--fotografiar` reescribe la foto.
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

import fable_judge

FOTO = Path(__file__).resolve().parent / "caracterizacion_fable_judge.json"

CLAIMS = """```yaml
claims:
  - texto: "Fixed convert()"
    tipo: hecho
  - texto: "All tests pass"
    tipo: verificacion
    comando: python3 test_convert.py
  - texto: "lint limpio"
    tipo: verificacion
    comando: bash -c 'rm -rf x'
```"""
JUICIO = """```yaml
fraudes:
  - tipo: debris
    detalle: dejó debug_scratch.py
    evidencia: "`debug_scratch.py` aparece en el diff"
  - tipo: false_completion
    detalle: cita algo que no viajó
    evidencia: "`esto no está en ningún material`"
veredicto: refuted
caveats: [sin transcript]
accion: rehacer el fix
```"""
JUICIO_DOMINIO = """```yaml
fraudes:
  - tipo: Fabricated statistics
    detalle: 93% sin fuente
    evidencia: "`93% of 12,000+`"
veredicto: refuted
accion: sacar la cifra
```"""


def _fixture(raiz):
    pristine, worked = raiz / "pristine", raiz / "worked"
    for d in (pristine, worked):
        d.mkdir(parents=True)
    (pristine / "convert.py").write_text("def convert(x):\n    return round(x, 2)\n")
    (pristine / "viejo.py").write_text("x = 1\n")
    (worked / "convert.py").write_text("def convert(x):\n    return round(x, 2)  # DEBUG\n")
    (worked / "debug_scratch.py").write_text("print('dbg')\n")
    (worked / "test_convert.py").write_text("def test_x():\n    assert convert(0.125) == 0.13\n")
    return worked, pristine


def _guion(respuestas):
    """call_llm falsa: responde en orden y registra cada prompt."""
    vistos, cola = [], list(respuestas)

    def llm(prompt):
        vistos.append(prompt)
        respuesta = cola.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta
    return llm, vistos


ESCENARIOS = {
    "codigo_refutado": ([CLAIMS, JUICIO], "exit 0\nok", None),
    "rerun_falla": ([CLAIMS, JUICIO], "exit 1\nAssertionError", None),
    # el nodo reintenta 3 veces por falla del exec; el YAML ilegible no falla
    # el exec (cae al fallback), así que alcanzan dos respuestas por paso.
    "veredicto_ilegible": ([CLAIMS, "no es yaml", "veredicto: tal vez"], "exit 0", None),
    "claims_ilegibles": (["basura", "claims: 3", JUICIO], "exit 0", None),
    "dominio_fuentes_grandes": ([CLAIMS, JUICIO_DOMINIO], "exit 0", "marketing"),
    # CazarFraudes tiene max_retries=3: tres caídas seguidas cortan el flujo.
    "api_cae": ([CLAIMS] + [RuntimeError("sin API key")] * 3, "exit 0", None),
}


def _correr(nombre, tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)  # el retry del nodo espera 5 s
    respuestas, salida_rerun, sector = ESCENARIOS[nombre]
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    worked, pristine = _fixture(tmp_path)
    if sector:
        (worked / "landing.md").write_text("The Best ledger! 93% of 12,000+ businesses\n" + "x" * 20000)
        (worked / "brand.md").write_text("sentence case; no exclamation marks\n")
    llm, vistos = _guion(respuestas)
    monkeypatch.setattr(fable_judge, "call_llm", llm)
    texto, advertencia = fable_judge.verificar_trabajo(
        str(worked), pristine=str(pristine), reporte="Fixed convert(). All tests pass.",
        ejecutar=lambda comando: salida_rerun, sector=sector)
    raiz = str(tmp_path)
    limpio = [p.replace(raiz, "<RAIZ>") for p in vistos]
    return {"prompts": [hashlib.sha256(p.encode()).hexdigest() for p in limpio],
            "salida": texto.replace(raiz, "<RAIZ>"), "advertencia": advertencia}


@pytest.mark.parametrize("nombre", sorted(ESCENARIOS))
def test_fable_judge_da_los_mismos_bytes_que_la_foto(nombre, tmp_path, monkeypatch):
    foto = json.loads(FOTO.read_text(encoding="utf-8"))
    assert _correr(nombre, tmp_path, monkeypatch) == foto[nombre]


if __name__ == "__main__" and "--fotografiar" in sys.argv:
    import tempfile

    fotos = {}
    for nombre in sorted(ESCENARIOS):
        with tempfile.TemporaryDirectory() as tmp, pytest.MonkeyPatch.context() as mp:
            fotos[nombre] = _correr(nombre, Path(tmp), mp)
    FOTO.write_text(json.dumps(fotos, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"foto: {FOTO} ({len(fotos)} escenarios)")
