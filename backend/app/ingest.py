"""Accept arXiv papers and coordinate indexing.

Accept paragraphs the user has consented to send. Validate the arXiv
source, version, structure, and input limits, then compute the content
hash on the server. Reuse paper_id for the same owner, content, and
index configuration.

Chunk paragraphs with chunking.py and build BM25 to reach lexical_ready.
Track embedding progress by batch and set semantic_ready once all
matching vectors are stored.
"""
