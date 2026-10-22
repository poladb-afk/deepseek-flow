"""Small general helpers (sin bugs conocidos)."""

import json


def load_json(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def clamp(value, minimum, maximum):
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value
