"""Candado de la sonda de tokens (exp/93): la agregación de eventos usage.

Fixtures sintéticos: el formato del evento es el de `utils/tracing.py:evento_llm`
(`accion: "usage"` con prompt/completion, sin contenido). Lo que se clava es la
lectura: secuencia fiel (la curva de contexto), trazas sin usage ignoradas en
silencio y directorio vacío sin reventar.
"""
import json

from banco.probes import tokens_runs


def _traza(ruta, nombres, usos):
    lineas = [{"ts": 1.0, "nodo": "GetQuestion", "accion": "continue", "seg": 0.1}]
    lineas += [{"ts": 1.0, "nodo": n, "accion": "default", "seg": 0.0} for n in nombres]
    for prompt, completion in usos:
        lineas.append({"ts": 2.0, "nodo": "llm", "accion": "usage", "seg": 0.0,
                       "prompt_tokens": prompt, "completion_tokens": completion})
        lineas.append({"ts": 3.0, "nodo": "AgentStep", "accion": "tool", "seg": 1.0})
    ruta.write_text("\n".join(json.dumps(f) for f in lineas) + "\n", encoding="utf-8")


def test_agrega_por_traza_con_secuencia_fiel(tmp_path):
    _traza(tmp_path / "a.jsonl", ["read_file"], [(100, 10), (250, 20)])
    _traza(tmp_path / "b.jsonl", ["search_files"], [(400, 5)])
    trazas = tokens_runs.barrer(tmp_path)
    primera = trazas[0]
    assert primera["nombre"] == "a" and primera["llamadas"] == 2
    assert primera["prompt_total"] == 350 and primera["completion_total"] == 30
    assert primera["max_prompt"] == 250
    assert primera["secuencia"] == [100, 250]
    assert trazas[1]["secuencia"] == [400]


def test_trazas_sin_usage_se_ignoran_en_silencio(tmp_path):
    (tmp_path / "historica.jsonl").write_text(
        json.dumps({"ts": 1.0, "nodo": "AgentStep", "accion": "tool", "seg": 1.0}) + "\n",
        encoding="utf-8")
    _traza(tmp_path / "con_uso.jsonl", [], [(7, 3)])
    trazas = tokens_runs.barrer(tmp_path)
    assert [t["nombre"] for t in trazas] == ["con_uso"]
    assert tokens_runs.agregados(trazas)["llamadas"] == 1


def test_directorio_vacio_no_revienta(tmp_path):
    assert tokens_runs.barrer(tmp_path) == []
    assert tokens_runs.barrer(tmp_path / "no_existe") == []
    assert tokens_runs.agregados([])["llamadas"] == 0
    assert tokens_runs.main(["--runs", str(tmp_path)]) == 1


def test_agregados_globales_por_llamada(tmp_path):
    _traza(tmp_path / "a.jsonl", [], [(10, 1), (20, 1), (30, 1), (40, 1), (1_000, 1)])
    a = tokens_runs.agregados(tokens_runs.barrer(tmp_path))
    assert a["traza"] == 1 and a["llamadas"] == 5
    assert a["prompt_total"] == 1_100 and a["max"] == 1_000
    assert a["p50"] == 30 and a["p90"] == 1_000


def test_desglose_por_llamador_y_cache_hit(tmp_path):
    """X98: las llamadas se agrupan por el nodo que las hizo; el hit ausente
    (trazas pre-X98) es DESCONOCIDO, no cero — `con_hit` cuenta las que lo
    informan, así un 0% no se confunde con "sin dato"."""
    lineas = [
        {"ts": 1, "nodo": "llm", "accion": "usage", "prompt_tokens": 1000,
         "completion_tokens": 10, "cache_hit": 900, "llamador": "AgentStep"},
        {"ts": 2, "nodo": "llm", "accion": "usage", "prompt_tokens": 1200,
         "completion_tokens": 40, "cache_hit": 0, "llamador": "Cierre"},
        {"ts": 3, "nodo": "llm", "accion": "usage", "prompt_tokens": 500, "completion_tokens": 5},
    ]
    (tmp_path / "t.jsonl").write_text("\n".join(json.dumps(x) for x in lineas) + "\n", encoding="utf-8")
    traza = tokens_runs.barrer(tmp_path)[0]
    assert traza["por_llamador"] == {
        "AgentStep": {"llamadas": 1, "prompt": 1000, "con_hit": 1, "cache_hit": 900},
        "Cierre": {"llamadas": 1, "prompt": 1200, "con_hit": 1, "cache_hit": 0},
        "?": {"llamadas": 1, "prompt": 500, "con_hit": 0, "cache_hit": 0},
    }
    assert tokens_runs.agregados([traza, traza])["por_llamador"]["Cierre"]["llamadas"] == 2
    assert tokens_runs.main(["--runs", str(tmp_path)]) == 0
