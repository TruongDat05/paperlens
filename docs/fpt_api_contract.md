# FPT Retrieval API Contract

Status **pending verification**. The implementation belongs in `backend/app/providers/fpt.py`. Verify the contract through `scripts/smoke_test_fpt.py`.

| Role | Planned model | Evidence to record |
| --- | --- | --- |
| Embedding | `intfloat/multilingual-e5-large` | Catalog model ID, endpoint, schema, vector dimensions, vectors per batch, and usage reporting |
| Reranking | `BAAI/bge-reranker-v2-m3` | Catalog model ID, endpoint, question-passage pair schema, ordering and scores, batching, and usage |

Record authentication, size limits, truncation, timeouts, retries, and errors for each endpoint. Record the verification date and redact credentials from request and response examples. The embedding smoke test checks the `query: ` and `passage: ` prefixes. The reranking smoke test checks that scores map to the correct passages for one query and two passages. [v4.1 plan, section 6](../PaperLens_Research_Project_Plan.md#62-verify-fpt-retrieval-and-the-llm-gateway)
