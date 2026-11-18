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
