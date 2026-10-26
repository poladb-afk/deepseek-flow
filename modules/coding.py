"""Módulo `coding`: run_command y edit_file con aprobación humana (HITL).

El agente de archivos se vuelve agente de código: ejecutar comandos y
editar quirúrgicamente. Nada se ejecuta sin un 's' del usuario — para
shell esa aprobación ES la contención (un comando llega a donde las
raíces permitidas de las tools de archivos no llegan; decirlo explícito
es parte del contrato). Rieles mecánicos: timeout, salida truncada (el
resultado viaja al historial del chat), stdin cerrado para que nada
quede esperando input interactivo. Con HITL graduado, solo los comandos
de solo-lectura verificado se saltan el 's' (con el comando igual a la
vista); el resto mantiene la aprobación.

edit_file es reemplazo exacto y único: la lección medida del clobber de
fs_tools.py — write_file de archivo entero lo pisó con un fragmento
(282→16 líneas). Un edit que falla ruidosamente (no existe / no es
único) obliga al modelo a volver al archivo en vez de reescribirlo de
memoria. write_file queda para archivos nuevos o reescrituras totales.

HITL graduado (mesa 2): con HITL_AUTO=1 (default) `utils/policy.py`
clasifica el comando ANTES del preview. Solo los de solo-lectura
verificado (whitelist determinista) se ejecutan 'auto', con una línea
visible de transparencia; el resto pregunta como siempre y lo más
peligroso (git push, rm -rf) pide dos confirmaciones. Con HITL_AUTO=0
todo vuelve al s/n de hoy (compatibilidad).
"""
import difflib
import re as _re
import subprocess
from pathlib import Path

from utils.aprobaciones import Pedido, pedir_aprobacion
from utils.aprobaciones import registrar as registrar_aprobacion
from utils.call_llm import _setting
from utils.estado_sesion import ultimo_usuario
from utils.fs_tools import _resolve, escribir_atomico
from utils.policy import clasificar, explicar, segmentos
from utils.riesgo import juzgar
from utils.riesgo import registrar as registrar_riesgo
from utils.terminal import colorear, highlight_diff, recortar_chars

TIMEOUT_S = 120
SALIDA_MAX = 4000  # chars: el resultado entra al historial y al costo
PREVIEW_LINES = 30


# Patrones de comandos PROHIBIDOS sin excepción (denylist dura): no hay s/n
# que los apruebe. Corre como hook PRE (HOOKS_PRE["run_command"]), es decir
# ANTES de que el comando exista siquiera como propuesta: un hook post ya
# llegaría tarde a un comando que ya corrió. La lista es deliberadamente
# corta y de daño irreversible — la política graduada (utils/policy.py) ya
# cubre el resto con fricción; acá solo va lo que NUNCA debería ejecutarse
# desde un chat automatizado (borrado de disco/fork bomb en el host).
_PROHIBIDOS = _re.compile(
    r"(?:^|[;&|`(\n]|\s)\s*(?:sudo\s+)?"             # inicio de segmento (+ sudo)
    r"(?:(?:/usr)?/bin/)?rm\s+"                       # rm, /bin/rm, /usr/bin/rm
    r"(?=(?:\S*\s+)*?-(?:[a-zA-Z]*[rR][a-zA-Z]*|-recursive)\b)"  # algún flag recursivo
    r"(?:\S+\s+)*?"                                  # flags en cualquier orden (-r -f)
    r"(?:--no-preserve-root\s+)?"
    r"(?:/\*?|~/?\*?|\$HOME/?\*?|/\.\*?)(?:\s+--no-preserve-root)?\s*(?:$|[;&|\n])"  # /, /*, ~, $HOME
    r"|:\s*\(\s*\)\s*\{"                             # :(){ :|:& };  fork bomb
)


def _vetar_comando_prohibido(tool_call):
    """Hook PRE de run_command: si el comando matchea la denylist dura,
    CANCELA la ejecución devolviendo el veto como texto (el modelo lo ve y
    se autocorrige); si no, devuelve None (no opina). Nunca lanza."""

    import json as _json

    try:
        args = _json.loads(tool_call["function"].get("arguments") or "{}")
        comando = args.get("command") or ""
    except (ValueError, TypeError, AttributeError):  #  # noqa: BLE001 (argumentos del tool call: JSON no confiable)
        return None
    if comando and _PROHIBIDOS.search(comando):
        # Fix 10a: línea VERBATIM de la spec — el ancla de
        # MARCADORES["veto_denylist"] es el formato impreso, no el vocabulario
        # ni el comando que eligió el modelo.
        print(colorear("  [denylist] comando vetado (daño irreversible): "
                       "no se ejecutó ni se pidió aprobación", "error"), flush=True)
        return (
            "ERROR: comando prohibido por la denylist de seguridad (daño "
            "irreversible en el host); no se ejecutó ni se pidió aprobación. "
            "Reformulá el comando acotado a un directorio del proyecto."
        )
    return None


def _registrar_hooks():
    """Engancha el denylist de run_command al registro PRE del CORE. Se hace
    acá (no en fs_tools) para que la política de coding viaje con su módulo."""
    from utils.fs_tools import HOOKS_PRE

    if _vetar_comando_prohibido not in HOOKS_PRE.get("run_command", []):
        HOOKS_PRE.setdefault("run_command", []).append(_vetar_comando_prohibido)


_registrar_hooks()


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Ejecuta un comando de shell (tests, git, python, herramientas del sistema) "
                "y devuelve código de salida más la salida combinada. Requiere aprobación "
                "humana en la terminal antes de ejecutar; un rechazo se devuelve como texto. "
                "El comando corre en el directorio de trabajo actual, sin stdin, con tope de "
                "2 minutos y salida truncada."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "El comando a ejecutar"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Edita un archivo de forma quirúrgica: reemplaza old_string por new_string "
                "(una sola ocurrencia, texto EXACTO copiado del archivo). Muestra el diff y "
                "pide aprobación humana. Falla si old_string no aparece o aparece varias "
                "veces: usá read_file y copiá literal, no reescribas de memoria. Para "
                "archivos nuevos o reescrituras completas usá write_file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta absoluta o relativa a un directorio permitido"},
                    "old_string": {"type": "string", "description": "Texto exacto a reemplazar (único en el archivo)"},
                    "new_string": {"type": "string", "description": "Texto de reemplazo (vacío = borrar)"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
]


def _approve(pedido):
    """Punto de parcheo de los tests: la lógica vive en utils/aprobaciones."""
    return pedir_aprobacion(pedido)


NEUTROS_SHELL = {"", "&&", "||", "|", "&", ";", "\n", "\r"}


def _dentro_de_raices(destino, roots):
    """El destino está en una raíz permitida (o es una)."""
    return any(destino == r or r in destino.parents for r in roots)


def _resolver_token(tok, cwd_efectivo):
    """Token → ruta resuelta (siguiendo symlinks) desde el cwd efectivo."""
    p = Path(tok)  # `~` no se expande: _fuera_de_raices ya lo trata como opaco
    if not p.is_absolute():
        p = cwd_efectivo / p
    try:
        return p.resolve()
    except OSError:
        return p


def _fuera_de_raices(tok, cwd_efectivo, roots):
    """True si el token (ruta, --flag=/ruta o $VAR) puede tocar fuera."""
    if tok in NEUTROS_SHELL:
        return False
    if tok.startswith(("$", "~")):
        return True  # $HOME, $VAR, ~user: el destino real no es visible
    if tok.startswith("-"):
        if "=" not in tok:
            return False
        tok = tok.split("=", 1)[1]
        if not tok:
            return False
    return not _dentro_de_raices(_resolver_token(tok, cwd_efectivo), roots)


def _cd(destinos, cwd_efectivo, roots):
    """El cwd tras `cd <destinos>`, o None si puede quedar fuera de las raíces.
    `cd` solo va a $HOME y `cd -` al OLDPWD: ninguno es visible acá."""
    if len(destinos) != 1 or destinos[0] == "-":
        return None
    resuelto = _resolver_token(destinos[0], cwd_efectivo)
    if not _dentro_de_raices(resuelto, roots):
        return None
    return resuelto if resuelto.is_dir() else cwd_efectivo


def _sale_de_raices(command):
    """True si el comando puede tocar (leer/escribir) fuera de las raíces.

    Auditoría F2: el chequeo lexical anterior dejaba pasar symlinks dentro de
    las raíces que resuelven afuera (`cat link` → auto leía /etc) y `cd sub`
    cambiaba el cwd del subshell sin que el chequeo lo supiera. Ahora cada
    token se resuelve como ruta (siguiendo symlinks) contra el cwd EFECTIVO
    del subshell, y `--flag=/ruta` también se resuelve. Los segmentos salen
    del MISMO partidor que usa la policy: `cd ..;cat x` son dos comandos para
    el shell y para este chequeo (auditoría 2026-10-26, S3). Ante la duda, True."""
    import shlex

    from utils.fs_tools import allowed_roots

    roots = allowed_roots()
    cwd_efectivo = Path.cwd()
    for segmento in segmentos(command):
        try:
            tokens = shlex.split(segmento)
        except ValueError:
            return True  # comillas desbalanceadas: no se puede verificar
        if tokens and tokens[0] == "cd":
            cwd_efectivo = _cd(tokens[1:], cwd_efectivo, roots)
            if cwd_efectivo is None:
                return True
            continue
        if any(_fuera_de_raices(tok, cwd_efectivo, roots) for tok in tokens):
            return True
    return False


RECHAZO = ("RECHAZADO por el usuario: el comando no se ejecutó. "
           "Puedes proponer otro o preguntar qué cambiaría.")
RECHAZO_DOBLE = ("RECHAZADO por el usuario: el comando no se ejecutó (segunda confirmación). "
                 "Puedes proponer otro o preguntar qué cambiaría.")


def _nivel(command):
    """Clasificación del comando + los dos ajustes de la casa.

    'auto' = solo-lectura verificado → ejecuta directo, pero SIEMPRE se imprime
    el comando (transparencia: el usuario lo ve igual) — y 'auto' solo vale
    DENTRO del proyecto: un cat/grep/find a una ruta fuera de
    AGENT_ALLOWED_DIRS vuelve a pedir aprobación. HITL_AUTO=0 devuelve el s/n
    de siempre."""
    nivel = clasificar(command)
    if nivel == "auto" and _sale_de_raices(command):
        nivel = "preguntar"
    if _setting("HITL_AUTO", "1") != "1":
        nivel = "preguntar"
    return nivel


def _observar_riesgo(command, nivel):
    """exp/44 — OBSERVACIÓN de riesgo (el s/n NO cambia): solo en las bandas
    que un humano gatea (preguntar/confirmar_doble). 'auto' y la denylist NO
    se juzgan: las reglas duras van primero. Sin LAYA_MODEL_RIESGO, juzgar()
    devuelve None y todo queda no-op."""
    if nivel not in ("preguntar", "confirmar_doble"):
        return None
    juicios = juzgar(command, ultimo_usuario())
    if juicios:
        resumen = " · ".join(f"{k.split('_')[0]}={v[0]} {v[1]:.2f}"
                             for k, v in juicios.items())
        print(colorear(f"  [riesgo] observa: {resumen}", "info"))
    return juicios


def _registrar_riesgo(command, juicios, aprobado):
    """El riesgo se registra UNA vez por corrida, junto a la aprobación o su
    rechazo, y solo si hubo observación."""
    if juicios is not None:
        registrar_riesgo(command, ultimo_usuario(), juicios, aprobado)


def _aprobar(command, nivel, juicios):
    """Pide lo que el nivel exija, en orden, y registra cada respuesta.
    Devuelve (aprobado, motivo del rechazo): el preview y el pedido viven
    juntos para que no se pueda agregar un nivel sin su registro."""
    if nivel == "auto":
        # Rótulo histórico: "solo-lectura" es PRESUNCIÓN por prefijo, no una
        # garantía (pytest ejecuta conftest y escribe cachés: ver A45 en policy).
        print(f"\n── run_command [auto: solo-lectura] ──\n{command}")
        return True, ""
    if nivel == "confirmar_doble":
        print("\n── run_command [¡doble confirmación!] ──")
        preguntas = (("¿Seguro? (1/2)", RECHAZO),
                     ("¿Confirmás de nuevo? (2/2)", RECHAZO_DOBLE))
    else:  # 'preguntar': el flujo de hoy
        print("\n── run_command ──")
        preguntas = (("¿Ejecutar?", RECHAZO),)
    print(f"   ↳ {explicar(command)}")
    print(command)
    for pregunta, motivo_rechazo in preguntas:
        decision = _approve(Pedido(pregunta, command, "comando", command, nivel))
        if decision:
            continue
        registrar_aprobacion("run_command", command, False, nivel)
        _registrar_riesgo(command, juicios, False)
        motivo = getattr(decision, "motivo", "")
        if motivo:
            return False, f'{motivo_rechazo} Motivo del humano: "{motivo}"'
        return False, motivo_rechazo
    registrar_aprobacion("run_command", command, True, nivel)
    _registrar_riesgo(command, juicios, True)
    return True, ""


def _ejecutar(command):
    """Corre el comando ya aprobado y arma la salida que ve el modelo."""
    try:
        r = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            stdin=subprocess.DEVNULL,
            cwd=Path.cwd(),
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: timeout de {TIMEOUT_S}s — el comando no terminó (¿loop infinito o esperaba algo?)"
    salida = (r.stdout or "").strip()
    if r.stderr:
        salida += (("\n" if salida else "") + "[stderr]\n" + r.stderr.strip()).rstrip()
    salida = recortar_chars(salida, SALIDA_MAX, "[... salida truncada ...]")
    return f"exit {r.returncode}\n{salida or '(sin salida)'}"


def run_command(command):
    if not command or not str(command).strip():
        return "ERROR: comando vacío"
    command = str(command)

    nivel = _nivel(command)                               # clasificar + raíces + HITL_AUTO
    juicios = _observar_riesgo(command, nivel)            # exp/44: solo bandas humanas
    aprobado, motivo = _aprobar(command, nivel, juicios)  # auto / s-n / doble s-n
    if not aprobado:
        return motivo
    return _ejecutar(command)                             # subprocess + timeout + recorte


def _normalizar_ws(s):
    """Normaliza whitespace para el diagnóstico: tabs→4 espacios y sin
    espacios al final de línea. Sirve para DISTINGUIR la causa clásica
    del no-match (indentación/copiado a mano) sin perdonar el match."""
    return "\n".join(
        linea.expandtabs(4).rstrip() for linea in s.splitlines()
    ).strip("\n")


def _contiene_subsecuencia(lineas_txt, lineas_old):
    """True si la secuencia normalizada de old_string aparece como bloque
    contiguo (al menos 2 líneas) dentro de la del texto: señal de que el
    no-match es solo por espacios/tabs, no por texto equivocado."""
    if not lineas_old or len(lineas_old) > len(lineas_txt):
        return False
    alto = len(lineas_old)
    # una sola línea: basta que alguna línea del texto normalice igual
    # (el caso clásico: tab vs espacios en la misma línea)
    if alto == 1:
        return lineas_old[0] in lineas_txt
    return any(
        lineas_txt[i : i + alto] == lineas_old
        for i in range(len(lineas_txt) - alto + 1)
    )


def candidatos_similares(texto, old_string, max_candidatos=3):
    """Top ventanas de líneas parecidas a old_string (difflib): para que
    el modelo corrija en UN intento sin releer el archivo entero. Cada
    candidato es (num_linea_inicio_base_1, excerpt). Ventanas del mismo
    alto que old_string; si old_string tiene 1 línea, ventanas de 1.
    Empates y orden por ratio descendente."""
    lineas = texto.splitlines()
    objetivo = old_string.splitlines()
    alto = len(objetivo) or 1
    if not lineas:
        return []

    evaluados = []
    for i in range(len(lineas) - alto + 1):
        ventana = lineas[i : i + alto]
        # ratio sobre el texto UNIDO (caracteres): sobre listas de líneas
        # SequenceMatcher compararía líneas enteras y toda casi-igual daría 0
        ratio = difflib.SequenceMatcher(None, "\n".join(ventana), "\n".join(objetivo)).ratio()
        evaluados.append((ratio, i + 1, "\n".join(ventana)))

    evaluados.sort(key=lambda c: c[0], reverse=True)
    mejores = [c for c in evaluados if c[0] > 0.5]
    return [(num, excerpt) for _, num, excerpt in mejores[:max_candidatos]]


def _lineas_ocurrencias(texto, old_string):
    """Números de línea (base 1) donde EMPIEZA cada ocurrencia de
    old_string — para el mensaje de ambigüedad (n > 1)."""
    lineas = texto.splitlines()
    n_lineas_old = len(old_string.splitlines())
    inicios = []
    for idx in range(len(lineas) - n_lineas_old + 1):
        if "\n".join(lineas[idx : idx + n_lineas_old]) == old_string:
            inicios.append(idx + 1)
    return inicios


def _error_no_aparece(resolved, texto, old_string):
    """El error más caro de la casa (63% de los fallos medidos del harness):
    dice QUÉ pasó, si el texto coincide salvo espacios y qué líneas se le
    parecen. Va aparte para que edit_file se lea como su contrato."""
    mensaje = (
        f"ERROR: old_string no aparece en {resolved.name}. "
        "Leé el archivo con read_file y copiá el texto EXACTO; no lo reescribas de memoria."
    )
    lineas_old = _normalizar_ws(old_string).split("\n")
    lineas_txt = _normalizar_ws(texto).split("\n")
    if _contiene_subsecuencia(lineas_txt, lineas_old):
        mensaje += (
            "\nNOTA: coincide salvo espacios/tabs — copiá la indentación "
            "EXACTA del archivo (tabs vs espacios)."
        )
    candidatos = candidatos_similares(texto, old_string)
    if candidatos:
        mensaje += "\n¿Quisiste decir (línea n):"
        for num, excerpt in candidatos:
            recorte = excerpt if len(excerpt) <= 200 else excerpt[:200]
            mensaje += f"\n  L{num}: {recorte!r}"
    return mensaje


def _cuenta_diff(diff):
    """(hunks, agregadas, borradas) del diff COMPLETO: es lo que el aprobador
    tiene que ver, aunque el panel recorte el texto."""
    hunks = agrega = borra = 0
    for linea in diff.splitlines():
        if linea.startswith("@@"):
            hunks += 1
        elif linea.startswith("+") and not linea.startswith("+++"):
            agrega += 1
        elif linea.startswith("-") and not linea.startswith("---"):
            borra += 1
    return hunks, agrega, borra


def edit_file(path, old_string, new_string):
    resolved, err = _resolve(path)
    if err:
        return f"ERROR: {err}"
    if resolved.is_dir():
        return f"ERROR: es un directorio: {resolved}"
    if not resolved.exists():
        return f"ERROR: no existe: {resolved} (para crear archivos usá write_file)"
    if not old_string:
        return "ERROR: old_string vacío — no hay nada que buscar"
    if old_string == new_string:
        return "ERROR: old_string y new_string son idénticos — el edit no haría nada"

    try:
        # bytes → str sin traducir saltos (un CRLF sigue CRLF fuera del hunk
        # aprobado) y estricto: con errors="replace" un byte Latin-1 volvía al
        # disco como U+FFFD en silencio (auditoría 2026-10-26, F1)
        texto = resolved.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return f"ERROR: {resolved.name} no es UTF-8; edit_file no lo reescribe"
    n = texto.count(old_string)
    if n == 0:
        return _error_no_aparece(resolved, texto, old_string)
    if n > 1:
        lineas = _lineas_ocurrencias(texto, old_string)
        listado = ", ".join(str(x) for x in lineas)
        return (
            f"ERROR: old_string aparece {n} veces en {resolved.name}. "
            "Agregá líneas de contexto alrededor hasta que la ocurrencia sea única.\n"
            f"Ocurrencias en líneas: {listado} — agregá contexto para apuntar una."
        )

    nuevo = texto.replace(old_string, new_string, 1)
    diff = "\n".join(
        difflib.unified_diff(
            texto.splitlines(),
            nuevo.splitlines(),
            fromfile=f"{resolved.name} (actual)",
            tofile=f"{resolved.name} (editado)",
            lineterm="",
        )
    )
    print(f"\n── edit_file: {resolved} ──")
    hunks, agrega, borra = _cuenta_diff(diff)
    if len(diff) <= SALIDA_MAX:
        diff_mostrado = diff
    else:
        vista = recortar_chars(diff, SALIDA_MAX, "\0")
        inicial, _, final = vista.partition("\0")
        oculto = len(diff) - len(inicial) - len(final)
        diff_mostrado = recortar_chars(
            diff, SALIDA_MAX,
            f"[... diff truncado: quedan {oculto} de {len(diff)} caracteres sin ver ...]")
    print(highlight_diff(diff_mostrado))
    decision = _approve(Pedido(f"¿Aplicar? → {resolved} ({hunks} hunks, +{agrega}/−{borra})",
                               diff_mostrado, "escritura", str(resolved)))
    if not decision:
        registrar_aprobacion("edit_file", f"{resolved}", False, "preguntar")
        # getattr: el seam _approve también acepta bools (los mocks viejos)
        motivo = getattr(decision, "motivo", "") or "el archivo no se modificó"
        return f"RECHAZADO por el usuario: {motivo}."
    registrar_aprobacion("edit_file", f"{resolved}", True, "preguntar")

    try:
        escribir_atomico(resolved, nuevo)
    except OSError as e:
        return f"ERROR al escribir: {e.strerror}"
    return f"Editado: {resolved} ({len(diff.splitlines())} líneas de diff)"


IMPL = {"run_command": run_command, "edit_file": edit_file}
