"""Manage agent run lifecycle and results through FastAPI.

Store runs by owner, paper version, and request_id. A retry with the
same payload returns the existing run. Reusing request_id with a
different payload returns a conflict.

Load the paper and index before running A1 or A2. Record progress for
polling and pass cancellation and the deadline into the pipeline.
Publish results only when the current run state allows it.

On restart, end interrupted runs and retain unreconciled usage. Apply
the product retention limit of at most 24 hours for run data.
"""
