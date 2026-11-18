"""Verify the gateway contract for both LLM aliases directly.

Use gateway configuration to check generation, tool round trips, finish
reasons, and usage separately for Gemini and Claude. Test handoff with
normalized history and observations.

Record redacted evidence in docs/llm_gateway_contract.md. Retest through
llm_gateway.py once the adapter is available.
"""
