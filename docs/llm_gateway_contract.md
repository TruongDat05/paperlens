# Agent Gateway API Contract

Status: **Qwen JSON and streaming responses are live-verified through 9Router (2026-11-20).** See provider verification (local only) for the current check and review_verification.md (local only) for earlier Gemini/Claude checks.
Implementation: `backend/app/providers/llm_gateway.py` and `backend/app/agent/model_router.py`.
Verification entry point: `scripts/smoke_test_llm_gateway.py`.
Current Qwen live check: `python -m scripts.check_local_models --live`.

All chat models use `LLM_API_URL` and `LLM_API_KEY`, including Qwen.
The gateway receives the configured alias unchanged; Qwen no longer bypasses it to call FPT directly.
E5 embeddings and BGE reranking separately use direct FPT `API_URL` and `API_KEY`.

## Model Aliases

| Role | Configured Alias | Protocol / Schema | Timeout |
| --- | --- | --- | --- |
| Low | `ag/gemini-3.8-flash-low` | OpenAI-compatible function/tool calling; structured JSON answer blocks | 60 seconds |
| Medium | `ag/gemini-3.8-flash-medium` | OpenAI-compatible function/tool calling; structured JSON answer blocks | 60 seconds |
| High | `fpt/Qwen3.8-27B` | Structured JSON answer blocks; JSON and streaming live-verified | 90 seconds |
| Fallback | `ag/claude-sonnet-4-6` | OpenAI-compatible function/tool calling; portable transcript handoff | 90 seconds |

`fpt/qwen/qwen3.8-27b-fp8` was listed by the gateway but returned an upstream model-not-available 404, wrapped as gateway HTTP 503. The user selected the working `fpt/Qwen3.8-27B` alias for High.

## Tool Calling Wire Format

### Request
```json
{
  "model": "ag/gemini-3.8-flash-medium",
  "messages": [
    {"role": "system", "content": "You are PaperLens..."},
    {"role": "user", "content": "How does Transformer work with self-attention?"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_evidence",
        "description": "Search paper evidence passages",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer"}
          },
          "required": ["query"]
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

### Tool Invocation Response (Step 1)
```json
{
  "id": "chatcmpl-step1",
  "model": "ag/gemini-3.8-flash-medium",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_search_1",
            "type": "function",
            "function": {
              "name": "search_evidence",
              "arguments": "{\"query\": \"self-attention\", \"top_k\": 3}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ],
  "usage": {"prompt_tokens": 120, "completion_tokens": 35, "total_tokens": 155}
}
```

### Observation Handoff (Step 2)
The backend executes the tool locally, formats the observation into a tool message with matching `tool_call_id`, and passes it to the next step (or to Claude on failover):
```json
{
  "role": "tool",
  "tool_call_id": "call_search_1",
  "content": "[{\"passage_id\": \"S1.p1\", \"text\": \"The Transformer is the first transduction model...\"}]"
}
```

### Final Cited Answer Format
```json
{
  "answer_blocks": [
    {
      "text": "The Transformer relies entirely on self-attention without recurrent layers.",
      "evidence_ids": ["S1.p1"]
    }
  ],
  "limitations": null
}
```
All emitted `evidence_ids` are strictly validated against the run's evidence registry before publishing.

## Observed live wire behavior

Six bounded text-generation probes returned text successfully, three per preserved alias. For this gateway, omitting `stream` returns SSE, `stream: true` returns SSE, and `stream: false` returns JSON. The adapter now explicitly sends `stream: false` before parsing JSON. Text generation and this wire behavior are live-verified; native tool round trips and complete QA after the fix remain unverified. See the verification record (local only).

Version 0.1.1 additionally verifies native side-panel synthesis through Gemini. It sends `tool_choice: none`, JSON response format and low reasoning effort for final answers, and accepts Markdown-fenced JSON. Native tool planning was observed in the baseline; native side-panel synthesis and follow-up outcomes are recorded in browser validation (local only).
