"""Guardas contra la deriva docs ↔ código (PR 1 del plan de orden).

Lo que hoy se detectaba a mano (README con 24 tools cuando había 29, 18
settings sin documentar, subcomandos sin README) pasa a ser un test: la
documentación no puede volver a mentir en silencio."""
import re
from collections import Counter

from conftest import RAIZ

# Lo que el harness lee pero no es "configuración del usuario"
NO_DOCUMENTABLES = {"HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "DEEPSEEK_API_KEY"}
LECTORES = [
    r'_(?:setting|entero|real|umbral)\(\s*["\']([A-Z][A-Z0-9_]+)["\']',
    r'environ(?:\.get)?\(\s*["\']([A-Z][A-Z0-9_]+)["\']',
    r'environ\[\s*["\']([A-Z][A-Z0-9_]+)',
    r'setting(?:_modelo)?\s*=\s*["\']([A-Z][A-Z0-9_]+)["\']',
    r'(?:disponible|agente)\(\s*["\']([A-Z][A-Z0-9_]+)["\']',
]


# Directorios que NO son fuente del harness: tests (se leen a sí mismos),
# docs (informes y este plan), salidas/ (artefactos de corrida: puede haber
# copias de scripts y daría falsos positivos) y los ocultos.
_IGNORAR = ("tests/", "docs/", "salidas/", ".")


def _fuentes():
    for p in RAIZ.rglob("*.py"):
        rel = p.relative_to(RAIZ).as_posix()
        if rel.startswith(_IGNORAR) or "__pycache__" in rel:
            continue
        yield rel, p.read_text(encoding="utf-8")


def _settings_usados():
    usados = {}
    for rel, src in _fuentes():
        for rx in LECTORES:
            for m in re.finditer(rx, src):
                usados.setdefault(m.group(1), rel)
    return {k: v for k, v in usados.items() if k not in NO_DOCUMENTABLES}


def _settings_documentados():
    env = (RAIZ / ".env.example").read_text(encoding="utf-8")
    return Counter(re.findall(r"^#?\s*([A-Z][A-Z0-9_]{2,})=", env, re.M))


def test_todo_setting_usado_esta_documentado():
    faltan = {k: v for k, v in _settings_usados().items() if k not in _settings_documentados()}
    assert not faltan, f"settings leídos por el código y ausentes de .env.example: {faltan}"


def test_ningun_setting_documentado_dos_veces():
    dobles = {k: n for k, n in _settings_documentados().items() if n > 1}
    assert not dobles, f"settings documentados más de una vez en .env.example: {dobles}"


def test_readme_cuenta_bien_las_tools():
    import nodes

    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    m = re.search(r"## Capacidades \((\d+)", readme)
    assert m, "el README perdió el encabezado '## Capacidades (N ...)'"
    assert int(m.group(1)) == len(nodes.TOOLS), (
        f"README dice {m.group(1)} tools y hay {len(nodes.TOOLS)}")


def test_readme_menciona_cada_tool():
    import nodes

    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    tabla = readme.split("## Capacidades", 1)[1].split("\n## ", 1)[0]
    nombres = {t["function"]["name"] for t in nodes.TOOLS}
    faltan = sorted(n for n in nombres if f"`{n}`" not in tabla)
    assert not faltan, f"tools sin fila en la tabla de Capacidades del README: {faltan}"


def test_readme_lista_cada_subcomando():
    from main import SUBCOMANDOS

    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    listados = set(re.findall(r"python3 main\.py ([\w-]+)", readme))
    faltan = sorted(set(SUBCOMANDOS) - listados)
    assert not faltan, f"subcomandos de main.py sin línea en 'CLI completo': {faltan}"
