"""Verificación determinista de citas archivo:línea (A40)."""
import pytest


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


@pytest.mark.parametrize("artefacto", ["salidas", "memoria", "rag_index", ".runs", ".modelos"])
def test_cita_por_nombre_suelto_no_mira_artefactos(tmp_path, monkeypatch, artefacto):
    """X175 (Auditor): un homónimo en un directorio de artefactos no puede
    cambiar la resolución —ni, en consecuencia, las líneas que ejecuta el
    verificador y mide la cobertura."""
    from utils.citas import verificar_citas

    (tmp_path / "utils").mkdir()
    (tmp_path / "utils" / "tracing.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    limpio = verificar_citas("ver tracing.py:1")
    (tmp_path / artefacto / "x").mkdir(parents=True)
    (tmp_path / artefacto / "x" / "tracing.py").write_text("x = 1\n", encoding="utf-8")
    assert verificar_citas("ver tracing.py:1") == limpio
    assert limpio["ok"] == 1 and limpio["citas"][0]["resuelto_por_nombre"] is True


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



@pytest.mark.parametrize("subcarpeta", [False, True], ids=["raiz", "utils"])
def test_cita_externa_no_depende_de_su_existencia(tmp_path, monkeypatch, subcarpeta):
    """Una fuente no autorizada no participa en lectura, búsqueda o unicidad."""
    from pathlib import Path

    from utils.citas import verificar_citas

    permitido = tmp_path / "permitido"
    permitido.mkdir()
    trabajo = tmp_path / "trabajo"
    trabajo.mkdir()
    carpeta = trabajo / "utils" if subcarpeta else trabajo
    carpeta.mkdir(exist_ok=True)
    archivo = carpeta / "dato_restringido.py"
    monkeypatch.chdir(trabajo)
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(permitido))
    ausente = verificar_citas("dato_restringido.py:1")
    archivo.write_text("fuera = 1\n", encoding="utf-8")
    leidos = []
    recorridos = []
    leer = Path.read_text
    recorrer = Path.rglob

    def observar_lectura(path, *args, **kwargs):
        leidos.append(path.resolve())
        return leer(path, *args, **kwargs)

    def observar_recorrido(path, *args, **kwargs):
        recorridos.append(path.resolve())
        return recorrer(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", observar_lectura)
    monkeypatch.setattr(Path, "rglob", observar_recorrido)
    assert verificar_citas("dato_restringido.py:1") == ausente
    assert archivo.resolve() not in leidos
    assert not recorridos


@pytest.mark.parametrize("directorio", [False, True], ids=["enlace_archivo", "enlace_base"])
def test_fallback_excluye_enlaces_hacia_fuentes_externas(tmp_path, monkeypatch, directorio):
    from utils.citas import verificar_citas

    trabajo = tmp_path / "trabajo"
    externo = tmp_path / "externo"
    trabajo.mkdir()
    externo.mkdir()
    if directorio:
        (trabajo / "utils").symlink_to(externo, target_is_directory=True)
    else:
        (trabajo / "utils").mkdir()
        (trabajo / "utils" / "dato_restringido.py").symlink_to(externo / "dato_restringido.py")
    monkeypatch.chdir(trabajo)
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(trabajo))
    ausente = verificar_citas("dato_restringido.py:1")
    (externo / "dato_restringido.py").write_text("fuera = 1\n", encoding="utf-8")
    assert verificar_citas("dato_restringido.py:1") == ausente
    assert ausente["ok"] == 0


def test_fallback_admite_una_base_autorizada_sin_ampliar_al_padre(tmp_path, monkeypatch):
    from utils.citas import verificar_citas

    permitido = tmp_path / "utils"
    permitido.mkdir()
    (permitido / "dato_autorizado.py").write_text("permitido = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(permitido))
    resultado = verificar_citas("dato_autorizado.py:1")
    assert resultado["ok"] == 1
    assert "permitido = 1" in resultado["citas"][0]["detalle"]


def test_fallback_conserva_ambiguedad_autorizada(tmp_path, monkeypatch):
    from utils.citas import verificar_citas

    for nombre in ("docs", "utils"):
        carpeta = tmp_path / nombre
        carpeta.mkdir()
        (carpeta / "dato_duplicado.py").write_text("dato = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    resultado = verificar_citas("dato_duplicado.py:1")
    assert resultado["ok"] == 0
    assert resultado["citas"][0]["estado"] == "no_existe"
