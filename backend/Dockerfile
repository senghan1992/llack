# Multi-stage: build wheels once, ship a slim runtime without a compiler.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./
# Resolve dependencies from the project metadata so the image and local dev
# install the same versions.
RUN pip install --upgrade pip setuptools wheel \
    && pip wheel --wheel-dir /wheels .

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Run as a non-root user: the API writes only to /app/var.
RUN groupadd --gid 10001 llack \
    && useradd --uid 10001 --gid llack --create-home --shell /usr/sbin/nologin llack

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY pyproject.toml ./
RUN pip install --no-index --find-links=/wheels . \
    && rm -rf /wheels

COPY --chown=llack:llack alembic.ini ./
COPY --chown=llack:llack alembic ./alembic
COPY --chown=llack:llack app ./app
COPY --chown=llack:llack docker-entrypoint.sh ./

RUN mkdir -p /app/var/uploads && chown -R llack:llack /app/var \
    && chmod +x /app/docker-entrypoint.sh

USER llack
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# --proxy-headers so client_ip() can trust X-Forwarded-For behind a reverse
# proxy; --forwarded-allow-ips must be narrowed to the proxy in production.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--proxy-headers", "--forwarded-allow-ips", "*"]
