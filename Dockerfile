FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Non-root runtime user (12G container verification: the image must not run as root).
RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY --chown=app:app app ./app
COPY --chown=app:app config.yaml ./
COPY --chown=app:app examples ./examples

RUN uv sync --frozen --no-dev

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
