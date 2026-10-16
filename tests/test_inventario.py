"""Candado del inventario de tests (PR 4).

La suite se partió por tema el 2026-10-16: 245 bloques salieron de
`test_smoke.py` (5.621 líneas) a 19 archivos. El riesgo de un movimiento así
es silencioso — un test que se pierde en el camino no rompe nada, simplemente
deja de correr y nadie se entera. Este candado lo hace ruidoso.

`inventario_tests.txt` es la foto de los tests que existían al partir. Acá se
exige que TODOS sigan recolectándose, que ningún archivo de test pase de 800
líneas (el criterio del plan) y que la foto esté ordenada y sin repetidos.

Agregar tests NO requiere tocar la foto (solo se comprueba que no falte
ninguno). Borrar o mover uno, sí — y es deliberado:

    LC_ALL=C python3 -m pytest tests/ --collect-only -q | grep '::' | LC_ALL=C sort > tests/inventario_tests.txt
"""
import subprocess
import sys
from pathlib import Path

from conftest import RAIZ

AQUI = Path(__file__).resolve().parent
INVENTARIO = AQUI / "inventario_tests.txt"
MAX_LINEAS = 800


def _foto():
    return [linea.strip() for linea in INVENTARIO.read_text(encoding="utf-8").splitlines() if linea.strip()]


def _recolectados():
    """Los tests que pytest recolecta hoy, con el MISMO comando que usa el gate."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=RAIZ, capture_output=True, text=True, timeout=300,
    )
    if r.returncode not in (0, 5):  # 5 = "no se recolectó nada"
        raise AssertionError(f"la recolección falló (exit {r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return {linea.strip() for linea in r.stdout.splitlines() if "::" in linea}


def test_no_se_perdio_ningun_test_del_inventario():
    """El candado del PR 4: los 245 bloques movidos siguen todos vivos."""
    foto = _foto()
    vivos = _recolectados()
    perdidos = sorted(set(foto) - vivos)
    assert not perdidos, (
        f"{len(perdidos)} tests del inventario ya no se recolectan: {perdidos[:8]}"
        f"{' …' if len(perdidos) > 8 else ''}. Si el movimiento fue a propósito, "
        "actualizá tests/inventario_tests.txt con el comando del docstring."
    )
    assert len(vivos) >= len(foto), f"se recolectan {len(vivos)} tests y la foto tiene {len(foto)}"


def test_ningun_archivo_de_tests_pasa_de_800_lineas():
    """El otro criterio del PR 4: la suite no vuelve a ser un archivo gigante."""
    largos = {p.name: len(p.read_text(encoding="utf-8").splitlines()) for p in sorted(AQUI.glob("test_*.py"))}
    gordos = {nombre: n for nombre, n in largos.items() if n > MAX_LINEAS}
    assert not gordos, f"archivos de test de más de {MAX_LINEAS} líneas: {gordos}"


def test_el_inventario_esta_ordenado_y_sin_repetidos():
    foto = _foto()
    assert foto == sorted(foto), "el inventario no está ordenado (regeneralo con el comando del docstring)"
    assert len(foto) == len(set(foto)), "el inventario tiene líneas repetidas"
