"""Stable P1 persistence failure contract shared across runtime reloads."""


class P1PersistenceError(RuntimeError):
    """Safe failure raised when P1 database persistence is unavailable."""

    code = "P1_DATABASE_UNAVAILABLE"
