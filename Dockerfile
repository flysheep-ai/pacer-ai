FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/
COPY scripts/ scripts/
COPY data/ data/
COPY alembic.ini .

RUN pip install --no-cache-dir -e '.[dev]'

# Pre-download the embedding model so first request doesn't time out
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8000

CMD ["uvicorn", "pacer.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
