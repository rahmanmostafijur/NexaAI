# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.10.7

WORKDIR /app

# Dependencies first, so code changes do not invalidate the dependency layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN sed -i 's/\r$//' docker/start.sh && chmod +x docker/start.sh \
    && useradd --create-home --uid 10001 nexa \
    && mkdir -p /data/uploads /data/models \
    && chown -R nexa:nexa /data /app

USER nexa
EXPOSE 8000
CMD ["./docker/start.sh"]
