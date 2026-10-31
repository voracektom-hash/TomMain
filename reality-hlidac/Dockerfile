# One image for the watcher, the web app and the backup job.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Prague \
    DB_PATH=/data/hlidac.db

WORKDIR /app
COPY pyproject.toml ./
COPY hlidac ./hlidac
RUN pip install --no-cache-dir . \
 && useradd --uid 1000 --create-home app \
 && mkdir -p /data && chown app:app /data

USER app
VOLUME ["/data"]
