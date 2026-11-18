"""Connect to FPT AI Factory for E5 embeddings and BGE reranking.

Use the endpoints and schemas verified in docs/fpt_api_contract.md.
Accept prefixed text for embedding and question-passage pairs for
reranking.

Return vectors or scores aligned with their inputs, along with usage and
normalized errors. Apply batch limits, timeouts, and retries according
to the provider contract.
"""
