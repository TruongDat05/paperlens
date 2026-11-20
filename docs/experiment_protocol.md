# PaperLens QASPER Experiment Protocol (v4.1)

## 1. Dataset Specification and Splits
- **Dataset:** Official QASPER v0.3 (`allenai/qasper`, revision `006d967a57a550974051a8f9a3ba0814bb653456`).
- **Disjoint Splits by Paper:**
  - Train: 888 papers, 2,585 questions
  - Dev: 281 papers, 1,005 questions
  - Test: 416 papers, 1,459 questions

## 2. Text-Evidence and Reference Set Definitions
Each QASPER question is associated with one or more annotations.
1. **Valid Reference Set:** An annotation's evidence strings are deterministically mapped to the paper's parent paragraph IDs using normalized whitespace and case-insensitive matching. Non-empty, fully mapped paragraph sets form valid reference sets.
2. **Text Retrieval Eligibility:** A question is eligible for text retrieval evaluation if at least one annotation is answerable and provides at least one valid text reference set.
3. **Abstention Populations:**
   - **Abstention Positives:** All annotations are answerable and have at least one valid text reference.
   - **Abstention Negatives:** All annotations are explicitly marked unanswerable.

## 3. Retrieval Metrics (§W2.2)
All metrics operate on **unique parent paragraphs**, deduplicated in rank order from candidate chunks:
- **Recall@5:** Fraction of gold paragraphs in reference set $R$ present in top 5 predicted parents: $\frac{|P_5 \cap R|}{|R|}$.
- **Paragraph Evidence F1@5:** Harmonic mean of precision at 5 and recall at 5: $2 \cdot \frac{P@5 \cdot R@5}{P@5 + R@5}$.
- **Multi-annotation aggregation:** For questions with multiple annotators, compute Recall@k and F1@k against each valid reference set and take the **maximum** over valid reference sets, then compute the macro-average across eligible questions.
- **Candidate Recall@20:** Evaluates the top 20 candidate chunks before reranking, mapped to unique parents, against the reference sets.
- **MRR@10:** Reciprocal rank ($1 / \text{rank}$) of the first gold paragraph appearing in the top 10 predictions, maximized over reference sets.

## 4. Pipeline Configurations
- **B1:** Lexical retrieval via Lucene-floored BM25 over chunked passages.
- **B2:** Dense retrieval via `intfloat/multilingual-e5-large` with `query: ` and `passage: ` prefixes and cosine similarity.
- **B3:** Reciprocal Rank Fusion (RRF with $k=60$) combining B1 (40 chunks) and B2 (40 chunks).
- **B4:** B3 fused candidates reranked with `BAAI/bge-reranker-v2-m3` (top 20 pairs).
- **A1:** Single-pass cited answering with B4 retrieval + Gemini generation.
- **A2:** Bounded tool-loop agent using 3 read-only tools (`get_paper_outline`, `search_evidence`, `read_section`).
- **Research Evaluation Routing:** Strict `primary_only` routing (`ag/gemini-3.8-flash-medium`) for matched scientific evaluation.

---

## 5. Frozen Evaluation Record (W6.4)
- **Code Revision:** Locked at current git HEAD (`implement-plan` branch).
- **Frozen Configurations:**
  - `configs/baseline.yaml` (B1–B4 benchmark)
  - `configs/agent_qa.yaml` (A1 vs A2 comparative evaluation)
- **QASPER Stratified Test Subset:**
  - Pinned seed: `42`.
  - Sample size: 100 evaluation questions stratified across papers, answerability, and single vs multi-paragraph evidence.
- **Execution Policy:**
  - Single turn limit: 30 seconds.
  - Max tool invocations: 4.
  - Max searches: 2.
  - Max parent evidence: 8 unique paragraphs.
  - Routing: `primary_only` (`ag/gemini-3.8-flash-medium`).
- **Paired Analysis Convention:**
  - Cluster bootstrap resampling at the paper level ($B=2,000$ resamples).
  - 95% confidence intervals on macro-averaged $\Delta \text{Recall@5}$, $\Delta \text{Evidence F1@5}$, and $\Delta \text{Rubric}$.
  - Technical failures (timeouts, network drops) counted as 0-score outcomes in intention-to-treat analysis.
