"""Pre-fetch como POLÍTICA declarativa del chat (exp/50, apéndice 13).

El material del 12-factor lo dice plano: "if you already know what tools
you'll want the model to call, JUST CALL THEM DETERMINISTICALLY". Hoy el
pre-fetch existe ad-hoc en 2 sitios (juez, catálogo de memoria); acá pasa a
POLÍTICA declarativa del chat, en un módulo PURO (sin LLM).

Ley de ausencia de la casa (igual que el pre-filtro de contexto): sin match
la pieza es NO-OP. Si la pregunta no menciona ninguna ruta existente dentro
del perímetro, `decidir` devuelve [] y `mensaje` devuelve None — no hay
mensaje que inyectar.

La tabla de reglas es una LISTA para crecer, pero v1 trae UNA sola regla
(`archivos_mencionados`) — no se especula con reglas que nadie pidió.

Setting PREFETCH (default "1"); "0" apaga TODO.
"""
import re

from utils.call_llm import _entero, _setting

# Prefijo FIJO e inconfundible del mensaje user sintético (patrón compacción).
# Un solo lugar para cambiarlo; los tests y el router lo leen de acá.
PREFIJO_PREFETCH = "[pre-fetch]"

# La ruta que se menciona en la pregunta: mismo espíritu que juez.ARCHIVO_RE.
ARCHIVO_RE = re.compile(r"[\w./-]+\.[A-Za-z]{1,4}")


def decidir(pregunta):
    """[(path, contenido)] con las rutas EXISTENTES dentro del perímetro que
    la pregunta menciona. PURA en su lógica de matching (regex, contención,
    existencia); la única I/O es leer el archivo — y JAMÁS lanza: un error de
    lectura salta esa ruta. Sin match, lista vacía (ley de ausencia)."""
    if _setting("PREFETCH", "1") == "0":
        return []
    texto = str(pregunta or "")
    if not texto:
        return []
    max_archivos = _entero("PREFETCH_MAX_ARCHIVOS", 2)
    max_lineas = _entero("PREFETCH_MAX_LINEAS", 80)
    if max_archivos <= 0:
        return []

    # Una sola pasada por el resolvedor de contención que ya existe.
    from utils.fs_tools import _resolve

    vistos = set()
    resultado = []
    for cruda in ARCHIVO_RE.findall(texto):
        if cruda in vistos:
            continue
        vistos.add(cruda)
        try:
            resolved, err = _resolve(cruda)
        except (OSError, ValueError):  # noqa: BLE001  (decidir JAMÁS lanza)
            continue
        if err or resolved is None or not resolved.is_file():
            continue  # fuera del perímetro o inexistente → se salta
        try:
            contenido = _leer_lineas(resolved, max_lineas)
        except (OSError, ValueError):  # noqa: BLE001  (error de lectura → esa ruta se salta)
            continue
        resultado.append((resolved, contenido))
        if len(resultado) >= max_archivos:
            break
    return resultado


def _leer_lineas(path, max_lineas):
    """Las primeras `max_lineas` líneas del archivo, como texto plano."""
    lineas = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for linea in f:
            lineas.append(linea.rstrip("\n"))
            if len(lineas) >= max_lineas:
                break
    return "\n".join(lineas)


def mensaje(prefetches):
    """El texto user-role con prefijo FIJO `[pre-fetch]` (patrón compacción):
    por cada archivo, `[pre-fetch] {path} (primeras {n} líneas):\\n{contenido}`.
    None si no hay nada — sin match no hay mensaje (ley de ausencia)."""
    if not prefetches:
        return None
    bloques = []
    for path, contenido in prefetches:
        n = len(contenido.splitlines()) if contenido else 0
        bloques.append(f"{PREFIJO_PREFETCH} {path} (primeras {n} líneas):\n{contenido}")
    return "\n\n".join(bloques)
