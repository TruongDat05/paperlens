# Agent Gateway API Contract

Status **pending verification**. `backend/app/providers/llm_gateway.py` normalizes gateway communication. `backend/app/agent/model_router.py` applies the model-switching policy. Verify the contract through `scripts/smoke_test_llm_gateway.py`.

| Role | Configured alias | Evidence to record |
| --- | --- | --- |
| Primary | `ag/gemini-3.8-flash-medium` | Generation, finish reason, structured output, tool round trip, and usage |
| Fallback | `ag/claude-sonnet-4-6` | The same checks, plus handoff from Gemini with normalized observations |

Record the base URL, authentication, protocol per alias, timeout and error categories, token and usage fields, quotas, billing, and reachability from the hosted backend. Verify a tool action → observation → final answer round trip and tool call ID mapping for each alias. Choose native tool calls or structured-action JSON based on the alias's tested capabilities. Preserve portable history and the turn's evidence IDs at handoff. Record potentially unknown charges after a timeout and redact credentials from examples. [v4.1 plan, section 6](../PaperLens_Research_Project_Plan.md#62-verify-fpt-retrieval-and-the-llm-gateway)
