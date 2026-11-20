"""Define shared paper, passage, and retrieval data schemas.

Define Paper, Section, Passage, and EvidenceResult for the backend and
QASPER. A Passage carries its own ID, parent_passage_id when split, and
a source location for HTML or QASPER.

Define HTTP schemas for session, ingest, and retrieve. The agent's
action, observation, and answer types live in agent/schemas.py.
"""

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class SourceLocation(BaseModel):
    element_id: Optional[str] = None
    selector: Optional[str] = None
    xpath: Optional[str] = None
    # For QASPER coordinate compatibility
    dataset_name: Optional[str] = None
    paragraph_index: Optional[int] = None


class SectionInput(BaseModel):
    id: str
    heading: str
    path: str
    order: int
    section_type: Optional[str] = None


class ParagraphInput(BaseModel):
    id: str
    section_id: str
    section_path: str
    paragraph_order: int = Field(default=0, alias="order")
    text: str
    locator: Optional[SourceLocation] = Field(default=None, alias="source_locator")
    fingerprint: Optional[str] = None
    has_math: Optional[bool] = False
    has_table: Optional[bool] = False

    model_config = ConfigDict(populate_by_name=True)


class PaperIngestRequest(BaseModel):
    title: str
    arxiv_id: str
    version: str = "unknown"
    canonical_url: str
    parser_version: str = "1.0.0"
    sections: List[SectionInput] = Field(default_factory=list)
    paragraphs: List[ParagraphInput] = Field(default_factory=list)


class PaperIngestResponse(BaseModel):
    paper_id: str
    index_status: str
    lexical_ready: bool
    semantic_ready: bool
    content_hash: str


class PaperStatusResponse(BaseModel):
    paper_id: str
    title: str
    arxiv_id: str
    version: str
    lexical_ready: bool
    semantic_ready: bool
    indexing_error: Optional[str] = None


class PassageChunk(BaseModel):
    passage_id: str
    parent_passage_id: str
    paper_id: Optional[str] = None
    section_id: str
    section_path: str
    paragraph_order: int
    text: str
    locator: SourceLocation
    offset_start: int
    offset_end: int
    fingerprint: Optional[str] = None


class EvidenceItem(BaseModel):
    passage_id: str  # Unique parent passage ID
    parent_passage_id: str
    rank: int
    score: float
    section_heading: str
    section_path: str
    text: str
    locator: SourceLocation
    contributing_chunks: List[str] = Field(default_factory=list)
    fingerprint: Optional[str] = None
    section_id: Optional[str] = None
    paper_id: Optional[str] = None


class RetrieveRequest(BaseModel):
    request_id: str
    paper_id: str
    question: str
    top_k: int = Field(default=5, ge=1, le=20, strict=True)
    mode: Literal["B1", "B2", "B3", "B4"] = "B1"


class EvidenceResult(BaseModel):
    request_id: str
    paper_id: str
    status: str
    retrieval_mode: str
    fallback_reason: Optional[str] = None
    evidence: List[EvidenceItem] = Field(default_factory=list)
    candidate_passage_ids: List[str] = Field(default_factory=list)
