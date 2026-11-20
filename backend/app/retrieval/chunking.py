"""Split long paragraphs while preserving their source lineage.

Accept arXiv or QASPER paragraphs and an E5 tokenizer or whitespace
fallback. Target about 400 tokens including the prefix, with room for
special tokens.

Assign deterministic subchunk IDs and text offsets. Keep
parent_passage_id so results and evaluation labels map to the same
original paragraph. For replay, use tokenizer resources already
available locally.
"""

from typing import List, Optional
import re
from backend.app.core.schemas import ParagraphInput, PassageChunk, SourceLocation


def estimate_token_count(text: str) -> int:
    """Rough estimation of token count: approx 1.3 tokens per word or regex tokenization."""
    words = text.split()
    return int(len(words) * 1.3) + 1


def chunk_paragraph(
    para: ParagraphInput,
    max_tokens: int = 400,
    tokenizer=None,
    paper_id: Optional[str] = None,
) -> List[PassageChunk]:
    """Split a paragraph into subchunks if it exceeds max_tokens."""
    text = para.text.strip()
    locator = para.locator or SourceLocation(element_id=para.id)

    # Calculate token count
    if tokenizer is not None and hasattr(tokenizer, "encode"):
        tokens = tokenizer.encode(text)
        token_count = len(tokens)
    else:
        token_count = estimate_token_count(text)

    # If within limit, return a single passage chunk
    if token_count <= max_tokens:
        return [
            PassageChunk(
                passage_id=para.id,
                parent_passage_id=para.id,
                paper_id=paper_id,
                section_id=para.section_id,
                section_path=para.section_path,
                paragraph_order=para.paragraph_order,
                text=text,
                locator=locator,
                offset_start=0,
                offset_end=len(text),
                fingerprint=para.fingerprint,
            )
        ]

    # Split long paragraph by sentence boundaries, falling back to word boundaries
    sentence_matches = [m.group(0) for m in re.finditer(r'([^.!?]+[.!?]+(?:\s+|$)|[^.!?]+$)', text) if m.group(0)]

    # Subdivide any sentence that alone exceeds max_tokens
    units: List[str] = []
    for s in sentence_matches:
        if estimate_token_count(s) > max_tokens:
            words = s.split(" ")
            curr_w: List[str] = []
            curr_cnt = 0
            for w in words:
                w_str = w + " "
                w_cnt = estimate_token_count(w_str)
                if curr_w and (curr_cnt + w_cnt > max_tokens):
                    units.append("".join(curr_w))
                    curr_w = [w_str]
                    curr_cnt = w_cnt
                else:
                    curr_w.append(w_str)
                    curr_cnt += w_cnt
            if curr_w:
                units.append("".join(curr_w))
        else:
            units.append(s)

    chunks: List[PassageChunk] = []
    current_units = []
    current_start = 0
    current_tokens = 0
    chunk_index = 0

    for u in units:
        u_tokens = estimate_token_count(u)
        if current_units and (current_tokens + u_tokens > max_tokens):
            raw_chunk_text = "".join(current_units)
            chunk_text = raw_chunk_text.strip()
            # Align offset_start and offset_end to chunk_text in original text
            actual_start = text.find(chunk_text, current_start)
            if actual_start == -1:
                actual_start = current_start
            actual_end = actual_start + len(chunk_text)
            chunks.append(
                PassageChunk(
                    passage_id=f"{para.id}:c{chunk_index}",
                    parent_passage_id=para.id,
                    paper_id=paper_id,
                    section_id=para.section_id,
                    section_path=para.section_path,
                    paragraph_order=para.paragraph_order,
                    text=chunk_text,
                    locator=locator,
                    offset_start=actual_start,
                    offset_end=actual_end,
                    fingerprint=para.fingerprint,
                )
            )
            chunk_index += 1
            current_start = actual_end
            current_units = [u]
            current_tokens = u_tokens
        else:
            current_units.append(u)
            current_tokens += u_tokens

    if current_units:
        raw_chunk_text = "".join(current_units)
        chunk_text = raw_chunk_text.strip()
        actual_start = text.find(chunk_text, current_start)
        if actual_start == -1:
            actual_start = current_start
        actual_end = actual_start + len(chunk_text)
        chunks.append(
            PassageChunk(
                passage_id=f"{para.id}:c{chunk_index}",
                parent_passage_id=para.id,
                paper_id=paper_id,
                section_id=para.section_id,
                section_path=para.section_path,
                paragraph_order=para.paragraph_order,
                text=chunk_text,
                locator=locator,
                offset_start=actual_start,
                offset_end=actual_end,
                fingerprint=para.fingerprint,
            )
        )

    return chunks


def chunk_paper(
    paragraphs: List[ParagraphInput],
    max_tokens: int = 400,
    tokenizer=None,
    paper_id: Optional[str] = None,
) -> List[PassageChunk]:
    """Chunk all paragraphs of a paper, preserving document order."""
    all_chunks: List[PassageChunk] = []
    for para in paragraphs:
        chunks = chunk_paragraph(para, max_tokens=max_tokens, tokenizer=tokenizer, paper_id=paper_id)
        all_chunks.extend(chunks)
    return all_chunks
