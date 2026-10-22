"""Reporting helpers for the nightly exports."""

import datetime


class Counter:
    history = []

    def add(self, value):
        self.history.append(value)
        return len(self.history)


def total_and_count(rows):
    rows_iter = iter(rows)
    total = sum(rows_iter)
    count = len(list(rows_iter))
    return total, count


def acquired_run(lock, task):
    lock.acquire()
    result = task()
    lock.release()
    return result


def timestamp_key(moment):
    return datetime.datetime.utcnow().timestamp()
