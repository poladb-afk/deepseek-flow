"""Stub mínimo de `laya` (dependencia OPCIONAL: checkpoint local del operador).

El paquete real no está en `requirements-dev.txt` (el CI no lo tiene; algunas
máquinas sí), así que sin stub su tipo dependería de qué esté instalado y
movería el baseline de Pyright (X184). El único uso del producto es
`laya.load(...)`: acá se declara `Any`, igual en toda máquina.
"""
from typing import Any

def load(clave: str, *args: Any, **kwargs: Any) -> Any:
    ...
