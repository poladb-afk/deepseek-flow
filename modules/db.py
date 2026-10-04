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


def sql(consulta):
    try:
        con = _con()
    except RuntimeError as e:
        return f"ERROR: {e}"
    if not consulta.strip().lower().startswith("select"):
        con.close()
        return "ERROR: solo SELECT"
    if ";" in consulta.strip()[:-1]:
        con.close()
        return "ERROR: una sola sentencia"
    if PROHIBIDOS.search(consulta):
        con.close()
        return "ERROR: solo SELECT"
    if "limit" not in consulta.lower():
        consulta = f"{consulta.rstrip(';')} LIMIT {MAX_FILAS}"
    try:
        filas = con.execute(consulta).fetchall()
    except sqlite3.Error as e:
        con.close()
        return f"ERROR SQL: {e}"
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
