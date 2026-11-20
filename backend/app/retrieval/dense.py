"""Create E5 vectors and retrieve similar passages within one paper.

Use the "passage: " prefix for paragraph embeddings and "query: " for
question embeddings. Apply the same rules in the product and benchmark.

Check vector dimensions and model snapshots. Rank candidates by cosine
similarity or dot product on normalized vectors and return candidates
from the loaded paper.
"""

from typing import Dict, List, Tuple
import numpy as np


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two vector lists."""
    v1 = np.asarray(vec1, dtype=np.float32)
    v2 = np.asarray(vec2, dtype=np.float32)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


def rank_passages_dense(
    query_vector: List[float],
    passage_vectors: Dict[str, List[float]],
    top_k: int = 40,
) -> List[Tuple[str, float]]:
    """Rank passage IDs by cosine similarity against query vector."""
    scores: List[Tuple[str, float]] = []
    for passage_id, vec in passage_vectors.items():
        sim = cosine_similarity(query_vector, vec)
        scores.append((passage_id, sim))

    # Sort descending by score, tie-break by passage_id
    scores.sort(key=lambda x: (-x[1], x[0]))
    return scores[:top_k]
