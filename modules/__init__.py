"""Registro de módulos del CORE.

Un módulo es un archivo Python en este paquete que exporta:
- TOOLS: esquemas de herramientas (formato OpenAI) que agrega al chat
- IMPL: {nombre_de_herramienta: implementación}

Agregar una capacidad = dejar un archivo aquí; quitarla = borrarlo.
El descubrimiento ocurre al iniciar el proceso.
"""
import importlib
import pkgutil


def discover():
    """Un módulo que falla al importar se SALTEA con aviso (antes tiraba el
    chat entero: "quitar = borrar el archivo" también debe valer para un
    archivo roto). Un nombre de tool repetido entre módulos también avisa:
    el segundo pisaba al primero en silencio."""
    import sys

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
