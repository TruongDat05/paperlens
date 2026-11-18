"""Load artifacts to replay the pipeline offline.

Verify the manifest and checksums, load the pinned local E5 tokenizer,
and supply adapters that read recorded embeddings, scores, and LLM
responses.

Match records by run inputs, configuration, and snapshot. Report missing
records or version mismatches and label the results as replay.
"""
