"""Chuẩn hóa giao tiếp với gateway cho các alias ag/*.

Nhận message, action và observation theo schema nội bộ. Chuyển sang
native tool calls hoặc structured-action JSON đã kiểm chứng cho từng
alias.

Chuẩn hóa tool call ID, output, finish reason, usage và lỗi theo
docs/llm_gateway_contract.md. Mỗi lần gọi adapter là một provider
attempt. model_router.py quyết định chuyển model.
"""
