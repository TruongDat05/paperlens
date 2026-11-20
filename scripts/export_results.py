"""Export tables from identified evaluation runs.

Read metric outputs and manifests for the selected runs and write tables
to reports/tables. Keep the split, sample size, errors, routing, and
live or replay mode for traceability.
"""

from typing import Any, Dict, List, Optional
import argparse
import glob
import json
import os


def load_run_artifact(run_dir: str) -> Optional[Dict[str, Any]]:
    """Load manifest.json and metrics.json from a run directory."""
    manifest_path = os.path.join(run_dir, "manifest.json")
    metrics_path = os.path.join(run_dir, "metrics.json")
    if not (os.path.exists(manifest_path) and os.path.exists(metrics_path)):
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        with open(metrics_path, "r", encoding="utf-8") as f:
            metrics = json.load(f)
        return {
            "run_dir": run_dir,
            "manifest": manifest,
            "metrics": metrics,
        }
    except Exception:
        return None


def generate_retrieval_table(runs: List[Dict[str, Any]]) -> str:
    """Generate Markdown comparison table for B1-B4 retrieval pipelines."""
    retrieval_runs = [
        r for r in runs if r["manifest"].get("pipeline") in ("B1", "B2", "B3", "B4")
    ]
    if not retrieval_runs:
        return "No retrieval runs found."

    lines = [
        "| Pipeline | Mode | Recall@5 | Evidence F1@5 | Cand Recall@20 | MRR@10 | Queries | Commit |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for r in sorted(retrieval_runs, key=lambda x: x["manifest"].get("pipeline", "")):
        m = r["metrics"]
        mf = r["manifest"]
        rec5 = metric(m.get('recall@5'))
        f1 = metric(m.get('f1@5'))
        cand20 = metric(m.get('candidate_recall@20'))
        mrr10 = metric(m.get('mrr@10'))
        q_count = int(mf.get("eligible_queries", mf.get("total_queries", 0)))
        commit_short = mf.get("git_commit", "unknown")[:7]
        lines.append(
            f"| **{mf.get('pipeline')}** | {mf.get('mode')} | {rec5} | {f1} | {cand20} | {mrr10} | {q_count} | `{commit_short}` |"
        )
    return "\n".join(lines)


def metric(value):
    return "unknown" if value is None else f"{value:.4f}"


def generate_qa_table(runs: List[Dict[str, Any]]) -> str:
    """Generate Markdown comparison table for A1 and A2 QA pipelines."""
    qa_runs = [
        r for r in runs if r["manifest"].get("pipeline") in ("A1", "A2")
    ]
    if not qa_runs:
        return "No agent QA runs found."

    lines = [
        "| Pipeline | Mode | Citation Validity | Rubric (0-2) | Abstention Acc | Support Prec | Recall@5 | Queries |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for r in sorted(qa_runs, key=lambda x: x["manifest"].get("pipeline", "")):
        m = r["metrics"]
        mf = r["manifest"]
        cite_val = metric(m.get('citation_validity'))
        rubric = metric(m.get('average_rubric_score'))
        abstain = metric(m.get('unanswerable_abstention_accuracy'))
        support = metric(m.get('citation_support_precision'))
        rec5 = metric(m.get('recall@5'))
        q_count = int(mf.get("total_queries", 0))
        lines.append(
            f"| **{mf.get('pipeline')}** | {mf.get('mode')} | {cite_val} | {rubric} | {abstain} | {support} | {rec5} | {q_count} |"
        )
    return "\n".join(lines)


def export_all_tables(artifacts_dir: str = "artifacts", output_dir: str = "reports/tables") -> None:
    """Scan artifact directories and write markdown tables to reports/tables/."""
    os.makedirs(output_dir, exist_ok=True)
    subdirs = glob.glob(os.path.join(artifacts_dir, "*"))

    loaded_runs: List[Dict[str, Any]] = []
    for d in subdirs:
        if os.path.isdir(d):
            artifact = load_run_artifact(d)
            if artifact:
                loaded_runs.append(artifact)

    retrieval_md = generate_retrieval_table(loaded_runs)
    qa_md = generate_qa_table(loaded_runs)

    with open(os.path.join(output_dir, "retrieval_summary.md"), "w", encoding="utf-8") as f:
        f.write("# PaperLens Retrieval Benchmarks (B1–B4)\n\n" + retrieval_md + "\n")

    with open(os.path.join(output_dir, "agent_qa_summary.md"), "w", encoding="utf-8") as f:
        f.write("# PaperLens agent evaluation artifacts\n\nFixture rows use synthetic providers and do not measure live model quality. Semantic support requires explicit judgments.\n\n" + qa_md + "\n")

    print(f"Exported benchmark tables to {output_dir}/")


def main():
    parser = argparse.ArgumentParser(description="Export benchmark tables from evaluation artifacts.")
    parser.add_argument("--artifacts-dir", type=str, default="artifacts")
    parser.add_argument("--output-dir", type=str, default="reports/tables")
    args = parser.parse_args()

    export_all_tables(args.artifacts_dir, args.output_dir)


if __name__ == "__main__":
    main()
