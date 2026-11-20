> Pending acceptance criteria, not a record of browser or study verification. See current verification (local only).

# PaperLens Release Checklist & Verification Runbook (W6.3 & W7.2)

This checklist enforces required technical, security, and policy gates before building the Chrome Web Store production release package and deploying the hosted FastAPI backend.

---

## 1. Technical Gates (Code, Tests, and Type Safety)

- [ ] **Python Backend Test Suite:**
  - `python -m pytest backend/tests/ research/tests/` passes with 100% green tests (requires current verification).
  - Temporary SQLite test DB isolation (`backend/tests/conftest.py`) ensures zero test polluters.
- [ ] **Extension Typecheck & Unit Tests:**
  - `npm --prefix extension run typecheck` passes with 0 errors.
  - `npm --prefix extension test` passes with 100% green tests (requires current verification).
- [ ] **Production Bundle Build:**
  - `npm --prefix extension run build` bundles scripts cleanly into `extension/dist/`.
  - Zero development test fixtures or private credentials included in the bundle.
- [ ] **Navigation & Parser Acceptance Gate:**
  - 20-paper corpus audit verified with $\ge 95\%$ paragraph jump accuracy (requires current verification).
  - Zero known wrong highlights across all attempts.
  - Abstract-to-HTML conversion link verified.

---

## 2. Chrome Web Store Compliance & Manifest Audit

- [ ] **Manifest Version:** MV3 (`"manifest_version": 3`).
- [ ] **Permission Justifications:**
  | Permission | Justification |
  | :--- | :--- |
  | `sidePanel` | Provides persistent, non-intrusive research side panel alongside arXiv HTML papers. |
  | `storage` | Stores user notes, saved quotes, and session run state locally. |
  | `activeTab` | Detects paper URL and DOM content in the active reading tab upon user consent. |
  | `tabs` | Directs user from abstract pages to the corresponding HTML version when requested. |
- [ ] **Host Permissions:**
  - Scoped strictly to `https://arxiv.org/html/*` and `https://arxiv.org/abs/*`.
  - Backend API origin explicitly declared in CSP (`connect-src`).
- [ ] **Single Purpose Policy:** Extension operates exclusively to index and answer questions on research papers.
- [ ] **Privacy Disclosures:** `docs/privacy.md` published and accessible via public URL.

---

## 3. Backend & Security Configuration

- [ ] **Authentication:** Bearer token session authentication (`core/security.py`) enforced on all protected endpoints (`/papers/*`, `/retrieve`, `/agent/*`).
- [ ] **Rate Limiting & Quotas:** Quotas per user session and IP (`core/limits.py`) enforced for new indices, retrieval queries, and agent turns.
- [ ] **Input Limits:** Hard server-side caps:
  - Max paper paragraphs: 2,500.
  - Max question length: 1,024 characters.
  - Product turn execution deadline: 120 seconds.
  - Cumulative chat allowance: 500,000 input/output tokens.
- [ ] **Owner Isolation:** Cross-user paper or run access forbidden; verified with test suite.
- [ ] **Data Deletion:** Complete resource release and DB pruning on `DELETE /api/v1/papers/{id}`.

---

## 4. Packaging and Release Artifact Generation

To produce the official release ZIP for the Chrome Web Store:
```bash
# 1. Clean build of extension assets
cd extension && npm run build

# 2. Package into zip file
cd dist && zip -r ../../paperlens-v0.1.0-release.zip ./*
```

## 5. Reviewer Test Instructions (Chrome Web Store Review)
1. Unpack or install the provided extension candidate.
2. Navigate in Chrome to `https://arxiv.org/html/1706.03762v7`.
3. Open the PaperLens side panel via the toolbar action.
4. Click **"Consent & Enable Analysis"**, then **"Analyze This Paper"**.
5. When the paper is ready, type *"What datasets are used for evaluation?"* and send it at the desired Low/Medium/High level.
6. Verify the answer has small numbered citations and contextual follow-up questions.
7. Click a numbered in-paper citation to verify scrolling and highlighting of the correct source. The in-page overlay should minimize to reveal it.
8. Click **"Save answer to notes"** to verify local note preservation.
