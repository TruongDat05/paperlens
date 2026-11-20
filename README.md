# PaperLens: Evidence-Grounded Research Paper Reading Companion

**PaperLens** is an open-source, evidence-grounded research companion designed for ML and NLP researchers. Operating alongside arXiv HTML papers in a Chrome side panel, PaperLens enables interactive question answering with evidence citations and navigation to source passages. Citation-ID validity does not establish semantic support.

---

## 1. The Problem
Modern research paper reading with LLM assistants suffers from critical trust barriers:
- **Ungrounded Hallucinations:** Generic chat interfaces hallucinate evaluation numbers, hyperparameters, and baseline comparisons that do not exist in the paper.
- **Lost Document Context:** Answering across long multi-section papers requires targeted multi-hop navigation (e.g. comparing §3 model architecture against §5 training ablations).
- **Zero In-Document Verification:** Readers cannot easily verify model claims against the original text, leading to tedious manual scanning.

---

## 2. Our Method & Architecture

PaperLens solves these issues with a hybrid retrieval pipeline and a multi-step bounded agent loop:

```mermaid
flowchart TD
    subgraph Browser ["Chrome MV3 Browser (Client)"]
        Tab["arXiv HTML Tab (https://arxiv.org/html/*)"]
        Parser["DOM Parser (parser.ts)"]
        Nav["Verified Jump Engine (navigation.ts)"]
        Panel["Side Panel React App (App.tsx)"]
    end

    subgraph Backend ["FastAPI Local / Hosted Service"]
        API["FastAPI App (main.py)"]
        Store["SQLite Paper Store & Cache (WAL Mode)"]
        BM25["Lucene-floored BM25 Index (bm25.py)"]
        Dense["E5 Dense Retriever (dense.py)"]
        Hybrid["RRF & BGE Reranker (hybrid.py)"]
        Agent["A2 Agent Controller (controller.py)"]
        Reg["Evidence Registry & Citation Gate (citations.py)"]
    end

    subgraph Providers ["Inference Providers"]
        FPT["FPT Cloud (E5 Embeddings / BGE Reranker)"]
        Gateway["9Router (Gemini / Claude / Qwen)"]
    end

    Tab -->|Extract paragraphs & headings| Parser
    Parser -->|POST /api/v1/papers/ingest| API
    API --> Store
    Store --> BM25
    Store --> Dense
    Panel -->|POST /api/v1/agent/runs (A2)| Agent
    Agent -->|Optional outline| Store
    Agent -->|Optional search| Hybrid
    Agent -->|Optional section read| Store
    Hybrid --> FPT
    Agent --> Gateway
    Gateway --> Reg
    Reg -->|Answer with valid citation IDs| Panel
    Panel -->|Click numbered citation| Nav
    Nav -->|Scroll & yellow highlight| Tab
```

### Key Technical Pillars:
1. **Hybrid Retrieval (B1–B4):**
   - *B1:* Lucene-floored BM25 ($\ln(1 + \frac{N - n + 0.5}{n + 0.5})$) preventing zero/negative IDF on small corpora.
   - *B2:* Dense retrieval via `intfloat/multilingual-e5-large` with task prefixes.
   - *B3:* Reciprocal Rank Fusion ($k=60$) combining BM25 and E5 candidates.
   - *B4:* Two-stage reranking via `BAAI/bge-reranker-v2-m3` on top 20 candidate pairs.
2. **Bounded Agent Controller (A2):**
   - 4 read-only tools: `get_paper_outline`, `search_evidence`, `read_section`, `search_external_papers` (arXiv, Semantic Scholar).
   - Product requests first receive a validated research scope plan. Unrelated and mixed requests are refused before retrieval. Research directions combine paper evidence with external abstracts, with proposals labeled as hypotheses.
   - Strict budget bounds: 120-second turn deadline, at most 4 answer/tool steps plus a bounded scope check, at most 6 provider attempts, 6 tool invocations, 3 searches, and 24 unique source items.
   - Routing follows the selected research level, with eligible sticky fallback within the same turn and `primary_only` routing available for scientific benchmarking.
3. **Conversation controls:** Low uses `ag/gemini-3.8-flash-low`, Medium uses `ag/gemini-3.8-flash-medium`, and High uses `fpt/Qwen3.8-27B`. Every chat has a server-enforced 500,000-token allowance (input plus output across model calls). The circle shows cumulative usage without numerical labels and gives a small new-session reminder at 90%; start a new chat when exhausted. The backend retains the transcript and selects relevant older turns plus recent context within each model request's budget; the allowance does not make a model accept a single 500k-token prompt. Image upload, paste and drop support PNG/JPEG/WebP research figures; generic file upload and starter question menus have been removed. Answers include contextual follow-up questions. Mathematical expressions render through bundled KaTeX, including offline fonts.
4. **Verified In-Document Jump:**
   - Content script locates paragraph nodes via element ID, CSS selector, or paragraph fingerprint.
   - Uses each answer's own source locators, scrolls to the verified paragraph and highlights it. The in-page chat minimizes to reveal the source; section fallback is labeled when an exact paragraph cannot be verified.
5. **Local Notes & Export:**
   - Client-side notes library (`chrome.storage.local`) preserving paper title, canonical URL, exact quotes, and answers.
   - One-click export to clean Markdown compatible with Obsidian, Notion, and Logseq.

---

## 3. Verification status

The publication checks on 2026-11-20 passed **142 Python backend/research tests**, **76 extension tests**, TypeScript typecheck and an isolated production build. Python checks blocked external socket connections and used temporary SQLite state. These tests exercise retrieval, owner isolation, bounded agents, citation handling, cancellation, OAuth contracts, memory, history and the chat interface.

Fixtures and mocked providers do not establish live model quality, semantic citation support, QASPER benchmark performance or real Google/GitHub sign-in. No paid provider calls or fresh browser acceptance run were made for this publication. Configure OAuth applications using the [account setup guide](docs/account_setup.md) before testing real sign-in.

Runtime retrieval uses E5 embeddings and BGE reranking through FPT Cloud; chat uses the configured 9Router gateway. Keep provider validation separate from offline tests and run the explicit live checks only when their usage is authorized.

Design drafts, agent tickets, raw browser/provider reports, downloaded browsers, local databases and credentials are intentionally excluded from Git. Public setup and API documentation remain in `docs/`.

---

## 4. Quickstart & Reproduction

### Prerequisites
- Python 3.11+ (tested with Python 3.13)
- Node.js 18+ (tested with Node v24)
- Google Chrome (or Chromium-based browser)

### 1. Backend Setup
```bash
# Install Python dependencies in virtual environment
python -m pip install -e '.[dev]'

# Configure FPT retrieval (API_URL/API_KEY) and 9Router chat (LLM_API_URL/LLM_API_KEY)
cp .env.example .env  # First-time setup only; preserve an existing .env

# Start the FastAPI backend
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
Verify the backend is live at `http://127.0.0.1:8000/api/v1/health`.

To check Qwen through 9Router and E5/BGE directly through FPT, run `python -m scripts.check_local_models --live`. This uses small synthetic inputs and exits nonzero if any model check fails. The FPT adapter sends wire model names `multilingual-e5-large` and `bge-reranker-v2-m3`; Qwen keeps the gateway alias `fpt/Qwen3.8-27B`.

The personal local configuration has no daily application caps (`-1`), while per-turn time, token and tool budgets remain enforced. Set `DAILY_AGENT_TURNS`, `DAILY_NEW_INDEXES` and `DAILY_SEMANTIC_RETRIEVALS` in `.env` to positive daily limits for a hosted service (`0` disables new work). Restart the backend after changing settings. Finite quotas reset at 00:00 UTC; upstream provider quotas are independent. Existing usage and paper data are preserved.

### 2. Extension Build & Installation
```bash
# Install NPM packages and build bundle
cd extension
npm ci
npm run build
```
1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in top right).
3. Click **Load unpacked** and select the `extension/dist/` directory.
4. Navigate to any supported arXiv HTML paper (e.g. `https://arxiv.org/html/1706.03762v7`).
5. Click the PaperLens toolbar icon to open the side panel.

### 3. Run Test Suites
```bash
# Run all Python backend and evaluation tests
python -m pytest backend/tests/ research/tests/

# Run extension unit tests and typecheck
cd extension
npm run typecheck
npm test
```

### 4. Offline fixture evaluation
Run synthetic fixture evaluation in a temporary database:
```bash
# Run B1 retrieval evaluation in fixture mode
python -m research.evaluation.run_eval --pipeline B1 --mode fixture

# Run A2 agent evaluation in fixture mode
python -m research.evaluation.run_eval --pipeline A2 --mode fixture

# Export results to Markdown tables
python -m scripts.export_results
```

---

## 5. Security & Privacy
- **User Disclosures:** Documented in [Privacy Policy](docs/privacy.md).
- **Owner Scope:** The extension persists a unique backend-issued bearer capability. Optional Google/GitHub sign-in associates a verified provider subject with an owner and rotates the capability. Production validates token hashes; development also accepts explicit local test identities. Anonymous local sessions remain available before OAuth setup.
- **Data Deletion:** Full immediate deletion of in-memory indices and SQLite records via `DELETE /api/v1/papers/{id}`.

---

## 6. License
Distributed under the Apache 2.0 License.
