"""Specify tests for the agent run lifecycle and result integrity.

Cover ownership, duplicate request_id, cancellation, deadlines, and late
responses. Simulate Gemini failure, one failover, continued use of
Claude until the turn ends, and failure of both models.

Check unknown usage, out-of-scope actions, and citation IDs missing from
the evidence registry.
"""
