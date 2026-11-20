"""Normalize gateway communication for configured model aliases.

Accept messages, actions, and observations in the internal schema.
Convert them to native tool calls or structured-action JSON verified for
each alias.

Normalize tool call IDs, output, finish reasons, usage, and errors
according to docs/llm_gateway_contract.md. Each adapter call is one
provider attempt. model_router.py decides when to switch models.
"""

from typing import Any, Callable, Dict, List, Optional
import json
import re
import httpx
from json_repair import loads as load_repaired_json
from backend.app.core.config import get_settings
from backend.app.agent.schemas import AnswerBlock, ActionCall, MemoryCandidate


def extract_partial_answer_text(raw: str) -> str:
    """Extract incremental text from partially streamed answer_blocks JSON or plain text.

    Never leaks raw JSON structure, tool calls, or reasoning tags to the user.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)

    # Strip any internal reasoning or thought tags
    cleaned = re.sub(r"<reasoning>[\s\S]*?</reasoning>", "", cleaned)
    cleaned = re.sub(r"<thought>[\s\S]*?</thought>", "", cleaned)

    matches = []
    for match in re.finditer(r"\"text\"\s*:\s*\"((?:[^\"\\]|\\.)*)(\"|$)", cleaned):
        escaped_str = match.group(1)
        try:
            decoded = json.loads(f'"{escaped_str}"')
        except Exception:
            decoded = escaped_str.replace("\\n", "\n").replace('\\"', '"')
        if decoded:
            matches.append(decoded)

    if matches:
        return "\n\n".join(matches)

    # If raw content contains JSON structure or tool calls, do NOT leak raw JSON!
    lower = cleaned.lower()
    if (
        cleaned.startswith("{")
        or cleaned.startswith("[")
        or '"answer_blocks"' in lower
        or '"tool_calls"' in lower
        or '"function"' in lower
        or '"arguments"' in lower
    ):
        return ""

    return cleaned


def repair_math_json(raw):
    """Escape odd TeX backslashes inside math, preserving valid JSON escapes."""
    def value(match):
        def math(part):
            return re.sub(r'(?<!\\)((?:\\\\)*)\\(?=[A-Za-z]{2,}|[()\[\]{}_])',
                          lambda slash: slash[1] + '\\\\', part[0])
        text = re.sub(r'\\{1,2}\([\s\S]*?\\{1,2}\)|\\{1,2}\[[\s\S]*?\\{1,2}\]|\$\$[\s\S]*?\$\$|\$[^$]+\$',
                      math, match[1])
        return '"' + text + '"'
    return re.sub(r'"((?:\\.|[^"\\])*)"', value, raw)


def parse_response_content(content):
    cleaned = (content or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        fence = re.search(r'\x60{3}(?:json)?\s*(\{[\s\S]*\})\s*\x60{3}', cleaned)
        if fence:
            cleaned = fence[1]
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as error:
            if error.msg.startswith('Invalid \\escape'):
                cleaned = repair_math_json(cleaned)
            parsed = load_repaired_json(cleaned)
            # Recover complete schema records independently when a prose quote
            # inside one text value would otherwise swallow subsequent fields.
            records = re.findall(r'\{\s*"text"\s*:\s*"([\s\S]*?)"\s*,\s*"evidence_ids"\s*:\s*(\[[\s\S]*?\])\s*\}', cleaned)
            if records and isinstance(parsed, dict):
                blocks = []
                for raw_text, raw_ids in records:
                    quoted = re.sub(r'(?<!\\)((?:\\\\)*)"', lambda match: match[1] + '\\"', raw_text)
                    try:
                        text = json.loads('"' + quoted + '"')
                    except json.JSONDecodeError:
                        text = json.loads(repair_math_json('"' + quoted + '"'))
                    blocks.append({"text": text, "evidence_ids": json.loads(raw_ids)})
                parsed["answer_blocks"] = blocks
                follow = re.search(r'"follow_ups"\s*:\s*(\[[\s\S]*?\])\s*(?:,\s*"limitations"|})', cleaned)
                if follow:
                    parsed["follow_ups"] = load_repaired_json(follow[1])
        if not isinstance(parsed, dict) or not any(key in parsed for key in ("answer_blocks", "research_plan")):
            raise ValueError("Missing structured research response")
        blocks = []
        for raw_block in parsed.get("answer_blocks", []):
            block = AnswerBlock(**raw_block)
            # Decode an extra prose-escaping layer only when doubled TeX marks
            # identify it. Valid single-escaped formulas remain untouched.
            if re.search(r'(?<!\\)\\\\(?:[([]|frac\b|alpha\b|theta\b|sum\b)', block.text):
                escapes = {"\\": "\\", "n": "\n", "r": "\r", "t": "\t", '"': '"'}
                block.text = re.sub(r'\\([\\nrt"])', lambda match: escapes[match[1]], block.text)
            # A provider may double-escape paragraph breaks independently of
            # correctly escaped TeX. Preserve literal code while decoding prose.
            if r"\n\n" in block.text:
                pieces = re.split(r'(```[\s\S]*?```|`[^`]*`)', block.text)
                block.text = "".join(part if part.startswith('`') else part.replace(r"\n", "\n")
                                     for part in pieces)
            blocks.append(block)
        memories = []
        candidates = parsed.get('memory_candidates')
        for item in (candidates if isinstance(candidates, list) else [])[:3]:
            try:
                memories.append(MemoryCandidate.model_validate(item))
            except (ValueError, TypeError):
                continue
        return {
            "answer_blocks": blocks,
            "memory_candidates": memories,
            "research_plan": parsed.get("research_plan"),
            "follow_ups": [q.strip() for q in parsed.get("follow_ups", []) if isinstance(q, str) and 0 < len(q.strip()) <= 240][:3],
            "limitations": parsed.get("limitations") if isinstance(parsed.get("limitations"), str) else None,
        }
    except (ValueError, TypeError, AttributeError):
        raise RuntimeError("Malformed JSON output from research provider")


def message_text(message):
    content = message.get("content") or ""
    return "\n".join(part.get("text", "") for part in content if part.get("type") == "text") if isinstance(content, list) else content


class LLMGateway:
    """Adapter for Gemini, Claude and Qwen through the shared LLM gateway."""

    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_url = api_url if api_url is not None else settings.llm_api_url
        self.api_key = api_key if api_key is not None else settings.llm_api_key

    async def generate_step(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        mock: Optional[bool] = None,
        on_chunk: Optional[Callable[[str, str], Any]] = None,
    ) -> Dict[str, Any]:
        """Send one generation request to the LLM gateway."""
        is_mock = get_settings().mock_providers if mock is None else mock
        raw_url = self.api_url
        target_key = self.api_key

        if not is_mock and not target_key:
            raise RuntimeError(f"API key not configured for live request ({model})")

        if is_mock:
            # Deterministic offline mock response for contract testing
            last_msg = message_text(messages[-1]) if messages else ""
            if messages and "You classify requests for PaperLens" in message_text(messages[0]):
                data = json.loads(last_msg)
                question = data["question"].lower()
                from backend.app.retrieval.hybrid import is_research_extension_query
                scope = "literature" if is_research_extension_query(question) else "paper"
                if any(term in question for term in ("weather", "cook", "pizza", "shopping", "thời tiết", "nấu ăn")):
                    scope = "refuse"
                return {"research_plan": {"scope": scope,
                        "query": data["paper_title"][:200] if scope == "literature" else "",
                        "paper_query": question[:256], "language": "vi" if any(c in question for c in "ừểướếệỏàáôơ") else "en"},
                        "usage": {"input_tokens": 100, "output_tokens": 30}}

            # Check if this is an A2 tool loop where model wants to call search_evidence or search_external_papers
            if tools:
                if any(k in last_msg.lower() for k in ("extension", "promising", "direction", "external")):
                    return {
                        "tool_calls": [
                            ActionCall(
                                tool_name="search_external_papers",
                                arguments={"query": "efficient transformer sparse attention", "top_k": 2},
                                tool_call_id="call_mock_ext",
                            )
                        ],
                        "answer_blocks": [],
                        "finish_reason": "tool_calls",
                        "usage": {"input_tokens": 140, "output_tokens": 35},
                    }
                elif "tool loop" in last_msg.lower():
                    return {
                        "tool_calls": [
                            ActionCall(
                                tool_name="search_evidence",
                                arguments={"query": "transformer self-attention", "top_k": 3},
                                tool_call_id="call_mock_1",
                            )
                        ],
                        "answer_blocks": [],
                        "finish_reason": "tool_calls",
                        "usage": {"input_tokens": 120, "output_tokens": 30},
                    }

            # Final answer generation mock: extract any evidence IDs provided in prompt or prior transcript messages
            full_context = "\n".join(message_text(m) for m in messages)
            eids = [eid for eid in re.findall(r"\[([a-zA-Z0-9_.-]+)\]", full_context) if eid not in ("role", "user", "assistant", "system", "tool") and not eid.endswith("...")]
            cited_ids = [eids[0]] if eids else ["S1.p1"]
            if len(eids) > 1 and any(e.startswith("ext_") for e in eids):
                # Pick one in-paper id and one external id if present
                in_paper = [e for e in eids if not e.startswith("ext_")]
                external = [e for e in eids if e.startswith("ext_")]
                cited_ids = ([in_paper[0]] if in_paper else []) + ([external[0]] if external else [])
            elif len(eids) > 1:
                cited_ids = eids[:2]
            if any(k in last_msg.lower() for k in ("extension", "promising", "direction", "external")):
                mock_text = (
                    "To extend the paper beyond its quadratic attention limitation, a promising research direction "
                    "is integrating sparse locality-sensitive hashing or IO-aware tiling. Concrete implementation "
                    "involves replacing standard softmax attention with block-tiled CUDA kernels, evaluated on "
                    "Long Range Arena benchmarks with compute budget assumptions."
                )
            else:
                mock_text = "The paper introduces the Transformer model relying on self-attention mechanisms without recurrence."

            if on_chunk:
                try:
                    import inspect
                    res = on_chunk(mock_text, mock_text)
                    if inspect.isawaitable(res):
                        await res
                except Exception:
                    pass

            return {
                "tool_calls": [],
                "follow_ups": ["How could this method be evaluated?", "Which assumptions should be tested first?"],
                "answer_blocks": [
                    AnswerBlock(
                        text=mock_text,
                        evidence_ids=cited_ids,
                    )
                ],
                "finish_reason": "stop",
                "usage": {"input_tokens": 250, "output_tokens": 50},
            }

        endpoint = raw_url if raw_url.endswith("/chat/completions") else f"{raw_url.rstrip('/')}/chat/completions"

        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
            headers = {
                "Authorization": f"Bearer {target_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": model,
                "messages": messages,
                "temperature": 0.0,
                "stream": bool(on_chunk and not tools),
                "max_tokens": getattr(self, "max_tokens", get_settings().limits.max_final_answer_tokens),
            }
            if "gemini" in model:
                if model.endswith("-low"):
                    body["reasoning_effort"] = "low"
                elif model.endswith("-high"):
                    body["reasoning_effort"] = "high"
                else:
                    body["reasoning_effort"] = "medium"
            if body["stream"]:
                body["stream_options"] = {"include_usage": True}
            if not tools:
                body["tool_choice"] = "none"
                body["response_format"] = {"type": "json_object"}
            if tools:
                body["tools"] = tools
                body["tool_choice"] = "auto"

            if on_chunk and not tools:
                # Streaming mode for final answer synthesis
                accumulated_content: List[str] = []
                finish_reason = "stop"
                prompt_tokens = 0
                completion_tokens = 0

                async with client.stream("POST", endpoint, json=body, headers=headers) as stream_res:
                    stream_res.raise_for_status()
                    async for line in stream_res.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            if "usage" in chunk and chunk["usage"]:
                                prompt_tokens = chunk["usage"].get("prompt_tokens", prompt_tokens)
                                completion_tokens = chunk["usage"].get("completion_tokens", completion_tokens)
                            choice = (chunk.get("choices") or [{}])[0]
                            delta = choice.get("delta", {})
                            content_delta = delta.get("content", "")
                            if choice.get("finish_reason"):
                                finish_reason = choice["finish_reason"]
                            if "usage" in chunk and chunk["usage"]:
                                prompt_tokens = chunk["usage"].get("prompt_tokens", prompt_tokens)
                                completion_tokens = chunk["usage"].get("completion_tokens", completion_tokens)
                            if content_delta:
                                accumulated_content.append(content_delta)
                                full_raw = "".join(accumulated_content)
                                partial_text = extract_partial_answer_text(full_raw)
                                import inspect
                                res = on_chunk(content_delta, partial_text)
                                if inspect.isawaitable(res):
                                    await res
                        except Exception:
                            continue

                if finish_reason in {"length", "max_tokens"}:
                    raise RuntimeError("Token budget exhausted: truncated provider output")

                content = "".join(accumulated_content)
                parsed = parse_response_content(content)

                return {
                    "tool_calls": [],
                    **parsed,
                    "finish_reason": finish_reason,
                    "usage": {
                        "input_tokens": prompt_tokens,
                        "output_tokens": completion_tokens or len(content.split()),
                    },
                }

            res = await client.post(endpoint, json=body, headers=headers)
            res.raise_for_status()
            data = res.json()
            choice = data["choices"][0]
            finish_reason = choice.get("finish_reason", "stop")
            if finish_reason in {"length", "max_tokens"}:
                raise RuntimeError("Token budget exhausted: truncated provider output")
            message = choice.get("message", {})

            tool_calls = []
            if "tool_calls" in message and message["tool_calls"]:
                for tc in message["tool_calls"]:
                    fn = tc.get("function", {})
                    args = json.loads(fn.get("arguments", "{}"))
                    tool_calls.append(
                        ActionCall(
                            tool_name=fn.get("name", ""),
                            arguments=args,
                            tool_call_id=tc.get("id"),
                        )
                    )

            # Native tool calls may include a plain-language planning preface.
            # It is not the final JSON answer and must not invalidate the calls.
            parsed = parse_response_content(message.get("content")) if message.get("content") and not tool_calls else {"answer_blocks": [], "follow_ups": []}

            usage = {
                "input_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                "output_tokens": data.get("usage", {}).get("completion_tokens", 0),
            }
            return {
                **parsed,
                "tool_calls": tool_calls,
                "finish_reason": finish_reason,
                "usage": usage,
            }
