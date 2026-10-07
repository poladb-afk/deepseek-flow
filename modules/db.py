"""Módulo `db`: interrogar las trazas cargadas en SQLite con SQL de solo lectura.

Leyes: solo SELECT (una sola sentencia), LIMIT forzado si no lo trae,
timeout corto. Sin base cargada, la tool lo dice y sugiere el comando."""
import re
import sqlite3
from pathlib import Path

from utils.call_llm import _setting

DB_PATH = str(Path(__file__).resolve().parent.parent / "trazas.db")
MAX_FILAS = 50
PROHIBIDOS = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|pragma)\b", re.IGNORECASE)


def _con():
    ruta = _setting("DB_PATH", DB_PATH)
    if not Path(ruta).is_file():
        raise RuntimeError(
            f"no hay base en {ruta}: corre primero `python3 carga_trazas.py [carpeta]`"
        )
    con = sqlite3.connect(ruta, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def db_schema():
    try:
        con = _con()
    except RuntimeError as e:
        return f"ERROR: {e}"
    filas = con.execute(
        "SELECT name, sql FROM sqlite_master WHERE type IN ('table','index')"
    ).fetchall()
    con.close()
    return "\n\n".join(r["sql"] or r["name"] for r in filas) + (
        "\n\nColumnas de trazas: id, archivo, carpeta, registro, modulo, "
        "task, criterios, pasos, json_valido"
    )


def _sentencias(texto):
    """Trocea por ';' ignorando los que están dentro de literales ('...' o
    "..."). Devuelve las partes no vacías: > 1 significa multi-sentencia.
    Un ';' dentro de una cadena es legal, no una segunda sentencia."""
    partes, actual, comilla = [], [], None
    for ch in texto:
        if comilla:
            actual.append(ch)
            if ch == comilla:
                comilla = None
        elif ch in ("'", '"'):
            comilla = ch
            actual.append(ch)
        elif ch == ";":
            partes.append("".join(actual))
            actual = []
        else:
            actual.append(ch)
    partes.append("".join(actual))
    return [p for p in partes if p.strip()]


def _sin_literales(consulta):
    """La consulta con el contenido de los literales ('...' y "...")
    reemplazado por vacío: para escanear palabras clave del SQL sin falsear
    por texto de usuario. Misma noción de literal que _sentencias."""
    partes, actual, comilla = [], [], None
    for ch in consulta:
        if comilla:
            if ch == comilla:
                comilla = None
            continue  # el contenido del literal no se escanea
        if ch in ("'", '"'):
            comilla = ch
        elif ch == ";":
            partes.append(";")  # el troceado de sentencias no se falsea
        else:
            actual.append(ch)
    partes.append("".join(actual))
    return "".join(partes)


_RE_LIMIT = re.compile(r"\blimit\b", re.IGNORECASE)


def sql(consulta):
    try:
        con = _con()
    except RuntimeError as e:
        return f"ERROR: {e}"
    try:
        if not consulta.strip().lower().startswith("select"):
            return "ERROR: solo SELECT"
        if len(_sentencias(consulta)) > 1:
            return "ERROR: una sola sentencia"
        # los chequeos escanean la consulta SIN literales: un 'delete' o un
        # 'limit' dentro de un string es texto de usuario, no SQL. La consulta
        # que se EJECUTA sigue siendo la original.
        limpia = _sin_literales(consulta)
        if PROHIBIDOS.search(limpia):
            return "ERROR: solo SELECT"
        # la ley es 'LIMIT forzado si no lo trae': hay que mirar la CLÁUSULA
        # LIMIT, no una subcadena (un LIKE '%unlimited%' la suprimía).
        if not _RE_LIMIT.search(limpia):
            consulta = f"{consulta.rstrip(';').rstrip()} LIMIT {MAX_FILAS}"
        try:
            filas = con.execute(consulta).fetchall()
        except sqlite3.Error as e:
            return f"ERROR SQL: {e}"
        except Exception as e:  # noqa: BLE001 (el error es un hecho, no un crash:
            # sqlite3.Warning no hereda de sqlite3.Error y otros fallos de uso
            # también deben volver como texto, no propagarse al chat)
            return f"ERROR SQL: {type(e).__name__}: {e}"
    finally:
        # cierra siempre: antes, un fallo que no fuera sqlite3.Error (p. ej.
        # sqlite3.Warning, que no hereda de sqlite3.Error) filtraba la conexión.
        con.close()
    if not filas:
        return "(sin resultados)"
    encabezado = " | ".join(filas[0].keys())
    cuerpo = "\n".join(" | ".join(str(v) for v in f) for f in filas)
    return f"{encabezado}\n{'-' * len(encabezado)}\n{cuerpo}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "sql",
            "description": "Corre una consulta SELECT de solo lectura sobre la base SQLite de trazas (cargadas de los .jsonl con carga_trazas.py). Solo una sentencia, solo SELECT; si no pones LIMIT se aplica 50. Ideal para agregaciones (GROUP BY, conteos, filtros por módulo o carpeta).",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "La consulta SQL SELECT"},
                },
                "required": ["consulta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "db_schema",
            "description": "Devuelve el esquema de la base de trazas (tablas, índices, columnas) para escribir consultas correctas.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


IMPL = {"sql": sql, "db_schema": db_schema}
