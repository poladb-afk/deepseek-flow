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
    assert extraer(texto) == [("utils/a.py", 3), ("tests/b.py", 10)]


def test_cita_por_nombre_suelto_unico():
    """Si el modelo abrevia (policy.py:88 tras citar utils/policy.py), y el
    nombre es único en el árbol fuente, se verifica igual (medido: 9/14 citas
    abreviadas en una sesión real)."""
    from utils.citas import verificar_citas

    r = verificar_citas("ver tracing.py:1")
    assert r["ok"] == 1 and r["citas"][0]["estado"] == "ok"
