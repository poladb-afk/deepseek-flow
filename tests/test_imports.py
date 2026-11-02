"""El arranque del chat no carga las dependencias opcionales (X125).

`python -X importtime` es el gate de la mudanza de imports perezosos: el
ratchet dice cuántos quedan, esto dice que ninguno de los que se movieron al
tope arrastra una dependencia opcional al producto. Las opcionales se cargan
en su punto de uso (fallback local, MCP, búsqueda web), no al arrancar.
"""
import subprocess
import sys

from conftest import RAIZ

OPCIONALES = ("ddgs", "fastembed", "fastmcp", "laya", "opik")


def test_el_arranque_del_chat_no_carga_dependencias_opcionales():
    proceso = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", "import main"],
        cwd=RAIZ, capture_output=True, text=True, timeout=120)
    assert proceso.returncode == 0, proceso.stderr
    cargados = {linea.rsplit("|", 1)[-1].strip().split(".")[0]
                for linea in proceso.stderr.splitlines() if "|" in linea}
    presentes = sorted(set(OPCIONALES) & cargados)
    assert not presentes, f"el arranque del chat carga dependencias opcionales: {presentes}"
