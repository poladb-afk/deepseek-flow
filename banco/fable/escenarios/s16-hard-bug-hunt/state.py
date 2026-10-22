"""Session state shared by the API workers."""

import copy
import threading

_CACHE = {}
_LOCK = threading.Lock()


def get_user(user_id):
    """Return the cached user, loading it on a miss.

    Called concurrently from the request threads.
    """
    if user_id not in _CACHE:
        _CACHE[user_id] = _load(user_id)
    return _CACHE[user_id]


def _load(user_id):
    return {"id": user_id, "roles": []}


def clone_user(user):
    """Copy for a caller that mutates roles without touching the cache."""
    copia = copy.copy(user)
    return copia


def add_role(user, role):
    user["roles"].append(role)
