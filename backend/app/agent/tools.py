"""Run read-only tools against the paper in the current run.

Expose get_paper_outline, search_evidence, read_section and scholarly search. Use the
paper version assigned to the run by the backend and validate tool
names, arguments, section IDs, offsets, and passage limits.

Search uses the shared retrieval engine. Return observations in the
agreed schema, with passage IDs and source information for the passages
the agent read.
"""

from typing import Any, Dict, List, Optional
import json

from backend.app.core.db import get_connection
from backend.app.core.config import get_settings
from backend.app.core.schemas import EvidenceItem, SourceLocation
from backend.app.cache.paper_store import (
    get_paper_chunks,
    get_bm25_index,
)
from backend.app.retrieval.hybrid import retrieve_hybrid
from backend.app.agent.schemas import Observation

AGENT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_paper_outline",
            "description": "Get the hierarchical outline of the paper with section titles and IDs.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_evidence",
            "description": "Search the paper for evidence passages matching a natural language query or concept.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "English search query or reformulation.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of evidence passages to retrieve (1-8).",
                        "default": 3,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_section",
            "description": "Read paragraphs in a specific section by section_id in document order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section_id": {
                        "type": "string",
                        "description": "Valid section_id obtained from the outline.",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Nonnegative paragraph offset within the section.",
                        "default": 0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of paragraphs to read (1-6).",
                        "default": 5,
                    },
                },
                "required": ["section_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_external_papers",
            "description": "Search external scholarly literature (arXiv / Semantic Scholar) for related papers, alternative approaches, or promising research extension directions beyond the current paper. Use when answering questions about related work, comparisons, or future extension directions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Scholarly search query in English (e.g., 'sparse attention linear complexity' or 'self-reflection retrieval augmented generation').",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of external papers to retrieve (1-5).",
                        "default": 3,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]


class PaperAgentTools:
    """Executes validated read-only tool calls for an authorized paper and owner."""

    def __init__(self, paper_id: str, owner_id: str):
        self.paper_id = paper_id
        self.owner_id = owner_id
        self.retrieval_mode = None
        self.retrieval_fallback_reason = None

    def _check_paper_ownership(self, conn) -> bool:
        cursor = conn.execute(
            "SELECT paper_id FROM papers WHERE paper_id = ? AND owner_id = ?",
            (self.paper_id, self.owner_id),
        )
        return cursor.fetchone() is not None

    async def get_paper_outline(self) -> Observation:
        """Return the section tree and titles for the paper."""
        conn = get_connection()
        if not self._check_paper_ownership(conn):
            return Observation(
                tool_name="get_paper_outline",
                content=f"Error: paper '{self.paper_id}' not found or unauthorized.",
            )
        cursor = conn.execute(
            """
            SELECT section_id, heading, path, section_order, section_type
            FROM sections
            WHERE paper_id = ?
            ORDER BY section_order ASC
            """,
            (self.paper_id,),
        )
        rows = cursor.fetchall()

        if not rows:
            return Observation(
                tool_name="get_paper_outline",
                content="Paper outline not found or paper has no structured sections.",
            )

        lines = ["# Paper Outline:"]
        for r in rows:
            sec_type = f" ({r['section_type']})" if r["section_type"] else ""
            lines.append(f"- [{r['section_id']}] {r['heading']}{sec_type}")

        return Observation(
            tool_name="get_paper_outline",
            content="\n".join(lines),
        )

    async def search_evidence(
        self,
        query: str,
        top_k: int = 3,
        tool_call_id: Optional[str] = None,
    ) -> Observation:
        """Search the paper using hybrid retrieval within the authorized paper scope."""
        bounded_k = max(1, min(int(top_k), 8))
        chunks = get_paper_chunks(self.paper_id, self.owner_id)
        bm25_idx = get_bm25_index(self.paper_id, self.owner_id)

        res = await retrieve_hybrid(
            query=query,
            chunks=chunks,
            bm25_index=bm25_idx,
            mode=get_settings().retrieval.default_mode,
            top_k=bounded_k,
            paper_id=self.paper_id,
            owner_id=self.owner_id,
        )

        self.retrieval_mode = res.retrieval_mode
        self.retrieval_fallback_reason = res.fallback_reason
        if not res.evidence:
            return Observation(
                tool_name="search_evidence",
                content="No relevant passages found for query.",
                tool_call_id=tool_call_id,
                evidence_ids=[],
            )

        lines = [f"Found {len(res.evidence)} evidence passages:"]
        evidence_ids = []
        for ev in res.evidence:
            evidence_ids.append(ev.passage_id)
            lines.append(f"[{ev.passage_id}] in {ev.section_path}:\n\"{ev.text}\"")

        return Observation(
            tool_name="search_evidence",
            content="\n\n".join(lines),
            tool_call_id=tool_call_id,
            evidence_ids=evidence_ids,
            raw_evidence=res.evidence,
        )

    async def read_section(
        self,
        section_id: str,
        offset: int = 0,
        limit: int = 5,
        tool_call_id: Optional[str] = None,
    ) -> Observation:
        """Read sequential paragraphs in a section."""
        offset = max(0, int(offset))
        limit = max(1, min(int(limit), 6))

        conn = get_connection()
        if not self._check_paper_ownership(conn):
            return Observation(
                tool_name="read_section",
                content=f"Error: paper '{self.paper_id}' not found or unauthorized.",
                tool_call_id=tool_call_id,
                evidence_ids=[],
            )
        # Verify section exists in this paper
        s_cursor = conn.execute(
            "SELECT heading, path FROM sections WHERE paper_id = ? AND section_id = ?",
            (self.paper_id, section_id),
        )
        sec_row = s_cursor.fetchone()
        if not sec_row:
            return Observation(
                tool_name="read_section",
                content=f"Error: section_id '{section_id}' not found in this paper.",
                tool_call_id=tool_call_id,
                evidence_ids=[],
            )

        p_cursor = conn.execute(
            """
            SELECT passage_id, parent_passage_id, text, paragraph_order, source_locator, fingerprint
            FROM passages
            WHERE paper_id = ? AND section_id = ?
            ORDER BY paragraph_order ASC, offset_start ASC
            LIMIT ? OFFSET ?
            """,
            (self.paper_id, section_id, limit, offset),
        )
        passages = p_cursor.fetchall()

        if not passages:
            return Observation(
                tool_name="read_section",
                content=f"Section '{sec_row['heading']}' has no further paragraphs at offset {offset}.",
                tool_call_id=tool_call_id,
                evidence_ids=[],
            )

        lines = [f"=== Section: {sec_row['heading']} (Offset {offset}) ==="]
        evidence_ids = []
        raw_evidence: List[EvidenceItem] = []
        for idx, p in enumerate(passages):
            parent_id = p["parent_passage_id"]
            if parent_id not in evidence_ids:
                evidence_ids.append(parent_id)
            lines.append(f"[{parent_id}]: {p['text']}")

            loc_dict = json.loads(p["source_locator"]) if p["source_locator"] else {"element_id": p["passage_id"]}
            raw_evidence.append(
                EvidenceItem(
                    passage_id=parent_id,
                    parent_passage_id=parent_id,
                    rank=idx + 1,
                    score=1.0,
                    section_heading=sec_row["heading"],
                    section_path=sec_row["path"],
                    text=p["text"],
                    locator=SourceLocation(**loc_dict),
                    fingerprint=p["fingerprint"] if "fingerprint" in p.keys() else None,
                    section_id=section_id,
                    paper_id=self.paper_id,
                )
            )

        return Observation(
            tool_name="read_section",
            content="\n\n".join(lines),
            tool_call_id=tool_call_id,
            evidence_ids=evidence_ids,
            raw_evidence=raw_evidence,
        )

    async def search_external_papers(
        self,
        query: str,
        top_k: int = 3,
        tool_call_id: Optional[str] = None,
    ) -> Observation:
        """Search external scholarly literature (arXiv / Semantic Scholar) for relevant research papers."""
        from backend.app.retrieval.scholarly import search_external_scholarly
        if not self._check_paper_ownership(get_connection()):
            return Observation(tool_name="search_external_papers", tool_call_id=tool_call_id,
                               content="Error: paper not found or unauthorized.")
        bounded_k = max(1, min(int(top_k), 5))
        papers = await search_external_scholarly(query, max_results=bounded_k)
        if not papers:
            return Observation(
                tool_name="search_external_papers",
                content="No usable external scholarly sources were returned (no matches, rate limit, or service unavailable). Disclose this limitation; do not invent external papers or claim a completed literature review.",
                tool_call_id=tool_call_id,
                evidence_ids=[],
            )

        raw_evidence: List[EvidenceItem] = []
        lines = [f"Found {len(papers)} external scholarly papers:"]
        evidence_ids = []
        for idx, p in enumerate(papers, start=1):
            ev = p.to_evidence_item(rank=idx)
            raw_evidence.append(ev)
            evidence_ids.append(ev.passage_id)
            authors_str = ", ".join(p.authors[:3]) + (" et al." if len(p.authors) > 3 else "")
            year_str = f" ({p.year})" if p.year else ""
            lines.append(
                f"[{ev.passage_id}] {p.title} - {authors_str}{year_str}\n"
                f"URL: {p.url}\n"
                f"Abstract: {p.abstract}"
            )

        return Observation(
            tool_name="search_external_papers",
            content="\n\n".join(lines),
            tool_call_id=tool_call_id,
            evidence_ids=evidence_ids,
            raw_evidence=raw_evidence,
        )

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        tool_call_id: Optional[str] = None,
    ) -> Observation:
        """Validate and dispatch tool call."""
        from backend.app.core.config import get_settings
        limits = get_settings().limits
        # The configured gateway may attach a planning reason to native calls.
        # It is metadata, not a tool argument; keep operation validation strict.
        if "reason" in arguments:
            if not isinstance(arguments["reason"], str) or len(arguments["reason"]) > limits.max_question_chars:
                return Observation(tool_name=tool_name, tool_call_id=tool_call_id, content="Error: invalid tool arguments")
            arguments = {key: value for key, value in arguments.items() if key != "reason"}
        allowed = {
            "get_paper_outline": set(),
            "search_evidence": {"query", "top_k"},
            "read_section": {"section_id", "offset", "limit"},
            "search_external_papers": {"query", "top_k", "max_results"},
        }
        invalid = tool_name not in allowed or bool(set(arguments) - allowed.get(tool_name, set()))
        for key, low, high in (("top_k", 1, 8), ("max_results", 1, 5), ("offset", 0, 100000), ("limit", 1, 10)):
            if key in arguments and (type(arguments[key]) is not int or not low <= arguments[key] <= high):
                invalid = True
        required = "query" if tool_name in ("search_evidence", "search_external_papers") else "section_id" if tool_name == "read_section" else None
        if required and (not isinstance(arguments.get(required), str) or not arguments[required].strip() or len(arguments[required]) > limits.max_question_chars):
            invalid = True
        if invalid:
            return Observation(tool_name=tool_name, tool_call_id=tool_call_id, content="Error: invalid tool arguments")
        if tool_name == "get_paper_outline":
            return await self.get_paper_outline()
        elif tool_name == "search_evidence":
            query = arguments.get("query", "")
            top_k = arguments.get("top_k", 3)
            return await self.search_evidence(query=query, top_k=top_k, tool_call_id=tool_call_id)
        elif tool_name == "search_external_papers":
            query = arguments.get("query", "")
            top_k = arguments.get("top_k") or arguments.get("max_results") or 3
            return await self.search_external_papers(query=query, top_k=top_k, tool_call_id=tool_call_id)
        elif tool_name == "read_section":
            section_id = arguments.get("section_id", "")
            offset = arguments.get("offset", 0)
            limit = arguments.get("limit", 5)
            return await self.read_section(
                section_id=section_id,
                offset=offset,
                limit=limit,
                tool_call_id=tool_call_id,
            )
        else:
            return Observation(
                tool_name=tool_name,
                content=f"Error: Unknown tool '{tool_name}'. Available tools: get_paper_outline, search_evidence, read_section, search_external_papers.",
                tool_call_id=tool_call_id,
            )


def validate_paper_question(paper_id, owner_id, question, history=None):
    from backend.app.agent.schemas import AgentRunRequest
    from backend.app.cache.paper_store import get_paper_status
    from fastapi import HTTPException
    AgentRunRequest(request_id="validation", paper_id=paper_id, question=question, history=history or [])
    paper = get_paper_status(paper_id, owner_id)
    if not paper:
        raise HTTPException(404, "Paper not found or unauthorized")
    if not paper.lexical_ready:
        raise HTTPException(409, "Paper is not ready")
