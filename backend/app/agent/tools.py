"""Run read-only tools against the paper in the current run.

Expose get_paper_outline, search_evidence, and read_section. Use the
paper version assigned to the run by the backend and validate tool
names, arguments, section IDs, offsets, and passage limits.

Search uses the shared retrieval engine. Return observations in the
agreed schema, with passage IDs and source information for the passages
the agent read.
"""
