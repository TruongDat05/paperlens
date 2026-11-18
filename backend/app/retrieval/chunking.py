"""Split long paragraphs while preserving their source lineage.

Accept arXiv or QASPER paragraphs and a pinned E5 tokenizer. Target
about 400 tokens including the prefix, with room for special tokens.

Assign deterministic subchunk IDs and text offsets. Keep
parent_passage_id so results and evaluation labels map to the same
original paragraph. For replay, use tokenizer resources already
available locally.
"""
