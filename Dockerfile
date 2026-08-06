# syntax=docker/dockerfile:1.4
# Multi-stage: Node builds the SPA, the Python image serves API + statics.
# Mirrors gribranker's Dockerfile; UID 1504 matches the `markrounding`
# service user on bibliotekarien-vps so the named data volume gets the
# right ownership.

FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_NO_CACHE=1
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY markrounding ./markrounding
RUN uv sync --locked --no-dev
COPY --from=frontend /build/dist ./frontend/dist
RUN mkdir -p /app/data \
    && groupadd --gid 1504 appuser \
    && useradd --uid 1504 --gid 1504 --no-create-home appuser \
    && chown -R appuser:appuser /app
USER appuser
CMD ["uv", "run", "--no-sync", "markrounding", "serve", "--host", "0.0.0.0", "--port", "8000"]
