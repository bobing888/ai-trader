FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.118.0" \
    "uvicorn[standard]>=0.32.0" \
    "pydantic>=2.9.0" \
    "pydantic-settings>=2.6.0" \
    "pandas>=2.2.0" \
    "numpy>=2.0.0" \
    "httpx>=0.27.0" \
    "redis>=5.0.0" \
    "aiosqlite>=0.20.0" \
    "sqlalchemy>=2.0.30"

# Copy app
COPY app/ ./app/

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8765/api/health || exit 1

EXPOSE 8765

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "2", "--log-level", "info"]
