"""Kiểm tra trực tiếp hợp đồng của hai alias LLM trên gateway.

Dùng cấu hình gateway để kiểm tra generation, tool round trip, finish
reason và usage riêng cho Gemini và Claude. Thử handoff với history và
observations đã chuẩn hóa.

Ghi bằng chứng đã bỏ thông tin xác thực vào
docs/llm_gateway_contract.md. Kiểm tra lại qua llm_gateway.py khi
adapter đã có.
"""
