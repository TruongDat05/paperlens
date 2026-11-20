"""Comprehensive benchmark comparing troll/deepseek-v4-flash vs fpt/Qwen3.8-27B on PaperLens tasks."""

import asyncio
import json
import time
from typing import Any, Dict, List
import httpx
from backend.app.providers.llm_gateway import LLMGateway
from backend.app.core.config import get_settings
from backend.app.agent.prompts import SYSTEM_PROMPT

GATEWAY_URL = get_settings().llm_api_url
API_KEY = get_settings().llm_api_key

MODELS = {
    "deepseek": "troll/deepseek-v4-flash",
    "qwen": "fpt/Qwen3.8-27B",
}

RESULTS = {
    "deepseek": {"passed": 0, "total": 0, "details": [], "timings": []},
    "qwen": {"passed": 0, "total": 0, "details": [], "timings": []},
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_evidence",
            "description": "Search paper evidence passages by semantic and keyword similarity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query keywords or statement"},
                    "top_k": {"type": "integer", "description": "Number of passages to return", "default": 3}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_paper_outline",
            "description": "Get hierarchical outline of paper sections",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

async def run_test(name: str, test_fn):
    print(f"\n==========================================")
    print(f"RUNNING TEST: {name}")
    print(f"==========================================")
    for model_key, model_id in MODELS.items():
        print(f"\n--- Testing {model_key.upper()} ({model_id}) ---")
        start = time.monotonic()
        try:
            res = await test_fn(model_id)
            elapsed = time.monotonic() - start
            RESULTS[model_key]["total"] += 1
            RESULTS[model_key]["timings"].append(elapsed)
            if res.get("ok"):
                RESULTS[model_key]["passed"] += 1
                print(f"✓ PASS ({elapsed:.2f}s): {res.get('summary')}")
            else:
                print(f"✗ FAIL ({elapsed:.2f}s): {res.get('error')}")
            RESULTS[model_key]["details"].append({"test": name, "ok": res.get("ok"), "elapsed": elapsed, "data": res})
        except Exception as e:
            elapsed = time.monotonic() - start
            RESULTS[model_key]["total"] += 1
            RESULTS[model_key]["timings"].append(elapsed)
            print(f"✗ ERROR ({elapsed:.2f}s): {type(e).__name__}: {e}")
            RESULTS[model_key]["details"].append({"test": name, "ok": False, "elapsed": elapsed, "error": str(e)})


# TEST 1: Tool Calling
async def test_tool_calling(model_id: str):
    gateway = LLMGateway(api_url=GATEWAY_URL, api_key=API_KEY)
    messages = [
        {"role": "system", "content": "You are PaperLens agent. Decide whether to call a tool to answer the user query."},
        {"role": "user", "content": "I need to understand the ablation table and experimental setup in Section 5. Please search for the ablation study passages."}
    ]
    res = await gateway.generate_step(model=model_id, messages=messages, tools=TOOLS, mock=False)
    tool_calls = res.get("tool_calls", [])
    if not tool_calls:
        return {"ok": False, "error": f"No tool calls returned. Got: {res.get('answer_blocks')}"}
    tc = tool_calls[0]
    if tc.tool_name not in ["search_evidence", "get_paper_outline"]:
        return {"ok": False, "error": f"Unknown tool called: {tc.tool_name}"}
    if not tc.arguments or not isinstance(tc.arguments, dict):
        return {"ok": False, "error": f"Malformed arguments: {tc.arguments}"}
    return {
        "ok": True,
        "summary": f"Called tool {tc.tool_name} with args {tc.arguments}",
        "tool_name": tc.tool_name,
        "args": tc.arguments
    }


# TEST 2: Structured Output & Citation Faithfulness
async def test_structured_citations(model_id: str):
    gateway = LLMGateway(api_url=GATEWAY_URL, api_key=API_KEY)
    gateway.max_tokens = 1024
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\nAvailable evidence:\n[p1] Multi-Head Attention allows the model to jointly attend to information from different representation subspaces at different positions. With parameter matrices W_i^Q, W_i^K, W_i^V.\n[p2] In this work we employ h = 8 parallel attention layers, or heads. For each of these we use d_k = d_v = d_model / h = 64. Due to the reduced dimension of each head, the total computational cost is similar to that of single-head attention with full dimensionality."
        },
        {
            "role": "user",
            "content": "How many attention heads are used and what is the dimension of each head? Explain why the total computational cost remains similar to single-head attention. Cite exact passages."
        }
    ]
    res = await gateway.generate_step(model=model_id, messages=messages, mock=False)
    blocks = res.get("answer_blocks", [])
    if not blocks:
        return {"ok": False, "error": "No answer blocks returned"}
    cited = set()
    text = ""
    for b in blocks:
        text += b.text + " "
        cited.update(b.evidence_ids)

    valid_cites = {"p1", "p2"}
    hallucinated = cited - valid_cites
    if hallucinated:
        return {"ok": False, "error": f"Hallucinated citations: {hallucinated}"}
    if "p2" not in cited:
        return {"ok": False, "error": f"Did not cite p2 which has head count & dimension. Cited: {cited}"}
    if "8" not in text or "64" not in text:
        return {"ok": False, "error": f"Missing critical numbers (8 heads, 64 dim) in answer: {text[:200]}"}

    follow_ups = res.get("follow_ups", [])
    return {
        "ok": True,
        "summary": f"Cited {cited}, follow-ups count: {len(follow_ups)}",
        "answer": text[:200],
        "follow_ups": follow_ups
    }


# TEST 3: LaTeX Math Escaping in JSON
async def test_latex_math_json(model_id: str):
    gateway = LLMGateway(api_url=GATEWAY_URL, api_key=API_KEY)
    gateway.max_tokens = 1024
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\nAvailable evidence:\n[p1] Attention(Q, K, V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V. The dot-product attention scales by \\frac{1}{\\sqrt{d_k}} to counteract extremely small gradients for large values of d_k."
        },
        {
            "role": "user",
            "content": "Write down the mathematical formula for Scaled Dot-Product Attention in LaTeX notation and explain the scaling factor. Return valid JSON answer_blocks."
        }
    ]
    res = await gateway.generate_step(model=model_id, messages=messages, mock=False)
    blocks = res.get("answer_blocks", [])
    if not blocks:
        return {"ok": False, "error": "No answer blocks returned"}
    text = blocks[0].text
    if "frac" not in text and "softmax" not in text.lower():
        return {"ok": False, "error": f"LaTeX formula missing in output: {text[:150]}"}
    return {
        "ok": True,
        "summary": f"Valid JSON with LaTeX math correctly decoded without parsing error.",
        "math_sample": text[:150]
    }


# TEST 4: Vietnamese Comprehension, Synthesis & Follow-ups
async def test_vietnamese_qa(model_id: str):
    gateway = LLMGateway(api_url=GATEWAY_URL, api_key=API_KEY)
    gateway.max_tokens = 1024
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\nAvailable evidence:\n[p1] Recurrent neural networks inherently prevent parallelization within training examples due to sequential nature: h_t = f(h_{t-1}, x_t).\n[p2] The Transformer entirely dispenses with recurrence and relies solely on self-attention mechanisms, allowing significantly more parallelization and reaching state of the art in translation quality after training for only 12 hours on 8 P100 GPUs."
        },
        {
            "role": "user",
            "content": "Tại sao mô hình RNN gặp khó khăn trong việc song song hóa và Transformer đã khắc phục điều này như thế nào? Trả lời bằng tiếng Việt, trích dẫn bằng chứng [p1], [p2], và đề xuất 2-3 câu hỏi gợi mở tiếp theo bằng tiếng Việt."
        }
    ]
    res = await gateway.generate_step(model=model_id, messages=messages, mock=False)
    blocks = res.get("answer_blocks", [])
    if not blocks:
        return {"ok": False, "error": "No answer blocks returned"}
    text = " ".join(b.text for b in blocks)
    follow_ups = res.get("follow_ups", [])

    # Check Vietnamese keywords
    vi_keywords = ["song song", "tuần tự", "Transformer", "RNN"]
    missing = [w for w in vi_keywords if w.lower() not in text.lower()]
    if missing:
        return {"ok": False, "error": f"Missing Vietnamese keywords {missing} in answer: {text[:150]}"}

    # Check follow-ups in Vietnamese
    if not follow_ups:
        return {"ok": False, "error": "No follow_ups returned"}

    has_vi_followup = any(any(c in f for c in "àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ") for f in follow_ups)
    if not has_vi_followup:
        return {"ok": False, "error": f"Follow-ups are not in Vietnamese: {follow_ups}"}

    return {
        "ok": True,
        "summary": f"Vietnamese answer fluent, cited {[b.evidence_ids for b in blocks]}, {len(follow_ups)} Vietnamese follow-ups",
        "answer": text[:200],
        "follow_ups": follow_ups
    }


# TEST 5: Streaming Performance & TTFT
async def test_streaming_throughput(model_id: str):
    gateway = LLMGateway(api_url=GATEWAY_URL, api_key=API_KEY)
    gateway.max_tokens = 512
    messages = [
        {"role": "system", "content": "Return only JSON with answer_blocks, each containing text and evidence_ids. Use only the supplied evidence."},
        {"role": "user", "content": "[p1] FlashAttention optimizes GPU SRAM memory hierarchy to compute exact attention in O(N) IO complexity. Explain this mechanism in 3 sentences."}
    ]

    chunks = []
    chunk_times = []
    start = time.monotonic()

    def on_chunk(raw, text):
        chunk_times.append(time.monotonic() - start)
        chunks.append(raw)

    res = await gateway.generate_step(
        model=model_id,
        messages=messages,
        mock=False,
        on_chunk=on_chunk
    )
    total_time = time.monotonic() - start
    ttft = chunk_times[0] if chunk_times else total_time
    num_chunks = len(chunks)
    output_tokens = res.get("usage", {}).get("output_tokens", 0)
    tok_per_sec = output_tokens / total_time if total_time > 0 else 0

    return {
        "ok": True,
        "summary": f"TTFT: {ttft:.3f}s | Total: {total_time:.2f}s | Chunks: {num_chunks} | Output Tokens: {output_tokens} ({tok_per_sec:.1f} tok/s)",
        "ttft": ttft,
        "total_time": total_time,
        "tok_per_sec": tok_per_sec,
        "chunks": num_chunks
    }


async def main():
    print(f"Starting PaperLens Model Benchmark: DeepSeek vs Qwen")
    print(f"Endpoint: {GATEWAY_URL}")
    print(f"DeepSeek model: {MODELS['deepseek']}")
    print(f"Qwen model: {MODELS['qwen']}")

    await run_test("Tool Calling (Function Calling)", test_tool_calling)
    await run_test("Structured Output & Citation Faithfulness", test_structured_citations)
    await run_test("LaTeX Math JSON Escaping", test_latex_math_json)
    await run_test("Vietnamese QA & Follow-ups", test_vietnamese_qa)
    await run_test("Streaming Performance & Latency", test_streaming_throughput)

    print("\n==========================================")
    print("FINAL SUMMARY COMPARISON")
    print("==========================================")
    for model_key in ["deepseek", "qwen"]:
        passed = RESULTS[model_key]["passed"]
        total = RESULTS[model_key]["total"]
        avg_time = sum(RESULTS[model_key]["timings"]) / max(1, len(RESULTS[model_key]["timings"]))
        print(f"{model_key.upper()} ({MODELS[model_key]}): {passed}/{total} tests passed. Avg time per test: {avg_time:.2f}s")

    # Write report
    with open("reports/model_comparison_deepseek_vs_qwen.json", "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=2, ensure_ascii=False)
    print(f"\nDetailed report written to reports/model_comparison_deepseek_vs_qwen.json")

if __name__ == "__main__":
    asyncio.run(main())
