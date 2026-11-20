"""Build a BM25 index and rank passages within one paper.

Accept chunked passages and a question. Return the lexical ranking for
B1, RRF fusion, and the product's BM25 fallback.
"""

import math
import re
from typing import List, Tuple
from rank_bm25 import BM25Okapi
from backend.app.core.schemas import PassageChunk


def tokenize_text(text: str) -> List[str]:
    """Tokenize query or passage into lowercased alphanumeric tokens."""
    return [token.lower() for token in re.findall(r"\w+", text) if len(token) > 1]


class LuceneBM25(BM25Okapi):
    """BM25Okapi with Lucene/Elasticsearch positive IDF floor (prevents zero/negative IDF on small corpora)."""

    def _calc_idf(self, nd):
        for word, freq in nd.items():
            self.idf[word] = math.log(1.0 + (self.corpus_size - freq + 0.5) / (freq + 0.5))


class BM25Index:
    """In-memory BM25 index over a paper's passage chunks."""

    def __init__(self, chunks: List[PassageChunk]):
        self.chunks = chunks
        self.corpus = [tokenize_text(c.text) for c in chunks]
        # Only initialize BM25 if corpus has non-empty documents
        if any(len(doc) > 0 for doc in self.corpus):
            self.model = LuceneBM25(self.corpus)
        else:
            self.model = None

    def search(self, query: str, top_k: int = 40) -> List[Tuple[PassageChunk, float]]:
        """Search chunks with BM25. Return sorted (chunk, score) list for scores > 0."""
        if not self.model or not self.chunks:
            return []

        query_tokens = tokenize_text(query)
        if not query_tokens:
            return []

        scores = self.model.get_scores(query_tokens)
        scored_pairs = [
            (self.chunks[i], float(scores[i]))
            for i in range(len(self.chunks))
            if scores[i] > 0.0
        ]

        # Sort descending by score, deterministic tie-breaking by paragraph_order and offset_start
        scored_pairs.sort(
            key=lambda x: (-x[1], x[0].paragraph_order, x[0].offset_start)
        )
        return scored_pairs[:top_k]
