FROM python:3.14-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency files first — separate layer for better caching
COPY pyproject.toml uv.lock ./

# Install all dependencies into .venv (no project itself yet)
RUN uv sync --frozen --no-dev --no-install-project

# Copy source (README.md needed by hatchling for pyproject.toml metadata)
COPY README.md ./
COPY sovereign_brain/ ./sovereign_brain/

# Install the project package into the already-populated venv
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "sovereign_brain.mcp"]
