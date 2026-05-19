from __future__ import annotations
import json
import math
from typing import Optional
from sentence_transformers import SentenceTransformer

_MODEL: SentenceTransformer | None = None
_MODEL_NAME = "all-MiniLM-L6-v2"


def _get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def encode(text: str) -> list[float]:
    """Encode text into a 384-dimensional embedding vector."""
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors (assumes normalized)."""
    dot = sum(x * y for x, y in zip(a, b))
    # Clamp to [-1, 1] to avoid floating-point drift
    return max(-1.0, min(1.0, dot))


def embedding_to_json(vec: list[float]) -> str:
    return json.dumps(vec)


def embedding_from_json(s: str) -> list[float] | None:
    try:
        v = json.loads(s)
        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], (int, float)):
            return v
    except (json.JSONDecodeError, TypeError):
        pass
    return None
