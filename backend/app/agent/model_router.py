"""Choose a model for each LLM step and manage failover.

Prefer ag/gemini-3.8-flash-medium. In primary_then_fallback mode, switch
at most once to ag/claude-sonnet-4-6 for an eligible failure when the
fallback contract has been verified and budget remains.

Keep Claude for the rest of the turn with the same deadline and verified
observations. Cap each attempt's timeout by the remaining time. The
primary_only benchmark uses Gemini. Disable SDK retries and record the
model, usage, and errors per attempt.

Use normalized errors and pipeline output validation to determine
failover eligibility. Stop for cancellation, shared authentication
errors, or exhausted budget.
"""

from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field
from backend.app.core.config import CHAT_TOKEN_LIMIT
from backend.app.core.config import get_settings


class RoutingMode(str, Enum):
    PRIMARY_ONLY = "primary_only"
    PRIMARY_THEN_FALLBACK = "primary_then_fallback"


class AttemptRecord(BaseModel):
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    success: bool = True
    error_type: Optional[str] = None


def normalize_provider_error(err: Any) -> str:
    """Normalize raw exceptions or provider error strings into recognized category keys."""
    import asyncio
    import httpx
    if isinstance(err, (asyncio.TimeoutError, httpx.TimeoutException)):
        return "provider_timeout"
    err_str = str(err).lower()
    if any(x in err_str for x in ("401", "403", "not configured", "authentication", "api key")):
        return "authentication_error"
    if any(x in err_str for x in ("budget", "quota", "payment", "402", "cancel")):
        return "budget_or_cancelled"
    if "404" in err_str:
        return "endpoint_not_found"
    if "429" in err_str or "rate limit" in err_str:
        return "rate_limit_429"
    if "500" in err_str:
        return "provider_500"
    if "502" in err_str:
        return "provider_502"
    if "503" in err_str:
        return "provider_503"
    if "504" in err_str:
        return "provider_504"
    if "timeout" in err_str:
        return "provider_timeout"
    if "connect" in err_str or "connection" in err_str or "unavailable" in err_str:
        return "provider_unavailable"
    if "malformed" in err_str or "json" in err_str:
        return "malformed_output"
    return "gateway_error"


class ModelRouter:
    """Manages model selection and failover per turn."""

    def __init__(self, mode: RoutingMode = RoutingMode.PRIMARY_THEN_FALLBACK, level: str = "low", token_budget: int = CHAT_TOKEN_LIMIT):
        settings = get_settings()
        self.mode = mode
        self.primary_model = {
            "low": getattr(settings.models, "low", settings.models.primary),
            "medium": getattr(settings.models, "medium", "ag/gemini-3.8-flash-medium"),
            "high": getattr(settings.models, "high", "fpt/Qwen3.8-27B"),
        }[level]
        self.token_budget = token_budget
        self.usage_estimated = False
        self.budget_exhausted = False
        self.fallback_model = settings.models.fallback  # ag/claude-sonnet-4-6
        self.active_model = self.primary_model
        self.fallback_count = 0
        self.attempts: List[AttemptRecord] = []

    def get_active_model(self) -> str:
        """Return the current active model alias."""
        return self.active_model

    def handle_attempt_failure(
        self,
        error_type: str,
        remaining_turn_seconds: float,
    ) -> bool:
        """Evaluate whether an attempt failure qualifies for switching to Claude.

        Returns True if failover succeeded and Claude is now active; False otherwise.
        """
        # Record failure
        self.attempts.append(
            AttemptRecord(
                model=self.active_model,
                success=False,
                error_type=error_type,
            )
        )

        # In primary_only mode (e.g. for QASPER scientific evaluation), never failover
        if self.mode == RoutingMode.PRIMARY_ONLY:
            return False

        # Only failover once per turn, when Gemini is the current model
        if self.fallback_count > 0 or self.active_model == self.fallback_model:
            return False

        # Require at least 5 seconds remaining to attempt Claude recovery
        if remaining_turn_seconds < 5.0:
            return False

        # Eligible failure classes: timeout, 5xx, rate limits, provider unavailable, malformed output
        eligible_errors = {
            "provider_timeout",
            "provider_500",
            "provider_502",
            "provider_503",
            "provider_504",
            "provider_unavailable",
            "rate_limit_429",
            "malformed_output",
            "gateway_error",
        }
        if len(self.attempts) < get_settings().limits.max_provider_attempts and error_type in eligible_errors:
            self.active_model = self.fallback_model
            self.fallback_count += 1
            return True

        return False

    def record_success(self, input_tokens: int, output_tokens: int) -> None:
        """Record successful model step usage."""
        self.attempts.append(
            AttemptRecord(
                model=self.active_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True,
            )
        )

    def record_attempt_failure(self, error_type: str) -> None:
        """Record an attempt failure without switching model."""
        self.attempts.append(
            AttemptRecord(
                model=self.active_model,
                success=False,
                error_type=error_type,
            )
        )


async def generate_bounded(router, gateway, messages, tools, deadline, on_chunk=None, output_token_cap=None):
    import asyncio
    import json
    import time
    limits = get_settings().limits
    while True:
        remaining = deadline - time.monotonic()
        # UTF-8 bytes are a conservative token upper bound, including tool schemas.
        estimated = estimate_input_tokens(messages, tools)
        used_input = sum(a.input_tokens for a in router.attempts)
        used_output = sum(a.output_tokens for a in router.attempts)
        if remaining <= 0 or len(router.attempts) >= limits.max_provider_attempts:
            raise RuntimeError("Turn deadline or attempt budget exhausted")
        if used_input + estimated > limits.max_input_tokens or used_output >= limits.max_output_tokens:
            raise RuntimeError("Token budget exhausted")
        chat_remaining = router.token_budget - used_input - used_output - estimated
        if chat_remaining < 128:
            router.budget_exhausted = True
            raise RuntimeError("Chat token budget exhausted. Start a new chat.")
        model = router.get_active_model()
        gateway.max_tokens = min(limits.max_final_answer_tokens, limits.max_output_tokens - used_output, chat_remaining)
        if output_token_cap is not None:
            gateway.max_tokens = min(gateway.max_tokens, output_token_cap)
        if "qwen" in model.lower():
            model_timeout = getattr(limits, "qwen_timeout_seconds", 60.0)
        elif "claude" in model.lower():
            model_timeout = limits.claude_timeout_seconds
        else:
            model_timeout = limits.gemini_timeout_seconds
        timeout = min(remaining, model_timeout)
        try:
            if on_chunk is not None:
                try:
                    result = await asyncio.wait_for(gateway.generate_step(model=model, messages=messages, tools=tools, on_chunk=on_chunk), timeout)
                except TypeError:
                    result = await asyncio.wait_for(gateway.generate_step(model=model, messages=messages, tools=tools), timeout)
            else:
                result = await asyncio.wait_for(gateway.generate_step(model=model, messages=messages, tools=tools), timeout)
        except asyncio.CancelledError:
            router.record_attempt_failure("cancelled")
            router.attempts[-1].input_tokens = estimated
            router.attempts[-1].output_tokens = gateway.max_tokens
            router.usage_estimated = True
            raise
        except Exception as err:
            router.usage_estimated = True
            switched = router.handle_attempt_failure(normalize_provider_error(err), deadline - time.monotonic())
            # Unknown usage after a failed attempt is reserved conservatively.
            router.attempts[-1].input_tokens = estimated
            router.attempts[-1].output_tokens = gateway.max_tokens
            if switched:
                continue
            raise
        usage = result.get("usage", {})
        if not usage.get("input_tokens"):
            usage["input_tokens"] = estimated
            router.usage_estimated = True
        router.record_success(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        if sum(a.input_tokens + a.output_tokens for a in router.attempts) >= router.token_budget:
            router.budget_exhausted = True
        if used_input + usage.get("input_tokens", 0) > limits.max_input_tokens or used_output + usage.get("output_tokens", 0) > limits.max_output_tokens:
            raise RuntimeError("Provider exceeded token budget")
        return result


def estimate_input_tokens(messages, tools=None):
    """Conservative UTF-8 bound for text; reserve vision tokens, not base64 bytes."""
    import json
    normalized = []
    image_count = 0
    for message in messages:
        message = dict(message)
        if isinstance(message.get("content"), list):
            image_count += sum(part.get("type") == "image_url" for part in message["content"])
            message["content"] = [part for part in message["content"] if part.get("type") != "image_url"]
        normalized.append(message)
    return len(json.dumps([normalized, tools], ensure_ascii=False).encode()) + image_count * 8192
