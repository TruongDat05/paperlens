# arXiv ML/NLP Corpus Selection and Proposed Parser Audit

## 1. Selection Criteria
1. Papers published in ML/NLP venues available in arXiv experimental HTML (`https://arxiv.org/html/<arxiv_id>v<version>`).
2. Structural variety: nested sections, long paragraphs, multi-part appendices, equations/math blocks, tables, footnotes, and varying section numbering styles.
3. Subfield coverage: Transformers, Retrieval-Augmented Generation, Model Compression / Quantization, Mixture of Experts, Instruction Tuning, Multimodal LLMs, Evaluation.
4. Entry path coverage: Abstract-to-HTML conversion links (`/abs/...` -> `/html/...`).

---

## 2. Candidate paper list

| No | Candidate arXiv ID & Version | Proposed Title (unverified) | Proposed Layout Features |
|---|---|---|---|
| 1 | `1706.03762v7` | Attention Is All You Need | Multi-head math, sub-layer tables, Appendix A/B |
| 2 | `2005.11401v4` | Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks | Dense equations, parametric / nonparametric breakdown |
| 3 | `2105.03011v2` | QASPER: A Dataset of Information-Seeking Questions on Research Papers | Multi-paragraph answers, nested tables, ablations |
| 4 | `2310.06825v1` | Mistral 7B | Grouped-query attention, sliding window architecture |
| 5 | `2401.04088v1` | Mixtral of Experts | Sparse MoE routing formulas, benchmark tables |
| 6 | `2203.02155v1` | Training language models to follow instructions with human feedback | Alignment loss equations, qualitative outputs |
| 7 | `2305.14314v1` | QLoRA: Efficient Finetuning of Quantized LLMs | 4-bit NormalFloat math, double quantization, paged optimizers |
| 8 | `2302.13971v1` | LLaMA: Open and Efficient Foundation Language Models | Pre-training loss curves, token throughput, architecture tables |
| 9 | `2312.11805v1` | Gemini: A Family of Highly Capable Multimodal Models | Complex multimodal figures/captions, extensive appendices |
| 10 | `2309.05463v2` | Contrastive Decoding: Open-ended Text Generation | Decoding formulas, human evaluation tables, sample outputs |
| 11 | `2307.09288v2` | Llama 2: Open Foundation and Fine-Tuned Chat Models | Safety evaluation protocols, multi-stage RLHF tables |
| 12 | `2303.08774v6` | GPT-4 Technical Report | Nonstandard broad layout, extensive system card appendix |
| 13 | `2304.03442v1` | Generative Agents: Interactive Simulacra of Human Behavior | Long interview dialogue transcripts, simulation tables |
| 14 | `2308.08155v2` | FlashDecoding++: Faster Large Language Model Inference on GPUs | Kernel performance math, memory bandwidth figures |
| 15 | `2310.11511v1` | Self-RAG: Learning to Retrieve, Generate, and Critique | Reflection tokens, critique trees, algorithmic blocks |
| 16 | `2402.01680v2` | MobileLLM: Optimizing Sub-billion Parameter Language Models | Deep thin architectures, embedding sharing tables |
| 17 | `2403.09611v1` | DeepSeek-V2: A Strong, Economical MoE Language Model | Multi-head Latent Attention formulas, device maps |
| 18 | `2404.14219v1` | Phi-3 Technical Report: Highly Capable Language Models Locally | Synthetic data filtering rules, benchmark scorecards |
| 19 | `2305.18290v2` | Direct Preference Optimization: Your Language Model is Secretly a Reward Model | Implicit reward derivation, Bradley-Terry objective math |
| 20 | `2407.21783v1` | The Llama 3 Herd of Models | 405B dense architecture, massive synthetic recipe |

Candidate metadata and HTML availability require checking. No parser or browser outcomes have been measured for this list in this review.
