"""Coordinate the A2 loop for one question about a paper.

Accept a question, valid history, and a loaded paper. Ask the model
router for an action or answer, validate each action before dispatch,
and add verified observations to the evidence registry.

Enforce the configured step, tool call, search, token, and time limits
across the turn. Block duplicate actions, reserve the last step for the
answer, and check for cancellation between steps.

Return a validated answer, partial, or evidence_only based on the
available evidence and stop reason.
"""
