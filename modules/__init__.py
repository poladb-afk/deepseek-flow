"""Registro de módulos del CORE.

Un módulo es un archivo Python en este paquete que exporta:
- TOOLS: esquemas de herramientas (formato OpenAI) que agrega al chat
- IMPL: {nombre_de_herramienta: implementación}
- HOOKS (opcional): {evento: función} para el ciclo de vida del chat
- CONECTORES (opcional): tupla de `utils.conector.Conector` con los tipos de
  artefacto que el módulo consume y produce (X194). Se validan al armar: un
  módulo que declara otra cosa se saltea, como uno que no importa.

Agregar una capacidad = dejar un archivo aquí; quitarla = borrarlo.
El descubrimiento ocurre al iniciar el proceso.

Eventos de HOOKS (el CORE los recorre sin saber qué módulo los aporta):
- `al_arrancar(shared)` y `al_salir(shared)`: bookkeeping de la sesión, en
  orden de nombre de módulo al arrancar y en el inverso al salir.
- `al_compactar(mensajes, shared)`: antes de descartar la zona fría de
  `mensajes`, la guarda y devuelve dónde (o None). La primera ruta es la que
  nombra el marcador `[compacción]`.
Un gancho no lanza: su fallo es del módulo, que lo degrada a no-op.
"""
import importlib
import pkgutil
import sys

from utils.conector import Conector


def discover():
    """Un módulo que falla al importar se SALTEA con aviso (antes tiraba el
    chat entero: "quitar = borrar el archivo" también debe valer para un
    archivo roto). Un nombre de tool repetido entre módulos también avisa:
    el segundo pisaba al primero en silencio.

    X194: los `CONECTORES` declarados se validan acá, antes de que sus tools
    entren al chat. Un módulo con un conector que no es del template se saltea
    entero: la composición no arranca con una arista que no encaja."""
    tools, impls = [], {}
    for info in pkgutil.iter_modules(__path__):
        try:
            module = importlib.import_module(f"{__name__}.{info.name}")
        except Exception as e:  # noqa: BLE001 (un módulo roto no tumba el chat)
            print(f"[módulos] {info.name} no cargó ({type(e).__name__}: {e}) → se saltea",
                  file=sys.stderr)
            continue
        conectores = getattr(module, "CONECTORES", ())
        if not isinstance(conectores, tuple) or not all(type(c) is Conector for c in conectores):
            print(f"[módulos] {info.name} declara conectores que no son del template → se saltea",
                  file=sys.stderr)
            continue
        nuevos = getattr(module, "IMPL", {})
        for nombre in set(nuevos) & set(impls):
            print(f"[módulos] {info.name} redefine la tool '{nombre}'", file=sys.stderr)
        tools.extend(getattr(module, "TOOLS", []))
        impls.update(nuevos)
    return tools, impls


def ganchos(evento):
    """Las funciones que los módulos presentes registran para `evento`, en
    orden de nombre de módulo. Solo los ya cargados por `discover()`: un
    módulo roto no se reintenta (ni re-avisa) en cada evento."""
    cargados = (sys.modules.get(f"{__name__}.{info.name}") for info in pkgutil.iter_modules(__path__))
    return [m.HOOKS[evento] for m in cargados if m is not None and evento in getattr(m, "HOOKS", {})]
