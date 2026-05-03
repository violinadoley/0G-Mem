FROM python:3.11-slim

WORKDIR /app

# System deps for sentence-transformers + web3
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Node deps (0g Storage bridge)
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Application code
COPY ogmem/ ./ogmem/
COPY proto/ ./proto/
COPY api/ ./api/
COPY scripts/ ./scripts/

# Non-root user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
