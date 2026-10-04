"""Structured Output (patrón del doc de PocketFlow).

Técnica: pedir el resultado en un bloque ```yaml```, extraerlo, validarlo
con asserts. Un assert que revienta sube como excepción desde exec() y el
retry del Node vuelve a pedirle el YAML al modelo — la validación y el
reintento son el mismo mecanismo."""
import yaml


def extraer_yaml(texto):
    """Extrae y valida el YAML de una respuesta del modelo.

    Acepta tres formas (el modelo no siempre usa los fences):
    bloque ```yaml ...```, bloque ``` ...``` de cualquier lenguaje,
    o el texto completo si es YAML pelado. Si nada parsea, lanza —
    y el retry del Node vuelve a preguntar."""
    if "```yaml" in texto:
        bloque = texto.split("```yaml")[1].split("```")[0].strip()
    elif "```" in texto:
        bloque = texto.split("```")[1].split("```")[0].strip()
    else:
        bloque = texto.strip()
    datos = yaml.safe_load(bloque)
    assert isinstance(datos, dict), "el YAML no es un diccionario"
    return datos
