"""Record operational metrics by stage and provider attempt.

Record stage latency, cache hits, models, errors, tokens, and costs.
Distinguish provider-reported usage, estimates, and unknown usage from
attempts that timed out or were canceled.

Record the serving model and fallback reason per run. Limit product logs
to metadata needed for operations.
"""
