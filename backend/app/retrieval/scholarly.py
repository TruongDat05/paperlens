"""External scholarly literature retrieval client for PaperLens.

Queries arXiv and Semantic Scholar APIs to retrieve relevant research papers,
extract titles, authors, abstracts, URLs, and convert them to EvidenceItems.

Includes a bounded live-result cache. Fixtures are available only in explicit
mock mode; an unavailable live source never becomes synthetic evidence.
"""

from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET
import re
import time
import asyncio
from pydantic import BaseModel, Field
import httpx

from backend.app.core.config import get_settings
from backend.app.core.schemas import EvidenceItem, SourceLocation


class ScholarlyPaper(BaseModel):
    """Normalized metadata for an external scholarly paper."""
    paper_id: str
    title: str
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    abstract: str
    url: str
    source: str = "arxiv"

    def to_evidence_item(self, rank: int = 1) -> EvidenceItem:
        """Convert external paper into a PaperLens EvidenceItem."""
        clean_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", self.paper_id)
        passage_id = f"ext_{clean_id}"
        authors_str = ", ".join(self.authors[:3])
        if len(self.authors) > 3:
            authors_str += " et al."
        year_str = f" ({self.year})" if self.year else ""

        full_text = f"Title: {self.title}\nAuthors: {authors_str}{year_str}\nURL: {self.url}\nAbstract (not full text): {self.abstract[:6000]}"

        return EvidenceItem(
            passage_id=passage_id,
            parent_passage_id=passage_id,
            rank=rank,
            score=0.0,  # Provider ordering is not a calibrated relevance score.
            section_heading=f"External Paper: {self.title}",
            section_path="External Scholarly Literature",
            text=full_text,
            locator=SourceLocation(xpath=self.url, element_id=self.paper_id),
            contributing_chunks=[passage_id],
            paper_id=self.paper_id,
        )


# ponytail: process-local cache and pacing; use a shared limiter for multiple workers.
_SCHOLARLY_CACHE: Dict[str, tuple[float, List[ScholarlyPaper]]] = {}
_ARXIV_LOCK = asyncio.Lock()
_last_arxiv_request = 0.0


def _cache_results(key: str, papers: List[ScholarlyPaper]) -> List[ScholarlyPaper]:
    if len(_SCHOLARLY_CACHE) >= 128:
        _SCHOLARLY_CACHE.pop(next(iter(_SCHOLARLY_CACHE)))
    _SCHOLARLY_CACHE[key] = (time.monotonic(), papers)
    return papers

# Offline fixture papers for deterministic tests
OFFLINE_FIXTURE_PAPERS: List[ScholarlyPaper] = [
    ScholarlyPaper(
        paper_id="arxiv:2001.04451",
        title="Reformer: The Efficient Transformer",
        authors=["Nikita Kitaev", "Lukasz Kaiser", "Anselm Levskaya"],
        year=2020,
        abstract="Large Transformer models routinely achieve state-of-the-art results on a number of tasks but training these models can be prohibitively expensive, especially on long sequences. We present two techniques to improve the efficiency of Transformers: locality-sensitive hashing (LSH) attention replacing dot-product attention to reduce complexity from O(L^2) to O(L log L), and reversible residual layers preserving activations instead of storing them during backpropagation.",
        url="https://arxiv.org/abs/2001.04451",
        source="arxiv",
    ),
    ScholarlyPaper(
        paper_id="arxiv:2004.05150",
        title="Longformer: The Long-Document Transformer",
        authors=["Iz Beltagy", "Matthew E. Peters", "Arman Cohan"],
        year=2020,
        abstract="Transformer-based models are unable to process long sequences due to their self-attention operation scaling quadratically with sequence length. To address this limitation, we present Longformer with an attention mechanism that scales linearly with sequence length, making it easy to process documents of thousands of tokens or longer. Longformer's attention mechanism is a plug-and-play drop-in replacement for the standard self-attention and combines a local windowed attention with a task-motivated global attention.",
        url="https://arxiv.org/abs/2004.05150",
        source="arxiv",
    ),
    ScholarlyPaper(
        paper_id="arxiv:2205.14135",
        title="FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness",
        authors=["Tri Dao", "Daniel Y. Fu", "Stefano Ermon", "Atri Rudra", "Christopher Ré"],
        year=2022,
        abstract="Transformers are slow and memory-hungry on long sequences, since the time and memory complexity of self-attention are quadratic in sequence length. Approximate attention methods have attempted to trade off model quality with compute time, but often do not achieve wall-clock speedup. We propose FlashAttention, an IO-aware exact attention algorithm that uses tiling to reduce the number of memory reads/writes between GPU high bandwidth memory (HBM) and GPU on-chip SRAM.",
        url="https://arxiv.org/abs/2205.14135",
        source="arxiv",
    ),
    ScholarlyPaper(
        paper_id="arxiv:2005.11401",
        title="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        authors=["Patrick Lewis", "Ethan Perez", "Aleksandra Piktus", "Fabio Petroni"],
        year=2020,
        abstract="Large pre-trained language models have been shown to store factual knowledge in their parameters, but their ability to access and precisely manipulate knowledge is still limited. We explore general-purpose fine-tuning recipes for retrieval-augmented generation (RAG) — models which combine pre-trained parametric and non-parametric memory for language generation. We introduce RAG models where the parametric memory is a pre-trained seq2seq model and the non-parametric memory is a dense vector index of Wikipedia.",
        url="https://arxiv.org/abs/2005.11401",
        source="arxiv",
    ),
    ScholarlyPaper(
        paper_id="arxiv:2310.11511",
        title="Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection",
        authors=["Akari Asai", "Zeqiu Wu", "Yizhong Wang", "Avirup Sil", "Hannaneh Hajishirzi"],
        year=2023,
        abstract="Despite their remarkable capabilities, large language models (LLMs) often generate responses containing factual errors due to relying solely on their parametric knowledge. We propose Self-Reflective Retrieval-Augmented Generation (Self-RAG) that improves an LLM's quality and factuality through retrieval and self-reflection tokens. Our framework trains a single arbitrary LM that adaptively retrieves passages on-demand, generates responses, and reflects on retrieved passages and its own generations.",
        url="https://arxiv.org/abs/2310.11511",
        source="arxiv",
    ),
]


def _filter_mock_papers(query: str, max_results: int) -> List[ScholarlyPaper]:
    """Filter mock papers by query keywords or return defaults."""
    q_tokens = set(re.findall(r"\w+", query.lower()))
    scored: List[tuple[int, ScholarlyPaper]] = []
    for p in OFFLINE_FIXTURE_PAPERS:
        text = f"{p.title} {p.abstract}".lower()
        score = sum(1 for t in q_tokens if t in text)
        scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [p for _, p in scored[:max_results]]
    return results or OFFLINE_FIXTURE_PAPERS[:max_results]


def parse_arxiv_atom(xml_text: str) -> List[ScholarlyPaper]:
    """Parse arXiv Atom XML response into ScholarlyPaper list."""
    papers: List[ScholarlyPaper] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return papers

    atom_ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f"{atom_ns}entry"):
        id_elem = entry.find(f"{atom_ns}id")
        title_elem = entry.find(f"{atom_ns}title")
        summary_elem = entry.find(f"{atom_ns}summary")
        published_elem = entry.find(f"{atom_ns}published")

        if title_elem is None or summary_elem is None:
            continue

        raw_id = id_elem.text.strip() if id_elem is not None and id_elem.text else ""
        arxiv_num = raw_id.split("/abs/")[-1].strip() if "/abs/" in raw_id else raw_id
        if not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-zA-Z.-]+/\d{7})(?:v\d+)?", arxiv_num):
            continue  # Includes arXiv API error entries, which are not papers.
        paper_id = f"arxiv:{arxiv_num}" if not arxiv_num.startswith("arxiv:") else arxiv_num

        title = " ".join(title_elem.text.split()) if title_elem.text else "Untitled"
        abstract = " ".join(summary_elem.text.split()) if summary_elem.text else ""
        if not title.strip() or not abstract.strip():
            continue

        authors: List[str] = []
        for author in entry.findall(f"{atom_ns}author"):
            name_elem = author.find(f"{atom_ns}name")
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text.strip())

        year = None
        if published_elem is not None and published_elem.text:
            try:
                year = int(published_elem.text[:4])
            except ValueError:
                year = None

        url = f"https://arxiv.org/abs/{arxiv_num}" if arxiv_num else raw_id

        papers.append(
            ScholarlyPaper(
                paper_id=paper_id,
                title=title,
                authors=authors,
                year=year,
                abstract=abstract,
                url=url,
                source="arxiv",
            )
        )
    return papers


async def search_external_scholarly(
    query: str,
    max_results: int = 3,
    timeout_seconds: float = 6.0,
    force_mock: Optional[bool] = None,
) -> List[ScholarlyPaper]:
    """Search external scholarly literature via arXiv or Semantic Scholar APIs.

    Mock data is never cached or used as a live fallback. Empty live results
    mean the agent must disclose the missing external evidence.
    """
    bounded_limit = max(1, min(int(max_results), 6))
    clean_query = query.strip()
    if not clean_query:
        return []

    is_mock = get_settings().mock_providers if force_mock is None else force_mock
    if is_mock:
        return _filter_mock_papers(clean_query, bounded_limit)

    cache_key = f"{clean_query.lower()}:{bounded_limit}"
    cached = _SCHOLARLY_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < 900:
        return cached[1]

    # Live arXiv query
    try:
        global _last_arxiv_request
        # Escape query syntax and make each keyword's field explicit.
        terms = re.findall(r"\w+(?:-\w+)*", clean_query)[:16]
        params = {"search_query": " AND ".join(f'all:{term}' for term in terms),
                  "start": 0, "max_results": bounded_limit, "sortBy": "relevance"}
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            # Retry an over-specific, valid empty search once using its core terms.
            queries = [params["search_query"]]
            if len(terms) > 3:
                queries.append(" AND ".join(f'all:{term}' for term in terms[:3]))
            for search_query in queries:
                async with _ARXIV_LOCK:
                    await asyncio.sleep(max(0, 3 - (time.monotonic() - _last_arxiv_request)))
                    _last_arxiv_request = time.monotonic()
                    resp = await client.get("https://export.arxiv.org/api/query", params={**params, "search_query": search_query},
                                            headers={"User-Agent": "PaperLens/0.1 research companion"})
                if resp.status_code != 200:
                    break
                papers = parse_arxiv_atom(resp.text)
                if papers:
                    return _cache_results(cache_key, papers[:bounded_limit])
    except Exception:
        pass

    # Secondary fallback: Semantic Scholar API
    try:
        ss_url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": clean_query,
            "limit": bounded_limit,
            "fields": "title,authors,abstract,year,url,externalIds",
        }
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = await client.get(ss_url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                ss_papers: List[ScholarlyPaper] = []
                for item in data.get("data", []):
                    title = item.get("title")
                    abstract = item.get("abstract") or ""
                    if not title or not abstract:
                        continue
                    authors = [a.get("name", "") for a in item.get("authors", []) if a.get("name")]
                    year = item.get("year")
                    ext_ids = item.get("externalIds") or {}
                    arxiv_id = ext_ids.get("ArXiv")
                    source_id = item.get('paperId', '')
                    if not source_id:
                        continue
                    paper_id = f"arxiv:{arxiv_id}" if arxiv_id else f"ss:{source_id}"
                    url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else f"https://www.semanticscholar.org/paper/{source_id}"
                    ss_papers.append(
                        ScholarlyPaper(
                            paper_id=paper_id,
                            title=title,
                            authors=authors,
                            year=year,
                            abstract=abstract,
                            url=url,
                            source="semanticscholar",
                        )
                    )
                if ss_papers:
                    return _cache_results(cache_key, ss_papers[:bounded_limit])
    except Exception:
        pass

    return []
