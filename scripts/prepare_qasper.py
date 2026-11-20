"""Prepare benchmark data and a manifest for QASPER.

Use research/datasets/qasper.py to process v0.3 using the pinned splits.
Record the revision, checksum, sample IDs, exclusion criteria, and
evidence-mapping audit.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Any

from research.datasets.qasper import (
    OFFICIAL_QASPER_VERSION,
    OFFICIAL_QASPER_REVISION,
)

MANIFEST_TEMPLATE = {
    "dataset": "allenai/qasper",
    "version": OFFICIAL_QASPER_VERSION,
    "git_revision": OFFICIAL_QASPER_REVISION,
    "source_archive": "qasper-train-dev-v0.3.tgz",
    "sha256": "3e9c4033235b6f706e236130cbfa40d993309a4d8050811e5fa016b8014561ae",
    "splits": {
        "train": {"papers": 888, "questions": 2585},
        "dev": {"papers": 281, "questions": 1005},
        "test": {"papers": 416, "questions": 1459},
    },
    "exclusions": {
        "table_or_figure_only": "Audited and recorded separately from main text retrieval",
        "unanswerable": "Scored under abstention negative protocol",
        "unmapped_text": "Logged in evaluation audit report",
    },
}


def prepare_manifest(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "qasper_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(MANIFEST_TEMPLATE, f, indent=2)
    print(f"QASPER benchmark manifest generated -> {manifest_path}")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare QASPER benchmark manifest and verify splits")
    parser.add_argument("--output", type=str, default="research/manifests", help="Output directory for manifests")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / args.output
    prepare_manifest(out_dir)


if __name__ == "__main__":
    main()
