"""Compute retrieval metrics for scientific paper evaluation.

Calculate Recall@k, Paragraph Evidence F1@k, Candidate Recall@20, and
MRR@10 over valid reference sets according to the v4.1 QASPER protocol.
"""

from typing import Dict, List, Optional, Set


def deduplicate_parent_predictions(
    predicted_chunk_ids: List[str],
    top_k: int = 5,
) -> List[str]:
    """Map candidate chunks to their parent paragraph IDs, deduplicating in rank order."""
    unique_parents: List[str] = []
    seen: Set[str] = set()

    for chunk_id in predicted_chunk_ids:
        parent_id = chunk_id.split(":")[0]
        if parent_id not in seen:
            seen.add(parent_id)
            unique_parents.append(parent_id)
            if len(unique_parents) >= top_k:
                break

    return unique_parents


def compute_retrieval_metrics(
    predicted_parents: List[str],
    valid_reference_sets: List[List[str]],
    k: int = 5,
    candidate_predictions: Optional[List[str]] = None,
) -> Dict[str, float]:
    """Compute per-query Recall@k, Paragraph Evidence F1@k, Candidate Recall@20, and MRR@10 maximized over valid reference sets."""
    if not valid_reference_sets:
        return {
            f"recall@{k}": 0.0,
            f"f1@{k}": 0.0,
            "candidate_recall@20": 0.0,
            "mrr@10": 0.0,
        }

    preds_at_k = predicted_parents[:k]
    preds_set = set(preds_at_k)

    # Candidate pool for Candidate Recall@20
    cand_preds = candidate_predictions if candidate_predictions is not None else predicted_parents
    cand_parents = deduplicate_parent_predictions(cand_preds, top_k=20)
    cand_set = set(cand_parents)

    max_recall = 0.0
    max_f1 = 0.0
    max_mrr = 0.0
    max_cand_recall = 0.0

    for ref_set in valid_reference_sets:
        gold_set = set(ref_set)
        if not gold_set:
            continue

        intersection = preds_set.intersection(gold_set)
        num_matched = len(intersection)

        recall = num_matched / len(gold_set)
        precision = num_matched / len(preds_set) if preds_set else 0.0

        if precision + recall > 0.0:
            f1 = (2.0 * precision * recall) / (precision + recall)
        else:
            f1 = 0.0

        cand_recall = len(cand_set.intersection(gold_set)) / len(gold_set)
        if cand_recall > max_cand_recall:
            max_cand_recall = cand_recall

        # MRR@10: check first relevant hit in top 10
        mrr = 0.0
        for rank_idx, pred in enumerate(predicted_parents[:10], start=1):
            if pred in gold_set:
                mrr = 1.0 / rank_idx
                break

        if recall > max_recall:
            max_recall = recall
        if f1 > max_f1:
            max_f1 = f1
        if mrr > max_mrr:
            max_mrr = mrr

    return {
        f"recall@{k}": max_recall,
        f"f1@{k}": max_f1,
        "candidate_recall@20": max_cand_recall,
        "mrr@10": max_mrr,
    }
