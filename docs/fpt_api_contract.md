# Direct FPT Retrieval API Contract

Status (2026-11-20): **E5 embeddings and BGE reranking are live-verified directly through FPT Cloud.** See provider verification (local only).
Implementation: `backend/app/providers/fpt.py`.
Live verification: `python -m scripts.check_local_models --live`.
`scripts/smoke_test_fpt.py` retains the historical offline fixtures.

Both operations use `API_URL` (default `https://mkp-api.fptcloud.com`) and `API_KEY`.
Embedding posts to `/embeddings`; reranking posts to `/v1/rerank`.
Qwen separately uses `LLM_API_URL` and `LLM_API_KEY` through 9Router.
The FPT adapter sends the short wire model names shown below.

## Models and Endpoints

| Role | Configured Model | Wire Model | Wire Output Specification |
| --- | --- | --- | --- |
| Embedding | `intfloat/multilingual-e5-large` | `multilingual-e5-large` | Vector dimension: 1,024; float values; token usage in `usage` |
| Reranking | `BAAI/bge-reranker-v2-m3` | `bge-reranker-v2-m3` | Relevance scores per input pair; higher score indicates higher relevance |

## E5 Embedding Wire Contract

### Request Format
- **Headers:** `Authorization: Bearer <API_KEY>`, `Content-Type: application/json`
- **Prefix Convention:**
  - Queries: prefix with `query: ` (e.g. `query: How does self-attention work?`)
  - Passages: prefix with `passage: ` (e.g. `passage: The Transformer model architecture...`)
- **Body:**
```json
{
  "model": "multilingual-e5-large",
  "input": ["passage: First chunk text...", "passage: Second chunk text..."]
}
```

### Response Format
```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.03125, ...]
    }
  ],
  "model": "multilingual-e5-large",
  "usage": {
    "prompt_tokens": 42,
    "total_tokens": 42
  }
}
```

## BGE Reranker Wire Contract

### Request Format
- **Body:**
```json
{
  "model": "bge-reranker-v2-m3",
  "query": "How does self-attention work?",
  "documents": ["Passage 1 text...", "Passage 2 text..."]
}
```

### Response Format
```json
{
  "object": "rerank",
  "results": [
    {"index": 0, "relevance_score": 0.8845},
    {"index": 1, "relevance_score": 0.1203}
  ],
  "model": "bge-reranker-v2-m3",
  "usage": {
    "prompt_tokens": 85,
    "total_tokens": 85
  }
}
```

## Operational Limits and Error Handling
- **Embedding truncation limit:** Upstream 512 tokens. PaperLens chunks passages targeting ~400 tokens to leave safety margin.
- **Reranker truncation limit:** Upstream 512 tokens for query + passage pair.
- **HTTP 402 / 429:** Terminal for that attempt path. Backend falls back to Lucene BM25 lexical ranking when semantic path is unavailable.

## Endpoint configuration

Optional `FPT_EMBEDDING_URL` and `FPT_RERANK_URL` override the FPT-derived endpoint URLs. The adapter also accepts an `API_URL` ending in `/chat/completions`, `/embeddings` or `/v1/rerank` and derives the correct retrieval paths. Direct FPT rejected `baai/bge-reranker-v2-m3` with HTTP 404; use the short wire name. The gateway-only routing attempt is retained as historical evidence (local only).

Sources: [FPT embedding example](https://github.com/fpt-corp/ai-marketplace/blob/main/API%20Integration%20-%20Embedding%20Model.md), [FPT rerank example](https://github.com/fpt-corp/ai-marketplace/blob/main/API%20Integration%20-%20Rerank%20model.md). A bounded live check returned one 1024-dimensional vector and two rerank scores.
