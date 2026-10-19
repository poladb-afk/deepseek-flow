"""exp/66: la sonda de Long Method (criterio pre-registrado, funciones puras).

El probe mide contra `requests`; los tests NO dependen de esa referencia: se
verifica la unidad de medida (cuerpo `def..fin`, anidadas incluidas), el
percentil nearest-rank, el umbral derivado de la referencia y el criterio de
señal, con fuentes sintéticas.
"""
from banco.probes.forma_larga import (
    hay_senal,
    largos_de,
    medir,
    percentil,
    proporcion_mayores,
    umbral_de_referencia,
)

FUENTE = """\
def corta():
    return 1


class Clase:
    def metodo(self):
        def interna():
            return 2
        return interna()

    def larga(self):
        a = 1
        b = 2
        return a + b
"""


def test_largos_incluye_metodos_y_anidadas():
    """La unidad es toda función (métodos y anidadas incluidas): si el gate
    futuro midiera solo top-level, el smell se escaparía por las clases."""
    assert largos_de(FUENTE) == [2, 2, 4, 4]


def test_percentil_es_nearest_rank_y_vacio_da_cero():
    assert percentil([5, 10, 15, 20], 90) == 20
    assert percentil([7, 9, 11], 50) == 9
    assert percentil([], 99) == 0


def test_umbral_sale_de_la_referencia_hacia_abajo():
    """El umbral no se elige mirando el harness: p99 de la referencia,
    redondeado hacia abajo a múltiplo de 10, con piso 10."""
    assert umbral_de_referencia([10, 20, 30, 40, 55]) == 50
    assert umbral_de_referencia([5]) == 10


def test_proporcion_y_criterio_de_senal():
    """Señal = proporción del harness >= 2x la referencia (y algo en el
    harness). El doble exacto ya califica; una diferencia chica no."""
    assert proporcion_mayores([10, 20, 30], 15) == 2 / 3
    assert hay_senal(0.10, 0.04) is True
    assert hay_senal(0.10, 0.05) is True
    assert hay_senal(0.10, 0.10) is False
    assert hay_senal(0.0, 0.0) is False


def test_medir_compara_corpus_y_aplica_el_criterio(tmp_path):
    """Con una referencia de funciones cortas (p99 < 10 → umbral 10) y un
    harness con una función de 20 líneas, la señal es trivial: mitad de las
    funciones del harness > umbral vs 0% de la referencia."""
    referencia = tmp_path / "ref.py"
    referencia.write_text("def a():\n    return 1\n\ndef b():\n    return 2\n", encoding="utf-8")
    harness = tmp_path / "harness.py"
    lineas = ["def larga():", *["    x = 1"] * 18, "    return x", "", "def corta():", "    return 0"]
    harness.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    resultado = medir([harness], [referencia])

    assert resultado["umbral"] == 10
    assert resultado["harness"]["sobre_umbral"] == 1
    assert resultado["referencia"]["sobre_umbral"] == 0
    assert resultado["senal"] is True
