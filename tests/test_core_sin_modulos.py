"""El CORE no conoce a sus módulos (fase 1a de docs/elegancia.md, F5).

"Agregar una capacidad = dejar un archivo; quitarla = borrarlo" tiene que
valer también para el ciclo de vida: el arranque, la compacción y la salida
recorren los HOOKS que declaran los módulos presentes, sin nombrarlos."""
import site
import subprocess
import sys

from conftest import RAIZ

import modules
import modules.delegar as delegar_mod
import modules.memoria as memoria

# el chat real, en otro proceso, con modules/memoria.py ilegible (como si se
# hubiera borrado): arranca, compacta, responde y sale
SIN_MEMORIA = """
import importlib.abc, sys
class SinMemoria(importlib.abc.MetaPathFinder):
    def find_spec(self, nombre, *a):
        if nombre == "modules.memoria":
            raise ImportError("borrado a propósito")
sys.meta_path.insert(0, SinMemoria())
sys.path.insert(0, RAIZ)
from types import SimpleNamespace as NS
import builtins, main, nodes
from modules import ganchos
assert "memory_search" not in nodes.MODULE_IMPLS
assert not ganchos("al_compactar")
entradas = iter(["hola", "salir"])
builtins.input = lambda *a, **k: next(entradas)
nodes.call_llm_agent = lambda m, t=None: NS(content="ok", tool_calls=None)
viejo = [{"role": "user", "content": "x" * 300}, {"role": "assistant", "content": "y"}]
shared = {"messages": [{"role": "system", "content": "s"}] + viejo * 12}
for g in ganchos("al_arrancar"):
    g(shared)
main.create_agent_flow().run(shared)
for g in reversed(ganchos("al_salir")):
    g(shared)
assert shared["compacciones"] == 1, shared.get("compacciones")
print("CHAT-SIN-MEMORIA-OK")
"""


def test_los_ganchos_vienen_de_los_modulos_presentes():
    assert memoria.catalogo in modules.ganchos("al_arrancar")
    assert delegar_mod.estado_delegadas in modules.ganchos("al_arrancar")
    assert modules.ganchos("al_compactar") == [memoria.respaldar_zona_fria]
    assert modules.ganchos("evento_que_nadie_declara") == []


def test_el_chat_corre_sin_el_modulo_de_memoria(tmp_path):
    """Sin `modules/memoria.py` el chat arranca, compacta y sale: la memoria
    es una capacidad, no una dependencia del CORE."""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "AGENT_ALLOWED_DIRS": str(tmp_path),
           "USE_LAYA_ROUTER": "0", "CHAT_STREAM": "0", "PREFETCH": "0", "CITAS_VERIFICAR": "0",
           "SKILLS": "0", "COMPACTION_CHARS": "3000", "TRACE": "0", "THREAD_PERSIST": "0",
           "PREGUNTAS_LOG": "0", "LAYA_LOG_DECISIONES": "0"}
    # con deps en user site (pip --user), el HOME aislado del hijo las tapa:
    # heredan la ruta de paquetes del proceso que corre el test
    env["PYTHONPATH"] = site.getusersitepackages()
    script = SIN_MEMORIA.replace("sys.path.insert(0, RAIZ)", f"sys.path.insert(0, {str(RAIZ)!r})")
    r = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=120)
    assert "CHAT-SIN-MEMORIA-OK" in r.stdout, r.stdout[-1500:] + r.stderr[-1500:]
    assert "memoria no cargó" in r.stderr  # discover() avisa y sigue
