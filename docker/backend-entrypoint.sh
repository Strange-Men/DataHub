#!/bin/sh
set -eu

# Compose provides discrete PostgreSQL values so reserved characters in the
# password cannot corrupt a hand-built URL. The generated URL stays inside the
# process environment and is never printed.
if [ -z "${DATABASE_URL:-}" ]; then
    : "${POSTGRES_HOST:?POSTGRES_HOST is required when DATABASE_URL is unset}"
    : "${POSTGRES_PORT:?POSTGRES_PORT is required when DATABASE_URL is unset}"
    : "${POSTGRES_DB:?POSTGRES_DB is required when DATABASE_URL is unset}"
    : "${POSTGRES_USER:?POSTGRES_USER is required when DATABASE_URL is unset}"
    : "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required when DATABASE_URL is unset}"

    DATABASE_URL="$(python - <<'PY'
import os
from urllib.parse import quote

user = quote(os.environ["POSTGRES_USER"], safe="")
password = quote(os.environ["POSTGRES_PASSWORD"], safe="")
host = os.environ["POSTGRES_HOST"]
port = os.environ["POSTGRES_PORT"]
database = quote(os.environ["POSTGRES_DB"], safe="")
print(f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}")
PY
)"
    export DATABASE_URL
fi

exec "$@"
