"""Coordinate the A2 loop for one question about a paper.

Accept a question, valid history, and a loaded paper. Ask the model
router for an action or answer, validate each action before dispatch,
and add verified observations to the evidence registry.

Enforce the configured step, tool call, search, token, and time limits
across the turn. Block duplicate actions, reserve the last step for the
answer, and check for cancellation between steps.

Return a validated answer, partial, or evidence_only based on the
available evidence and stop reason.
"""

from datetime import datetime, timezone
import json
import time
from typing import Any, Dict, List, Optional
from backend.app.core.config import get_settings
from backend.app.core.schemas import EvidenceItem
from backend.app.cache.paper_store import (
    get_paper_chunks,
    get_bm25_index,
)
from backend.app.agent.schemas import (
    AgentResult,
    RunState,
    AnswerBlock,
    ActionCall,
    Observation,
)
from backend.app.agent.prompts import SYSTEM_PROMPT, format_evidence_context
from backend.app.agent.citations import EvidenceRegistry, validate_answer_citations
from backend.app.agent.tools import PaperAgentTools, AGENT_TOOLS_SCHEMA
from backend.app.agent.model_router import ModelRouter, normalize_provider_error, generate_bounded
from backend.app.agent.citations import answer_status
import asyncio
from backend.app.providers.llm_gateway import LLMGateway


async def run_bounded_agent(
    run_id: str,
    paper_id: str,
    owner_id: str,
    question: str,
    history: Optional[List[Dict[str, Any]]] = None,
    router: Optional[ModelRouter] = None,
    gateway: Optional[LLMGateway] = None,
    max_steps: Optional[int] = None,
    max_searches: Optional[int] = None,
    max_tool_calls: Optional[int] = None,
    turn_timeout_seconds: Optional[float] = None,
    on_event: Optional[Any] = None,
    external_query: Optional[str] = None,
    allow_external: bool = True,
    images=None,
    image_notes=None,
    image_pixels: bool = True,
    paper_query: Optional[str] = None,
    personal_sources=None,
) -> AgentResult:
    """Coordinate the bounded A2 agent loop with strict turn and tool caps."""
    from backend.app.agent.tools import validate_paper_question
    validate_paper_question(paper_id, owner_id, question, history)
    settings = get_settings()
    max_steps = min(max_steps if max_steps is not None else settings.limits.max_llm_steps, settings.limits.max_llm_steps)
    max_searches = min(max_searches if max_searches is not None else settings.limits.max_searches, settings.limits.max_searches)
    max_tool_calls = min(max_tool_calls if max_tool_calls is not None else settings.limits.max_tool_calls, settings.limits.max_tool_calls)
    turn_timeout_seconds = min(turn_timeout_seconds if turn_timeout_seconds is not None else settings.limits.turn_timeout_seconds, settings.limits.turn_timeout_seconds)
    router = router or ModelRouter()
    gateway = gateway or LLMGateway()
    tools = PaperAgentTools(paper_id=paper_id, owner_id=owner_id)
    registry = EvidenceRegistry()
    for source in personal_sources or []:
        registry.register_passage(source.passage_id,source.text,source.locator,source.section_heading,source.section_path,
                                  source.score,source.rank,source.fingerprint,source.section_id,source.paper_id)
    from backend.app.agent.schemas import multimodal_content
    images = images or []
    for i, image in enumerate(images, 1):
        registry.register_passage(f"img_{i}", image_notes[i-1] if image_notes else f"User-supplied research image: {image.name}. Read the attached visual directly; this label is not a transcription.",
                                  section_heading=image.name, section_path="User image")
    from backend.app.retrieval.hybrid import is_overview_query, is_research_extension_query
    is_extension_q = allow_external and (bool(external_query) or is_research_extension_query(question))

    start_time = time.monotonic()
    search_count = 0
    tool_call_count = 0
    executed_actions: set = set()

    # Initialize transcript
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    # Include the bounded, relevant conversation history selected for this turn.
    if history:
        for turn in history[-settings.limits.max_history_turns * 2:]:
            if "role" in turn and "content" in turn:
                messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({
        "role": "user",
        "content": f"Question: {question}\n\nYou may use tools to find evidence in the paper, or answer directly if you already have sufficient evidence."
    })
    if personal_sources:
        messages[-1]['content'] += '\n\n' + format_evidence_context(personal_sources)

    if history:
        user_context = "\n".join(turn["content"] for turn in history if turn["role"] == "user")
        if user_context:
            source = registry.register_passage("chat_context", "Earlier user-provided research context (not paper findings):\n" + user_context,
                                               section_heading="Earlier research settings", section_path="Conversation context")
            messages[-1]["content"] += "\n\n" + format_evidence_context([source])

    # Product technical questions get section IDs before planning, leaving model
    # steps for reading the method and experiments instead of discovering IDs.
    if paper_query and not images and not is_extension_q and not is_overview_query(question) and max_tool_calls > 1:
        tool_call_count += 1
        outline = await tools.get_paper_outline()
        executed_actions.add(("get_paper_outline", "{}"))
        messages[-1]["content"] += ("\n\n" + outline.content +
            "\nSection IDs are navigation metadata, not factual evidence. The outline is already available; "
            "read the relevant sections directly, preferably in the same tool step when several are needed.")
        if on_event:
            on_event({"type": "tool_call", "tool_name": "get_paper_outline", "arguments": {}})
            on_event({"type": "tool_result", "tool_name": "get_paper_outline", "summary": "Paper section directory loaded"})

    if max_searches > 0 and max_tool_calls > 0 and settings.limits.max_parent_evidence > 0:
        retrieval_query = paper_query or question
        if history:
            context = " ".join(t["content"] for t in history[-2:] if t["role"] == "user")
            remaining_chars = settings.limits.max_question_chars - len(question) - 10
            if remaining_chars > 0:
                retrieval_query += "\nContext: " + context[:min(384, remaining_chars)]
        if on_event:
            on_event({
                "type": "activity",
                "state": "searching_paper",
                "message": "Searching the paper...",
            })
            on_event({
                "type": "tool_call",
                "tool_name": "search_evidence",
                "arguments": {"query": retrieval_query, "top_k": min(settings.retrieval.product_top_k, max(1, settings.limits.max_parent_evidence - len(images)), 8)},
            })
        search_count += 1
        tool_call_count += 1
        try:
            initial = await asyncio.wait_for(
                tools.execute_tool("search_evidence", {"query": retrieval_query, "top_k": min(settings.retrieval.product_top_k, max(1, settings.limits.max_parent_evidence - len(images)), 8)}),
                max(0.001, turn_timeout_seconds - (time.monotonic() - start_time)),
            )
            for ev in initial.raw_evidence:
                registry.register_passage(ev.passage_id, ev.text, ev.locator, ev.section_heading, ev.section_path,
                                          ev.score, ev.rank, ev.fingerprint, ev.section_id, ev.paper_id)
            if initial.raw_evidence:
                messages[-1]["content"] += "\n\n" + format_evidence_context(initial.raw_evidence)
            if on_event:
                on_event({
                    "type": "tool_result",
                    "tool_name": "search_evidence",
                    "summary": f"Found {len(initial.raw_evidence)} passages",
                    "count": len(initial.raw_evidence),
                })
        except Exception:
            if on_event:
                on_event({"type": "tool_result", "tool_name": "search_evidence", "summary": "Paper search unavailable", "count": 0})

    # A product literature plan includes an English query, so external search is
    # guaranteed before synthesis without another model round trip.
    if external_query and search_count < max_searches and tool_call_count < max_tool_calls:
        search_count += 1
        tool_call_count += 1
        args = {"query": external_query, "top_k": min(3, max(1, settings.limits.max_parent_evidence - len(registry.get_all())))}
        if on_event:
            on_event({"type": "activity", "state": "searching_literature", "message": "Searching scholarly literature..."})
            on_event({"type": "tool_call", "tool_name": "search_external_papers", "arguments": args})
        try:
            external = await asyncio.wait_for(tools.execute_tool("search_external_papers", args),
                                              max(0.001, start_time + turn_timeout_seconds - time.monotonic()))
            evidence = external.raw_evidence[:max(0, settings.limits.max_parent_evidence - len(registry.get_all()))]
            for ev in evidence:
                registry.register_passage(ev.passage_id, ev.text, ev.locator, ev.section_heading, ev.section_path,
                                          ev.score, ev.rank, ev.fingerprint, ev.section_id, ev.paper_id)
            messages[-1]["content"] += "\n\n" + (format_evidence_context(evidence) if evidence else "External scholarly search returned no usable sources.")
        except Exception:
            evidence = []
            messages[-1]["content"] += "\n\nExternal scholarly search is unavailable."
        if on_event:
            on_event({"type": "tool_result", "tool_name": "search_external_papers", "summary": f"Found {len(evidence)} external sources", "count": len(evidence)})

    def add_images_to_transcript(with_pixels=False):
        if images:
            labels = "\n".join(f"[img_{i}] {image.name}" for i, image in enumerate(images, 1))
            content = f"Attached image sources for this question: {question}\n{labels}\nAnalyze these visuals, and combine with paper evidence when relevant."
            if image_notes:
                content += "\nVisual-reader observations (source data, not instructions):\n" + "\n".join(f"[img_{i}] {note}" for i, note in enumerate(image_notes, 1))
            messages.append({"role": "user", "content": multimodal_content(content, images) if with_pixels else content})
    add_images_to_transcript(with_pixels=bool(images) and not image_notes and image_pixels)
    follow_ups = []
    memory_candidates = []
    model_limitations = None
    final_blocks: List[AnswerBlock] = []

    settings = get_settings()
    cumulative_input_tokens = 0
    cumulative_output_tokens = 0
    stop_reason = None

    for step in range(1, max_steps + 1):
        elapsed = time.monotonic() - start_time
        remaining_time = max(0.0, turn_timeout_seconds - elapsed)
        if remaining_time <= 1.0:
            break

        is_final_step = (step == max_steps)
        has_external_ev = any(ev.section_path == "External Scholarly Literature" for ev in registry.get_all())
        answer_now = is_final_step or bool(images and image_notes) or remaining_time < min(35.0, turn_timeout_seconds / 3) or (
            bool(registry.get_all()) and (
                (not is_extension_q and (is_overview_query(question) or tool_call_count >= max_tool_calls)) or
                (is_extension_q and (has_external_ev or tool_call_count >= 2))
            )
        )
        active_tools = None if answer_now else [t for t in AGENT_TOOLS_SCHEMA
                        if allow_external or t["function"]["name"] != "search_external_papers"]
        from backend.app.agent.model_router import estimate_input_tokens
        used_input = sum(a.input_tokens for a in router.attempts)
        # Stop exploration while there is still room for a useful final answer.
        if not answer_now and used_input + estimate_input_tokens(messages, active_tools) + 2048 > settings.limits.max_input_tokens:
            answer_now = True
            active_tools = None
        if answer_now and images and image_pixels and not any(isinstance(m.get('content'), list) for m in messages):
            add_images_to_transcript(with_pixels=True)
        from backend.app.agent.complexity import determine_question_complexity
        complexity = determine_question_complexity(question)

        if answer_now:
            guidance_msg = (
                f"\n\n[Định mức output token & Hướng dẫn phân tích ({complexity.label})]:\n"
                f"- Mục tiêu độ dài: {complexity.target_tokens_min}–{complexity.target_tokens_max} tokens.\n"
                f"- {complexity.synthesis_guidance}\n"
                f"- Trích xuất đúng đoạn văn, bảng, công thức liên quan và trích dẫn rõ section/page."
            )
            if is_extension_q:
                messages.append({
                    "role": "user",
                    "content": (
                        f"Using the evidence above (both from the paper and external literature), return the answer_blocks JSON now. "
                        f"When discussing, comparing, or recommending another paper, you MUST attach the exact link to that paper as a Markdown link [Paper Title](exact_url) using the URL provided in the external evidence, and cite its external evidence ID (e.g. ext_paper_id). "
                        f"Compare related approaches and propose concrete, technically motivated research or engineering directions. "
                        f"Explain how each extends or relates to the paper, required implementation changes, evaluation plan, assumptions, resources, and uncertainties. "
                        f"Label proposed directions as hypotheses, never proven results or verified novelty. If external search failed, disclose this and use only paper-grounded hypotheses. "
                        f"{guidance_msg} "
                        f"Do not call tools. Match the language of this question: {question}"
                    )
                })
            else:
                messages.append({
                    "role": "user",
                    "content": (
                        f"Using the evidence above, return the answer_blocks JSON now. "
                        f"{guidance_msg} "
                        f"Do not call tools. Match the language of this question: {question}"
                    )
                })

        # Keep room for synthesis after tool observations. Compress only when the
        # conservative byte bound would otherwise reject a final answer request.
        used_input = sum(a.input_tokens for a in router.attempts)
        from backend.app.agent.model_router import estimate_input_tokens
        estimated = estimate_input_tokens(messages, active_tools)
        input_room = min(settings.limits.max_input_tokens - used_input,
                         router.token_budget - sum(a.input_tokens + a.output_tokens for a in router.attempts) - 1024)
        if answer_now and estimated > input_room:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            for turn in (history or [])[-settings.limits.max_history_turns * 2:]:
                messages.append({"role": turn["role"], "content": turn["content"][:384]})
            messages.append({"role": "user", "content": f"Answer in the language of this question: {question}\nReturn a developed, source-grounded answer_blocks JSON.\n"})
            # Reserve the vision payload BEFORE allocating space to paper passages.
            add_images_to_transcript(with_pixels=bool(images) and image_pixels)
            remaining = input_room - estimate_input_tokens(messages) - 256
            evidence = registry.get_all()
            allowance = max(0, remaining // max(1, len(evidence)) - 100)
            for ev in evidence:
                snippet = ev.text.encode()[:allowance].decode("utf-8", errors="ignore")
                if snippet:
                    messages.append({"role":"user", "content":f"[{ev.passage_id}] ({ev.section_path}) {snippet}"})

        if answer_now and on_event:
            on_event({
                "type": "activity",
                "state": "writing_answer",
                "message": "Writing an answer...",
            })

        async def _on_chunk_cb(delta: str, partial_text: str):
            if on_event and answer_now and partial_text:
                on_event({
                    "type": "delta",
                    "delta": delta,
                    "text": partial_text,
                })

        # Generate step action or answer
        try:
            step_res = await generate_bounded(
                router,
                gateway,
                messages,
                active_tools,
                start_time + turn_timeout_seconds,
                on_chunk=_on_chunk_cb if answer_now else None,
                output_token_cap=complexity.max_output_tokens if answer_now else None,
            )
        except Exception as err:
            stop_reason = normalize_provider_error(err)
            break
        active_model = router.get_active_model()

        in_tok = step_res.get("usage", {}).get("input_tokens", 0)
        out_tok = step_res.get("usage", {}).get("output_tokens", 0)
        cumulative_input_tokens += in_tok
        cumulative_output_tokens += out_tok

        try:
            from backend.app.telemetry.usage import record_usage
            record_usage(
                owner_id=owner_id,
                run_id=run_id,
                operation="agent_step",
                provider="fpt" if "qwen" in active_model.lower() else ("gemini" if "gemini" in active_model else "anthropic"),
                model=active_model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                status="success",
            )
        except Exception:
            pass

        tool_calls: List[ActionCall] = step_res.get("tool_calls", [])
        answer_blocks: List[AnswerBlock] = step_res.get("answer_blocks", [])

        # If token budget exceeded or model returned answer blocks or final step, exit
        budget_exceeded = (
            cumulative_input_tokens >= settings.limits.max_input_tokens or
            cumulative_output_tokens >= settings.limits.max_output_tokens
        )

        if (answer_blocks or is_final_step or budget_exceeded) and not tool_calls:
            final_blocks = answer_blocks
            follow_ups = step_res.get("follow_ups", [])
            memory_candidates = step_res.get('memory_candidates', [])
            model_limitations = step_res.get("limitations")
            break

        # Execute tool calls
        if tool_calls:
            for i, tc in enumerate(tool_calls):
                tc.tool_call_id = tc.tool_call_id or f"call_{step}_{i}"
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc.tool_call_id or f"call_{i+1}",
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for i, tc in enumerate(tool_calls)
                ],
            })
            for tc in tool_calls:
                if tc.tool_name == "search_evidence":
                    state_name = "searching_paper"
                    msg_desc = "Searching the paper..."
                elif tc.tool_name == "search_external_papers":
                    state_name = "searching_literature"
                    msg_desc = "Searching external scholarly literature..."
                else:
                    state_name = "reading_sources"
                    msg_desc = f"Reading {tc.tool_name.replace('_', ' ')}..."
                if on_event:
                    on_event({
                        "type": "activity",
                        "state": state_name,
                        "message": msg_desc,
                    })
                    on_event({
                        "type": "tool_call",
                        "tool_name": tc.tool_name,
                        "arguments": tc.arguments,
                    })
                action_key = (tc.tool_name, json.dumps({k: v for k, v in tc.arguments.items() if k != "reason"}, sort_keys=True))
                rejection = None
                if answer_now or budget_exceeded or tool_call_count >= max_tool_calls:
                    rejection = "Tool budget exhausted"
                elif tc.tool_name == "search_external_papers" and not allow_external:
                    rejection = "External search is outside this paper-only research plan"
                elif tc.tool_name in ("search_evidence", "search_external_papers") and search_count >= max_searches:
                    rejection = "Search budget exhausted"
                elif action_key in executed_actions:
                    rejection = "Duplicate action rejected"
                if rejection:
                    obs = Observation(tool_name=tc.tool_name, content=rejection)
                else:
                    executed_actions.add(action_key)
                    tool_call_count += 1
                    if tc.tool_name in ("search_evidence", "search_external_papers"):
                        search_count += 1
                    try:
                        obs = await asyncio.wait_for(tools.execute_tool(tc.tool_name, tc.arguments, tc.tool_call_id),
                                                     max(0.001, start_time + turn_timeout_seconds - time.monotonic()))
                    except Exception:
                        obs = Observation(tool_name=tc.tool_name, content="Tool failed or deadline exceeded")
                if on_event:
                    summary = f"Found {len(obs.raw_evidence)} passages" if obs.raw_evidence else (obs.content[:80] if obs.content else "Done")
                    on_event({
                        "type": "tool_result",
                        "tool_name": tc.tool_name,
                        "summary": summary,
                        "count": len(obs.raw_evidence) if obs.raw_evidence else 0,
                    })
                # Only expose and register evidence within the total run allowance.
                if obs.raw_evidence:
                    available = settings.limits.max_parent_evidence - len(registry.get_all())
                    obs.raw_evidence = [ev for ev in obs.raw_evidence if not registry.has_passage(ev.passage_id)][:max(0, available)]
                    obs.content = "\n\n".join(f"[{ev.passage_id}] {ev.text}" for ev in obs.raw_evidence) or "Evidence limit reached"

                # Register any newly discovered evidence into active run registry
                if obs.raw_evidence:
                    for ev in obs.raw_evidence:
                        registry.register_passage(
                            passage_id=ev.passage_id,
                            text=ev.text,
                            locator=ev.locator,
                            section_heading=ev.section_heading,
                            section_path=ev.section_path,
                            score=ev.score,
                            fingerprint=ev.fingerprint,
                            section_id=ev.section_id,
                            paper_id=ev.paper_id,
                        )

                # Append tool observation to transcript
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.tool_call_id or f"call_{tool_call_count}",
                    "content": obs.content,
                })

    registered_evidence = registry.get_all()
    status, sanitized_blocks, limitations = answer_status(final_blocks, registry)
    if model_limitations:
        limitations = " ".join(filter(None, [limitations, model_limitations]))
    if not final_blocks and stop_reason:
        limitations = f"No answer was generated ({stop_reason}). Please retry in a new chat or use a smaller image crop; your source passages are still available."
    if is_extension_q and not any(ev.section_path == "External Scholarly Literature" for ev in registered_evidence):
        limitations = ((limitations + " ") if limitations else "") + "External scholarly sources could not be retrieved; proposed directions are hypotheses based on the current paper, not a verified literature or novelty review."
        if status == RunState.COMPLETED:
            status = RunState.PARTIAL

    # Guarantee: attach exact paper links for external literature or other papers
    for block in sanitized_blocks:
        for eid in block.evidence_ids:
            ev = registry.get_passage(eid)
            if ev and ev.locator and ev.locator.xpath and ev.locator.xpath.startswith("http"):
                paper_url = ev.locator.xpath
                if paper_url not in block.text:
                    title = ev.section_heading.replace("External Paper: ", "").strip() or "Paper"
                    block.text = f"{block.text.rstrip()}\n\n🔗 [{title}]({paper_url})"

    if is_extension_q and sanitized_blocks:
        ext_passages = [ev for ev in registered_evidence if ev.passage_id.startswith("ext_") and ev.locator and ev.locator.xpath and ev.locator.xpath.startswith("http")]
        if ext_passages:
            # If no block has linked an external paper yet, attach the external paper links to the last block
            if not any(any(ev.locator.xpath in b.text for ev in ext_passages) for b in sanitized_blocks):
                links_text = "\n\n**External Paper Links:**\n" + "\n".join(
                    f"- [{ev.section_heading.replace('External Paper: ', '').strip()}]({ev.locator.xpath}) [{ev.passage_id}]"
                    for ev in ext_passages[:3]
                )
                sanitized_blocks[-1].text += links_text
                for ev in ext_passages[:3]:
                    if ev.passage_id not in sanitized_blocks[-1].evidence_ids:
                        sanitized_blocks[-1].evidence_ids.append(ev.passage_id)

    return AgentResult(
        run_id=run_id,
        paper_id=paper_id,
        status=status,
        answer_blocks=sanitized_blocks,
        follow_ups=follow_ups,
        memory_candidates=memory_candidates,
        emitted_citation_ids=[eid for b in final_blocks for eid in b.evidence_ids],
        evidence=registered_evidence,
        serving_model=router.get_active_model(),
        fallback_reason="Claude failover applied" if router.fallback_count > 0 else None,
        limitations=limitations,
        retrieval_mode=tools.retrieval_mode,
        retrieval_fallback_reason=tools.retrieval_fallback_reason,
    )
