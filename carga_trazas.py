"""Carga las trazas .jsonl de decisiones a SQLite (una vez, código puro).

Tabla `trazas`: una fila por registro, con el archivo de origen, el módulo
elegido y los campos de la traza. Después, la tool `sql` del chat
interroga los datos en vivo (agregaciones que el informe responde estático).

Dos garantías que la auditoría externa (C11/C12) encontró ausentes:
- La lectura es la MISMA del informe (`informe.leer_registro`): un renglón
  con JSON válido y forma equivocada (`[]`, `null`, `{"answers": null}`)
  se cuenta como inválido en vez de tumbar la carga entera.
- La recarga es todo-o-nada (una sola transacción): si algo falla a mitad,
  la base anterior queda intacta. Y no se toca si la carpeta no trae nada.

Uso:
    python3 carga_trazas.py [carpeta] [--db trazas.db] [--glob '*.jsonl']
"""
import argparse
import json
import sqlite3

from informe import collect_files, leer_registro
from utils.fs_tools import _resolve

# Sentencias sueltas a propósito: `executescript` COMMITEA lo pendiente, así
# que el DROP no puede vivir ahí si la recarga tiene que ser atómica.
ESQUEMA = (
    """
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
    )
    """,
    "CREATE INDEX idx_trazas_modulo ON trazas(modulo)",
    "CREATE INDEX idx_trazas_carpeta ON trazas(carpeta)",
)


def _texto(v):
    """None/str pasan; cualquier otro tipo se serializa a JSON (criteria
    puede venir como lista/dict del task yaml y sqlite3 solo acepta str)."""
    if v is None or isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def cargar(carpeta, db="trazas.db", glob="*.jsonl"):
    folder, err = _resolve(carpeta)
    if err:
        raise ValueError(f"ERROR: {err}")
    # max_files=None: la carga completa NO hereda el muestreo de 30 del informe
    archivos = collect_files(str(folder), glob, max_files=None)
    if not archivos:
        raise ValueError(f"ERROR: no hay archivos {glob} en {folder}: la base no se toca")
    con = sqlite3.connect(db)
    total, rotas, forma = 0, 0, 0
    try:
        # Todo-o-nada: el DROP vive DENTRO de la transacción. Medido: con el
        # DROP fuera, un renglón inválido a mitad dejaba la tabla anterior
        # borrada y la nueva a medio cargar.
        con.execute("BEGIN IMMEDIATE")
        con.execute("DROP TABLE IF EXISTS trazas")
        for sentencia in ESQUEMA:
            con.execute(sentencia)
        for archivo in archivos:
            with open(archivo, encoding="utf-8") as f:
                for n, linea in enumerate(f, 1):
                    if not linea.strip():
                        continue
                    total += 1
                    rec, motivo = leer_registro(linea)
                    if motivo == "json":
                        rotas += 1
                    elif motivo:
                        forma += 1
                    campos = (rec or {}).get("fields") or {}
                    respuestas = (rec or {}).get("answers") or {}
                    con.execute(
                        "INSERT INTO trazas (archivo, carpeta, registro, modulo, task, criterios, pasos, json_valido) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (str(archivo), str(archivo.parent), n,
                         _texto(respuestas.get("next")), _texto(campos.get("task")),
                         _texto(campos.get("criteria")),
                         len(campos.get("steps") or []), 0 if motivo else 1),
                    )
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    print(f"{total} registros ({rotas} JSON roto, {forma} forma inválida) "
          f"de {len(archivos)} archivos → {db}")
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
