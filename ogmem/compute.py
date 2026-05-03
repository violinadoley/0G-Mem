"""Embedding + similarity search client. Uses local sentence-transformers with OpenAI fallback."""

import math
from typing import Optional

import requests


_local_model = None  # lazy-loaded on first use


def _get_local_model():
    """Load sentence-transformers model once and cache it."""
    global _local_model
    if _local_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _local_model = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            raise RuntimeError(
                "sentence-transformers not installed. Run: "
                "pip install sentence-transformers"
            )
    return _local_model


class ComputeClient:
    """Embedding and similarity search. Local sentence-transformers, with 0G Serving / OpenAI fallback."""

    EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 dimension

    def __init__(self, serving_broker_url: str, openai_api_key: Optional[str] = None):
        self.serving_broker_url = serving_broker_url.rstrip("/")
        self.openai_api_key = openai_api_key
        self.session = requests.Session()

    def embed(self, text: str) -> list[float]:
        """Return a normalized embedding vector. Falls back to 0G Serving then OpenAI."""
        errors = []

        try:
            model = _get_local_model()
            return model.encode(text, normalize_embeddings=True).tolist()
        except Exception as e:
            errors.append(f"local: {e}")

        try:
            resp = self.session.post(
                f"{self.serving_broker_url}/v1/embeddings",
                json={"model": "text-embedding-3-small", "input": text},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()["data"][0]["embedding"]
            errors.append(f"serving: HTTP {resp.status_code}")
        except Exception as e:
            errors.append(f"serving: {e}")

        if self.openai_api_key:
            try:
                resp = requests.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {self.openai_api_key}"},
                    json={"model": "text-embedding-3-small", "input": text},
                    timeout=15,
                )
                if resp.status_code == 200:
                    return resp.json()["data"][0]["embedding"]
                errors.append(f"openai: HTTP {resp.status_code}")
            except Exception as e:
                errors.append(f"openai: {e}")

        raise RuntimeError(
            "All embedding sources failed. "
            "Ensure sentence-transformers is installed: pip install sentence-transformers\n"
            f"Details: {'; '.join(errors)}"
        )

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            model = _get_local_model()
            return model.encode(texts, normalize_embeddings=True).tolist()
        except Exception:
            return [self.embed(t) for t in texts]

    def similarity_search(
        self,
        query_vec: list[float],
        candidate_vecs: list[list[float]],
        top_k: int = 3,
    ) -> list[tuple[int, float]]:
        """Return top-k (index, score) pairs sorted by cosine similarity descending."""
        if not candidate_vecs:
            return []

        scores = [
            (i, self._cosine_similarity(query_vec, vec))
            for i, vec in enumerate(candidate_vecs)
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
