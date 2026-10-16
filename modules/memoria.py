"""Módulo `memoria`: la biblioteca consultable entre sesiones.

Filosofía EXACTA: la memoria es una BIBLIOTECA, no contexto inyectado.
Cada chat arranca con la memoria VACÍA (nada se auto-inyecta al inicio y
el system prompt no se toca); el agente consulta/guarda solo cuando el
pedido lo justifica, vía estas tools.

Dos tools, código puro (sin LLM):
- memory_search: busca texto (case-insensitive) dentro de los .md de
  `memoria/` y lista la biblioteca.
- memory_save: escribe `memoria/nota_FECHA_slug.md` SIN HITL (es la
  libreta del agente) pero con contención dura: solo escribe DENTRO de
  `memoria/`, el slug se deriva del título y rechaza rutas o '..'."""
import os
import re
import unicodedata
from datetime import date
from pathlib import Path

from utils.call_llm import _setting
from utils.fs_tools import escribir_atomico

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

        elegidos = elegir_por_laya(query, archivos, maximo, setting_modelo="LAYA_MODEL_PREFILTRO")
    except Exception:  # el prefiltro nunca rompe la memoria
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
