"""Summarize the quality of answers and their cited sources.

Apply the rubric for correctness, completeness, citation support,
coverage, and abstention on the frozen subset. Record citation validity
from ID checks.

Compare A1 and A2 on the same questions. Link observations to source
evidence, the model, and the run ID, and report successes, errors,
usage, and cost.
"""

from typing import Any, Dict, List


def run_qa_audit(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Ingest evaluation QA outputs and judgments to compute quality, citation, and abstention metrics."""
    total_queries = len(results)
    if total_queries == 0:
        return {
            "total_queries": 0,
            "citation_validity": None,
            "average_rubric_score": None,
            "unanswerable_abstention_accuracy": None,
            "false_abstention_count": 0,
            "rubric_distribution": {"0": 0, "1": 0, "2": 0},
            "citation_support_precision": None,
        }

    total_emitted_citations = 0
    valid_citations = 0

    rubric_scores: List[int] = []
    rubric_counts = {"0": 0, "1": 0, "2": 0}

    total_claims = 0
    supported_claims = 0

    unanswerable_total = 0
    justified_abstentions = 0
    false_abstentions = 0

    for item in results:
        is_unanswerable = item.get("is_unanswerable_gold", False)
        abstained = item.get("abstained", False) or item.get("status") == "abstain"

        # Abstention tracking
        if is_unanswerable:
            unanswerable_total += 1
            if abstained:
                justified_abstentions += 1
        else:
            if abstained:
                false_abstentions += 1

        # Citation validity
        emitted = item.get("emitted_citation_ids", [])
        available = set(item.get("available_evidence_ids", []))
        total_emitted_citations += len(emitted)
        for cid in emitted:
            if cid in available:
                valid_citations += 1

        # Rubric & claim support
        judgment = item.get("human_judgment", {})
        score = judgment.get("score")
        if score is not None and score in (0, 1, 2):
            rubric_scores.append(score)
            rubric_counts[str(score)] += 1

        total_claims += judgment.get("total_claims", 0)
        supported_claims += judgment.get("supported_claims", 0)

    citation_validity = (
        valid_citations / total_emitted_citations if total_emitted_citations > 0 else None
    )
    avg_rubric = (
        sum(rubric_scores) / len(rubric_scores) if rubric_scores else None
    )
    abstention_accuracy = (
        justified_abstentions / unanswerable_total if unanswerable_total > 0 else None
    )
    support_precision = (
        supported_claims / total_claims if total_claims > 0 else None
    )

    return {
        "total_queries": total_queries,
        "citation_validity": citation_validity,
        "valid_citations_count": valid_citations,
        "total_emitted_citations_count": total_emitted_citations,
        "average_rubric_score": avg_rubric,
        "rubric_distribution": rubric_counts,
        "unanswerable_total": unanswerable_total,
        "justified_abstentions": justified_abstentions,
        "unanswerable_abstention_accuracy": abstention_accuracy,
        "false_abstention_count": false_abstentions,
        "citation_support_precision": support_precision,
    }
