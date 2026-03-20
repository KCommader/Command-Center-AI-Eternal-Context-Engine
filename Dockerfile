# Command Center AI — Eternal Context Engine
# Minimal image: runs the engine on port 8765.
# Mount your vault and .lancedb as volumes — data never lives inside the container.

FROM python:3.11-slim

WORKDIR /app

# System deps for sentence-transformers (numpy, torch)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps first (cache layer — only rebuilds when requirements change)
COPY engine/requirements.txt engine/requirements.txt
RUN pip install --no-cache-dir -r engine/requirements.txt

# Copy engine code
COPY engine/ engine/

# Default env vars — override via docker-compose.yml or -e flags
ENV OMNI_VAULT_PATH=/data/vault
ENV OMNI_DB_DIR=/data/.lancedb
ENV PYTHONUNBUFFERED=1

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

CMD ["python", "engine/omniscience.py", "start", "--foreground"]
