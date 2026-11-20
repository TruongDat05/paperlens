"""Tests for gateway-routed Qwen and exact paper link attachments."""

import pytest
import json
import httpx
from backend.tests.test_confirmed_regressions import paper
from backend.app.agent.schemas import AgentRunRequest, AnswerBlock
from backend.app.agent.model_router import ModelRouter
from backend.app.providers.llm_gateway import LLMGateway
from backend.app.agent.runs import create_or_get_run, _active_run_tasks, get_run
from backend.app.retrieval.hybrid import is_research_extension_query
from backend.app.retrieval.scholarly import ScholarlyPaper


def test_high_level_routes_to_qwen():
    """Verify that level='high' selects the working gateway alias."""
    router = ModelRouter(level="high")
    assert router.get_active_model() == "fpt/Qwen3.8-27B"


def test_is_research_extension_recognizes_other_paper_queries():
    """Verify that asking about other papers or links triggers literature scope."""
    assert is_research_extension_query("Tìm bài báo khác về Sparse Attention")
    assert is_research_extension_query("Có paper nào khác so sánh với Transformer không?")
    assert is_research_extension_query("Cho tôi link tới paper Reformer")
    assert is_research_extension_query("Compare with other papers on arXiv")


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["fpt/Qwen3.8-27B", "fpt/qwen/qwen3.8-27b-fp8"])
async def test_llm_gateway_routes_qwen_through_configured_gateway(monkeypatch, model):
    """Keep the gateway URL, credentials and full model alias for Qwen."""
    monkeypatch.setenv("API_URL", "https://legacy.test/chat/completions")
    monkeypatch.setenv("API_KEY", "legacy-key")
    captured = {}
    actual_client = httpx.AsyncClient

    def respond(request):
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps({
                                "answer_blocks": [
                                    {
                                        "text": "FlashAttention improves IO efficiency [ext_arxiv_2205_14135].",
                                        "evidence_ids": ["ext_arxiv_2205_14135"],
                                    }
                                ]
                            }),
                            "role": "assistant",
                        },
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 30},
            },
        )

    monkeypatch.setattr(
        "backend.app.providers.llm_gateway.httpx.AsyncClient",
        lambda **kw: actual_client(transport=httpx.MockTransport(respond), **kw),
    )

    gateway = LLMGateway(api_url="http://default-gateway/v1", api_key="gw-key")
    res = await gateway.generate_step(
        model=model,
        messages=[{"role": "user", "content": "Explain FlashAttention"}],
        mock=False,
    )

    assert captured["url"] == "http://default-gateway/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer gw-key"
    assert captured["body"]["model"] == model
    assert len(res["answer_blocks"]) == 1
    assert res["answer_blocks"][0].evidence_ids == ["ext_arxiv_2205_14135"]


@pytest.mark.asyncio
async def test_agent_attaches_exact_paper_links_when_asking_about_another_paper(paper, monkeypatch):
    """Verify that when a user asks about another paper, the exact link is attached."""
    req = AgentRunRequest(
        request_id="req-paper-link-1",
        paper_id=paper,
        question="Có bài báo nào khác giải quyết vấn đề quadratic memory không? Cho tôi link tới paper đó.",
        level="high",
    )

    res, _, _ = await create_or_get_run(req, "owner")
    await _active_run_tasks[("owner", res.run_id)]
    final_run = get_run(res.run_id, "owner")

    assert final_run.status.value in ("completed", "partial")
    assert final_run.serving_model == "fpt/Qwen3.8-27B"
    assert len(final_run.answer_blocks) > 0

    all_text = " ".join(b.text for b in final_run.answer_blocks)
    # Must contain exact link to external paper (e.g. arXiv URL)
    assert "https://arxiv.org/abs/" in all_text or "semanticscholar.org" in all_text
    # Evidence must include external paper
    assert any(e.passage_id.startswith("ext_") for e in final_run.evidence)
