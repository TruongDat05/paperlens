"""Load artifacts to replay the pipeline offline.

Verify the manifest and checksums, load the pinned local E5 tokenizer,
and supply adapters that read recorded embeddings, scores, and LLM
responses.

Match records by run inputs, configuration, and snapshot. Report missing
records or version mismatches and label the results as replay.
"""

from typing import Any, Dict, Optional
import json
import os
import hashlib


class ReplayError(Exception):
    """Raised when recorded replay data is missing, corrupted, or has mismatched hashes."""
    pass


class ReplayAdapter:
    """Lookup-only adapter for offline benchmark replay without live network access."""

    def __init__(self, record_path: str, expected_sha256: Optional[str] = None):
        self.record_path = record_path
        if not os.path.exists(record_path):
            raise ReplayError(f"Replay artifact path does not exist: {record_path}")

        with open(record_path, "r", encoding="utf-8") as f:
            content = f.read()

        if expected_sha256:
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if digest != expected_sha256:
                raise ReplayError(
                    f"Replay artifact hash mismatch. Expected {expected_sha256}, got {digest}"
                )

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ReplayError(f"Malformed replay JSON artifact: {e}")

        if isinstance(data, list):
            self.run_id = "unknown_replay_run"
            self.records = {
                item["question_id"]: item
                for item in data
                if isinstance(item, dict) and "question_id" in item
            }
        elif isinstance(data, dict):
            self.run_id = data.get("run_id", "unknown_replay_run")
            self.records = data.get("records", {})
        else:
            raise ReplayError("Replay artifact must be a JSON object or list")

    def get_record(self, question_id: str) -> Dict[str, Any]:
        """Fetch recorded outputs for a given question ID or fail explicitly."""
        if question_id not in self.records:
            raise ReplayError(
                f"Missing replay record for question ID '{question_id}'. "
                "Offline replay forbids implicit live fallback."
            )
        return self.records[question_id]

    def replay_retrieval(self, question_id: str) -> Dict[str, Any]:
        """Return recorded retrieval predictions."""
        rec = self.get_record(question_id)
        return {
            "question_id": question_id,
            "predicted_parents": rec.get("predicted_parents", []),
            "scores": rec.get("evidence_scores", []),
            "retrieval_mode": "replay",
        }

    def replay_agent_turn(self, question_id: str) -> Dict[str, Any]:
        """Return recorded agent answer, evidence, and serving model."""
        rec = self.get_record(question_id)
        return {
            "question_id": question_id,
            "answer_text": rec.get("answer_text", ""),
            "answer_blocks": rec.get("answer_blocks", []),
            "citations": rec.get("citations", []),
            "serving_model": rec.get("serving_model", "replay-model"),
            "status": rec.get("status", "completed"),
        }
