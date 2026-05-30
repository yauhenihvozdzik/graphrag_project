FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl unzip p7zip-full && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir -e ".[otel]" && pip install --no-cache-dir pytest pytest-asyncio pytest-timeout

# Application code (backend)
COPY backend/ .

# Tests (for in-container pytest runner)
COPY tests/ /app/tests/

# Create directories
RUN mkdir -p logs data/uploads data/processed

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
