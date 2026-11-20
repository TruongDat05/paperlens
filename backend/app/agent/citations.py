"""Maintain an evidence registry and validate citation IDs.

Register passages provided to the model in the current run. Validate
each evidence_id against the registry, owner, and paper version before
publishing its answer block.

Use quotes and locators from registered source passages. Evaluate how
well passages support claims in research/evaluation/qa_audit.py.
"""

from typing import Dict, List, Optional, Tuple
from backend.app.core.schemas import EvidenceItem, SourceLocation
from backend.app.agent.schemas import AnswerBlock


class EvidenceRegistry:
    """Registry of passages admitted and exposed to the model during an agent run."""

    def __init__(self):
        self._passages: Dict[str, EvidenceItem] = {}

    def register_passage(
        self,
        passage_id: str,
        text: str,
        locator: Optional[SourceLocation] = None,
        section_heading: str = "Section",
        section_path: str = "Section",
        score: float = 1.0,
        rank: Optional[int] = None,
        fingerprint: Optional[str] = None,
        section_id: Optional[str] = None,
        paper_id: Optional[str] = None,
    ) -> EvidenceItem:
        """Register a source passage into the active run registry."""
        loc = locator or SourceLocation(element_id=passage_id)
        current_rank = rank or (len(self._passages) + 1)
        item = EvidenceItem(
            passage_id=passage_id,
            parent_passage_id=passage_id,
            rank=current_rank,
            score=score,
            section_heading=section_heading,
            section_path=section_path,
            text=text,
            locator=loc,
            contributing_chunks=[passage_id],
            fingerprint=fingerprint,
            section_id=section_id,
            paper_id=paper_id,
        )
        self._passages[passage_id] = item
        return item

    def has_passage(self, passage_id: str) -> bool:
        """Check whether passage_id is in the registry."""
        return passage_id in self._passages

    def get_passage(self, passage_id: str) -> Optional[EvidenceItem]:
        """Get registered passage by ID."""
        return self._passages.get(passage_id)

    def get_all(self) -> List[EvidenceItem]:
        """Return all registered passages ordered by rank."""
        return sorted(self._passages.values(), key=lambda x: x.rank)


def validate_answer_citations(
    blocks: List[AnswerBlock],
    registry: EvidenceRegistry,
) -> Tuple[bool, List[AnswerBlock]]:
    """Validate that all evidence_ids cited in blocks exist in the registry.

    Returns:
        (all_valid, sanitized_blocks): all_valid is True only if every emitted ID
        exists in the registry. Sanitized blocks strip any invalid or fabricated IDs.
    """
    all_valid = True
    sanitized: List[AnswerBlock] = []

    for block in blocks:
        valid_ids = []
        for eid in block.evidence_ids:
            if registry.has_passage(eid):
                valid_ids.append(eid)
            else:
                all_valid = False

        sanitized.append(
            AnswerBlock(
                text=block.text,
                evidence_ids=valid_ids,
            )
        )

    return all_valid, sanitized


def answer_status(blocks, registry):
    """Validate citation coverage, allowing synthesis. This is not an entailment score."""
    from backend.app.agent.schemas import RunState
    valid, sanitized = validate_answer_citations(blocks, registry)
    cited = [b for b in sanitized if b.evidence_ids]
    if not cited:
        return RunState.EVIDENCE_ONLY, [], "No usable cited answer could be produced from the available sources."
    # Omit unsupported blocks instead of publishing uncited factual claims.
    if valid and len(cited) == len(sanitized) and all(b.text.strip() for b in cited):
        return RunState.COMPLETED, sanitized, None
    return RunState.PARTIAL, cited, "Some answer sections were omitted because their source citations were missing or invalid."
