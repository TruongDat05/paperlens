"""Define data contracts for agent execution and HTTP endpoints.

Define actions, observations, answer blocks with text and evidence_ids,
run states, and HTTP responses. Use shared message and observation
formats across both model aliases.

Record per-attempt metadata, finish reasons, errors, and stop reasons so
the controller, router, and evaluator interpret outcomes consistently.
"""
