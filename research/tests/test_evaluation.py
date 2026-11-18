"""Specify tests for the QASPER protocol and replay.

Use fixtures for multiple reference sets, duplicate parents, missing or
table- or figure-only gold evidence, and abstention. Check the
denominator for each metric.

Verify replay against the correct artifact hashes, report missing
records, and use primary_only for the main A1/A2 comparison.
"""
