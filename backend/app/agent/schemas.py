"""Define data contracts for agent execution and HTTP endpoints.

Define actions, observations, answer blocks with text and evidence_ids,
run states, and HTTP responses. Use shared message and observation
formats across both model aliases.

Record per-attempt metadata, finish reasons, errors, and stop reasons so
the controller, router, and evaluator interpret outcomes consistently.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator
from typing import Literal
from backend.app.core.config import CHAT_TOKEN_LIMIT
from backend.app.core.schemas import EvidenceItem


class ImageInput(BaseModel):
    name: str = Field(default="Research image", max_length=200)
    data_url: str = Field(max_length=700000)

    @model_validator(mode="after")
    def validate_image(self):
        import base64
        import re
        match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", self.data_url)
        if not match:
            raise ValueError("Only inline PNG, JPEG and WebP images are supported")
        try:
            data = base64.b64decode(match[2], validate=True)
        except ValueError as err:
            raise ValueError("Invalid image encoding") from err
        signatures = {"png": data.startswith(b"\x89PNG\r\n\x1a\n"), "jpeg": data.startswith(b"\xff\xd8\xff"),
                      "webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP"}
        if not data or len(data) > 512 * 1024 or not signatures[match[1]]:
            raise ValueError("Invalid image or image exceeds 512 KiB")
        return self


def multimodal_content(text, images):
    if not images:
        return text
    return [{"type": "text", "text": text}] + [
        {"type": "image_url", "image_url": {"url": image.data_url}} for image in images
    ]


class RunState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    EVIDENCE_ONLY = "evidence_only"
    CANCELLED = "cancelled"
    FAILED = "failed"
    REFUSED = "refused"


class AnswerBlock(BaseModel):
    text: str
    evidence_ids: List[str] = Field(default_factory=list)


class MemoryCandidate(BaseModel):
    kind: Literal['user_context', 'paper_knowledge']
    quote: str = Field(min_length=12, max_length=600)
    evidence_id: str = Field(default='', max_length=160)


class StepProgress(BaseModel):
    step_index: int
    action_name: str
    message: str


class AgentRunRequest(BaseModel):
    request_id: str
    paper_id: str
    question: str
    history: List[Dict[str, Any]] = Field(default_factory=list)
    mode: Literal["A1", "A2"] = "A2"
    level: Literal["low", "medium", "high"] = "low"
    chat_id: Optional[str] = Field(default=None, max_length=100)
    images: List[ImageInput] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_request(self):
        from backend.app.core.config import get_settings
        limits = get_settings().limits
        if not self.request_id.strip() or not self.paper_id.strip():
            raise ValueError("request_id and paper_id are required")
        if not self.question.strip() or len(self.question) > limits.max_question_chars:
            raise ValueError("Invalid question length")
        if len(self.history) > limits.max_history_turns * 2:
            raise ValueError("Too much history")
        for turn in self.history:
            if set(turn) != {"role", "content"} or turn["role"] not in ("user", "assistant"):
                raise ValueError("Invalid history role or fields")
            if not isinstance(turn["content"], str) or not turn["content"].strip() or len(turn["content"]) > limits.max_question_chars * 4:
                raise ValueError("Invalid history content")
        return self


class AgentRunResponse(BaseModel):
    run_id: str
    paper_id: str
    status: RunState
    answer_blocks: Optional[List[AnswerBlock]] = None
    evidence: Optional[List[EvidenceItem]] = None
    serving_model: Optional[str] = None
    fallback_reason: Optional[str] = None
    limitations: Optional[str] = None
    retrieval_mode: Optional[str] = None
    retrieval_fallback_reason: Optional[str] = None
    step_progress: Optional[List[StepProgress]] = None
    error_message: Optional[str] = None
    follow_ups: List[str] = Field(default_factory=list)
    chat_id: Optional[str] = None
    tokens_used: int = 0
    token_limit: int = CHAT_TOKEN_LIMIT
    usage_estimated: bool = False
    chat_exhausted: bool = False


class ActionCall(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    tool_call_id: Optional[str] = None


class Observation(BaseModel):
    tool_name: str
    content: str
    tool_call_id: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    raw_evidence: List[EvidenceItem] = Field(default_factory=list)


class AgentResult(BaseModel):
    run_id: str
    paper_id: str
    status: RunState
    answer_blocks: List[AnswerBlock] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    emitted_citation_ids: List[str] = Field(default_factory=list)
    serving_model: str
    retrieval_mode: Optional[str] = None
    retrieval_fallback_reason: Optional[str] = None
    fallback_reason: Optional[str] = None
    limitations: Optional[str] = None
    follow_ups: List[str] = Field(default_factory=list)
    memory_candidates: List[MemoryCandidate] = Field(default_factory=list)
