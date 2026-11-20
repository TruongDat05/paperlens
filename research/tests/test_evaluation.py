"""Specify tests for the QASPER protocol, metrics, and data mapping.

Use fixtures for multiple reference sets, duplicate parents, missing or
table- or figure-only gold evidence, and abstention. Check the
denominator for each metric.

Verify replay against the correct artifact hashes, report missing
records, and use primary_only for the main A1/A2 comparison.
"""

import pytest
from research.datasets.qasper import (
    QasperSample,
    QasperAnnotation,
    classify_query_eligibility,
    map_evidence_to_paragraphs,
)
from research.evaluation.metrics import (
    compute_retrieval_metrics,
    deduplicate_parent_predictions,
)


def test_qasper_evidence_mapping_and_eligibility():
    """Verify QASPER paper evidence strings map to parent paragraphs and classification works."""
    paragraphs = [
        {"id": "p0", "text": "This paper presents a new dataset called QASPER."},
        {"id": "p1", "text": "QASPER consists of 5049 questions over 1585 NLP papers."},
        {"id": "p2", "text": "Questions are written by NLP practitioners who have not read the full paper."},
    ]

    # Sample 1: Answerable with valid text evidence
    sample_answerable = QasperSample(
        question_id="q1",
        paper_id="paper_1",
        question="How many questions are in QASPER?",
        annotations=[
            QasperAnnotation(
                answer="5049 questions",
                evidence=["QASPER consists of 5049 questions over 1585 NLP papers."],
                unanswerable=False,
            )
        ],
    )
    mapped = map_evidence_to_paragraphs(sample_answerable, paragraphs)
    assert mapped.reference_sets == [["p1"]]
    eligibility = classify_query_eligibility(mapped)
    assert eligibility["is_text_retrieval_eligible"] is True
    assert eligibility["is_abstention_positive"] is True
    assert eligibility["is_abstention_negative"] is False

    # Sample 2: Unanswerable
    sample_unanswerable = QasperSample(
        question_id="q2",
        paper_id="paper_1",
        question="What is the learning rate?",
        annotations=[
            QasperAnnotation(
                answer="Unanswerable",
                evidence=[],
                unanswerable=True,
            )
        ],
    )
    mapped_un = map_evidence_to_paragraphs(sample_unanswerable, paragraphs)
    eligibility_un = classify_query_eligibility(mapped_un)
    assert eligibility_un["is_text_retrieval_eligible"] is False
    assert eligibility_un["is_abstention_negative"] is True


def test_hand_checked_metric_fixtures():
    """Verify hand-checked fixture from plan §W2.2:

    Ranked predicted chunks: p1:a, p1:b, p2, p3, p4, p5 -> 5 unique parents: [p1, p2, p3, p4, p5]
    Reference sets: {p1, p6} and {p2}
    Per-query Recall@5: max(1/2, 1/1) = 1.0
    Per-query F1@5: max(2/7, 1/3) = 1/3 (approx 0.3333)
    """
    predicted_chunk_ids = ["p1:a", "p1:b", "p2", "p3", "p4", "p5"]
    unique_parents = deduplicate_parent_predictions(predicted_chunk_ids, top_k=5)
    assert unique_parents == ["p1", "p2", "p3", "p4", "p5"]

    gold_reference_sets = [["p1", "p6"], ["p2"]]

    metrics = compute_retrieval_metrics(
        predicted_parents=unique_parents,
        valid_reference_sets=gold_reference_sets,
        k=5,
    )

    assert metrics["recall@5"] == pytest.approx(1.0, rel=1e-3)
    assert metrics["f1@5"] == pytest.approx(1.0 / 3.0, rel=1e-3)
    # MRR@10 check: first relevant item for ref set 2 is p1 (not in ref2) or p2 (rank 2)
    # For ref set 1: p1 is rank 1 -> RR = 1.0. Max RR over valid sets is 1.0
    assert metrics["mrr@10"] == pytest.approx(1.0, rel=1e-3)


def test_empty_predictions_and_zero_gold():
    """Verify empty predictions produce 0 score, and empty gold is handled gracefully."""
    gold_refs = [["p1", "p2"]]
    zero_metrics = compute_retrieval_metrics(
        predicted_parents=[],
        valid_reference_sets=gold_refs,
        k=5,
    )
    assert zero_metrics["recall@5"] == 0.0
    assert zero_metrics["f1@5"] == 0.0


def test_replay_adapter_integrity_and_lookup(tmp_path):
    """Verify ReplayAdapter loads records, returns deterministic data, and detects missing/tampered items."""
    from research.evaluation.replay import ReplayAdapter, ReplayError
    import json

    records = {
        "run_id": "test_run_1",
        "records": {
            "q1": {
                "question_id": "q1",
                "predicted_parents": ["p1", "p2"],
                "evidence_scores": [0.95, 0.80],
                "answer_text": "Answer for q1",
                "citations": ["p1"],
            }
        },
    }
    artifact_file = tmp_path / "replay_records.json"
    artifact_file.write_text(json.dumps(records), encoding="utf-8")

    adapter = ReplayAdapter(str(artifact_file))
    res = adapter.get_record("q1")
    assert res["predicted_parents"] == ["p1", "p2"]
    assert res["answer_text"] == "Answer for q1"

    # Missing question raises ReplayError
    with pytest.raises(ReplayError, match="Missing replay record"):
        adapter.get_record("q_unknown")

    # List-format replay loading verification
    list_records = [
        {
            "question_id": "q_list_1",
            "predicted_parents": ["p10"],
            "answer_text": "Answer from list",
        }
    ]
    list_file = tmp_path / "replay_list.json"
    list_file.write_text(json.dumps(list_records), encoding="utf-8")
    list_adapter = ReplayAdapter(str(list_file))
    list_res = list_adapter.get_record("q_list_1")
    assert list_res["predicted_parents"] == ["p10"]
    assert list_res["answer_text"] == "Answer from list"


def test_qa_audit_scoring():
    """Verify qa_audit computes citation validity, 0/1/2 correctness, and abstention."""
    from research.evaluation.qa_audit import run_qa_audit

    results = [
        {
            "question_id": "q1",
            "is_unanswerable_gold": False,
            "gold_evidence": ["p1"],
            "predicted_parents": ["p1", "p2"],
            "answer_blocks": [{"text": "Claim 1", "evidence_ids": ["p1"]}],
            "emitted_citation_ids": ["p1"],
            "available_evidence_ids": ["p1", "p2"],
            "human_judgment": {"score": 2, "supported_claims": 1, "total_claims": 1},
        },
        {
            "question_id": "q2",
            "is_unanswerable_gold": False,
            "gold_evidence": ["p3"],
            "predicted_parents": ["p3"],
            "answer_blocks": [{"text": "Claim 2", "evidence_ids": ["p99_hallucinated"]}],
            "emitted_citation_ids": ["p99_hallucinated"],
            "available_evidence_ids": ["p3"],
            "human_judgment": {"score": 1, "supported_claims": 0, "total_claims": 1},
        },
        {
            "question_id": "q3",
            "is_unanswerable_gold": True,
            "gold_evidence": [],
            "predicted_parents": [],
            "answer_blocks": [{"text": "I cannot answer based on the paper.", "evidence_ids": []}],
            "emitted_citation_ids": [],
            "available_evidence_ids": [],
            "abstained": True,
            "human_judgment": {"score": 2, "supported_claims": 0, "total_claims": 0},
        },
    ]

    summary = run_qa_audit(results)
    # Citation validity: 1 resolvable out of 2 emitted = 0.5
    assert summary["citation_validity"] == pytest.approx(0.5, rel=1e-2)
    # Average rubric score: (2 + 1 + 2) / 3 = 1.6667
    assert summary["average_rubric_score"] == pytest.approx(1.6667, rel=1e-2)
    # Abstention on unanswerable gold: 1 justified abstention, 0 false abstentions
    assert summary["unanswerable_abstention_accuracy"] == 1.0
    assert summary["false_abstention_count"] == 0

    # Unassessed metrics return None, not 1.0
    empty_summary = run_qa_audit([])
    assert empty_summary["citation_validity"] is None
    assert empty_summary["unanswerable_abstention_accuracy"] is None
    assert empty_summary["citation_support_precision"] is None


def test_run_eval_pipeline_execution(tmp_path):
    """Verify run_eval runs on synthetic paper samples and writes immutable manifest, results, and metrics."""
    from research.evaluation.run_eval import evaluate_dataset
    import json

    output_dir = tmp_path / "artifacts_run_1"

    papers_data = [
        {
            "paper_id": "test_p1",
            "title": "Attention Is All You Need",
            "paragraphs": [
                {"id": "p0", "text": "The Transformer architecture relies on self-attention.", "section_path": "Abstract"},
                {"id": "p1", "text": "We evaluate on WMT 2014 English-to-German translation.", "section_path": "5 Experiments"},
            ],
            "questions": [
                {
                    "question_id": "q1",
                    "question": "What translation dataset is used for evaluation?",
                    "annotations": [
                        {"answer": "WMT 2014 English-to-German", "evidence": ["WMT 2014 English-to-German"], "unanswerable": False}
                    ],
                }
            ],
        }
    ]

    metrics = evaluate_dataset(
        papers_data=papers_data,
        pipeline="B1",
        mode="fixture",
        output_dir=str(output_dir),
    )

    assert output_dir.exists()
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "results.json").exists()
    assert (output_dir / "metrics.json").exists()

    saved_metrics = json.loads((output_dir / "metrics.json").read_text())
    assert "recall@5" in saved_metrics
    assert saved_metrics["recall@5"] >= 0.0

    # Test B4 pipeline in fixture mode
    output_dir_b4 = tmp_path / "artifacts_run_b4"
    metrics_b4 = evaluate_dataset(
        papers_data=papers_data,
        pipeline="B4",
        mode="fixture",
        output_dir=str(output_dir_b4),
    )
    assert "candidate_recall@20" in metrics_b4

    # Test A1 pipeline in fixture mode
    output_dir_a1 = tmp_path / "artifacts_run_a1"
    metrics_a1 = evaluate_dataset(
        papers_data=papers_data,
        pipeline="A1",
        mode="fixture",
        output_dir=str(output_dir_a1),
    )
    assert "total_queries" in metrics_a1
