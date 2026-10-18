"""Verificación determinista de citas archivo:línea (A40)."""
def test_verificar_citas_estados(tmp_path, monkeypatch):
    from utils.citas import reporte, verificar_citas

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    codigo = tmp_path / "codigo.py"
    codigo.write_text("uno\ndos\ntres\n", encoding="utf-8")

    texto = f"ok {codigo}:2; malo {codigo}:99; fuera /etc/secreto.py:1"
    r = verificar_citas(texto)
    assert r["total"] == 3 and r["ok"] == 1
    por_linea = {c["linea"]: c["estado"] for c in r["citas"] if c["path"] == str(codigo)}
    assert por_linea == {2: "ok", 99: "linea_fuera"}
    assert any(c["estado"] == "fuera" for c in r["citas"])
    rep = reporte(r)
    assert "1/3" in rep and "linea_fuera" in rep and "99" in rep


def test_extraer_deduplica_y_limpia_markdown(tmp_path):
    from utils.citas import extraer

    texto = "ver utils/a.py:3 y de nuevo utils/a.py:3; y tests/b.py:10."
    assert extraer(texto) == [("utils/a.py", 3, None), ("tests/b.py", 10, None)]


def test_cita_por_nombre_suelto_unico():
    """Si el modelo abrevia (policy.py:88 tras citar utils/policy.py), y el
    nombre es único en el árbol fuente, se verifica igual (medido: 9/14 citas
    abreviadas en una sesión real)."""
    from utils.citas import verificar_citas

    r = verificar_citas("ver tracing.py:1")
    assert r["ok"] == 1 and r["citas"][0]["estado"] == "ok"


def test_verificar_citas_rango(tmp_path, monkeypatch):
    """A52: un rango N-M se valida en sus DOS extremos (antes se truncaba al
    primer número y se reportaba ok como si el rango completo existiera)."""
    from utils.citas import reporte, verificar_citas

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    codigo = tmp_path / "codigo.py"
    codigo.write_text("uno\ndos\ntres\ncuatro\n", encoding="utf-8")

    r = verificar_citas(f"{codigo}:2-3")
    assert r["ok"] == 1 and r["citas"][0]["linea2"] == 3
    r = verificar_citas(f"{codigo}:3-9")
    assert r["ok"] == 0 and r["citas"][0]["estado"] == "linea_fuera"
    assert "3-9" in reporte(r)


def test_citas_placeholder_no_cuentan():
    """Nombres de ejemplo en prosa (archivo.py:10-20) no son citas reales:
    no deben disparar correcciones (medido en S10)."""
    from utils.citas import extraer

    assert extraer("por ejemplo archivo.py:10-20") == []


def test_mencionar_archivo_sin_linea_no_es_cita():
    """S11: un archivo nombrado sin `:línea` no es una cita verificable;
    antes se contaba como :0 y generaba falsos linea_fuera."""
    from utils.citas import extraer, verificar_citas

    assert extraer("revisar utils/policy.py y utils/contexto.py") == []
    assert verificar_citas("revisar utils/policy.py")["total"] == 0


def test_verificar_citas_jsonl(tmp_path, monkeypatch):
    """La corrida continua citó `.runs/*.jsonl:5`; el verificador no cubría
    jsonl y esas citas quedaban sin chequear. Ahora las cubre."""
    from utils.citas import verificar_citas

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    traza = tmp_path / "traza.jsonl"
    traza.write_text('{"nodo": "a"}\n{"nodo": "b"}\n', encoding="utf-8")
    r = verificar_citas(f"ver {traza}:2")
    assert r["total"] == 1 and r["ok"] == 1
