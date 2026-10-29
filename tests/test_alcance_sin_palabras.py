"""La sonda del contrafáctico 2 de la fase 4b-mín, sin disco real ni modelo."""
import json

from banco.probes import alcance_sin_palabras as asp


def test_una_pregunta_amplia_solo_por_palabras_se_lista(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    ruta = tmp_path / "preguntas.jsonl"
    filas = [{"origen": "terminal", "pregunta": "revisá todo el repo"},
             {"origen": "terminal", "pregunta": "¿qué hace esta línea?"},
             {"origen": "banco", "pregunta": "auditoría completa del proyecto"},
             {"origen": "web", "pregunta": "revisá todo el repo"}]
    ruta.write_text("\n".join(json.dumps(f) for f in filas) + "\nroto\n", encoding="utf-8")
    assert asp.main(["--ruta", str(ruta)]) == 2
    salida = capsys.readouterr().out
    assert "2 preguntas únicas · 1 amplias con la regex · 1 dejan de serlo" in salida
    assert "revisá todo el repo" in salida and "REVISAR" in salida


def test_la_regex_queda_intacta_despues_de_clasificar():
    original = asp.nodes._PALABRAS_AMPLIAS
    asp.clasificar("revisá todo el repo")
    assert asp.nodes._PALABRAS_AMPLIAS is original
