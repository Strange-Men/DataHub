FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 datahub \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin datahub

COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement /tmp/requirements.txt

COPY --chown=10001:10001 backend/app /app/backend/app
COPY --chown=10001:10001 scripts /app/scripts
COPY --chown=10001:10001 samples /app/samples
COPY docker/backend-entrypoint.sh /usr/local/bin/datahub-entrypoint

RUN install -d -o 10001 -g 10001 \
    /app/backend/storage \
    /app/.local-data \
    /data/assets \
    && chmod 0555 /usr/local/bin/datahub-entrypoint

USER 10001:10001

EXPOSE 8000

ENTRYPOINT ["datahub-entrypoint"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
