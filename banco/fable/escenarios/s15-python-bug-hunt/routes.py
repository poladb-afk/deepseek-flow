"""Tiny request handlers for the internal admin app."""

import os
import sqlite3


def find_user(name):
    connection = sqlite3.connect("store.db")
    query = f"SELECT * FROM users WHERE name = '{name}'"
    return connection.execute(query).fetchall()


def read_attachment(base_dir, name):
    path = os.path.join(base_dir, name)
    with open(path, "rb") as file:
        return file.read()
