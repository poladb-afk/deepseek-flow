"""Export de grafos y visor HTML: mermaid, tabla markdown y regeneración (PR 4)."""


def test_mermaid_export():
    from research import create_research_flow
    from utils.viz import mermaid

    texto = mermaid(create_research_flow())
    assert "Planner" in texto and "research" in texto

def test_mermaid_flujos_batch_y_lote():
    """El export de grafos cubre los flujos nuevos: el batch puro
    (effective_n multi) y la rama async del lote. Un flujo anidado declara su
    nombre aunque su start sea hoja."""
    from utils.viz import FLOWS, mermaid

    multi = mermaid(FLOWS["effective_n_multi"]())
    assert "EffectiveNMulti" in multi
    lote = mermaid(FLOWS["juez_lote"]())
    assert "JuezLoteFlow" in lote
    # el single conserva su pipeline de 3 nodos
    single = mermaid(FLOWS["effective_n"]())
    assert "ScanFiles" in single and "HashFile" in single and "WriteReport" in single

def test_tabla_markdown():
    from informe import tabla_markdown

    analisis = [{"file": "a.jsonl", "total": 3, "errores": 0, "modulos": {"x": 2}}]
    fila = tabla_markdown(analisis)
    assert "a.jsonl" in fila and "x: 2" in fila

def test_visor_genera_html(tmp_path):
    import json

    from visor import generar

    traza = tmp_path / "trace.jsonl"
    eventos = [
        {"ts": 100.0, "nodo": "ElegirSiguiente", "accion": "ejecutar", "seg": 0.2},
        {"ts": 100.2, "nodo": "EjecutarPaso", "accion": "elegir", "seg": 5.0},
        {"ts": 105.2, "nodo": "ElegirSiguiente", "accion": "sintetizar", "seg": 0.1},
        {"ts": 105.3, "nodo": "Sintetizar", "accion": "default", "seg": 0.0},
    ]
    traza.write_text("\n".join(json.dumps(e) for e in eventos) + "\n", encoding="utf-8")
    destino = generar(traza)
    h = destino.read_text(encoding="utf-8")
    assert destino.name == "trace.html"
    for s in ("Recorrido", "Cronología", "Resumen por nodo", "ElegirSiguiente", "5.00s"):
        assert s in h, s
    # determinista: el mismo jsonl produce el mismo html
    assert generar(traza).read_text(encoding="utf-8") == h

def test_visor_watch_regenera_al_crecer(tmp_path):
    """--watch vuelve a generar el HTML cuando la traza crece, y no rompe
    con una traza vacía entre vueltas. En vez de esperar el loop infinito,
    ejercitamos el paso que decide (contar_y_mtime) y el umbral de cambio."""
    import json
    import time

    from visor import contar_y_mtime, generar

    traza = tmp_path / "w.jsonl"
    # traza inexistente: el watch no rompe (0 eventos)
    assert contar_y_mtime(traza)[0] == 0

    traza.write_text(json.dumps({"ts": 1, "nodo": "A", "accion": "x", "seg": 0.1}) + "\n")
    n1, m1 = contar_y_mtime(traza)
    assert n1 == 1
    h1 = generar(traza).read_text(encoding="utf-8")

    # la traza crece (como en vivo): hay cambio detectable y el HTML cambia
    time.sleep(0.01)
    traza.write_text(traza.read_text() + json.dumps(
        {"ts": 2, "nodo": "B", "accion": "y", "seg": 0.2}) + "\n")
    n2, m2 = contar_y_mtime(traza)
    assert (n2, m2) != (n1, m1)  # el watch volvería a generar
    h2 = generar(traza).read_text(encoding="utf-8")
    assert "B" in h2 and h2 != h1
