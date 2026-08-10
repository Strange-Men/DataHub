"""Test-only P1 schema bootstrap resilient to application module reloads."""


def ensure_p1_test_database(app) -> None:
    import app.storage as storage

    runtimes = [storage]
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        globals_dict = getattr(endpoint, "__globals__", {})
        for value in globals_dict.values():
            if callable(value) and getattr(value, "__module__", "") == "app.storage":
                runtime_globals = getattr(value, "__globals__", {})
                database = runtime_globals.get("database")
                repositories = runtime_globals.get("db_repo")
                if database is not None and repositories is not None:
                    runtimes.append(type("Runtime", (), {
                        "database": database,
                        "db_repo": repositories,
                    }))
    seen: set[int] = set()
    for runtime in runtimes:
        engine = runtime.database.SessionLocal.kw["bind"]
        if id(engine) in seen:
            continue
        seen.add(id(engine))
        runtime.db_repo.RawBatch.metadata.create_all(bind=engine)
