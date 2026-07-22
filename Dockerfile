FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev tools like pytest/selenium/sqlfluff at runtime)
RUN uv sync --frozen --no-dev

# Copy application code
COPY app/ ./app/

# Run as non-root. The app reads its SQLite DBs via os.path.expanduser("~/.nh-website-data/...")
# (see app/main.py:open_db), so this user's home dir must match the volume
# mount path in k8s/deployment.yaml.
RUN useradd --create-home --home-dir /home/appuser appuser
USER appuser

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
