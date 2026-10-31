"""Módulo `memoria`: la biblioteca consultable entre sesiones.

Filosofía EXACTA: la memoria es una BIBLIOTECA, no contexto inyectado.
Cada chat arranca con la memoria VACÍA (nada se auto-inyecta al inicio y
el system prompt no se toca); el agente consulta/guarda solo cuando el
pedido lo justifica, vía estas tools.

Además engancha el ciclo de vida del chat (`HOOKS`, ver modules/__init__):
el catálogo al arrancar, el respaldo de la zona fría al compactar y el
resumen de la sesión al salir. Sin este archivo el chat corre igual, sin
biblioteca: el CORE no sabe que la memoria existe.

Dos tools, código puro (sin LLM):
- memory_search: busca texto (case-insensitive) dentro de los .md de
  `memoria/` y lista la biblioteca.
- memory_save: escribe `memoria/nota_FECHA_slug.md` SIN HITL (es la
  libreta del agente) pero con contención dura: solo escribe DENTRO de
  `memoria/`, el slug se deriva del título y rechaza rutas o '..'."""
import os
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

from utils import call_llm as cliente
from utils.call_llm import _setting
from utils.compaccion import MAX_RESPALDO_CHARS, PREFIJO_COMPACCION, huella, serializar, zona_fria
from utils.fs_tools import escribir_atomico
from utils.prefetch import PREFIJO_PREFETCH
from utils.skills import PREFIJO_SKILL

MEMORIA_DIR_DEFAULT = "memoria"
SEARCH_MAX_FILES = 50
SEARCH_HITS_PER_FILE = 20
SEARCH_MAX_MATCHES = 200


def _raiz():
    """Raíz de la biblioteca. Configurable para tests; por defecto
    `memoria/` bajo el CWD del proyecto."""
    raw = Path(_setting("MEMORIA_DIR", MEMORIA_DIR_DEFAULT)).expanduser()
    if not raw.is_absolute():
        # anclada al PROYECTO, no al CWD: arrancar el chat desde otra carpeta
        # ya no crea una biblioteca nueva vacía en otro lado.
        raw = Path(__file__).resolve().parent.parent / raw
    return raw.resolve()


def _slug(titulo):
    """Slug seguro del título: sin acentos, sin separadores de ruta, sin
    '..'. Devuelve '' si el título no deja nada utilizable."""
    base = unicodedata.normalize("NFKD", str(titulo)).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").lower()
    return base[:60].strip("-")


def _archivos_md():
    raiz = _raiz()
    if not raiz.is_dir():
        return []
    # misma política que fs_tools.sin_enlaces: la biblioteca no sigue enlaces
    # (medido: un memoria/enlace.md -> /otro/lado devolvía contenido externo)
    return sorted(p for p in raiz.glob("*.md") if p.is_file() and not p.is_symlink())


def memory_search(query=None):
    """Busca `query` (case-insensitive) dentro de los .md de la biblioteca.
    Devuelve las coincidencias (archivo + línea) y, siempre, el listado de
    los archivos de memoria/ para que el agente sepa qué hay disponible.

    Con query y `MEMORIA_PREFILTRO=1`, un prefiltro local (Laya) elige
    hasta `MEMORIA_PREFILTRO_N` archivos relevantes ANTES de leerlos: sin
    Laya disponible el prefiltro es no-op (entran todos, como siempre)."""
    query = (query or "").strip()
    archivos = _archivos_md()
    if not archivos:
        return ("La biblioteca de memoria está vacía (no hay archivos en "
                f"{_raiz()}). Usá memory_save para guardar una nota.")
    listado = "Biblioteca de memoria:\n" + "\n".join(f"- {p.name}" for p in archivos)
    if not query:
        return listado

    candidatos, prefiltro = _prefiltrar(query, archivos)

    q = query.lower()
    bloques, total = [], 0
    for p in candidatos:
        try:
            texto = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = [
            (n, line.strip()[:200])
            for n, line in enumerate(texto.splitlines(), 1)
            if q in line.lower()
        ]
        if not hits:
            continue
        total += len(hits)
        bloques.append(f"- {p.name}")
        for n, line in hits[:SEARCH_HITS_PER_FILE]:
            bloques.append(f"    L{n}: {line}")
        if len(hits) > SEARCH_HITS_PER_FILE:
            bloques.append(f"    ... y {len(hits) - SEARCH_HITS_PER_FILE} líneas más")
        if total >= SEARCH_MAX_MATCHES:
            break

    aviso = (f"[prefiltro Laya: {len(archivos)} → {len(candidatos)} archivos]"
             if prefiltro else "")
    if not bloques:
        return f"'{query}' no aparece en la biblioteca.\n\n{listado}" + (
            f"\n{aviso}" if aviso else "")
    cabecera = f"'{query}' aparece en la memoria ({total} líneas):"
    return "\n".join([linea for linea in [cabecera, aviso] if linea] + bloques + ["", listado])


def _texto_de_nota(ruta):
    """El CONTENIDO de la nota para el clasificador (A07).

    Antes el prefiltro recibía la ruta y elegía por nombre de archivo; el
    contenido es lo que decide si la nota aporta. Una nota ilegible puntúa
    como texto vacío, no rompe el prefiltro."""
    try:
        return ruta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _prefiltrar(query, archivos):
    """(archivos a consultar, si el prefiltro actuó). Con
    MEMORIA_PREFILTRO=0 o sin juicio de Laya, devuelve todos y False: el
    aviso "[prefiltro Laya: …]" aparece SOLO si Laya realmente puntuó."""
    if _setting("MEMORIA_PREFILTRO", "1") != "1":
        return archivos, False
    try:
        maximo = int(_setting("MEMORIA_PREFILTRO_N", "8"))
    except (TypeError, ValueError):
        maximo = 8
    if maximo <= 0 or len(archivos) <= maximo:
        return archivos, False
    try:
        from utils.contexto import elegir_por_laya

        elegidos = elegir_por_laya(query, archivos, maximo,
                                   setting_modelo="LAYA_MODEL_PREFILTRO",
                                   texto_de=_texto_de_nota)
    except Exception:  # el prefiltro nunca rompe la memoria  # noqa: BLE001 (prefiltro Laya best-effort: nunca rompe la memoria)
        return archivos, False
    if len(elegidos) >= len(archivos):
        return archivos, False  # no actuó: sin aviso
    return elegidos, True


def guardar_nota(titulo, contenido):
    """Escribe la nota y devuelve su Path (None si no se pudo). Contención
    dura: solo dentro de memoria/, destino resuelto y sin symlinks. Lo
    comparten la tool memory_save y el respaldo de la zona fría que hace la
    compacción antes de descartar mensajes (A17)."""
    slug = _slug(titulo)
    if not slug:
        return None
    raiz = _raiz()
    destino = raiz / f"nota_{date.today().isoformat()}_{slug}.md"
    # A26 primero: un enlace en el destino NO se sigue nunca (podría apuntar
    # fuera de la biblioteca), ni con sufijo.
    if destino.is_symlink():
        return None
    # X4: dos notas del mismo título el mismo día NO se pisan — la segunda va
    # con sufijo (antes la primera se perdía en silencio).
    if destino.exists():
        n = 2
        while True:
            candidato = raiz / f"nota_{date.today().isoformat()}_{slug}-{n}.md"
            if candidato.is_symlink():
                return None
            if not candidato.exists():
                destino = candidato
                break
            n += 1
    # doble chequeo: el destino resuelto DEBE quedar dentro de memoria/
    if destino.is_symlink() or raiz not in destino.resolve().parents:
        return None
    cuerpo = contenido if contenido is not None else ""
    texto = f"{titulo.strip()}\n\n{cuerpo}\n"
    try:
        raiz.mkdir(parents=True, exist_ok=True)
        escribir_atomico(destino, texto)
    except OSError:
        return None
    return destino


def memory_save(titulo, contenido):
    """Escribe una nota en `memoria/nota_FECHA_slug.md` (título como primera
    línea). Sin HITL: es la libreta del agente. Contención dura: solo
    escribe DENTRO de memoria/ (slug del título, sin rutas ni '..')."""
    if not _slug(titulo):
        return "ERROR: el título no contiene caracteres utilizables para el nombre del archivo."
    destino = guardar_nota(titulo, contenido)
    if destino is None:
        return "ERROR: no se pudo escribir la nota (fuera de la biblioteca o error de disco)."
    return f"Guardado en {destino}"


def guardar_resumen_sesion(contenido):
    """Escribe `memoria/sesion_FECHA.md` (resumen de la sesión). Sin HITL:
    es bookkeeping, no una acción nueva. Devuelve el path o None."""
    raiz = _raiz()
    destino = raiz / f"sesion_{date.today().isoformat()}.md"
    # El nombre se hace único contra lo que YA existe, no contra el reloj: con
    # el sufijo horario solo (HHMM) dos sesiones del mismo minuto se pisaban.
    # lexists, no exists: un symlink COLGANTE da exists()=False y write_text
    # lo seguía, creando el archivo fuera de memoria/ (medido)
    if os.path.lexists(destino):
        from datetime import datetime

        marca = datetime.now().strftime("%H%M")
        destino = raiz / f"sesion_{date.today().isoformat()}-{marca}.md"
        n = 2
        while os.path.lexists(destino):
            destino = raiz / f"sesion_{date.today().isoformat()}-{marca}-{n}.md"
            n += 1
    # misma guarda que memory_save: el destino resuelto queda DENTRO de memoria/
    if raiz not in destino.resolve().parents:
        return None
    try:
        raiz.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido.rstrip() + "\n", encoding="utf-8")
    except OSError:
        return None
    return destino


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": (
                "Consulta la BIBLIOTECA de memoria entre sesiones (archivos markdown en "
                "memoria/). Busca texto (insensible a mayúsculas) y devuelve archivo+línea, "
                "más el listado de todo lo que hay. La memoria NO se inyecta sola: usá esta "
                "tool cuando el pedido lo justifique (retomar algo de una sesión anterior, "
                "ver decisiones o hallazgos pasados)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Texto a buscar dentro de la memoria (opcional: sin query, solo lista la biblioteca)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_save",
            "description": (
                "Guarda una nota en la biblioteca de memoria (memoria/nota_FECHA_slug.md), "
                "con el título como primera línea. Es la libreta del agente: no pide "
                "aprobación humana pero solo escribe dentro de memoria/. Usala para dejar "
                "un hallazgo, una decisión o un dato que valga la pena recuperar después."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Título de la nota (una línea); genera el nombre del archivo"},
                    "contenido": {"type": "string", "description": "Cuerpo de la nota en markdown"},
                },
                "required": ["titulo", "contenido"],
            },
        },
    },
]


IMPL = {"memory_search": memory_search, "memory_save": memory_save}


# ciclo de vida del chat


def preguntas_reales(mensajes):
    """Cuenta los user-role que son PREGUNTAS: excluye los mensajes sintéticos
    de prefetch, skill y el marcador de compacción (medido en vivo: con 1
    pregunta + 1 pre-fetch el resumen se disparaba igual)."""
    return sum(
        1 for m in mensajes
        if m.get("role") == "user"
        and not str(m.get("content", "")).startswith(
            (PREFIJO_PREFETCH, PREFIJO_COMPACCION, PREFIJO_SKILL))
    )


def _transcript(mensajes):
    lineas = []
    for m in mensajes:
        if m.get("role") == "system":
            continue
        contenido = m.get("content")
        if not contenido and m.get("tool_calls"):
            contenido = "(herramientas) " + ", ".join(tc["function"]["name"] for tc in m["tool_calls"])
        if contenido:
            lineas.append(f"{m.get('role')}: {contenido}")
    return "\n".join(lineas)


def resumen_de_sesion(shared):
    """Al salir, UNA llamada a call_llm comprime la conversación y la guarda
    como memoria/sesion_FECHA.md (bookkeeping, sin HITL). Con MEMORIA=0 o
    menos de 2 preguntas no hace nada; si la llamada falla se sale igual.
    Ninguna ruta es muda: un resumen ausente sin print no se pudo reproducir
    (4 intentos)."""
    if _setting("MEMORIA", "1") != "1":
        print("\n[memoria] desactivada (MEMORIA=0): sin resumen de sesión")
        return
    mensajes = shared.get("messages", [])
    n_users = preguntas_reales(mensajes)
    if n_users < 2:
        print(f"\n[memoria] sesión corta ({n_users} pregunta): sin resumen")
        return
    try:
        resumen = cliente.call_llm(
            "Resumí esta conversación entre un usuario y un agente, en español, "
            "en pocas líneas y para consulta futura. Incluí: el tema en una línea; "
            "los pedidos del usuario y sus resultados; las decisiones tomadas; los "
            "hallazgos; y los archivos tocados. No repitas saludos ni el texto crudo.\n\n"
            f"--- Conversación ---\n{_transcript(mensajes)}"
        )
        destino = guardar_resumen_sesion(resumen)
    except Exception as e:  # noqa: BLE001 (bookkeeping: nunca corta la salida)
        print(f"\n[memoria] no se pudo guardar el resumen de la sesión ({type(e).__name__})")
        return
    if destino:
        print(f"\n[memoria] resumen de sesión guardado en {destino}")
    else:
        print("\n[memoria] el resumen no se pudo escribir (OSError en memoria/)")


CATALOGO_MAX = 8


def catalogo(_shared=None):
    """Al arrancar, el CATÁLOGO de la biblioteca (cuántas notas y las más
    recientes) SIN su contenido: el arranque vacío es regla. Con MEMORIA=0 o
    la biblioteca vacía no imprime nada; nunca corta el arranque."""
    if _setting("MEMORIA", "1") != "1":
        return
    try:
        archivos = _archivos_md()
    except OSError:
        return
    if not archivos:
        return
    # lista completa = spam de arranque (229 de 234 notas eran respaldos de
    # compacción): van las últimas; el nombre desempata cuando el mtime empata.
    recientes = sorted(archivos, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)[:CATALOGO_MAX]
    print(f"\n[memoria] biblioteca: {len(archivos)} notas; las {len(recientes)} más recientes:")
    for p in recientes:
        print(f"  - {p.name}")
    print("  (consultá cualquier nota con memory_search)")


def _ahora():
    """Timestamp del título del respaldo (segundos: dos compacciones del mismo
    minuto colisionaban y guardar_nota las desambiguaba con -2, -3)."""
    return datetime.now().strftime("%Y-%m-%d %H-%M-%S")


def respaldar_zona_fria(mensajes, shared=None):
    """Guarda en memoria/ los mensajes que la compacción va a descartar (A17)
    y devuelve la ruta, o None. Transcripción literal, sin LLM: barata y sin
    modos de fallo nuevos.

    - Con `shared`, la sesión recuerda la huella del último respaldo: la zona
      fría casi no cambia entre compacciones y respaldarla siempre dejó 143
      copias idénticas (X37); si es la misma, devuelve la ruta existente.
    - Con MEMORIA=0 no escribe: sin biblioteca no hay memory_search que lo
      recupere (exp/71: 157 respaldos de fixture en la curada).
    - Una zona fría sin ningún `user` no se respalda: los resultados de tools
      se re-obtienen y la prosa del asistente es derivada (exp/88: la
      compacción rodante escribía un archivo por ronda)."""
    if _setting("MEMORIA", "1") != "1":
        return None
    frios = zona_fria(mensajes)
    if not any(isinstance(m, dict) and m.get("role") == "user" for m in frios):
        return None
    firma = huella(frios)
    if shared is not None and shared.get("_respaldo_huella") == firma:
        return shared.get("_respaldo_ruta")
    cuerpo = serializar(frios)
    if len(cuerpo) > MAX_RESPALDO_CHARS:
        cuerpo = cuerpo[:MAX_RESPALDO_CHARS] + "\n\n[... transcripción truncada por tamaño ...]"
    destino = guardar_nota(f"Compactación {_ahora()}", cuerpo)
    if destino is None:
        return None
    if shared is not None:
        shared["_respaldo_huella"] = firma
        shared["_respaldo_ruta"] = str(destino)
    return str(destino)


HOOKS = {"al_arrancar": catalogo, "al_compactar": respaldar_zona_fria, "al_salir": resumen_de_sesion}
