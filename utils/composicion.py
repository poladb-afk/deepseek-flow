"""La composición declarada (X197): research + council, validada al armar.

Una composición es una cadena de `Conector`es que arranca en `pregunta` y
termina en un artefacto tipado. `componer()` la valida ANTES de gastar una
llamada. El runner pasa el contenido de cada artefacto a la tool siguiente
(como su primer parámetro requerido) y cobra todas las llamadas al mismo
`Ledger`. La declara el operador (CLI `main.py composicion`), no el modelo: un
adaptador entre tipos es un conector más (`PUENTE`), no una excepción.
"""
import argparse
import json

from modules import conectores, discover
from utils import fs_tools, kernel, tracing
from utils.conector import Artefacto, Conector, componer
from utils.kernel import Tool
from utils.terminal import recortar_chars

MAX_MOCION = 6000


def _mocion(llamada, _ctx):
    """El puente (D8=A): el informe (`borrador`) como moción del council."""
    informe = json.loads(llamada["function"].get("arguments") or "{}").get("tema", "")
    return ("Debatí si la evidencia de este informe sostiene sus conclusiones:\n"
            + recortar_chars(str(informe), MAX_MOCION, "…"))


ESQUEMA_PUENTE = {"type": "function", "function": {
    "name": "puente_research_council", "description": "Convierte el informe de research en la moción.",
    "parameters": {"type": "object", "required": ["tema"], "properties": {"tema": {"type": "string"}}}}}

PUENTE = Conector(Tool("puente_research_council", ESQUEMA_PUENTE, _mocion),
                  "pregunta", ("borrador",))

COMPOSICIONES = {"research_council": ("deep_research", "puente_research_council", "debate")}


def cadena_de(nombre):
    """Los conectores de una composición, resueltos por nombre de tool (los
    del catálogo salen de los módulos; el puente es interno). No valida la
    cadena: eso lo hace `componer()`."""
    if nombre not in COMPOSICIONES:
        raise ValueError(f"composición desconocida: {nombre!r} (hay: {sorted(COMPOSICIONES)})")
    discover()  # carga los módulos: el catálogo resuelve las aristas
    disponibles = conectores()
    try:
        return tuple(PUENTE if n == PUENTE.tool.nombre else disponibles[n]
                     for n in COMPOSICIONES[nombre])
    except KeyError as e:
        raise ValueError(f"la composición {nombre!r} necesita un conector que no está: {e}") from e


def _protegida(conector, llamada):
    """Una llamada a la tool del conector, con la protección del kernel (X146)."""
    return lambda: fs_tools.correr_protegido(lambda: conector.tool.correr(llamada, None))


def correr_composicion(nombre, tema):
    """Corre la composición: (artefacto final, llamadas que pagó el árbol).
    `componer()` valida al armar: una cadena que no encaja no gasta nada."""
    cadena = cadena_de(nombre)
    componer(*cadena)
    ledger = kernel.Ledger(1)
    artefacto = Artefacto("pregunta", tema, "usuario")
    for conector in cadena:
        requeridos = conector.tool.esquema["function"]["parameters"]["required"]
        llamada = {"function": {"name": conector.tool.nombre,
                                "arguments": json.dumps({requeridos[0]: conector.consumir(artefacto)})}}
        texto = tracing.cobrando(ledger, _protegida(conector, llamada))
        if texto.startswith("ERROR"):
            raise ValueError(texto)
        artefacto = conector.producir(texto)
    return artefacto, ledger.llamadas


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="composicion", description="Composición declarada de capacidades (research + council)")
    parser.add_argument("nombre", choices=sorted(COMPOSICIONES))
    parser.add_argument("tema", help="La pregunta que arranca la composición")
    args = parser.parse_args(argv)
    try:
        artefacto, llamadas = correr_composicion(args.nombre, args.tema)
    except ValueError as e:
        raise SystemExit(f"ERROR: {e}") from e
    print(f"\n{artefacto.contenido}")
    print(f"\n[{llamadas} llamadas del árbol]")
