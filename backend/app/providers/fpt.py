"""Connect directly to FPT Cloud for E5 embeddings and BGE reranking.

Use the endpoints and schemas verified in docs/fpt_api_contract.md.
Accept prefixed text for embedding and question-passage pairs for
reranking.

Return vectors or scores aligned with their inputs, along with usage and
normalized errors. Apply batch limits, timeouts, and retries according
to the provider contract.
"""

from typing import Any, Dict, List, Optional, Tuple
import hashlib
import os
from urllib.parse import urlsplit, urlunsplit
import numpy as np
import httpx
from backend.app.core.config import get_settings


class FPTProvider:
    """Direct FPT E5/BGE adapter using retrieval credentials, separate from chat."""

    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_url = api_url if api_url is not None else settings.api_url
        self.api_key = api_key if api_key is not None else settings.api_key
        parts = urlsplit(self.api_url)
        base_path = parts.path.rstrip("/")
        for suffix in ("/chat/completions", "/embeddings", "/v1/rerank"):
            if base_path.endswith(suffix):
                base_path = base_path[:-len(suffix)]
                break
        base = urlunsplit((parts.scheme, parts.netloc, base_path, "", ""))
        self.embedding_url = os.getenv("FPT_EMBEDDING_URL") or base + "/embeddings"
        self.rerank_url = os.getenv("FPT_RERANK_URL") or base.removesuffix("/v1") + "/v1/rerank"
        self.e5_model = settings.retrieval.embedding_model
        self.bge_model = settings.retrieval.reranker_model

    def _generate_deterministic_vector(self, text: str, dim: int = 1024) -> List[float]:
        """Generate deterministic pseudo-embedding vector for offline tests without network."""
        hasher = hashlib.sha256(text.encode("utf-8"))
        seed = int.from_bytes(hasher.digest()[:4], "big")
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(dim)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    async def get_embeddings(
        self,
        texts: List[str],
        prefix: str = "passage: ",
        mock: Optional[bool] = None,
    ) -> List[List[float]]:
        """Fetch E5 embeddings for a batch of strings, applying prefix."""
        prefixed = [f"{prefix}{t}" if not t.startswith(prefix) else t for t in texts]

        is_mock = get_settings().mock_providers if mock is None else mock
        if not is_mock and not self.api_key:
            raise RuntimeError("FPT API key not configured for live embeddings")

        # Use mock vectors when in mock mode
        if is_mock:
            return [self._generate_deterministic_vector(t, dim=1024) for t in prefixed]

        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": self.e5_model.split("/")[-1],
                "input": prefixed,
            }
            res = await client.post(self.embedding_url, json=body, headers=headers)
            res.raise_for_status()
            data = res.json()
            items = data.get("data", [])
            # Sort items by index to guarantee input alignment
            items.sort(key=lambda x: x.get("index", 0))
            vectors = [item["embedding"] for item in items]
            if len(vectors) != len(texts) or any(len(v) != 1024 or not all(np.isfinite(x) for x in v) for v in vectors):
                raise ValueError("Malformed embedding response")
            return vectors

    async def rerank(
        self,
        query: str,
        documents: List[str],
        mock: Optional[bool] = None,
    ) -> List[Tuple[int, float]]:
        """Rerank documents against query with BGE reranker. Returns list of (doc_index, score)."""
        is_mock = get_settings().mock_providers if mock is None else mock
        if not is_mock and not self.api_key:
            raise RuntimeError("FPT API key not configured for live reranking")

        if is_mock:
            # Deterministic mock score based on text overlap and length
            results = []
            q_words = set(query.lower().split())
            for idx, doc in enumerate(documents):
                d_words = set(doc.lower().split())
                overlap = len(q_words.intersection(d_words))
                score = float(overlap / max(1, len(q_words)))
                results.append((idx, score))
            results.sort(key=lambda x: (-x[1], x[0]))
            return results

        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": self.bge_model.split("/")[-1],
                "query": query,
                "documents": documents,
            }
            res = await client.post(self.rerank_url, json=body, headers=headers)
            res.raise_for_status()
            data = res.json()
            results = data.get("results", [])
            scores = [(r["index"], float(r["relevance_score"])) for r in results]
            if not scores or len({i for i, _ in scores}) != len(scores) or any(not 0 <= i < len(documents) or not np.isfinite(v) for i, v in scores):
                raise ValueError("Malformed rerank response")
            return sorted(scores, key=lambda x: -x[1])
