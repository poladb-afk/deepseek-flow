"""Política de riesgo de comandos: clasificador DETERMINISTA, sin LLM.

Decide cuánta fricción humana merece un comando de shell:

  - 'auto'             solo-lectura verificado: se ejecuta sin preguntar
                       (con una línea visible de transparencia).
  - 'preguntar'        el flujo HITL de siempre: un (s/n).
  - 'confirmar_doble'  dos (s/n) seguidos: la operación más peligrosa
                       (git push, rm -rf) paga la fricción extra.

Es código puro: mismo comando ⇒ misma clasificación, siempre. Sin
dependencias y sin red. El default de todo lo no reconocido es
'preguntar': la política solo RELAJA cuando el comando está en una
whitelist conservadora de solo-lectura; todo lo demás pregunta como hoy.

Regla de composición (la parte crítica): el comando se parte por `&&`,
`|` y `;`, y TODOS los segmentos deben ser 'auto' para que el compuesto sea
'auto'. Basta un segmento sospechoso para que todo pregunte — un
`ls && rm -rf /` NO es auto, y un `ls ; rm -rf /` tampoco (el `;` parte
igual que `&&`: medido en el test exhaustivo del 2026-10-06, antes de
partirlo `ls ; rm -rf /tmp/x` clasificaba 'auto' y el rm corría sin
aprobación). Además, la mera presencia de redirección (`>`, `<`, `>>`),
sustitución `$(...)`, backticks o `xargs` degrada a 'preguntar': escriben
o ejecutan lo que no podemos ver clasificar por prefijo. `python3 -c`
pregunta SIEMPRE (código arbitrario, aunque hoy lo usemos para repros).

`cd` es neutro (test exhaustivo 2026-10-06: el modelo prefijó `cd <dir> &&`
en 5/5 run_command y el compuesto degradaba a preguntar aunque el fondo
fuera `pytest` auto): cambia el cwd del subshell de ESTE comando, no escribe
ni ejecuta nada — mismo nivel de confianza que `cat`, que ya lee cualquier
ruta del disco.

Orden de evaluación: whitelist primero, negra después, default preguntar.
"""

import re

# Niveles de riesgo, de menor a mayor fricción humana.
AUTO = "auto"
PREGUNTAR = "preguntar"
CONFIRMAR_DOBLE = "confirmar_doble"

# Prefijos exactos de solo-lectura: la secuencia de primeros tokens del
# segmento debe COINCIDIR exactamente con uno de estos. Conservadora a
# propósito — solo herramientas que no escriben ni ejecutan nada del
# usuario. `echo` se admite solo sin redirección (se valida aparte).
_WHITELIST_PREFIJOS = (
    ("pytest",),
    ("python3", "-m", "pytest"),
    ("grep",),
    ("ls",),
    ("cat",),
    ("head",),
    ("tail",),
    ("wc",),
    ("find",),
    ("file",),
    ("echo",),
    ("git", "status"),
    ("git", "log"),
    ("git", "diff"),
    ("git", "show"),
    ("git", "blame"),
    # neutros: no leen ni escriben nada por sí mismos
    ("cd",),
    ("sort",),
)

# Comandos que SIEMPRE preguntan (aunque no tengan redirección ni xargs).
# python3 -c: código arbitrario disfrazado de comando de una línea.
_NEGRA_PREGUNTAR = (
    ("python3", "-c"),
    ("python", "-c"),
    ("rm",),
    ("pip",),
    ("pip3",),
    ("git", "commit"),
    ("git", "checkout"),
    ("git", "reset"),
)

# Comandos que piden DOS confirmaciones: lo más peligroso del inventario.
# rm -rf/-fr entra acá (("rm",) suelto queda en preguntar): la
# especificación de la mesa 2 le exige doble fricción a lo destructivo.
_NEGRA_DOBLE = (
    ("git", "push"),
    ("rm", "-rf"),
    ("rm", "-fr"),
)

# Patrones de shell que impiden clasificar por prefijo: escriben, sustituyen
# o ejecutan cosas que no vemos. Cualquier aparición ⇒ 'preguntar'.
#   > < >>     redirección (escribe/lee de archivo)
#   $(...)     sustitución de comando
#   `...`      backticks (sustitución de comando)
#   xargs      construye y ejecuta comandos a partir de stdin
_PELIGRO_SHELL = re.compile(r">|<|\$\(|`|\bxargs\b")


def _tokens(segmento):
    """Tokens del segmento, sin espacios vacíos. No interpretamos quoting:
    el prefijo se compara literal (conservador — cualquier rareza que
    cambie el primer token visible cae en el default 'preguntar')."""
    return segmento.split()


def _empieza_con(tokens, prefijo):
    return tuple(tokens[: len(prefijo)]) == prefijo


def _segmento_es_auto(segmento):
    segmento = segmento.strip()
    if not segmento:
        return True  # segmento vacío (p. ej. trailing &&) no aporta riesgo
    tokens = _tokens(segmento)
    if not tokens:
        return True
    # Redirección / sustitución / xargs: nunca auto, ni siquiera para echo.
    if _PELIGRO_SHELL.search(segmento):
        return False
    return any(_empieza_con(tokens, prefijo) for prefijo in _WHITELIST_PREFIJOS)


def _segmento_nivel(segmento):
    """Nivel que impone UN segmento (sin mirar composición)."""
    segmento = segmento.strip()
    if not segmento:
        return None
    tokens = _tokens(segmento)
    # La negra de doble confirmación gana sobre cualquier otra cosa.
    for prefijo in _NEGRA_DOBLE:
        if _empieza_con(tokens, prefijo):
            return CONFIRMAR_DOBLE
    # Luego la negra de un solo preguntar.
    for prefijo in _NEGRA_PREGUNTAR:
        if _empieza_con(tokens, prefijo):
            return PREGUNTAR
    return None


def clasificar(comando):
    """Devuelve 'auto' | 'preguntar' | 'confirmar_doble' para `comando`.

    Determinista y sin efectos: solo mira la superficie del comando.
    """
    if comando is None:
        return PREGUNTAR
    comando = str(comando).strip()
    if not comando:
        return PREGUNTAR

    # Partimos por &&, | y ; (los separadores de composición que importan:
    # el shell ejecuta los tres, ver docstring).
    segmentos = re.split(r"&&|\||;", comando)

    # 1) La negra manda: si CUALQUIER segmento pide doble o preguntar, ese
    #    es el piso del compuesto (tomamos el nivel más alto encontrado).
    nivel = None
    for seg in segmentos:
        impuesto = _segmento_nivel(seg)
        if impuesto == CONFIRMAR_DOBLE:
            return CONFIRMAR_DOBLE
        if impuesto == PREGUNTAR:
            nivel = PREGUNTAR

    # 2) Whitelist: solo si TODOS los segmentos son auto el compuesto es auto.
    #    (si un segmento no-auto ya fijó `nivel`, igual devolvemos preguntar)
    todos_auto = all(_segmento_es_auto(seg) for seg in segmentos)
    if todos_auto and nivel is None:
        return AUTO

    # 3) default: preguntar.
    return PREGUNTAR


# Explicaciones cortas por prefijo (mesa 8, UX): por qué el comando merece
# la fricción que merece. Determinista, sin LLM — es un rótulo, no un juicio.
_EXPLICACIONES = (
    (("rm", "-rf"), "borrado recursivo forzado (destructivo)"),
    (("rm", "-fr"), "borrado recursivo forzado (destructivo)"),
    (("rm",), "borra archivos"),
    (("git", "push"), "publica commits al remoto (irreversible en el server)"),
    (("git", "commit"), "crea un commit en tu repo local"),
    (("git", "checkout"), "cambia de rama/descarta cambios de working tree"),
    (("git", "reset"), "mueve HEAD (puede descartar cambios)"),
    (("pip",), "instala paquetes (modifica el entorno)"),
    (("pip3",), "instala paquetes (modifica el entorno)"),
    (("python3", "-c"), "código Python arbitrario en una línea"),
    (("python", "-c"), "código Python arbitrario en una línea"),
    (("mv",), "mueve o renombra archivos"),
    (("cp",), "copia archivos"),
    (("mkdir",), "crea directorios"),
    (("touch",), "crea o actualiza archivos"),
)

# Solo-lectura conocida: la explicación dice POR QUÉ no pide fricción.
_LECTURA = (
    (("pytest",), "corre tests (solo lee)"),
    (("python3", "-m", "pytest"), "corre tests (solo lee)"),
    (("grep",), "busca texto (solo lee)"),
    (("ls",), "lista un directorio (solo lee)"),
    (("cat",), "muestra un archivo (solo lee)"),
    (("head",), "muestra el inicio de un archivo (solo lee)"),
    (("tail",), "muestra el final de un archivo (solo lee)"),
    (("wc",), "cuenta líneas/palabras (solo lee)"),
    (("find",), "busca archivos (solo lee)"),
    (("file",), "identifica el tipo de archivo (solo lee)"),
    (("echo",), "imprime texto"),
    (("git", "status"), "estado del repo (solo lee)"),
    (("git", "log"), "historial de commits (solo lee)"),
    (("git", "diff"), "cambios sin commitear (solo lee)"),
    (("git", "show"), "contenido de un objeto (solo lee)"),
    (("git", "blame"), "autoría por línea (solo lee)"),
    (("cd",), "cambia de directorio (solo afecta al subshell del comando)"),
    (("sort",), "ordena líneas (solo lee)"),
)


def explicar(comando):
    """Explicación corta (una línea) de por qué `comando` tiene el nivel que
    tiene. Determinista y sin LLM: la misma política que `clasificar`. Si el
    comando no matchea ningún patrón conocido, describe el nivel por defecto."""
    if comando is None or not str(comando).strip():
        return "comando vacío o inválido → se pide aprobación (default seguro)"
    comando = str(comando).strip()
    nivel = clasificar(comando)
    tokens = comando.split()
    for prefijo, texto in _LECTURA:
        if tuple(tokens[: len(prefijo)]) == prefijo:
            return texto
    for prefijo, texto in _EXPLICACIONES:
        if tuple(tokens[: len(prefijo)]) == prefijo:
            return texto
    if nivel == AUTO:
        return "solo-lectura verificado: no cambia nada"
    if nivel == CONFIRMAR_DOBLE:
        return "operación destructiva o irreversible: pide doble confirmación"
    return "efecto no reconocido como solo-lectura: pide aprobación"
