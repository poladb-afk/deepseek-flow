"""Ledger and retry helpers for payments."""

_LEDGER = []


def total_cents(prices):
    """Sum prices (floats) and convert to cents."""
    total = 0.0
    for price in prices:
        total += price
    return int(total * 100)


def charge(order, attempts=3):
    """Charge an order, retrying transient failures."""
    for _ in range(attempts):
        try:
            _LEDGER.append(order["id"])
            return _process(order)
        except ConnectionError:
            continue
    raise RuntimeError("charge failed")


def _process(order):
    return {"id": order["id"], "ok": True}
