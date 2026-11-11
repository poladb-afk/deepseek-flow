"""El template del módulo (X194): el conector y los tipos de artefacto.

Un módulo declara qué consume y qué produce; la composición se valida al
armar, antes de gastar una llamada, y cada artefacto viaja con su procedencia
y sus citas verificadas. El conector ES la `Tool` del kernel: el flag `agente`
decide la única arista (tool o hijo), así que S0 y el saldo llegan por
construcción. No recibe política, validador ni allowlist por parámetro (X157:
la herencia es la propiedad, no un detalle que cada módulo configure).
"""
from dataclasses import dataclass

from utils.citas import verificar_citas
from utils.fs_tools import run_tool_call
from utils.kernel import Tool

# La lista blanca, como la de comandos: los tipos los declaran los módulos y
# crece cuando un módulo real lo pide, no cuando una palabra suena bien (N2).
TIPOS = ("pregunta", "plan", "hallazgos", "veredicto", "borrador")


@dataclass(frozen=True)
class Artefacto:
    """El dato que cruza una arista: tipado, con quién lo produjo y con las
    citas que lo respaldan. Un `hallazgos` sin citas no existe: es el dato
    inventado que el módulo siguiente tomaría como hecho (la cascada)."""

    tipo: str
    contenido: str
    procedencia: str
    citas: tuple[str, ...] = ()

    def __post_init__(self):
        if self.tipo not in TIPOS:
            raise ValueError(f"tipo de artefacto desconocido: {self.tipo!r}")
        if not self.procedencia.strip():
            raise ValueError("un artefacto sin procedencia no se puede auditar")
        if self.tipo == "hallazgos" and not self.citas:
            raise ValueError("hallazgos sin citas: no hay nada que verificar")
        # dedupe solo para verificar: el campo frozen conserva orden y repetidos
        citas = tuple(dict.fromkeys(self.citas))
        if citas:
            resultado = verificar_citas(" ".join(citas))
            # una cita que el parser no reconoce tampoco es cita (total corto)
            if resultado["total"] != len(citas) or resultado["mal"]:
                raise ValueError(f"citas que no verifican: {resultado['mal'] or self.citas}")


@dataclass(frozen=True)
class Conector:
    """El borde de un módulo: la `Tool` con su única descripción (la del
    esquema, que es la que lee el de arriba) más los tipos que consume y
    produce. Los frenos no son parámetros: bajan del árbol al armar."""

    tool: Tool
    produce: str
    consume: tuple[str, ...] = ()

    def __post_init__(self):
        descripcion = self.tool.esquema.get("function", {}).get("description", "")
        if not descripcion.strip():
            raise ValueError(f"{self.tool.nombre} sin descripción: el de arriba no la ve")
        if self.produce not in TIPOS:
            raise ValueError(f"tipo de artefacto desconocido: {self.produce!r}")
        fuera = set(self.consume) - set(TIPOS)
        if fuera:
            raise ValueError(f"tipos que no existen en el conector: {sorted(fuera)}")

    def consumir(self, artefacto: Artefacto) -> str:
        """Lo que ve el módulo: el contenido del artefacto que declaró consumir."""
        if artefacto.tipo not in self.consume:
            raise ValueError(f"{self.tool.nombre} no consume {artefacto.tipo!r}: {self.consume}")
        return artefacto.contenido

    def producir(self, contenido: str, citas: tuple[str, ...] = ()) -> Artefacto:
        """El artefacto sale con la procedencia del módulo, no con la que pase
        el llamador: un módulo no puede firmar como otro."""
        return Artefacto(self.produce, contenido, self.tool.nombre, tuple(citas))


def componer(*conectores: Conector) -> tuple[Tool, ...]:
    """La composición como dato, validada al armar: arranca en `pregunta` y
    cada salida tiene que ser una entrada del siguiente. Si no encaja, el
    `ValueError` sale acá, antes de gastar una llamada (el antecedente es la
    validación de `hijas` de `kernel.loop`, X147)."""
    if not conectores:
        raise ValueError("composición vacía")
    if "pregunta" not in conectores[0].consume:
        raise ValueError(f"la composición arranca en {conectores[0].consume}, no en 'pregunta'")
    for productor, consumidor in zip(conectores, conectores[1:], strict=False):
        if productor.produce not in consumidor.consume:
            raise ValueError(
                f"{productor.produce!r} no encaja con {consumidor.consume} de {consumidor.tool.nombre}")
    return tuple(c.tool for c in conectores)


def conector_de_modulo(esquema: dict, produce: str, consume: tuple[str, ...], impls: dict) -> Conector:
    """La arista de un módulo: su tool por el DESPACHO ÚNICO (`run_tool_call`,
    donde viven hooks, denylist y HITL). El conector no re-despacha: el módulo
    corre por el mismo camino que el chat."""
    def correr(llamada, _ctx):
        return run_tool_call(llamada, impls)["content"]

    return Conector(Tool(esquema["function"]["name"], esquema, correr), produce, consume)
