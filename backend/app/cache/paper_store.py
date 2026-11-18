"""Store papers, passages, indexes, and ingest progress by owner.

Provide consistent paper-version data for retrieval and agent runs. Key
vector caches by owner, content hash, parser and chunking versions, and
embedding configuration, including model, snapshot, and prefix.

Record access times and remove expired papers and indexes according to
configuration. Coordinate deletion of derived data when the owner
requests it.
"""
