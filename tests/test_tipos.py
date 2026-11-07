"""X191: los últimos tipos, cerrados sin cambiar conducta.

Caracteriza lo que tocó lógica: el grupo corto de la política (S0), la firma
que ve FastMCP sin `__signature__` a mano y los contadores de `effective_n`
que ahora se estrechan por el valor. El caso que el paquete externo declaraba
"bug real" en `juez_lote` no es ruta de producto: PocketFlow corre prep antes
de post, y el `post` directo ya no resta contra None desde X189 (bitácora).
"""
import inspect
import json

import pytest

import mcp_server
from utils import policy


@pytest.mark.parametrize(("tok", "letras"), [
    ("-abc", "abc"), ("-uo/x", "uo"), ("-rf", "rf"), ("-", ""), ("-1a", ""),
    ("--force", ""), ("x", ""), ("-a=b", "a"), ("-ñx", ""), ("-a\nb", "a"),
])
def test_el_grupo_corto_lee_las_letras_como_getopt(tok, letras):
    """`re.sub` en vez de `re.match(...).group()`: mismo prefijo de letras sin
    un `Match | None` que Pyright marque."""
    assert policy._grupo_corto(tok) == letras


def test_envolver_conserva_la_firma_sin_signature_a_mano():
    """`functools.wraps` deja `__wrapped__` e `inspect.signature` lo sigue: la
    línea de `__signature__` era redundante (FastMCP 4.1.6, medido por el autor
    externo; acá fastmcp no está instalado para repetirlo)."""
    def impl(command: str, timeout: int = 5) -> str:
        return command

    envuelta = mcp_server.envolver("zz", impl, {"zz": impl})
    assert "__signature__" not in vars(envuelta)
    assert list(inspect.signature(envuelta).parameters) == ["command", "timeout"]


@pytest.mark.red
def test_fastmcp_arma_el_schema_desde_la_firma_envuelta():
    """Con fastmcp instalado (opcional) el schema sale de la firma envuelta,
    sin `__signature__` a mano."""
    fastmcp = pytest.importorskip("fastmcp")
    import asyncio

    def impl(command: str, timeout: int = 5) -> str:
        return command

    servidor = fastmcp.FastMCP("t")
    servidor.tool(mcp_server.envolver("zz", impl, {"zz": impl}), name="zz")
    herramientas = asyncio.run(servidor.list_tools())
    esquema = next(h for h in herramientas if h.name == "zz").parameters
    assert esquema["required"] == ["command"]
    assert set(esquema["properties"]) == {"command", "timeout"}


def test_effective_n_sigue_separando_rotos_de_forma(tmp_path):
    """El `if rec is None` con contadores (X189) sigue separando JSON ilegible
    de forma inválida y no pierde el conteo."""
    import effective_n

    ruta = tmp_path / "a.jsonl"
    ruta.write_text("\n".join(["{no json", "[]", "null", '{"fields": null}',
                               json.dumps({"fields": {"steps": [1]}, "answers": {"next": "x"}})]) + "\n",
                    encoding="utf-8")
    r = effective_n.huellas_del_archivo(ruta)
    assert (r["n"], r["rotos"], r["forma"], r["con_steps"], r["dist"]) == (5, 1, 3, 1, {"x": 1})


def test_el_post_del_lote_sin_prep_no_resta_contra_none(tmp_path, monkeypatch):
    """El paquete externo lo declaraba bug real: cerrar el lote sin el arranque
    previo restaba contra None (`TypeError` en `1eea773`). En el tip mide desde
    la construcción (X191): no es ruta de producto —PocketFlow corre prep antes
    de post—, pero el fallback no puede ser ni un crash ni un número absurdo."""
    import asyncio

    import juez_lote

    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    flujo = juez_lote.JuezLoteFlow(salida=str(tmp_path / "lote.md"))
    asyncio.run(flujo.post_async({"resultados": []}, [], None))
    assert 0 <= flujo._seg_par < 60
