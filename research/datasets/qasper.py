"""Load QASPER v0.3 and map evidence to original paragraphs.

Verify the dataset revision, checksum, and official splits from the
manifest. Convert each paper to the shared Paper and Passage types.

Keep EvidenceLabel and each valid reference set for the evaluator.
Record ambiguous repeated evidence, unmapped evidence, and table- or
figure-only evidence. Define the text-evidence and abstention subsets
according to the v4.1 plan.
"""
