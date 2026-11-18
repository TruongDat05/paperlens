"""Maintain an evidence registry and validate citation IDs.

Register passages provided to the model in the current run. Validate
each evidence_id against the registry, owner, and paper version before
publishing its answer block.

Use quotes and locators from registered source passages. Evaluate how
well passages support claims in research/evaluation/qa_audit.py.
"""
