"""Carga las trazas .jsonl de decisiones a SQLite (una vez, código puro).

Tabla `trazas`: una fila por registro, con el archivo de origen, el módulo
elegido y los campos de la traza. Después, la tool `sql` del chat
interroga los datos en vivo (agregaciones que el informe responde estático).

Uso:
    python3 carga_trazas.py [carpeta] [--db trazas.db] [--glob '*.jsonl']
"""
import argparse
import json
import sqlite3

from informe import collect_files
from utils.fs_tools import _resolve

ESQUEMA = """
DROP TABLE IF EXISTS trazas;
CREATE TABLE trazas (
    id INTEGER PRIMARY KEY,
    archivo TEXT NOT NULL,
    carpeta TEXT NOT NULL,
    registro INTEGER NOT NULL,
    modulo TEXT,
    task TEXT,
    criterios TEXT,
    pasos INTEGER,
    json_valido INTEGER NOT NULL
);
CREATE INDEX idx_trazas_modulo ON trazas(modulo);
CREATE INDEX idx_trazas_carpeta ON trazas(carpeta);
"""


def cargar(carpeta, db="trazas.db", glob="*.jsonl"):
    folder, err = _resolve(carpeta)
    if err:
        raise ValueError(f"ERROR: {err}")
    archivos = collect_files(str(folder), glob)
    con = sqlite3.connect(db)
    con.executescript(ESQUEMA)
    total, rotas = 0, 0
    for archivo in archivos:
        with open(archivo, encoding="utf-8") as f:
            for n, linea in enumerate(f, 1):
                if not linea.strip():
                    continue
                total += 1
                modulo = task = criterios = None
                pasos = None
                valido = 1
                try:
                    rec = json.loads(linea)
                    modulo = rec.get("answers", {}).get("next")
                    campos = rec.get("fields", {})
                    task = campos.get("task")
                    criterios = campos.get("criteria")
                    pasos = len(campos.get("steps") or [])
                except json.JSONDecodeError:
                    valido = 0
                    rotas += 1
                con.execute(
                    "INSERT INTO trazas (archivo, carpeta, registro, modulo, task, criterios, pasos, json_valido) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(archivo), str(archivo.parent), n, modulo, task, criterios, pasos, valido),
                )
    con.commit()
    resumen = con.execute(
        "SELECT carpeta, modulo, COUNT(*) FROM trazas WHERE json_valido=1 GROUP BY carpeta, modulo"
    ).fetchall()
    con.close()
    print(f"{total} registros ({rotas} rotos) de {len(archivos)} archivos → {db}")
    return total, rotas


def main(argv=None):
    parser = argparse.ArgumentParser(prog="carga_trazas", description="jsonl de trazas → SQLite")
    parser.add_argument("carpeta", nargs="?", default=".")
    parser.add_argument("--db", default="trazas.db")
    parser.add_argument("--glob", default="*.jsonl")
    args = parser.parse_args(argv)
    cargar(args.carpeta, args.db, args.glob)


if __name__ == "__main__":
    main()
