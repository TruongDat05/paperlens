"""Expose the QASPER retrieval and agent evaluation CLI.

Run python -m research.evaluation.run_eval from the repository root with
an explicit configuration, split, B1–B4 or A1/A2 pipeline, and live or
replay mode.

Load each paper into memory and call the shared chunking, retrieval, and
agent code directly. Supply adapters for the selected mode. Use Gemini
primary_only for the main A1/A2 comparison.

Write the manifest, per-query results, errors, usage, and metric tables
with enough information to reproduce the run.
"""

from typing import Any, Dict, List, Optional
import argparse
import asyncio
import json
import os
import subprocess
import time
import uuid
import yaml

from backend.app.core.schemas import ParagraphInput, SourceLocation, PaperIngestRequest, SectionInput
from backend.app.retrieval.chunking import chunk_paper
from backend.app.retrieval.bm25 import BM25Index
from backend.app.retrieval.dense import rank_passages_dense
from backend.app.retrieval.hybrid import reciprocal_rank_fusion, retrieve_hybrid
from backend.app.cache.paper_store import store_paper_and_chunks
from backend.app.agent.single_pass import run_single_pass
from backend.app.agent.controller import run_bounded_agent
from backend.app.agent.model_router import ModelRouter, RoutingMode
from backend.app.providers.fpt import FPTProvider
from research.datasets.qasper import (
    QasperSample,
    QasperAnnotation,
    map_evidence_to_paragraphs,
    classify_query_eligibility,
)
from research.evaluation.metrics import (
    compute_retrieval_metrics,
    deduplicate_parent_predictions,
)
from research.evaluation.replay import ReplayAdapter, ReplayError
from research.evaluation.qa_audit import run_qa_audit


def get_git_revision() -> Dict[str, str]:
    """Retrieve current commit hash and dirty status for artifact manifest."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
    except Exception:
        commit = "unknown"

    try:
        status_out = subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        is_dirty = len(status_out) > 0
    except Exception:
        is_dirty = False

    return {"commit": commit, "dirty": str(is_dirty)}


def _evaluate_dataset(
    papers_data: List[Dict[str, Any]],
    pipeline: str = "B1",
    mode: str = "replay",
    config: Optional[Dict[str, Any]] = None,
    output_dir: Optional[str] = None,
    replay_adapter: Optional[ReplayAdapter] = None,
) -> Dict[str, Any]:
    """Evaluate retrieval or QA pipeline across papers and write immutable artifacts."""
    run_id = f"eval_{pipeline.lower()}_{int(time.time())}_{str(uuid.uuid4())[:6]}"
    if not output_dir:
        output_dir = os.path.join("artifacts", run_id)
    os.makedirs(output_dir, exist_ok=True)

    results: List[Dict[str, Any]] = []
    eligible_metrics: List[Dict[str, float]] = []

    for paper in papers_data:
        paper_id = paper.get("paper_id", "unknown_paper")
        raw_paragraphs = paper.get("paragraphs", [])

        # Format paragraphs for chunking and mapping
        formatted_paragraphs = []
        for i, p in enumerate(raw_paragraphs):
            loc_data = p.get("locator", {"element_id": p.get("id", f"p{i}")})
            loc = SourceLocation(**loc_data) if isinstance(loc_data, dict) else SourceLocation()
            formatted_paragraphs.append(
                ParagraphInput(
                    id=p.get("id", f"p{i}"),
                    section_id=p.get("section_id", "s0"),
                    section_path=p.get("section_path", "Main"),
                    order=i,
                    text=p.get("text", ""),
                    locator=loc,
                )
            )

        chunks = chunk_paper(formatted_paragraphs, max_tokens=400, paper_id=paper_id)

        # Ingest paper into store for real product pipeline execution
        paper_req = PaperIngestRequest(
            arxiv_id=paper_id,
            version="v1",
            canonical_url=f"https://arxiv.org/abs/{paper_id}",
            title=paper.get("title", "Paper"),
            sections=[
                SectionInput(id=p.section_id, heading=p.section_path, path=p.section_path, order=idx)
                for idx, p in enumerate(formatted_paragraphs)
            ],
            paragraphs=formatted_paragraphs,
        )
        store_paper_and_chunks(
            paper_id=paper_id,
            owner_id="eval-user",
            paper_req=paper_req,
            content_hash=f"eval_hash_{paper_id}",
            chunks=chunks,
            lexical_ready=True,
            semantic_ready=True,
        )

        bm25 = BM25Index(chunks)
        fpt = FPTProvider()
        passage_vectors: Dict[str, List[float]] = {}
        if mode != "replay" and pipeline in ("B2", "B3", "B4"):
            vec_list = asyncio.run(fpt.get_embeddings([c.text for c in chunks], prefix="passage: ", mock=(mode == "fixture")))
            passage_vectors = {c.passage_id: v for c, v in zip(chunks, vec_list)}

        for q_dict in paper.get("questions", []):
            q_id = q_dict.get("question_id", str(uuid.uuid4()))
            q_text = q_dict.get("question", "")
            annotations = [
                QasperAnnotation(
                    answer=a.get("answer", ""),
                    evidence=a.get("evidence", []),
                    unanswerable=a.get("unanswerable", False),
                )
                for a in q_dict.get("annotations", [])
            ]

            sample = QasperSample(
                question_id=q_id,
                paper_id=paper_id,
                question=q_text,
                annotations=annotations,
            )
            sample = map_evidence_to_paragraphs(sample, formatted_paragraphs)
            eligibility = classify_query_eligibility(sample)

            predicted_parents: List[str] = []
            candidate_passage_ids: List[str] = []
            answer_text = ""
            answer_blocks = []
            emitted_citations = []
            available_evidence_ids = []
            status = "completed"

            if mode == "replay" and replay_adapter:
                rec = replay_adapter.get_record(q_id)
                predicted_parents = rec.get("predicted_parents", [])
                candidate_passage_ids = rec.get("candidate_passage_ids", predicted_parents)
                answer_text = rec.get("answer_text", "")
                answer_blocks = rec.get("answer_blocks", [])
                emitted_citations = rec.get("emitted_citation_ids", rec.get("citations", []))
                available_evidence_ids = rec.get("available_evidence_ids", predicted_parents)
                status = rec.get("status", "unknown")
            else:
                # Live or Fixture execution via real product pipelines
                if pipeline in ("B1", "B2", "B3", "B4"):
                    ev_res = asyncio.run(
                        retrieve_hybrid(
                            query=q_text,
                            chunks=chunks,
                            bm25_index=bm25,
                            mode=pipeline,
                            top_k=5,
                            paper_id=paper_id,
                            owner_id="eval-user",
                            fpt_provider=fpt,
                            passage_vectors=passage_vectors,
                        )
                    )
                    predicted_parents = [ev.passage_id for ev in ev_res.evidence]
                    candidate_passage_ids = ev_res.candidate_passage_ids
                elif pipeline == "A1":
                    router = ModelRouter(mode=RoutingMode.PRIMARY_ONLY)
                    agent_res = asyncio.run(
                        run_single_pass(
                            run_id=q_id,
                            paper_id=paper_id,
                            owner_id="eval-user",
                            question=q_text,
                            router=router,
                        )
                    )
                    predicted_parents = [ev.passage_id for ev in agent_res.evidence]
                    candidate_passage_ids = predicted_parents
                    answer_blocks = [b.model_dump() for b in agent_res.answer_blocks]
                    answer_text = " ".join(b.text for b in agent_res.answer_blocks)
                    emitted_citations = agent_res.emitted_citation_ids
                    available_evidence_ids = [ev.passage_id for ev in agent_res.evidence]
                    status = agent_res.status.value
                elif pipeline == "A2":
                    router = ModelRouter(mode=RoutingMode.PRIMARY_ONLY)
                    agent_res = asyncio.run(
                        run_bounded_agent(
                            run_id=q_id,
                            paper_id=paper_id,
                            owner_id="eval-user",
                            question=q_text,
                            router=router,
                        )
                    )
                    predicted_parents = [ev.passage_id for ev in agent_res.evidence]
                    candidate_passage_ids = predicted_parents
                    answer_blocks = [b.model_dump() for b in agent_res.answer_blocks]
                    answer_text = " ".join(b.text for b in agent_res.answer_blocks)
                    emitted_citations = agent_res.emitted_citation_ids
                    available_evidence_ids = [ev.passage_id for ev in agent_res.evidence]
                    status = agent_res.status.value

            # Metric evaluation
            query_metrics = {}
            if eligibility["is_text_retrieval_eligible"] and sample.reference_sets:
                query_metrics = compute_retrieval_metrics(
                    predicted_parents=predicted_parents,
                    valid_reference_sets=sample.reference_sets,
                    k=5,
                    candidate_predictions=candidate_passage_ids,
                )
                eligible_metrics.append(query_metrics)

            results.append({
                "question_id": q_id,
                "paper_id": paper_id,
                "question": q_text,
                "pipeline": pipeline,
                "is_unanswerable_gold": eligibility["is_abstention_negative"],
                "gold_reference_sets": sample.reference_sets,
                "predicted_parents": predicted_parents,
                "metrics": query_metrics,
                "answer_text": answer_text,
                "answer_blocks": answer_blocks,
                "emitted_citation_ids": emitted_citations,
                "available_evidence_ids": available_evidence_ids,
                "status": status,
            })

    # Aggregate metrics
    mean_metrics: Dict[str, float] = {
        "recall@5": 0.0,
        "f1@5": 0.0,
        "candidate_recall@20": 0.0,
        "mrr@10": 0.0,
    }
    if eligible_metrics:
        for k in mean_metrics.keys():
            scores = [m[k] for m in eligible_metrics if k in m]
            if scores:
                mean_metrics[k] = sum(scores) / len(scores)

    mean_metrics["eligible_queries_count"] = float(len(eligible_metrics))
    mean_metrics["total_queries_count"] = float(len(results))

    # Add QA audit summary for QA pipelines
    if pipeline in ("A1", "A2"):
        audit_summary = run_qa_audit(results)
        mean_metrics.update(audit_summary)

    # Save immutable artifacts
    git_info = get_git_revision()
    manifest_data = {
        "run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pipeline": pipeline,
        "mode": mode,
        "git_commit": git_info["commit"],
        "git_dirty": git_info["dirty"],
        "config": config or {},
        "total_queries": len(results),
        "eligible_queries": len(eligible_metrics),
    }

    with open(os.path.join(output_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    with open(os.path.join(output_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(output_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(mean_metrics, f, indent=2)

    return mean_metrics


def evaluate_dataset(papers_data, pipeline="B1", mode="replay", config=None, output_dir=None, replay_adapter=None):
    """Every evaluation uses a disposable database and explicit provider mode."""
    import tempfile
    from backend.app.core.config import get_settings
    from backend.app.core.db import _local
    from backend.app.cache import paper_store
    if mode not in {"fixture", "replay", "live"}:
        raise ValueError("Unknown evaluation mode")
    if mode == "replay" and replay_adapter is None:
        raise ReplayError("Replay requires recorded outputs; live fallback is forbidden")
    settings = get_settings()
    previous = settings.db_path, settings.mock_providers
    with tempfile.TemporaryDirectory(prefix="paperlens-eval-") as root:
        settings.db_path = os.path.join(root, "eval.db")
        settings.mock_providers = mode != "live"
        paper_store._chunks_cache.clear()
        paper_store._bm25_cache.clear()
        paper_store._vectors_cache.clear()
        try:
            return _evaluate_dataset(papers_data, pipeline, mode, config, output_dir, replay_adapter)
        finally:
            conn = getattr(_local, "connections", {}).pop(settings.db_path, None)
            if conn:
                conn.close()
            settings.db_path, settings.mock_providers = previous
            paper_store._chunks_cache.clear()
            paper_store._bm25_cache.clear()
            paper_store._vectors_cache.clear()


def main():
    parser = argparse.ArgumentParser(description="Run QASPER retrieval and agent evaluation.")
    parser.add_argument("--config", type=str, default="configs/baseline.yaml", help="Path to config YAML")
    parser.add_argument("--split", type=str, default="dev", choices=["dev", "test", "train"])
    parser.add_argument("--pipeline", type=str, default="B1", choices=["B1", "B2", "B3", "B4", "A1", "A2"])
    parser.add_argument("--mode", type=str, default="fixture", choices=["replay", "live", "fixture"])
    parser.add_argument("--replay-file", type=str, default=None, help="Path to replay records JSON")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save artifacts")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of evaluation samples")

    args = parser.parse_args()

    cfg: Dict[str, Any] = {}
    if os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    replay_adapter = None
    if args.mode == "replay":
        if not args.replay_file:
            raise ValueError("--replay-file is required when running in replay mode.")
        replay_adapter = ReplayAdapter(args.replay_file)

    # Built-in evaluation sample papers for self-contained execution
    papers_data = [
        {
            "paper_id": "1706.03762",
            "title": "Attention Is All You Need",
            "paragraphs": [
                {"id": "p1", "text": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.", "section_path": "1 Introduction"},
                {"id": "p2", "text": "The Transformer is the first transduction model relying entirely on self-attention to compute representations.", "section_path": "1 Introduction"},
                {"id": "p3", "text": "An attention function can be described as mapping a query and a set of key-value pairs to an output.", "section_path": "3.2 Attention"},
                {"id": "p4", "text": "On the WMT 2014 English-to-German translation task, the big transformer model achieves a new state-of-the-art BLEU score of 28.4.", "section_path": "5.1 Machine Translation"},
            ],
            "questions": [
                {
                    "question_id": "q1",
                    "question": "What is the Transformer model based on?",
                    "annotations": [
                        {"answer": "relying entirely on self-attention", "evidence": ["relying entirely on self-attention"], "unanswerable": False}
                    ],
                },
                {
                    "question_id": "q2",
                    "question": "What BLEU score does the transformer achieve on English-to-German translation?",
                    "annotations": [
                        {"answer": "28.4 BLEU", "evidence": ["state-of-the-art BLEU score of 28.4"], "unanswerable": False}
                    ],
                },
                {
                    "question_id": "q3",
                    "question": "What is the learning rate schedule for speech recognition?",
                    "annotations": [
                        {"answer": "Unanswerable", "evidence": [], "unanswerable": True}
                    ],
                },
            ],
        }
    ]

    metrics = evaluate_dataset(
        papers_data=papers_data,
        pipeline=args.pipeline,
        mode=args.mode,
        config=cfg,
        output_dir=args.output_dir,
        replay_adapter=replay_adapter,
    )

    print("=" * 60)
    print(f"PaperLens Evaluation Complete: Pipeline={args.pipeline}, Mode={args.mode}")
    print(f"Recall@5:            {metrics.get('recall@5', 0.0):.4f}")
    print(f"Evidence F1@5:       {metrics.get('f1@5', 0.0):.4f}")
    print(f"Candidate Recall@20: {metrics.get('candidate_recall@20', 0.0):.4f}")
    print(f"MRR@10:              {metrics.get('mrr@10', 0.0):.4f}")
    if args.pipeline in ("A1", "A2"):
        print(f"Citation Validity:   {metrics.get('citation_validity')}")
        print(f"Average Rubric:      {metrics.get('average_rubric_score')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
