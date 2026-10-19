"""Pulido de terminal (mesa 8): color por tipo de evento y progreso de rondas.

Dos piezas chicas y sin dependencias; el resto del harness las llama y
todo degrada a texto plano cuando la salida no es una terminal (pipes,
tests, `.runs`), así que nada cambia en logs ni en CI.

- **colorear(texto, tipo)**: devuelve el texto con códigos ANSI según el
  TIPO de evento (`tool`, `error`, `ok`, `info`, `aviso`, `respuesta`).
  Con `NO_COLOR` en el entorno, o cuando stdout NO es un tty, no colorea
  (regla estándar: el color es para humanos mirando la terminal).
- **progreso_ronda(ronda, tope)**: etiqueta `⚙ ronda 2/8` para las rondas
  largas de herramientas, para que una espera de varios segundos no parezca
  colgada. Sin tope conocido muestra solo la ronda.

`COLOR=0` apaga el color aunque haya tty (escape hatch), igual que `NO_COLOR`.
"""
import os
import sys

# Códigos ANSI por tipo de evento. Deliberadamente pocos y sobrios.
_CODIGOS = {
    "tool": "\033[36m",       # cian: herramienta en ejecución
    "ok": "\033[32m",         # verde: resultado ok
    "error": "\033[31m",      # rojo: error / rechazo
    "info": "\033[90m",       # gris: trazas y metadatos
    "aviso": "\033[33m",      # amarillo: sanitizado, interrupción
    "respuesta": "\033[1m",   # negrita: la respuesta del modelo
}
_RESET = "\033[0m"


def _quiere_color():
    """True solo si la salida es una terminal interactiva y no se pidió
    apagarlo (NO_COLOR es el estándar; COLOR=0 es nuestro escape hatch)."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("COLOR", "1") == "0":
        return False
    return sys.stdout.isatty()


def colorear(texto, tipo="info"):
    """Colorea `texto` según el tipo de evento. Sin color disponible,
    devuelve el texto intacto (los tests y los pipes no ven códigos)."""
    if not _quiere_color():
        return texto
    codigo = _CODIGOS.get(tipo)
    if not codigo:
        return texto
    return f"{codigo}{texto}{_RESET}"


def progreso_ronda(ronda, tope=None):
    """Etiqueta de progreso de una ronda de herramientas: `⚙ ronda 2/8`.
    Sin tope, `⚙ ronda 2`. No decide si imprimir: eso es del llamador."""
    if tope:
        return f"⚙ ronda {int(ronda)}/{int(tope)}"
    return f"⚙ ronda {int(ronda)}"


_TIPOS_DIFF = (("+++", "info"), ("---", "info"), ("+", "ok"),
               ("-", "error"), ("@@", "tool"))


def _tipo_de_linea_diff(linea):
    """Tipo de color de una línea de diff unificado (None = sin color)."""
    for prefijo, tipo in _TIPOS_DIFF:
        if linea.startswith(prefijo):
            return tipo
    return None


def highlight_diff(diff):
    """Colorea un diff unificado línea por línea (mesa 8): verde las
    adiciones (`+`, no `+++`), rojo las supresiones (`-`, no `---`), cian
    las cabeceras (`@@`). Sin tty o con el color apagado, devuelve el diff
    intacto: los tests, los pipes y los `.runs` no ven códigos."""
    if not _quiere_color():
        return diff
    lineas = []
    for linea in diff.splitlines():
        tipo = _tipo_de_linea_diff(linea)
        lineas.append(colorear(linea, tipo) if tipo else linea)
    return "\n".join(lineas)


def recortar_chars(texto, maximo, marca="[... recortado ...]"):
    """Recorta por CARACTERES: mitad inicial + marca + mitad final.

    Unificada en el PR 3: modules/coding.py y modules/escritura.py tenían dos
    variantes distintas con el MISMO nombre _clip (chars y lineas)."""
    if len(texto) <= maximo:
        return texto
    mitad = maximo // 2
    return texto[:mitad] + f"\n{marca}\n" + texto[-mitad:]


def recortar_lineas(texto, maximo, marca="[... recortado ...]"):
    """Recorta por LINEAS: una vista previa de diff no se mide en chars."""
    lineas = texto.splitlines()
    if len(lineas) <= maximo:
        return texto
    mitad = maximo // 2
    return "\n".join(lineas[:mitad] + [marca] + lineas[-mitad:])
