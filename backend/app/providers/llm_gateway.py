"""Normalize gateway communication for ag/* model aliases.

Accept messages, actions, and observations in the internal schema.
Convert them to native tool calls or structured-action JSON verified for
each alias.

Normalize tool call IDs, output, finish reasons, usage, and errors
according to docs/llm_gateway_contract.md. Each adapter call is one
provider attempt. model_router.py decides when to switch models.
"""
