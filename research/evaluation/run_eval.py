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
