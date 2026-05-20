from __future__ import annotations
import json
import logging

import numpy as np
from sentence_transformers import SentenceTransformer

log = logging.getLogger("pacer.embedding")

_MODEL: SentenceTransformer | None = None
_MODEL_NAME = "all-MiniLM-L6-v2"
_DTYPE = np.float32


def _get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def encode(text: str) -> np.ndarray:
    """Encode text into a normalized float32 vector."""
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return np.asarray(vec, dtype=_DTYPE)


def vec_to_bytes(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=_DTYPE).tobytes()


def bytes_to_vec(b: bytes | None, dim: int | None) -> np.ndarray | None:
    if not b:
        return None
    try:
        arr = np.frombuffer(b, dtype=_DTYPE)
        if dim and arr.shape[0] != dim:
            return None
        return arr
    except (ValueError, TypeError):
        return None


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for normalized vectors (= dot product, clamped)."""
    return float(np.clip(float(np.dot(a, b)), -1.0, 1.0))


# -- Legacy JSON-encoded interop --------------------------------------------

def embedding_to_json(vec: np.ndarray | list[float]) -> str:
    if isinstance(vec, np.ndarray):
        return json.dumps(vec.tolist())
    return json.dumps(vec)


def embedding_from_json(s: str) -> np.ndarray | None:
    try:
        v = json.loads(s)
        if isinstance(v, list) and v and isinstance(v[0], (int, float)):
            return np.asarray(v, dtype=_DTYPE)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None
