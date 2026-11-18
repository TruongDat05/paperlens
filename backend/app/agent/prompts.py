"""Maintain versioned prompts for A1 and A2.

Describe available tools, the answer format, and citation rules for
evidence_ids. Assign the appropriate roles to the question, history, and
observations, and treat paper content as source data.

Ask the model to identify missing evidence or return a partial answer in
the agreed schema. Record prompt versions for comparison across runs.
"""
