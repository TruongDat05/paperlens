"""Load QASPER v0.3 and map evidence to original paragraphs.

Verify the dataset revision, checksum, and official splits from the
manifest. Convert each paper to the shared Paper and Passage types.

Keep EvidenceLabel and each valid reference set for the evaluator.
Record ambiguous repeated evidence, unmapped evidence, and table- or
figure-only evidence. Define the text-evidence and abstention subsets
according to the v4.1 plan.
"""

from typing import Any, Dict, List, Optional
import re
from pydantic import BaseModel, Field

OFFICIAL_QASPER_VERSION = "0.3.0"
OFFICIAL_QASPER_REVISION = "006d967a57a550974051a8f9a3ba0814bb653456"


class QasperAnnotation(BaseModel):
    answer: str
    evidence: List[str] = Field(default_factory=list)
    unanswerable: bool = False
    extractive_spans: List[str] = Field(default_factory=list)
    yes_no: Optional[bool] = None


class QasperSample(BaseModel):
    question_id: str
    paper_id: str
    question: str
    annotations: List[QasperAnnotation] = Field(default_factory=list)
    reference_sets: List[List[str]] = Field(default_factory=list)
    unmapped_evidence: List[str] = Field(default_factory=list)


def normalize_evidence_text(text: str) -> str:
    """Normalize text for consistent substring matching across PDF/HTML variants."""
    return re.sub(r"\s+", " ", text.strip().lower())


def map_evidence_to_paragraphs(
    sample: QasperSample,
    paragraphs: List[Dict[str, Any]],
) -> QasperSample:
    """Map gold evidence strings from annotations to unique parent paragraph IDs."""
    norm_paras = [
        (
            p.id if hasattr(p, "id") else p["id"],
            normalize_evidence_text(p.text if hasattr(p, "text") else p["text"]),
        )
        for p in paragraphs
    ]

    all_reference_sets: List[List[str]] = []
    unmapped: List[str] = []

    for ann in sample.annotations:
        if ann.unanswerable:
            continue

        ann_parent_ids: List[str] = []
        for ev_str in ann.evidence:
            norm_ev = normalize_evidence_text(ev_str)
            if not norm_ev:
                continue

            # Look for exact or substring match in paragraphs
            matched_id = None
            for p_id, p_text in norm_paras:
                if norm_ev in p_text or p_text in norm_ev:
                    matched_id = p_id
                    break

            if matched_id:
                if matched_id not in ann_parent_ids:
                    ann_parent_ids.append(matched_id)
            else:
                unmapped.append(ev_str)

        if ann_parent_ids:
            all_reference_sets.append(ann_parent_ids)

    sample.reference_sets = all_reference_sets
    sample.unmapped_evidence = unmapped
    return sample


def classify_query_eligibility(sample: QasperSample) -> Dict[str, bool]:
    """Classify query into main text retrieval, abstention positive, and abstention negative populations."""
    has_annotations = len(sample.annotations) > 0
    all_unanswerable = has_annotations and all(a.unanswerable for a in sample.annotations)
    all_answerable = has_annotations and all(not a.unanswerable for a in sample.annotations)
    has_valid_text_ref = len(sample.reference_sets) > 0

    is_text_retrieval_eligible = any(
        (not a.unanswerable) for a in sample.annotations
    ) and has_valid_text_ref

    is_abstention_positive = all_answerable and has_valid_text_ref
    is_abstention_negative = all_unanswerable

    return {
        "is_text_retrieval_eligible": is_text_retrieval_eligible,
        "is_abstention_positive": is_abstention_positive,
        "is_abstention_negative": is_abstention_negative,
    }
