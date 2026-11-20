"""Load and validate PaperLens application configuration.

Read settings from environment variables and configuration files,
including FPT retrieval and LLM gateway credentials, database paths,
retrieval parameters, and operational caps.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

CHAT_TOKEN_LIMIT = 500_000

# Load root .env
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(REPO_ROOT / ".env")


class AppConfig(BaseModel):
    version: str = "0.1.0"
    environment: str = "development"


class RetrievalConfig(BaseModel):
    default_mode: str = "B4"
    product_top_k: int = 5
    sparse_candidates: int = 40
    dense_candidates: int = 40
    rrf_k: int = 60
    rerank_candidates: int = 20
    embedding_model: str = "intfloat/multilingual-e5-large"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    max_passage_tokens: int = 400


class ModelsConfig(BaseModel):
    primary: str = "ag/gemini-3.8-flash-low"
    medium: str = "ag/gemini-3.8-flash-medium"
    fallback: str = "ag/claude-sonnet-4-6"
    high: str = Field(default_factory=lambda: os.getenv("HIGH_MODEL", "fpt/Qwen3.8-27B"))


class LimitsConfig(BaseModel):
    max_body_bytes: int = 1048576  # 1 MiB
    max_chunks: int = 400
    max_tokens_per_paper: int = 80000
    max_question_chars: int = 1024
    max_history_turns: int = 6
    turn_timeout_seconds: float = 120.0
    gemini_timeout_seconds: float = 60.0
    claude_timeout_seconds: float = 30.0
    qwen_timeout_seconds: float = 90.0
    max_llm_steps: int = 3
    max_provider_attempts: int = 4
    max_tool_calls: int = 4
    max_searches: int = 2
    max_parent_evidence: int = 8
    max_input_tokens: int = 64000
    max_output_tokens: int = 32768
    max_final_answer_tokens: int = 16384


class QuotasConfig(BaseModel):
    # -1 disables a local daily cap; zero deliberately blocks new work.
    daily_new_indexes: int = Field(default=5, ge=-1)
    daily_agent_turns: int = Field(default=5, ge=-1)
    daily_semantic_retrievals: int = Field(default=20, ge=-1)


class RetentionConfig(BaseModel):
    paper_inactivity_days: int = 7
    run_retention_hours: int = 24
    operational_metadata_days: int = 7


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    quotas: QuotasConfig = Field(default_factory=QuotasConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)

    # Provider connections
    api_url: str = Field(default_factory=lambda: os.getenv("API_URL", "https://mkp-api.fptcloud.com"))
    api_key: str = Field(default_factory=lambda: os.getenv("API_KEY", ""))
    llm_api_url: str = Field(default_factory=lambda: os.getenv("LLM_API_URL", "http://127.0.0.1:20128/v1"))
    llm_api_key: str = Field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    mock_providers: bool = Field(default_factory=lambda: os.getenv("MOCK_PROVIDERS", "false").lower() in ("true", "1", "yes"))

    # Database
    db_path: str = Field(default_factory=lambda: os.getenv("DB_PATH", str(REPO_ROOT / "paperlens.db")))
    auth_public_base_url: str = Field(default_factory=lambda: os.getenv("AUTH_PUBLIC_BASE_URL", "http://localhost:8000"))
    google_client_id: str = Field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_ID", ""))
    google_client_secret: str = Field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_SECRET", ""))
    github_client_id: str = Field(default_factory=lambda: os.getenv("GITHUB_CLIENT_ID", ""))
    github_client_secret: str = Field(default_factory=lambda: os.getenv("GITHUB_CLIENT_SECRET", ""))


def load_yaml_config(path: Path) -> Dict[str, Any]:
    if path.is_file():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


@lru_cache()
def get_settings() -> Settings:
    yaml_data = load_yaml_config(REPO_ROOT / "configs" / "product_mvp.yaml")
    quotas = yaml_data.setdefault("quotas", {})
    for key in QuotasConfig.model_fields:
        if key.upper() in os.environ:
            quotas[key] = os.environ[key.upper()]
    return Settings(**yaml_data)
