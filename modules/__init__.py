"""Registro de módulos del CORE.

Un módulo es un archivo Python en este paquete que exporta:
- TOOLS: esquemas de herramientas (formato OpenAI) que agrega al chat
- IMPL: {nombre_de_herramienta: implementación}
- HOOKS (opcional): {evento: función} para el ciclo de vida del chat

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


def discover():
    """Un módulo que falla al importar se SALTEA con aviso (antes tiraba el
    chat entero: "quitar = borrar el archivo" también debe valer para un
    archivo roto). Un nombre de tool repetido entre módulos también avisa:
    el segundo pisaba al primero en silencio."""
    tools, impls = [], {}
    for info in pkgutil.iter_modules(__path__):
        try:
            module = importlib.import_module(f"{__name__}.{info.name}")
        except Exception as e:  # noqa: BLE001 (un módulo roto no tumba el chat)
            print(f"[módulos] {info.name} no cargó ({type(e).__name__}: {e}) → se saltea",
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
    return [m.HOOKS[evento] for m in cargados if evento in getattr(m, "HOOKS", {})]
