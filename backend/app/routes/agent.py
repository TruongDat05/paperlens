"""Expose HTTP endpoints to start, inspect, and cancel agent runs.

Register POST /api/v1/agent/runs, GET /api/v1/agent/runs/{run_id}, and
POST /api/v1/agent/runs/{run_id}/cancel. Authenticate the owner and
validate the paper, question, history, and request_id before passing
them to runs.py.

Return HTTP 202 and run_id on start. Polling returns progress or a
result with validated citations, the serving model, and fallback details
when applicable.
"""
