"""Helpers for the nightly reporting job."""

import json


def column_formatters(columns):
    formatters = []
    for column in columns:
        formatters.append(lambda value: f"{column}: {value}")
    return formatters


def load_summaries(paths):
    totals = []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as file:
                totals.append(json.load(file))
        except Exception:
            pass
    return totals


def validate(payload):
    assert "id" in payload, "missing id"
    return payload["id"]
