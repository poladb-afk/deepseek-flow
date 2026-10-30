"""Política de riesgo de comandos: clasificador DETERMINISTA, sin LLM.

Decide cuánta fricción humana merece un comando de shell:

  - 'auto'             whitelist de solo-lectura PRESUNTA: se ejecuta sin
                       preguntar (con una línea visible de transparencia).
                       Límites conocidos: pytest ejecuta conftest/plugins y
                       escribe cachés (A45); no es solo-lectura estricta.
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
Excepción semántica: el token `2>&1` se descarta ANTES de escanear, porque
duplicar stderr al stdout ya capturado es una LECTURA de descriptor, no una
escritura; toda redirección REAL conserva su carácter cazable (`> f`,
`2> f`, `2>&1 > f` queda `> f`, `> f 2>&1` queda `> f`).

`cd` es neutro (test exhaustivo 2026-10-06: el modelo prefijó `cd <dir> &&`
en 5/5 run_command y el compuesto degradaba a preguntar aunque el fondo
fuera `pytest` auto): cambia el cwd del subshell de ESTE comando, no escribe
ni ejecuta nada — mismo nivel de confianza que `cat`, que ya lee cualquier
ruta del disco.

Límite conocido de la whitelist (A45): `pytest` ejecuta `conftest.py` y
plugins del repo, y escribe cachés (`.pytest_cache`, `__pycache__`): "auto"
no es solo-lectura en sentido estricto. Se ACEPTA porque correr tests es el
flujo normal del agente; para exigir aprobación ante ejecución de código,
HITL_AUTO=0 vuelve todo a s/n. El costo se documenta, no se esconde.

Orden de evaluación: whitelist primero, negra después, default preguntar.
"""

import json
import re
from pathlib import Path

# Niveles de riesgo, de menor a mayor fricción humana.
AUTO = "auto"
PREGUNTAR = "preguntar"
CONFIRMAR_DOBLE = "confirmar_doble"

# Las listas de la política son DATOS (fase 5a): `politica_comandos.json`,
# al lado de este archivo. Acá queda el mecanismo. Se lee UNA vez, al
# importar, y si no valida el import falla: el chat no arranca. Nunca "todo
# auto" ni "todo preguntar" en silencio (una negra vacía bajaría `rm -rf` a
# una sola confirmación). Sin setting para la ruta: no es configurable.
_ARCHIVO = Path(__file__).with_name("politica_comandos.json")
_NIVELES = (AUTO, PREGUNTAR, CONFIRMAR_DOBLE)
_CLAVES = {"prefijos": list, "flags_peligrosos": dict, "bases_modulo": list,
           "envoltorios": dict, "git_globales_con_valor": list}


def _exigir(condicion, motivo):
    if not condicion:
        raise ValueError(f"política de comandos inválida ({_ARCHIVO.name}): {motivo}")


def _es_token(t):
    return isinstance(t, str) and t != "" and t.split() == [t]


def _validar_prefijos(prefijos):
    vistos = []
    for entrada in prefijos:
        _exigir(isinstance(entrada, dict), f"entrada que no es objeto: {entrada!r}")
        tokens = entrada.get("tokens")
        _exigir(isinstance(tokens, list) and tokens and all(map(_es_token, tokens)), f"tokens: {entrada!r}")
        _exigir(entrada.get("nivel", PREGUNTAR) in _NIVELES, f"nivel desconocido: {entrada!r}")
        _exigir(isinstance(entrada.get("explicacion"), str) and entrada["explicacion"].strip(),
                f"sin explicación: {entrada!r}")
        _exigir(tokens not in vistos, f"prefijo repetido: {tokens}")
        # el primero que matchea explica: uno más corto antes lo taparía
        _exigir(not any(tokens[:len(v)] == v for v in vistos), f"{tokens} queda tapado por uno anterior")
        vistos.append(tokens)
    for nivel in _NIVELES:
        _exigir(any(e.get("nivel") == nivel for e in prefijos), f"ningún prefijo con nivel {nivel}")


def _validar_politica(datos):
    _exigir(isinstance(datos, dict), "la raíz no es un objeto")
    for clave, tipo in _CLAVES.items():
        _exigir(isinstance(datos.get(clave), tipo), f"falta `{clave}` ({tipo.__name__})")
    _validar_prefijos(datos["prefijos"])
    for base, entrada in datos["flags_peligrosos"].items():
        flags = entrada.get("flags") if isinstance(entrada, dict) else None
        _exigir(isinstance(flags, list) and flags and all(_es_token(f) and f.startswith("-") for f in flags),
                f"flags de {base}")
    for entrada in datos["bases_modulo"]:
        _exigir(isinstance(entrada, dict) and all(map(_es_token, entrada.get("prefijo") or [None]))
                and _es_token(entrada.get("base")), f"base de módulo: {entrada!r}")
    for nombre, opciones in datos["envoltorios"].items():
        _exigir(_es_token(nombre) and isinstance(opciones, list) and all(map(_es_token, opciones)),
                f"envoltorio {nombre}")
    _exigir(all(map(_es_token, datos["git_globales_con_valor"])), "git_globales_con_valor")


def _leer_politica(ruta=_ARCHIVO):
    """Los datos de la política, validados. Falla cerrada: ValueError."""
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except OSError as e:
        raise ValueError(f"política de comandos ilegible: {ruta}: {e}") from e
    _validar_politica(datos)
    return datos


_POLITICA = _leer_politica()


def _con_nivel(nivel):
    """(prefijo, explicación) de las entradas con ese nivel EXPLÍCITO: las que
    no traen nivel solo explican (clasifican al default, no a la negra)."""
    return tuple((tuple(e["tokens"]), e["explicacion"]) for e in _POLITICA["prefijos"] if e.get("nivel") == nivel)


# Prefijos exactos de solo-lectura (whitelist): la secuencia de primeros
# tokens del segmento debe COINCIDIR con uno. Conservadora a propósito.
# `echo` se admite solo sin redirección (se valida aparte). Su texto dice POR
# QUÉ no pide fricción.
_LECTURA = _con_nivel(AUTO)
_WHITELIST_PREFIJOS = tuple(p for p, _ in _LECTURA)
# La negra: siempre preguntan, o piden DOS confirmaciones (lo más peligroso;
# `rm` suelto pregunta, `rm -rf` paga doble: mesa 2).
_NEGRA_PREGUNTAR = tuple(p for p, _ in _con_nivel(PREGUNTAR))
_NEGRA_DOBLE = tuple(p for p, _ in _con_nivel(CONFIRMAR_DOBLE))
# Explicaciones de lo que no es auto (mesa 8, UX): DELIBERADAMENTE más ancha
# que la negra — mv/cp/mkdir clasifican al default 'preguntar' pero igual
# merecen SU razón en el s/n (clasificar = riesgo; explicar = UX).
_EXPLICACIONES = tuple((tuple(e["tokens"]), e["explicacion"]) for e in _POLITICA["prefijos"]
                       if e.get("nivel") != AUTO)

# Patrones de shell que impiden clasificar por prefijo: escriben, sustituyen
# o ejecutan cosas que no vemos. Cualquier aparición ⇒ 'preguntar'.
#   > < >>     redirección (escribe/lee de archivo)
#   $VAR $(..) expansión de variables y sustitución de comando (aun entre "")
#   * ? [ ~ {,} (fuera de comillas) glob, tilde y llaves: el argv real lo arma el shell
#   `...`      backticks (sustitución de comando)
#   xargs      construye y ejecuta comandos a partir de stdin
_PELIGRO_SHELL = re.compile(r">|<|\$|`|\bxargs\b")
# Expansiones que el shell hace FUERA de comillas: glob, tilde al inicio de
# palabra y llaves. `find -name '*.py'` no expande; `cat d/*` sí.
_EXPANSION = re.compile(r"[*?\[]|(?:^|[\s=:])~|\{[^}]*(?:,|\.\.)[^}]*\}")
_COMILLAS = re.compile(r"'[^']*'|\"[^\"]*\"")

# Separadores de composición que el shell ejecuta: &&, ||, |, &, ; y el
# salto de línea. Basta que uno quede afuera para que un segmento entero
# viaje sin clasificar (medido: 'ls\nrm -rf ~' y 'cat a & rm -rf b' daban auto).
_SEPARADORES = re.compile(r"&&|\|\||\||&|;|\n|\r")

# Flags que vuelven escritor/ejecutor (o colgado) a un comando de la
# whitelist; el porqué de cada base va en su `nota` del archivo.
_FLAGS_PELIGROSOS = {base: tuple(e["flags"]) for base, e in _POLITICA["flags_peligrosos"].items()}



# Descarte de stderr/stdout a /dev/null: escribir ahí no escribe en el
# filesystem, así que el `>` no es una redirección real (A39: en una sesión
# real 3 de 15 HITL fueron solo por `cat f 2>/dev/null`). Formas: 2>/dev/null,
# 1>/dev/null, >/dev/null y &>/dev/null, con o sin espacio antes de la ruta.
# Destino EXACTO: `2>/dev/nullx` (archivo real) o `2>/tmp/err` siguen cayendo
# en _PELIGRO_SHELL y preguntan.
_DESCARTE_DEVNULL = re.compile(r"(?:(?<=\s)|^)(?:[12&]?>|&>)\s*/dev/null(?=\s|$)")


def _sin_dup_stderr(segmento):
    """Quita SOLO los tokens de descarte de descriptor: `2>&1` (duplicar stderr
    al stdout ya capturado es lectura) y la basura a `/dev/null` (A39). Un
    token pegado a otro texto (p. ej. dentro de un argumento) NO se toca: sigue
    viéndose el `>` y el compuesto degrada por prudencia (A44)."""
    segmento = re.sub(r"(?:(?<=\s)|^)2>&1(?=\s|$)", "", segmento)
    return _DESCARTE_DEVNULL.sub("", segmento)


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
    # `2>&1` es una duplicación de descriptor de LECTURA (manda stderr al
    # stdout ya capturado) y `2>/dev/null` descarta a la nada: ninguno escribe
    # en el filesystem, así que se quitan antes del escaneo. Toda redirección
    # REAL conserva su carácter cazable — `> f` queda, `2> f` queda,
    # `2>&1 > f` queda como `> f`, `> f 2>&1` queda como `> f`, y
    # `2>/tmp/err` (destino distinto de /dev/null) también queda.
    segmento = _sin_dup_stderr(segmento)
    # Redirección / sustitución / expansión / xargs: nunca auto, ni para echo.
    if opaco(segmento):
        return False
    if _tiene_flag_peligroso(tokens):
        return False
    return any(_empieza_con(tokens, prefijo) for prefijo in _WHITELIST_PREFIJOS)


# Formas `python3 -m X`: el veto de flags mira el MÓDULO, no el intérprete
# (sin esto, `python3 -m ruff check --fix` esquivaba el veto de ruff).
_BASES_MODULO = {tuple(e["prefijo"]): e["base"] for e in _POLITICA["bases_modulo"]}


def _tiene_flag_peligroso(tokens):
    """True si un comando de la whitelist trae un flag que escribe/ejecuta.
    Compara el flag exacto, `--flag=x` y los grupos cortos como los lee
    getopt (`-ox`, `-uo/x`, `-qf`). `find` no agrupa: sus opciones son palabras."""
    if not tokens:
        return False
    base = _BASES_MODULO.get(tuple(tokens[:3]), tokens[0])
    flags = _FLAGS_PELIGROSOS.get(base, ())
    cortos = {f[1] for f in flags if len(f) == 2}
    for tok in tokens[1:]:
        if any(tok == flag or tok.startswith(flag + "=") for flag in flags):
            return True
        if base != "find" and cortos & set(_grupo_corto(tok)):
            return True
    return False


def _grupo_corto(tok):
    """Las letras de `-abc` como las lee getopt: `-uo/x` es -u -o (y /x es el
    valor de -o). El primer carácter que no es letra cierra el grupo."""
    if not tok.startswith("-") or tok.startswith("--"):
        return ""
    return re.match(r"[A-Za-z]*", tok[1:]).group()


# Envoltorios que ejecutan el comando que les sigue: el riesgo es el del
# comando. Sus opciones (y los valores de esas opciones) no son el comando:
# `sudo -u root rm -rf x` sigue siendo un rm -rf recursivo y forzado.
_ENVOLTORIOS = set(_POLITICA["envoltorios"])
_OPCIONES_CON_VALOR = {e: tuple(o) for e, o in _POLITICA["envoltorios"].items() if o}
# Opciones globales de git que toman un valor: `git -C . push` sigue siendo push.
_GIT_GLOBAL_CON_VALOR = set(_POLITICA["git_globales_con_valor"])


def _saltar_opciones(tokens, envoltorio):
    """Tokens del comando real: sin las opciones del envoltorio ni sus valores.
    `timeout` además lleva una DURACIÓN antes del comando (no es el comando)."""
    con_valor = _OPCIONES_CON_VALOR.get(envoltorio, ())
    while tokens and tokens[0].startswith("-"):
        if tokens[0] == "--":
            tokens = tokens[1:]
            break
        # `nice -10` (forma vieja) es un ajuste, no una opción con valor aparte.
        saltar = 2 if tokens[0] in con_valor and not re.fullmatch(r"-\d+", tokens[0]) else 1
        tokens = tokens[saltar:]
    if envoltorio == "timeout" and tokens and not tokens[0].startswith("-"):
        tokens = tokens[1:]  # la duración (5, 1m, 0.5s) no es el comando
    return tokens


def _sin_envoltorios(tokens):
    """Saca los envoltorios (y las asignaciones de env) hasta el comando real."""
    while tokens:
        base = tokens[0].rsplit("/", 1)[-1]
        if base in _ENVOLTORIOS:
            tokens = _saltar_opciones(tokens[1:], base)
            continue
        if "=" in tokens[0] and not tokens[0].startswith("-"):
            tokens = tokens[1:]  # VAR=valor antes del comando
            continue
        break
    return tokens


def _normalizar_rm(tokens):
    """`rm` recursivo+forzado en cualquier forma (incluye `-rF`) → `rm -rf`."""
    cortos = "".join(t[1:] for t in tokens[1:] if t.startswith("-") and not t.startswith("--"))
    cortos = cortos.lower()
    largos = {t for t in tokens[1:] if t.startswith("--")}
    if ("r" in cortos or "--recursive" in largos) and ("f" in cortos or "--force" in largos):
        return ["rm", "-rf"] + [t for t in tokens[1:] if not t.startswith("-")]
    return tokens


def _normalizar_git(tokens):
    """`git` sin sus opciones globales (`-C .`, `-c user.name=x`): el
    subcomando es lo que decide el riesgo."""
    resto, i = tokens[1:], 0
    while i < len(resto) and resto[i].startswith("-"):
        i += 2 if resto[i] in _GIT_GLOBAL_CON_VALOR else 1
    return ["git"] + resto[i:]


def _normalizar(tokens):
    """Tokens con el riesgo a la vista: sin envoltorios, `/bin/rm` → `rm`,
    rm recursivo+forzado como `-rf`, y git sin opciones globales.
    Solo SUBE fricción: se usa para la lista negra, nunca para la whitelist."""
    tokens = _sin_envoltorios(list(tokens))
    if not tokens:
        return tokens
    tokens[0] = tokens[0].rsplit("/", 1)[-1]
    if tokens[0] == "rm":
        return _normalizar_rm(tokens)
    if tokens[0] == "git":
        return _normalizar_git(tokens)
    return tokens


def _segmento_nivel(segmento):
    """Nivel que impone UN segmento (sin mirar composición)."""
    segmento = segmento.strip()
    if not segmento:
        return None
    tokens = _normalizar(_tokens(segmento))
    # La negra de doble confirmación gana sobre cualquier otra cosa.
    for prefijo in _NEGRA_DOBLE:
        if _empieza_con(tokens, prefijo):
            return CONFIRMAR_DOBLE
    # Luego la negra de un solo preguntar.
    for prefijo in _NEGRA_PREGUNTAR:
        if _empieza_con(tokens, prefijo):
            return PREGUNTAR
    return None


IRREVERSIBLES = tuple(" ".join(p) for p in _NEGRA_DOBLE)


def irreversible(comando):
    """True si algún segmento es de la lista doble (git push, rm -rf), ya
    normalizado: `sudo rm -rf`, `/bin/rm -fr`, `git -C . push` también."""
    return any(_segmento_nivel(s) == CONFIRMAR_DOBLE for s in segmentos(comando))


def segmentos(comando):
    """Los segmentos que el shell ejecuta por separado (&&, ||, |, &, ;, salto
    de línea). `2>&1` se quita antes: su `&` no separa nada."""
    return [s.strip() for s in _SEPARADORES.split(_sin_dup_stderr(comando)) if s.strip()]


def opaco(comando):
    """True si el shell transforma el comando antes de correrlo (redirección,
    expansión, glob, sustitución): lo que se ve no es el argv que se ejecuta."""
    comando = _sin_dup_stderr(comando)
    return bool(_PELIGRO_SHELL.search(comando) or _EXPANSION.search(_COMILLAS.sub("", comando)))


def clasificar(comando):
    """Devuelve 'auto' | 'preguntar' | 'confirmar_doble' para `comando`.

    Determinista y sin efectos: solo mira la superficie del comando.
    """
    if comando is None:
        return PREGUNTAR
    comando = str(comando).strip()
    if not comando:
        return PREGUNTAR

    # 1) La negra manda: si CUALQUIER segmento pide doble o preguntar, ese
    #    es el piso del compuesto (tomamos el nivel más alto encontrado).
    nivel = None
    partes = segmentos(comando)
    for seg in partes:
        impuesto = _segmento_nivel(seg)
        if impuesto == CONFIRMAR_DOBLE:
            return CONFIRMAR_DOBLE
        if impuesto == PREGUNTAR:
            nivel = PREGUNTAR

    # 2) Whitelist: solo si TODOS los segmentos son auto el compuesto es auto.
    #    (si un segmento no-auto ya fijó `nivel`, igual devolvemos preguntar)
    todos_auto = all(_segmento_es_auto(seg) for seg in partes)
    if todos_auto and nivel is None:
        return AUTO

    # 3) default: preguntar.
    return PREGUNTAR


def explicar(comando):
    """Explicación corta (una línea) de por qué `comando` tiene el nivel que
    tiene. El NIVEL sale de `clasificar` (misma política, composición incluida);
    la EXPLICACIÓN describe el segmento que fija ese nivel.

    La forma CRUDA manda para el texto de solo-lectura: `sudo cat` pide
    aprobación, así que decir "solo lee" en el prompt de aprobación sería
    desinformar al humano. Para la lista negra SÍ se normaliza: `sudo rm -rf`
    merece nombrar el borrado aunque el riesgo venga envuelto."""
    if comando is None or not str(comando).strip():
        return "comando vacío o inválido → se pide aprobación (default seguro)"
    comando = str(comando).strip()
    nivel = clasificar(comando)
    # En un compuesto se explica el segmento que fija el nivel, no el primero:
    # es lo que lee el humano al aprobar (`ls && rm -rf /` no es "lista").
    peor = next((x for x in segmentos(comando) if clasificar(x) == nivel), comando)
    if nivel == AUTO:
        for prefijo, texto in _LECTURA:
            if _empieza_con(_tokens(peor), prefijo):
                return texto
    for prefijo, texto in _EXPLICACIONES:
        if _empieza_con(_normalizar(_tokens(peor)), prefijo):
            return texto
    if nivel == PREGUNTAR and _tiene_flag_peligroso(_tokens(peor)):
        return "flag que escribe, ejecuta o no termina: pide aprobación"
    if nivel == AUTO:
        return "sin efectos destructivos conocidos: no pide aprobación (puede escribir cachés si el comando lo hace)"
    if nivel == CONFIRMAR_DOBLE:
        return "operación destructiva o irreversible: pide doble confirmación"
    return "efecto no reconocido como solo-lectura: pide aprobación"
