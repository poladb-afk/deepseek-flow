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
    tools, impls = [], {}
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        tools.extend(getattr(module, "TOOLS", []))
        impls.update(getattr(module, "IMPL", {}))
    return tools, impls
