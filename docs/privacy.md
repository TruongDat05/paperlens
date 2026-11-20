# PaperLens Privacy Policy & Data Disclosures

**Last Updated:** November 2026
**Applicability:** PaperLens Chrome Extension & FastAPI Backend Service

---

## 1. Core Principles
PaperLens is designed as an evidence-grounded research companion for scientific reading. We adhere strictly to data minimization, transparent user disclosures, and the [Chrome Web Store User Data FAQ and Policies](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq).

1. **No Data Collection Without Prior Consent:** The extension never inspects, parses, or transmits page content until you explicitly click **"Consent & Enable Analysis"** on a supported paper.
2. **Single Purpose:** PaperLens processes paper text solely to index paragraphs and answer your research questions grounded in source evidence.
3. **No Monetization of Personal Data:** We do not sell, rent, or monetize your research queries, browsing habits, or personal identifiers.

---

## 2. What Data Is Processed and Where It Goes

### 2.1 In-Browser Processing (Client Side)
- **Extracted Content:** When you trigger paper analysis, PaperLens parses the active tab's DOM to extract section headings and text paragraphs from public arXiv HTML pages (`https://arxiv.org/html/*`).
- **Locators & Fingerprints:** Element IDs, CSS selectors, and SHA-256 paragraph hashes are generated locally to enable precise Jump highlighting in your browser tab.
- **Local Notes:** Saved answers and quoted passages are stored exclusively on your device using `chrome.storage.local`.
- **Profiles and Account Caches:** The first-use form requests the name, research area and nationality provided by you. Cached paper/chat state is separated by backend owner. Existing pre-account caches are claimed once by their original local owner. Window geometry and theme are stored locally.

### 2.2 Data Transferred to the PaperLens Backend
- **Analyze Action:** Sends extracted paper metadata (title, arXiv ID, version, canonical URL, section hierarchy, and paragraphs) to the PaperLens backend to build in-memory lexical (BM25) and dense indices.
- **Ask Action:** Sends attached research images when provided, your research question, bounded conversational history (up to the last 6 turns), and the paper ID to coordinate retrieval and cited answering. The backend stores questions and answers with the conversation and can retrieve relevant older turns.
- **Research Memory:** The backend stores your profile and important research quotations with source provenance. Explicit research-memory requests can retain the original question. Other automatically selected notes must match a supplied source or the current user question. You can disable long-term remembering, edit notes, or forget them in Settings. Disabling long-term memory does not delete chat transcripts or the profile.

### 2.3 Third-Party Provider Data Transfers
When backend inference is configured:
1. **FPT AI Factory (Serverless Inference):**
   - *Data Sent:* Paragraph text for generating vector embeddings (`intfloat/multilingual-e5-large`) and query/passage pairs for candidate reranking (`BAAI/bge-reranker-v2-m3`).
   - *Retention:* Ephemeral stateless processing for model inference without training on user inputs.
2. **Google DeepMind / LLM Gateway:**
   - *Data Sent:* Your research question, paper title, explicit research profile, relevant long-term memories and bounded history for scope classification; up to 24 retrieved source items and up to 6 previous conversational turns selected for relevance and recency, and attached image pixels (or visual-reader observations for High) for generating cited answers. Low uses `ag/gemini-3.8-flash-medium`, Medium uses `ag/gemini-3.8-flash-high`, and High uses `ag/claude-sonnet-4-6`.
   - *Retention:* Standard zero-data-retention API policies for commercial inference; queries are not used for foundation model pre-training.

3. **arXiv / Semantic Scholar:** For literature and research-direction questions, the backend sends short scholarly topic keywords derived from the paper title and question to these public search APIs. Returned metadata and abstracts are used as external evidence. Live results are cached in process for up to 15 minutes (128 entries); the entire paper is not submitted to these search APIs.

4. **Optional Google/GitHub Login:** Clicking a sign-in button starts the provider's consent flow. Google receives `openid profile`; GitHub receives `read:user`. The backend reads the stable provider subject and display name, stores that account mapping, and does not request repository access. Provider access tokens are used transiently for the profile request and are not stored. A new anonymous profile remains usable when OAuth is unconfigured. Nationality is supplied in PaperLens's form, not inferred from provider metadata.

---

## 3. Data Storage, Ownership, and Retention
- **Per-User Isolation:** Every indexed paper, search query, and agent run is scoped strictly to the authenticated bearer token (`user_id`). Users cannot access, query, or observe papers or traces belonging to another account.
- **Operational Logs:** Operational logs retain only anonymized technical telemetry (latency, token usage counts, error codes). User queries and raw paper text are excluded from operational server logs.
- **Conversation Records:** Questions, answers, image attachments, citations, follow-ups and token usage are stored in the backend SQLite database for conversation restoration and retrieval of earlier research context. Starting a new chat creates a separate conversation; it does not delete previous records. Chat history and long-term notes remain until explicitly deleted; the run-retention configuration does not currently automatically prune these chats.
- **Inactivity Expiry:** Unused in-memory indices and paper caches are automatically expired and reclaimed following 24 hours of inactivity.

---

## 4. User Rights and Data Deletion
You retain complete control over all data associated with your session:
1. **Local Notes Deletion:** You can delete individual saved notes or clear all stored research notes at any time from the extension interface.
2. **Server-Side Data Deletion:** You can trigger immediate server deletion of any indexed paper and all associated passage vectors and run traces via the backend API endpoint (`DELETE /api/v1/papers/{id}`).
3. **Session Reset:** Clicking **"New chat"** clears the active client conversation, image context and in-flight run identifiers, and starts a new token allowance. It does not erase backend records or saved notes.
4. **Memory and History:** Settings allows viewing, editing, adding and forgetting long-term notes. Chat history allows deleting an individual transcript. Deleting a chat keeps separately saved long-term notes; deleting an indexed paper also deletes long-term notes attached to that paper. Signing out revokes the current installation's token, switches to a separate local owner, and preserves account data for future login.

---

## 5. Contact
For questions regarding PaperLens data practices or privacy rights:
- **Email:** `privacy@paperlens.org` (or repository maintainer contact)
- **Repository:** `https://github.com/paperlens/paperlens`
