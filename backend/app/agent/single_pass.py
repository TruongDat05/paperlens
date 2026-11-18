"""Implement A1, the single-pass retrieval and answer flow.

In the benchmark, retrieve at most 8 original paragraphs from one B4
pass. The product alpha retrieves evidence according to its
configuration. Use the same evidence registry, model router, and answer
schema as A2.

Return a citation-validated result and metadata for the A1/A2
comparison.
"""
